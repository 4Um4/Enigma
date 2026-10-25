# -*- coding: utf-8 -*-
"""
S368 INTEGRATION: вызываем реальный routes_chronicle.decompose_fragment и
проверяем, что ChronicleEntry в draft получил historical_age через fallback.

В отличие от test_s368_age_route_fallback.py (который тестирует хелпер-реплику
логики), этот тест ходит через боевой route-обработчик. Monkeypatch:
- routes_chronicle._get_store → возвращает настоящий ChronicleStore с tmp_path;
- routes_chronicle._get_decomposer → возвращает мок с предзаданным DecomposeResult.

Запуск: python -m pytest backend/tests/micro/test_s368_route_integration.py -v
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from app.domain.chronicle import (
    DecompositionItem,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.biography_decomposer import DecomposeResult
from app.services.chronicle.chronicle_store import ChronicleStore


class _MockDecomposer:
    """Мок: 1 EVENT (без age в payload) + 1 RELATIONSHIP + 1 EFFECT,
    age_anchors=[8]. Воспроизводит дамп-сценарий s368_age_dump.txt
    (LLM не проставила age, но якорь есть)."""

    def __init__(self, items: List[DecompositionItem], anchors: List[int]):
        self._items = items
        self._anchors = anchors

    async def decompose(self, npc_id: str, fragment_ord: int, fragment: str) -> DecomposeResult:
        return DecomposeResult.success(self._items, self._anchors)


def _make_dump_items():
    """Воспроизводит raw-ответ LLM из дампа — 3 items, age=None в payload."""
    return [
        DecompositionItem(
            kind=EntryKind.EVENT,
            draft_payload={"summary": "осталась без родителей", "day": None},
            confidence=1.0,
            needs_confirmation=False,
            question=None,
        ),
        DecompositionItem(
            kind=EntryKind.RELATIONSHIP,
            draft_payload={"summary": "дальний родственник", "target_hint": "Торнин"},
            confidence=1.0,
            needs_confirmation=False,
            question=None,
        ),
        DecompositionItem(
            kind=EntryKind.EFFECT,
            draft_payload={"summary": "живёт в трактире", "effect_kind": "residence"},
            confidence=1.0,
            needs_confirmation=False,
            question=None,
        ),
    ]


def _setup_isolated_store(monkeypatch, tmp_path: Path) -> ChronicleStore:
    """Создаёт настоящий ChronicleStore с перенаправленными путями и
    monkeypatch-ит routes_chronicle._get_store возвращать его."""
    from app.api import routes_chronicle as rc

    store = ChronicleStore(
        canonical_dir=tmp_path / "canon",
        drafts_root=tmp_path / "drafts",
    )
    monkeypatch.setattr(rc, "_get_store", lambda: store)
    return store


def _set_mock_decomposer(monkeypatch, items, anchors) -> None:
    from app.api import routes_chronicle as rc
    mock = _MockDecomposer(items, anchors)
    monkeypatch.setattr(rc, "_get_decomposer", lambda: mock)


def test_route_fallback_full_path_to_chronicle_entry(monkeypatch, tmp_path):
    """Полный путь: DecomposeRequest → decompose_fragment → save_draft →
    load_draft → ChronicleEntry.historical_age. Проверяет, что fallback
    сработал в БОЕВОМ коде routes_chronicle.py и age=8 попал в EVENT,
    а RELATIONSHIP/EFFECT остались None."""
    import asyncio
    from app.api import routes_chronicle as rc
    from app.api.routes_chronicle import DecomposeRequest

    _setup_isolated_store(monkeypatch, tmp_path)
    _set_mock_decomposer(monkeypatch, _make_dump_items(), [8])

    req = DecomposeRequest(
        campaign_id="test_campaign",
        npc_id="maid_lusya",
        fragment_ord=0,
        fragment="В 8 лет Люся осталась без родителей.",
    )
    result = asyncio.run(rc.decompose_fragment("test_campaign", "maid_lusya", req))

    # Проверка 1: API-ответ OK и age_anchors переданы
    assert result["status"] == "OK"
    assert result["age_anchors"] == [8]

    # Проверка 2: в payload EVENT нет age (как в дампе)
    event_item = next(i for i in result["items"] if i["kind"] == "EVENT")
    assert "age" not in event_item["draft_payload"]

    # Проверка 3 (ГЛАВНАЯ): ChronicleEntry в draft получил historical_age=8 через fallback
    store = rc._get_store()
    doc = store.load_draft("test_campaign", "maid_lusya")
    assert doc is not None, "draft не сохранился"

    entries = list(doc.entries)
    assert len(entries) == 3, f"ожидал 3 entries, получил {len(entries)}"

    by_kind = {e.kind: e for e in entries}
    assert by_kind[EntryKind.EVENT].historical_age == 8, (
        f"EVENT.historical_age должен быть 8 (fallback), "
        f"получено {by_kind[EntryKind.EVENT].historical_age}"
    )
    assert by_kind[EntryKind.RELATIONSHIP].historical_age is None, (
        f"RELATIONSHIP.historical_age должен быть None (контракт: age только для событий), "
        f"получено {by_kind[EntryKind.RELATIONSHIP].historical_age}"
    )
    assert by_kind[EntryKind.EFFECT].historical_age is None, (
        f"EFFECT.historical_age должен быть None, "
        f"получено {by_kind[EntryKind.EFFECT].historical_age}"
    )

    # Проверка 4: provenance = LLM_DRAFT (всё ещё черновик, не канон)
    for e in entries:
        assert e.provenance == EntryProvenance.LLM_DRAFT


def test_route_llm_age_priority_over_fallback(monkeypatch, tmp_path):
    """LLM проставила age=24 в payload EVENT, anchors=[8]. Боевой route
    должен взять 24 (LLM приоритетнее), а не fallback 8."""
    import asyncio
    from app.api import routes_chronicle as rc
    from app.api.routes_chronicle import DecomposeRequest

    _setup_isolated_store(monkeypatch, tmp_path)
    items = [
        DecompositionItem(
            kind=EntryKind.EVENT,
            draft_payload={"summary": "поступил", "age": 24},
            confidence=0.9,
            needs_confirmation=False,
            question=None,
        ),
    ]
    _set_mock_decomposer(monkeypatch, items, [8])

    req = DecomposeRequest(
        campaign_id="test_campaign",
        npc_id="test_npc",
        fragment_ord=0,
        fragment="В 8 лет поступил.",
    )
    result = asyncio.run(rc.decompose_fragment("test_campaign", "test_npc", req))

    assert result["status"] == "OK"
    store = rc._get_store()
    doc = store.load_draft("test_campaign", "test_npc")
    entries = list(doc.entries)
    assert len(entries) == 1
    assert entries[0].historical_age == 24, (
        f"ожидал 24 (LLM priority), получил {entries[0].historical_age}"
    )


def test_route_no_fallback_multiple_anchors(monkeypatch, tmp_path):
    """2 якоря + 1 EVENT без age → None. §ENIGMA-003: не выдумываем."""
    import asyncio
    from app.api import routes_chronicle as rc
    from app.api.routes_chronicle import DecomposeRequest

    _setup_isolated_store(monkeypatch, tmp_path)
    items = [
        DecompositionItem(
            kind=EntryKind.EVENT,
            draft_payload={"summary": "что-то"},
            confidence=0.9,
            needs_confirmation=False,
            question=None,
        ),
    ]
    _set_mock_decomposer(monkeypatch, items, [8, 16])

    req = DecomposeRequest(
        campaign_id="test_campaign",
        npc_id="test_npc",
        fragment_ord=0,
        fragment="В 8 и в 16 лет.",
    )
    asyncio.run(rc.decompose_fragment("test_campaign", "test_npc", req))

    store = rc._get_store()
    doc = store.load_draft("test_campaign", "test_npc")
    entries = list(doc.entries)
    assert len(entries) == 1
    assert entries[0].historical_age is None, (
        f"2 якоря → неопределённость, ожидал None, получил {entries[0].historical_age}"
    )


def test_route_no_fallback_multiple_events(monkeypatch, tmp_path):
    """1 якорь + 2 EVENT без age → None. Неопределённость, какому событию
    соответствует якорь."""
    import asyncio
    from app.api import routes_chronicle as rc
    from app.api.routes_chronicle import DecomposeRequest

    _setup_isolated_store(monkeypatch, tmp_path)
    items = [
        DecompositionItem(
            kind=EntryKind.EVENT,
            draft_payload={"summary": "первое"},
            confidence=0.9,
            needs_confirmation=False,
            question=None,
        ),
        DecompositionItem(
            kind=EntryKind.EVENT,
            draft_payload={"summary": "второе"},
            confidence=0.9,
            needs_confirmation=False,
            question=None,
        ),
    ]
    _set_mock_decomposer(monkeypatch, items, [8])

    req = DecomposeRequest(
        campaign_id="test_campaign",
        npc_id="test_npc",
        fragment_ord=0,
        fragment="В 8 лет первое событие, а потом второе.",
    )
    asyncio.run(rc.decompose_fragment("test_campaign", "test_npc", req))

    store = rc._get_store()
    doc = store.load_draft("test_campaign", "test_npc")
    entries = list(doc.entries)
    assert len(entries) == 2
    assert all(e.historical_age is None for e in entries), (
        f"2 EVENT → неопределённость, ожидал None для обоих, "
        f"получено {[e.historical_age for e in entries]}"
    )

"""CCH-2 приёмочные тесты (ADR-O-420): нормализатор + декомпозитор (мок-router).

FR-2.2 «никаких молчаливых фолбэков» закреплён параметризованными fail-loud
тестами нормализатора. LLM не требуется — детерминизм живого контура
проверяется отдельно (T-CCH-02, протокол S316).
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.api.routes_chronicle import DecomposeRequest, chronicle_router
from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    ClarificationOption,
    ClarificationQuestion,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.chronicle_store import ChronicleStore
from app.domain.chronicle import DecompositionItem
from app.services.chronicle.biography_decomposer import (
    BiographyDecomposer,
    DecomposeResult,
)
from app.services.chronicle.decomposition_normalizer import (
    ChronicleDecompositionNormalizer,
    DecompositionError,
)

_GOOD = '{"items": [{"kind": "EVENT", "draft_payload": {"summary": "осталась без родителей", "age": 8}, "confidence": 0.95}]}'


class _FakeRouter:
    """Мок ModelRouter.request: очередь ответов/исключений + счётчик вызовов."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def request(self, capability, prompt, params=None, system_prompt=None):
        self.calls += 1
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _decompose(router, fragment="В [8 лет] осталась без родителей."):
    d = BiographyDecomposer(router=router)
    return asyncio.run(d.decompose("c1", 0, fragment))


# ── Нормализатор ─────────────────────────────────────────────────────────────


def test_normalize_happy():
    items = ChronicleDecompositionNormalizer.normalize(_GOOD, chronicle_id="c", fragment_ord=0)
    assert len(items) == 1
    assert items[0].kind is EntryKind.EVENT
    assert items[0].confidence == 0.95
    assert items[0].needs_confirmation is False


def test_normalize_strips_markdown_wrapper():
    wrapped = "Вот разбор:\n```json\n" + _GOOD + "\n```\nготово"
    items = ChronicleDecompositionNormalizer.normalize(wrapped, chronicle_id="c", fragment_ord=0)
    assert len(items) == 1


def test_question_auto_appends_white_spot_option():
    raw = (
        '{"items": [{"kind": "RELATIONSHIP", "draft_payload": {}, "confidence": 0.4, '
        '"question": {"question_id": "q1", "target_span": "стражник", '
        '"options": ["SELECT_EXISTING_NPC"]}}]}'
    )
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="c", fragment_ord=0)
    q = items[0].question
    assert q is not None
    assert ClarificationOption.LEAVE_WHITE_SPOT in q.options  # П3
    assert items[0].needs_confirmation is True


def test_vague_relation_membrane_injects_question():
    """Модель уверена (conf=1.0) при расплывчатой связи → мембрана понижает
    conf и инъецирует канонический вопрос с 4 опциями (П3)."""
    raw = (
        '{"items": [{"kind": "RELATIONSHIP", "draft_payload": {"summary": '
        '"взял трактирщик Торнин — дальний родственник матери", "target_hint": '
        '"Торнин", "nature": "guardianship", "valence": "positive"}, '
        '"confidence": 1.0}]}'
    )
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="c", fragment_ord=0)
    it = items[0]
    assert it.question is not None
    assert it.question.question_id == "vague_relation_0"
    assert {o.value for o in it.question.options} == {
        "SELECT_EXISTING_NPC", "CREATE_NEW_NPC", "UNKNOWN_PERSON", "LEAVE_WHITE_SPOT",
    }
    assert it.confidence <= 0.4 and it.needs_confirmation is True


def test_degrade_bad_question_options_drops_option_not_item():
    """Мусорная опция LLM ('guardianship') выбрасывается поимённо; вопрос жив
    (реестровые опции + обязательное LEAVE_WHITE_SPOT), item не умирает."""
    raw = (
        '{"items": [{"kind": "RELATIONSHIP", "draft_payload": {}, "confidence": 0.4, '
        '"question": {"question_id": "q1", "target_span": "стражник", '
        '"options": ["guardianship", "SELECT_EXISTING_NPC"]}}]}'
    )
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="c", fragment_ord=0)
    q = items[0].question
    assert q is not None
    opts = {o.value for o in q.options}
    assert "guardianship" not in opts and "SELECT_EXISTING_NPC" in opts and "LEAVE_WHITE_SPOT" in opts


def test_degrade_missing_confidence_forces_confirmation():
    """confidence None → 0.5 + needs_confirmation (честная деградация, не смерть item)."""
    raw = (
        '{"items": [{"kind": "EVENT", "draft_payload": {"summary": "s"}}]}'
    )
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="c", fragment_ord=0)
    assert items[0].confidence == 0.5 and items[0].needs_confirmation is True


def test_vague_relation_membrane_not_triggered_on_precise():
    """Точная формулировка («отец», «дядя») мембрану не запускает."""
    raw = (
        '{"items": [{"kind": "RELATIONSHIP", "draft_payload": {"summary": '
        '"опекун — дядя матери", "target_hint": "Торнин"}, "confidence": 0.9}]}'
    )
    items = ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="c", fragment_ord=0)
    assert items[0].question is None and items[0].confidence == 0.9


@pytest.mark.parametrize(
    "raw",
    [
        "мусор",  # не JSON
        '{"items": []}',  # пустой items
        '{"items": [{"kind": "MURDER", "draft_payload": {}, "confidence": 0.5}]}',  # kind вне реестра
        '{"items": [{"kind": "EVENT", "draft_payload": [], "confidence": 0.5}]}',  # payload не dict
        '{"items": [{"kind": "EVENT", "draft_payload": {}, "confidence": 1.5}]}',  # confidence
        '{"items": [{"kind": "EVENT", "draft_payload": {}, "confidence": 0.5}], "who": 1}',  # лишний ключ
    ],
)
def test_normalize_fail_loud_no_silent_fallback(raw):
    with pytest.raises(DecompositionError):
        ChronicleDecompositionNormalizer.normalize(raw, chronicle_id="c", fragment_ord=0)


# ── Декомпозитор (fast path + мок-router) ────────────────────────────────────


def test_extract_age_anchors_three_forms():
    a = BiographyDecomposer.extract_age_anchors(
        "В [8 лет] осталась без родителей. В 14 лет влюбилась. С 12 лет видела."
    )
    assert a == [8, 14, 12]


def test_decompose_empty_fragment_is_honest_failure():
    r = _decompose(_FakeRouter([_GOOD]), "   ")
    assert r.ok is False and r.items == []
    assert r.error is not None


def test_decompose_happy_with_mock_router():
    router = _FakeRouter([_GOOD])
    r = _decompose(router)
    assert r.ok is True and len(r.items) == 1
    assert r.age_anchors == [8]
    assert router.calls == 1


def test_decompose_retry_then_success():
    router = _FakeRouter(["не json вообще", _GOOD])
    r = _decompose(router)
    assert r.ok is True and router.calls == 2  # ровно один retry (FR-2.2)


def test_decompose_pool_down_no_retry_logged():
    router = _FakeRouter([RuntimeError("пул недоступен")])
    r = _decompose(router)
    assert r.ok is False
    assert "LLM-пул недоступен" in (r.error or "")
    assert router.calls == 1  # инфраструктурный отказ не ретраится


def test_decompose_double_failure_after_retry():
    router = _FakeRouter(["мусор-1", "мусор-2"])
    r = _decompose(router)
    assert r.ok is False and router.calls == 2
    assert "не удалась после retry" in (r.error or "")


def test_to_transient_builds_frozen_decomposition():
    d = BiographyDecomposer(router=_FakeRouter([]))
    r = DecomposeResult.success([DecompositionItem(kind=EntryKind.EVENT, confidence=1.0)], [8])
    tr = d.to_transient("c1", 3, r)
    assert tr.chronicle_id == "c1" and tr.fragment_ord == 3 and len(tr.items) == 1


# ── API: структура и границы Pydantic ────────────────────────────────────────


def test_chronicle_router_paths_registered():
    paths = {getattr(r, "path", "") for r in chronicle_router.routes}
    assert any("decompose" in p for p in paths)
    assert any("draft" in p for p in paths)


def test_canonize_flow_locked_by_open_question(tmp_path):
    """T-CCH-04 (бэкенд-уровень): canonize при открытом вопросе = 422-класс
    отказ store (require_canonical_clean) — блок с русским сообщением."""
    from fastapi.testclient import TestClient  # noqa: F401 — контракт ниже через store напрямую

    # Прямая проверка контракта store, который инвариантен эндпоинту:
    # draft с открытым вопросом не может пройти save_canonical.
    store = ChronicleStore(canonical_dir=tmp_path / "chronicles", drafts_root=tmp_path)
    q = ClarificationQuestion(
        question_id="q1", target_span="стражник", options=(ClarificationOption.LEAVE_WHITE_SPOT,)
    )
    doc = ChronicleDocument(
        chronicle_id="cc",
        npc_ref="a",
        canonical=False,
        entries=(
            ChronicleEntry(
                entry_id="e",
                kind=EntryKind.EVENT,
                subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="a"),
                provenance=EntryProvenance.AUTHOR_CONFIRMED,
                open_questions=(q,),
            ),
        ),
    )
    store.save_draft(doc, "c")
    from dataclasses import replace as _replace

    canon = _replace(doc, canonical=True, canonical_version=1)
    with pytest.raises(ValueError, match="без резолюции"):
        store.save_canonical(canon)


def test_decompose_request_rejects_empty_fragment():
    with pytest.raises(ValidationError):
        DecomposeRequest(campaign_id="c", npc_id="n", fragment_ord=0, fragment="")
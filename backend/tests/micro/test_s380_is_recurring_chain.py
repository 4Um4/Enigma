"""path: backend/tests/micro/test_s380_is_recurring_chain.py
Назначение: S380 — тест цепочки повторяемости события:
    Уровень А: ChronicleEntry.payload[is_recurring] → build_seed_memories → EventMemory.decay_rate
    Уровень Б: LLM JSON → normalizer → DecompositionItem.draft_payload (pass-through)
    Полная цепочка: mock LLM output → normalizer → ChronicleEntry → seeder → EventMemory
Зависимости: app.domain.chronicle, app.services.chronicle.chronicle_seeder,
             app.services.chronicle.decomposition_normalizer
Основные сущности: ChronicleEntry, ChronicleDocument, EventMemory, DecompositionItem
"""
from __future__ import annotations

import pytest

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.chronicle_seeder import (
    SEED_DECAY_RATE,
    SEED_DECAY_RATE_RECURRING,
    _PL_IS_RECURRING,
    build_seed_memories,
)


# ── Фикстуры ────────────────────────────────────────────────────

def _ref(npc_id: str) -> EntityRef:
    return EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id)

def _entry(
    entry_id: str,
    summary: str,
    *,
    is_recurring: bool | None = None,
    age: int = 20,
) -> ChronicleEntry:
    payload: dict = {"summary": summary}
    if is_recurring is not None:
        payload[_PL_IS_RECURRING] = is_recurring
    return ChronicleEntry(
        entry_id=entry_id,
        kind=EntryKind.EVENT,
        subject_id=_ref("npc_subject"),
        object_id=_ref("npc_object"),
        historical_age=age,
        payload=payload,
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
    )

def _doc(entries: tuple[ChronicleEntry, ...]) -> ChronicleDocument:
    return ChronicleDocument(
        chronicle_id="test_npc",
        npc_ref=_ref("test_npc"),
        entries=entries,
        game_start_age=25,
    )


# ── Уровень А: передача данных (ChronicleEntry → EventMemory) ──

class TestSeederDecayModulation:
    """Seeder модулирует decay_rate по is_recurring в ChronicleEntry.payload."""

    def test_recurring_gets_lower_decay(self) -> None:
        """is_recurring=True → decay_rate=SEED_DECAY_RATE_RECURRING (0.0005)."""
        doc = _doc((_entry("e1", "регулярно избивал", is_recurring=True),))
        mems = build_seed_memories("test_npc", doc)
        assert len(mems) == 1
        assert mems[0].decay_rate == SEED_DECAY_RATE_RECURRING
        assert mems[0].decay_rate < SEED_DECAY_RATE

    def test_single_event_standard_decay(self) -> None:
        """Без is_recurring → decay_rate=SEED_DECAY_RATE (backward compat)."""
        doc = _doc((_entry("e1", "одиночное событие"),))
        mems = build_seed_memories("test_npc", doc)
        assert len(mems) == 1
        assert mems[0].decay_rate == SEED_DECAY_RATE

    def test_explicit_false_same_as_missing(self) -> None:
        """is_recurring=False → decay_rate=SEED_DECAY_RATE (явный False = отсутствие)."""
        doc = _doc((_entry("e1", "событие", is_recurring=False),))
        mems = build_seed_memories("test_npc", doc)
        assert len(mems) == 1
        assert mems[0].decay_rate == SEED_DECAY_RATE

    def test_mixed_recurring_and_single(self) -> None:
        """В одном документе — recurring и single, разные decay."""
        doc = _doc((
            _entry("e1", "регулярно избивал", is_recurring=True),
            _entry("e2", "один раз ударил", is_recurring=False),
            _entry("e3", "просто событие"),
        ))
        mems = build_seed_memories("test_npc", doc)
        assert len(mems) == 3
        by_summary = {m.summary: m.decay_rate for m in mems}
        assert by_summary["регулярно избивал"] == SEED_DECAY_RATE_RECURRING
        assert by_summary["один раз ударил"] == SEED_DECAY_RATE
        assert by_summary["просто событие"] == SEED_DECAY_RATE

    def test_importance_not_affected(self) -> None:
        """is_recurring НЕ влияет на importance — только на decay_rate.
        ТЗ: «Не подменять семантику повторяемости простым увеличением важности»."""
        doc = _doc((_entry("e1", "регулярно избивал", is_recurring=True),))
        mems = build_seed_memories("test_npc", doc)
        # SEED_EVENT_IMPORTANCE = 0.6 (не trauma-linked)
        assert mems[0].importance == 0.6


# ── Уровень Б: normalizer pass-through (LLM JSON → DecompositionItem) ──

class TestNormalizerPassThrough:
    """Normalizer передаёт is_recurring из LLM JSON в DecompositionItem.draft_payload."""

    def test_is_recurring_survives_normalizer(self) -> None:
        """LLM выдаёт is_recurring=true → DecompositionItem сохраняет его."""
        from app.services.chronicle.decomposition_normalizer import ChronicleDecompositionNormalizer

        llm_output = {
            "items": [
                {
                    "kind": "EVENT",
                    "draft_payload": {
                        "summary": "регулярно избивал",
                        "is_recurring": True,
                        "day": None,
                    },
                    "confidence": 0.9,
                }
            ]
        }
        items = ChronicleDecompositionNormalizer.normalize(
            llm_output, chronicle_id="test", fragment_ord=0
        )
        assert len(items) == 1
        item = items[0]
        assert item.kind is EntryKind.EVENT
        assert item.draft_payload.get("is_recurring") is True


# ── Полная цепочка (mock LLM → normalizer → ChronicleEntry → seeder) ──

class TestFullChainRecurring:
    """REPEAT-событие: LLM JSON → normalizer → ChronicleEntry → EventMemory."""

    def test_recurring_full_chain_lower_decay(self) -> None:
        """От LLM-ответа с is_recurring=true до EventMemory с пониженным decay_rate."""
        from app.services.chronicle.decomposition_normalizer import ChronicleDecompositionNormalizer

        # 1. LLM выдаёт EVENT с is_recurring=true (следуя усиленной инструкции промпта)
        llm_output = {
            "items": [
                {
                    "kind": "EVENT",
                    "draft_payload": {
                        "summary": "регулярно избивал Торнин",
                        "is_recurring": True,
                        "day": None,
                    },
                    "confidence": 0.9,
                }
            ]
        }
        items = ChronicleDecompositionNormalizer.normalize(
            llm_output, chronicle_id="lusya", fragment_ord=0
        )
        assert items[0].draft_payload.get("is_recurring") is True

        # 2. Canonization: payload=dict(draft_payload) — is_recurring проходит
        item = items[0]
        entry = ChronicleEntry(
            entry_id="lusya_frag0_e1",
            kind=item.kind,
            subject_id=_ref("tavern_keeper_tornin"),
            object_id=_ref("maid_lusya"),
            historical_age=20,
            payload=dict(item.draft_payload),
            provenance=EntryProvenance.AUTHOR_CONFIRMED,
        )
        assert entry.payload.get(_PL_IS_RECURRING) is True

        # 3. Seeder → EventMemory с пониженным decay_rate
        doc = ChronicleDocument(
            chronicle_id="maid_lusya",
            npc_ref=_ref("maid_lusya"),
            entries=(entry,),
            game_start_age=25,
        )
        mems = build_seed_memories("maid_lusya", doc)
        assert len(mems) == 1
        assert mems[0].decay_rate == SEED_DECAY_RATE_RECURRING
        assert mems[0].summary == "регулярно избивал Торнин"
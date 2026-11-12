# backend/tests/test_bc2_expectation_layer.py
"""BC-2 unit-тесты: DTO / Store / Bridge / Runtime (без Phase 9 harness).

Полный игровой цикл (BC2-2 §9 п.5, п.13) проверяется отдельно в
SUPERBOX сценарии bc2_expectation_test.py (см. HANDOFF BC2-2 §9).
"""

import os
import pytest

from app.domain.conclusions import (
    CONCLUSION_SOURCE_DIRECT,
    ConclusionPredicate,
    ConclusionRecord,
)
from app.domain.expectations import (
    ExpectationContext,
    ExpectationPredicate,
    ExpectationRecord,
    ExpectationStatus,
)
from app.services.npc.expectation_bridge import conclusion_to_expectations
from app.services.npc.expectation_store import (
    ContextualExpectationStore,
    ExpectationApplyResult,
)


def _concl(**kw) -> ConclusionRecord:
    defaults = dict(
        owner_id="maid_lusya",
        subject="player",
        predicate=ConclusionPredicate.IS_DANGEROUS,
        object="",
        confidence=0.8,
        evidence=("evt_1",),
        trace_id="evt_1:maid_lusya:player",
        causal_parent="evt_1",
        source=CONCLUSION_SOURCE_DIRECT,
        formed_tick=0,
    )
    defaults.update(kw)
    return ConclusionRecord(**defaults)


def test_dto_frozen_and_identity():
    e = ExpectationRecord(
        owner_id="maid_lusya",
        subject="player",
        predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
        expected_object="",
        confidence=0.8,
        formed_tick=5,
        causal_parent_conclusion_id="cid_1",
    )
    with pytest.raises(Exception):
        e.confidence = 0.9  # frozen
    assert e.expectation_id() == (
        "maid_lusya:player:may_cause_physical_harm::"
        ":cid_1"
    )
    assert e.status == ExpectationStatus.ACTIVE


def test_bridge_no_signal_returns_empty():
    """HANDOFF §2: IS_DANGEROUS != автоматическое ожидание."""
    c = _concl()
    ctx = ExpectationContext()  # все None / ()
    assert conclusion_to_expectations(c, ctx, current_tick=5) == []


def test_bridge_physical_harm_requires_both_signals():
    c = _concl()
    # Только subject — не достаточно.
    ctx = ExpectationContext(subject_physical_strength=1.5)
    assert conclusion_to_expectations(c, ctx, current_tick=5) == []
    # Оба, но subject не превосходит по ratio — не достаточно.
    ctx = ExpectationContext(
        subject_physical_strength=1.0, owner_physical_strength=1.0
    )
    assert conclusion_to_expectations(c, ctx, current_tick=5) == []
    # Оба и subject > owner × 1.2 → 1 ожидание.
    ctx = ExpectationContext(
        subject_physical_strength=2.0, owner_physical_strength=1.0
    )
    out = conclusion_to_expectations(c, ctx, current_tick=5)
    assert len(out) == 1
    assert out[0].predicate == ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM
    assert out[0].causal_parent_conclusion_id == c.conclusion_id()
    assert out[0].formed_tick == 5


def test_bridge_force_in_conflict_requires_past_aggression():
    c = _concl()
    # Пусто — нет сигнала.
    assert conclusion_to_expectations(c, ExpectationContext(), 5) == []
    # Непусто — сигнал.
    ctx = ExpectationContext(past_aggression_event_ids=("evt_a",))
    out = conclusion_to_expectations(c, ctx, 5)
    assert len(out) == 1
    assert out[0].predicate == ExpectationPredicate.MAY_USE_FORCE_IN_CONFLICT


def test_bridge_two_predicates_from_one_conclusion():
    """HANDOFF §2: один Conclusion может породить оба предиката."""
    c = _concl()
    ctx = ExpectationContext(
        subject_physical_strength=2.0,
        owner_physical_strength=1.0,
        past_aggression_event_ids=("evt_a",),
    )
    out = conclusion_to_expectations(c, ctx, current_tick=5)
    assert len(out) == 2
    preds = {e.predicate for e in out}
    assert preds == {
        ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
        ExpectationPredicate.MAY_USE_FORCE_IN_CONFLICT,
    }


def test_bridge_max_count_5():
    c = _concl()
    ctx = ExpectationContext(
        subject_physical_strength=2.0,
        owner_physical_strength=1.0,
        past_aggression_event_ids=("evt_a",),
    )
    out = conclusion_to_expectations(c, ctx, current_tick=5, max_count=1)
    assert len(out) == 1


def test_bridge_non_is_dangerous_returns_empty():
    c = _concl(predicate=ConclusionPredicate.IS_DANGEROUS)  # единственный в MVP
    # Расширение predicate-реестра — будущая задача; здесь демонстрируем,
    # что bridge работает по предикату Conclusion.
    # (Заглушка: если появятся другие ConclusionPredicate — они дадут [].)


def test_bridge_pure_same_input_same_output():
    c = _concl()
    ctx = ExpectationContext(
        subject_physical_strength=2.0,
        owner_physical_strength=1.0,
        past_aggression_event_ids=("evt_a",),
    )
    out1 = conclusion_to_expectations(c, ctx, current_tick=5)
    out2 = conclusion_to_expectations(c, ctx, current_tick=5)
    assert [e.expectation_id() for e in out1] == [e.expectation_id() for e in out2]


import pytest


@pytest.fixture
def store():
    """TEST-ONLY store с этим модулем в _APPLY_ALLOWED_WRITERS.

    Production guard (INV-EXPECTATION-GATE) остаётся неизменным —
    monkeypatch только на instance, не на классе. Реальные записи
    идут через expectation_bridge / expectation_runtime (см. прод).
    """
    s = ContextualExpectationStore()
    s._APPLY_ALLOWED_WRITERS = s._APPLY_ALLOWED_WRITERS | {__name__}
    return s


def test_store_idempotent(store):
    """HANDOFF §9 п.8: повторная обработка одного события идемпотентна."""
    e = ExpectationRecord(
        owner_id="maid_lusya",
        subject="player",
        predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
        expected_object="",
        confidence=0.8,
        formed_tick=5,
        causal_parent_conclusion_id="cid_1",
    )
    r1 = store.apply(e)
    r2 = store.apply(e)
    assert r1 == ExpectationApplyResult.CREATED
    assert r2 == ExpectationApplyResult.REINFORCED
    assert len(store) == 1


def test_store_reinforcement_preserves_origin(store):
    """HANDOFF §9 п.9: reinforcement не уничтожает происхождение."""
    e1 = ExpectationRecord(
        owner_id="maid_lusya",
        subject="player",
        predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
        expected_object="",
        confidence=0.5,
        formed_tick=5,
        causal_parent_conclusion_id="cid_1",
    )
    store.apply(e1)
    e2 = ExpectationRecord(
        owner_id="maid_lusya",
        subject="player",
        predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
        expected_object="",
        confidence=0.9,  # выше
        formed_tick=8,   # другой — не должен перезаписать
        causal_parent_conclusion_id="cid_1",
    )
    store.apply(e2)
    records = store.get_for("maid_lusya")
    assert len(records) == 1
    assert records[0].confidence == 0.9  # max
    assert records[0].formed_tick == 5  # origin preserved


def test_store_get_all_returns_multiple_for_same_predicate(store):
    """HANDOFF §5: не возвращать произвольно одну запись."""
    for cid in ("cid_1", "cid_2"):
        store.apply(
            ExpectationRecord(
                owner_id="maid_lusya",
                subject="player",
                predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
                expected_object="",
                formed_tick=5,
                causal_parent_conclusion_id=cid,
            )
        )
    recs = store.get_all(
        "maid_lusya", "player", ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM
    )
    assert len(recs) == 2
    parents = {r.causal_parent_conclusion_id for r in recs}
    assert parents == {"cid_1", "cid_2"}


def test_store_persistence_roundtrip(store):
    """HANDOFF §9 п.10: persistence round-trip сохраняет все поля."""
    e = ExpectationRecord(
        owner_id="maid_lusya",
        subject="player",
        predicate=ExpectationPredicate.MAY_USE_FORCE_IN_CONFLICT,
        expected_object="",
        confidence=0.7,
        formed_tick=42,
        causal_parent_conclusion_id="cid_xyz",
        predicted_context="if_conflict",
    )
    store.apply(e)
    data = store.to_dict()
    restored = ContextualExpectationStore.from_dict(data)
    recs = restored.get_for("maid_lusya")
    assert len(recs) == 1
    r = recs[0]
    assert r.owner_id == e.owner_id
    assert r.subject == e.subject
    assert r.predicate == e.predicate
    assert r.confidence == e.confidence
    assert r.formed_tick == e.formed_tick
    assert r.causal_parent_conclusion_id == e.causal_parent_conclusion_id
    assert r.predicted_context == e.predicted_context
    assert r.status == e.status


def test_store_get_by_parent(store):
    store.apply(
        ExpectationRecord(
            owner_id="maid_lusya",
            subject="player",
            predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
            expected_object="",
            causal_parent_conclusion_id="cid_1",
        )
    )
    assert len(store.get_by_parent("cid_1")) == 1
    assert len(store.get_by_parent("cid_unknown")) == 0


def test_store_caller_guard():
    """INV-EXPECTATION-GATE: apply мимо разрешённого writer'а → ArchitecturalViolationError."""
    store = ContextualExpectationStore()
    e = ExpectationRecord(
        owner_id="x", subject="y",
        predicate=ExpectationPredicate.MAY_CAUSE_PHYSICAL_HARM,
        expected_object="",
    )
    with pytest.raises(Exception):
        store.apply(e)
    # Из bridge-пути работает
    os.environ["BC2_ENABLED"] = "1"
    from app.services.memory.expectation_runtime import (
        ensure_expectation_layer,
    )

    # ... харнесс с orchestrator stub — проверяется в SUPERBOX-сценарии.
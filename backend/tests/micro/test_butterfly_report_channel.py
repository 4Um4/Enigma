# backend/tests/micro/test_butterfly_report_channel.py
"""
path: /project/backend/tests/micro/test_butterfly_report_channel.py
Назначение: COGNITIVE-CONTINUITY-01 Этап 3 — report channel в EpistemicContextResolver.
Тестирует: INSULTED→about_self (жертва), report_proposition (свидетель),
  spread_rumor/talk boost, разделение каналов, порог.
Зависимости: app.domain.epistemology, app.services.npc.epistemic_context_resolver
"""

from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
from app.services.npc.epistemic_context_resolver import (
    EpistemicContextResolver,
    REPORT_CONFIDENCE_THRESHOLD,
)
from app.services.npc.epistemic_store import EpistemicStore


def _record(agent: str, subj: str, pred: Predicate, obj: str, conf: float = 0.5, tick: int = 1):
    """Минимальная EpistemicRecord для тестов."""
    return EpistemicRecord(
        agent_id=agent,
        proposition=Proposition(subject_id=subj, predicate=pred, object_id=obj),
        confidence=conf,
        source_id="player",
        source_claim_id="test-claim",
        first_observed_tick=tick,
        last_updated_tick=tick,
        source_type="testimony",
        original_source_id="player",
    )


def test_witness_gets_report_proposition():
    """Люся (свидетель) знает об оскорблении Торнина → report_proposition + spread_rumor boost."""
    store = EpistemicStore()
    store.upsert(_record("maid_lusya", "player", Predicate.INSULTED, "tavern_keeper_tornin", conf=0.5))
    resolver = EpistemicContextResolver(store)

    ctx = resolver.resolve("maid_lusya")

    assert ctx.report_proposition is not None
    assert ctx.report_proposition.predicate == Predicate.INSULTED
    assert ctx.report_proposition.subject_id == "player"
    assert ctx.report_proposition.object_id == "tavern_keeper_tornin"

    mods = EpistemicContextResolver.to_modifiers(ctx)
    assert "spread_rumor" in mods, f"spread_rumor missing: {mods}"
    assert mods["spread_rumor"] > 0
    assert mods.get("talk", 0) > 0


def test_victim_no_report_but_self_channel():
    """Торнин (жертва) — report_proposition is None, но claims_about_self растёт talk."""
    store = EpistemicStore()
    store.upsert(_record("tavern_keeper_tornin", "player", Predicate.INSULTED, "tavern_keeper_tornin", conf=0.5))
    resolver = EpistemicContextResolver(store)

    ctx = resolver.resolve("tavern_keeper_tornin")

    assert ctx.report_proposition is None
    assert len(ctx.claims_about_self) > 0
    assert ctx.max_self_confidence > 0

    mods = EpistemicContextResolver.to_modifiers(ctx)
    assert mods.get("talk", 0) > 0, f"self-boost talk missing: {mods}"


def test_below_threshold_no_report():
    """Запись ниже REPORT_CONFIDENCE_THRESHOLD не даёт report."""
    store = EpistemicStore()
    store.upsert(_record("maid_lusya", "player", Predicate.INSULTED, "tavern_keeper_tornin",
                         conf=REPORT_CONFIDENCE_THRESHOLD - 0.01))
    resolver = EpistemicContextResolver(store)

    ctx = resolver.resolve("maid_lusya")
    assert ctx.report_proposition is None


def test_stole_does_not_enter_report():
    """STOLE-запись не попадает в report (разделение каналов сохранено)."""
    store = EpistemicStore()
    store.upsert(_record("maid_lusya", "guard_borko", Predicate.STOLE, "merchant_goran", conf=0.7))
    resolver = EpistemicContextResolver(store)

    ctx = resolver.resolve("maid_lusya")
    assert ctx.report_proposition is None
    assert "guard_borko" in ctx.perceived_threats
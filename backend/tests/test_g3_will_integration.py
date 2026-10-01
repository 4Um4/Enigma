# path: /project/backend/tests/test_g3_will_integration.py
# Назначение: G3 Этап 2 (ADR-O-410) — Tier-A: юнит-интеграция воли.
#     Прямой compute() по прецеденту test_decision_calibration (реальные
#     NPCState/NPCPersonality/EventContext/EffectiveDrives — §13.4):
#     доказывает цепь «факт цели → OpportunityContext.steal_target →
#     STEAL с intent_target=wo_id» при разблокированной воле (DECEPTIVE).
#     Метрика = DecisionResult (канал воли); исполнение — Этап 1 (9/9 +
#     GC-00 GREEN). Tier-B (E2E honest-zero + замок R6.3) — g3_will_probe.
# Зависимости: pytest, app.services.npc.decision_hub, app.services.economy,
#     app.models.npc_state, app.domain.decision_context
# Основные сущности: TestG3WillIntegration
# Запуск: cd backend; python -m pytest tests/test_g3_will_integration.py -v -s; cd ..
from app.domain.identity_events import EffectiveDrives
from app.models.npc_profile import NPCProfileL0
from app.models.npc_state import NPCState, WillState
from app.services.economy.opportunity_engine import OpportunityContext
from app.services.npc.decision_hub import DecisionHub, EventContext


def _drives() -> EffectiveDrives:
    """Desire-доминанта (вор) — L3 по ADR-O-208, фабрика from_dict."""
    return EffectiveDrives.from_dict(
        {"control": 0.05, "significance": 0.05, "fear": 0.05, "desire": 0.85}
    )


def _personality() -> NPCProfileL0:
    """Thief-профиль (S209: NPCProfileL0.archetype → affinity-база 1.0)."""
    from app.models.npc_profile import PsycheBase

    return NPCProfileL0(
        id="thief_shadow",
        name="Тень",
        tier="mass",
        archetype="thief",
        drives_base={"control": 0.10, "significance": 0.10, "fear": 0.05, "desire": 0.75},
        psyche_base=PsycheBase(willpower=40, breakpoint=75),
        voice_profile="нейтральный",
    )


def _event() -> EventContext:
    """Idle-событие (нейтральный момент; полный конструктор-контракт)."""
    return EventContext(event_type="idle", actor_id="world")


class TestG3WillIntegration:
    def test_steal_will_chooses_object_target(self):
        """Воля DECEPTIVE + факт цели → STEAL intent_target=wo_id."""
        _hub = DecisionHub(seed=0)
        _ctx = OpportunityContext(
            player_attention=0.0,
            distance=8.0,
            weapon_access=False,
            allies=0,
            steal_target="wo_g3_tier_a_chair",
        )
        _res = _hub.compute(
            NPCState(npc_id="thief_shadow", will_state=WillState.DECEPTIVE),
            _personality(),
            _event(),
            effective_drives=_drives(),
            opportunity_ctx=_ctx,
        )
        assert _res.intent.value == "steal"
        assert _res.intent_target == "wo_g3_tier_a_chair"

    def test_no_target_degrades_to_observe(self):
        """Тот же момент, факт цели отсутствует → OBSERVE (BUG-01)."""
        _hub = DecisionHub(seed=0)
        _ctx = OpportunityContext(
            player_attention=0.0, distance=8.0, weapon_access=False, allies=0
        )
        _res = _hub.compute(
            NPCState(npc_id="thief_shadow", will_state=WillState.DECEPTIVE),
            _personality(),
            _event(),
            effective_drives=_drives(),
            opportunity_ctx=_ctx,
        )
        assert _res.intent.value == "observe"
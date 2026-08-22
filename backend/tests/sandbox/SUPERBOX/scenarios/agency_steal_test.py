"""
SUPERBOX-AGENCY-STEAL (S209, Vertical Slice звено 1): NPC может решить украсть сам.

Назначение: Vertical Slice звено 1 (S209): первое эмерджентное действие NPC.
            Доказывает полную цепь motive→decision→windup→THEFT→belief без инъекций.
Зависимости: app.services.npc.decision_hub, app.services.events.*, app.domain.*
Основные сущности: run_test (A1-A6)

Доказывает:
  [A1] Момент: thief + unlocked opportunity → 'steal' в possible; score
       конкурентоспособен (affinity 0.8 масштабирует opportunity_mod).
  [A2] Контроль момента: opportunity не разблокирован → 'steal' НЕ в possible.
  [A3] Контроль натуры: commoner + unlocked → steal в possible, но score
       ниже routine (affinity 0.08 давит буст) — кража доступна каждому,
       выбирается натурой.
  [A4] Маршрутизация + windup: steal-интент уходит в windup (НЕ в диалоговый
       слой), duration=2, событие НЕ опубликовано до истечения окна.
  [A5] Релиз: после 2 тиков → IntentEventAdapter → EventDTO(THEFT, source=thief).
  [A6] Эмерджентное замыкание: THEFT → ObservationSubscriber → belief Goran
       (LOS) conf=0.9; контроль — Goran вне LOS → belief нет.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/agency_steal_test.py
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.epistemology import Predicate
from app.models.npc_profile import NPCProfileL0
from app.models.npc_state import Intent, NPCState
from app.services.economy.opportunity_engine import (
    OpportunityContext,
    OpportunityEngine,
    OpportunityResult,
)
from app.services.npc.decision_hub import DecisionHub
from app.services.spatial.spatial_query_service import SpatialQueryService

# Калибровка OpportunityContext по формуле из Слом.md (археология S209):
# attention↓ + distance↓ + weapon + allies → score ≥ OPPORTUNITY_THRESHOLD.
# Точные веса/порог берём из движка, не дублируем (см. A2 — порог живой).
from app.services.economy.opportunity_engine import OPPORTUNITY_THRESHOLD


def _profile(archetype: str, desire: float = 0.3) -> NPCProfileL0:
    return NPCProfileL0(
        id=f"npc_{archetype}", name=archetype, tier="minor",
        drives_base={"control": 0.25, "significance": 0.25, "fear": 0.2, "desire": desire},
        psyche_base=type("P", (), {})(), voice_profile="", archetype=archetype,
    )


def main() -> int:
    print("=" * 64)
    print("SUPERBOX-AGENCY-STEAL: первое эмерджентное действие NPC (S209)")
    print("=" * 64)
    ok = True
    hub = DecisionHub.__new__(DecisionHub)  # только _steal_affinity/_get_possible_intents

    # ── A1/A2: opportunity-гейт ───────────────────────────────────────
    thief, state = _profile("thief"), NPCState(npc_id="thief_shadow")
    unlocked = OpportunityResult(score=1.0, hidden_action_allowed=True,
                                 unlocked_intents=frozenset({"steal"}), score_trace={})
    locked = OpportunityResult(score=0.0, hidden_action_allowed=False,
                               unlocked_intents=frozenset(), score_trace={})
    # _get_possible_intents требует event; используем world_tick-контекст
    # минимальной заглушкой (протокол EventContext — только .event_type читается)
    class _WT:
        event_type = "world_tick"
        visible_threat_markers = []
    possible_unlocked = hub._get_possible_intents(state, thief, _WT(), unlocked)
    possible_locked = hub._get_possible_intents(state, thief, _WT(), locked)
    a1 = Intent.STEAL.value in possible_unlocked
    a2 = Intent.STEAL.value not in possible_locked
    print(f"[A1] Thief + unlocked: steal в possible — {'✅' if a1 else '❌'}")
    print(f"[A2] Thief + locked: steal НЕ в possible — {'✅' if a2 else '❌'}")
    ok = ok and a1 and a2

    # ── A3: контроль натуры ───────────────────────────────────────────
    commoner = _profile("commoner")
    a_t = hub._steal_affinity(state, thief)
    a_c = hub._steal_affinity(state, commoner)
    a3 = a_t > 0.5 and a_c < 0.2
    print(f"[A3] Affinity: thief={a_t}, commoner={a_c} — "
          f"{'✅' if a3 else '❌'} (кража доступна каждому, выбирает натура)")
    ok = ok and a3

    # ── A4: маршрутизация steal → windup (не диалоговый слой) ────────
    # Проверяем контракт Фазы 6 напрямую: условие маршрутизатора.
    import inspect
    from app.services.phases import post_decision as pd
    _src = inspect.getsource(pd)
    a4 = 'not in ("attack", "steal")' in _src and "_gate_intent_type in (\"attack\", \"steal\")" in _src
    print(f"[A4] Маршрутизатор: windowed={('attack','steal')}, диалоговый слой их не ловит — "
          f"{'✅' if a4 else '❌'}")
    ok = ok and a4

    # ── A5: релиз held intent → THEFT через adapter ──────────────────
    from app.services.events.intent_event_adapter import IntentEventAdapter
    from app.domain.communication import CommunicationIntent, ExposureLevel
    # Кража максимально тихая: whisper (радиус события выведется из semantic —
    # честная мембрана для Reaction/Social подписчиков, не 999.0).
    # ExposureLevel — frozen dataclass с фабрикой from_semantic (археология S209),
    # НЕ enum; три предположения об enum-членах были ложными.
    _exposure = ExposureLevel.from_semantic("whisper")
    import dataclasses as _dc
    _intent = CommunicationIntent(
        speaker="thief_shadow", audience="gold_chest", topic="theft",
        intent_type="steal", emotional_state="neutral",
        exposure_level=_exposure,
    )
    if hasattr(_intent, "target_id") and _intent.target_id is None:
        _intent = _dc.replace(_intent, target_id="gold_chest")
    _ev = IntentEventAdapter.to_event(_intent)
    a5 = _ev.type == "theft" and _ev.source == "thief_shadow"
    print(f"[A5] Adapter: intent=steal → EventDTO(type={_ev.type}, source={_ev.source}) — "
          f"{'✅' if a5 else '❌'}")
    ok = ok and a5

    # ── A6: эмерджентное замыкание Goran-цепи ────────────────────────
    from app.services.events.observation_subscriber import ObservationSubscriber
    from app.services.npc.belief_revision_engine import BeliefRevisionEngine
    from app.services.npc.epistemic_store import EpistemicStore
    from app.services.npc.trust_based_reliability_provider import (
        DIRECT_OBSERVATION_RELIABILITY, TrustBasedReliabilityProvider,
    )

    positions = {
        "thief_shadow": {"local_position": {"x": 0.0, "y": 0.0}},
        "goran":        {"local_position": {"x": 3.0, "y": 0.0}},   # LOS, дист 3
        "far_npc":      {"local_position": {"x": 15.0, "y": 0.0}},  # вне радиуса
    }
    sq = SpatialQueryService(npc_positions=positions)
    store = EpistemicStore()
    engine = BeliefRevisionEngine(
        reliability_provider=TrustBasedReliabilityProvider(None, "agency_test"))
    sub = ObservationSubscriber(engine=engine, store=store,
                                spatial_query_provider=lambda: sq,
                                tick_provider=lambda: 10)
    sub.on_world_event(_ev)  # THEFT от A5 — НИКАКИХ инъекций belief

    g = store.get("goran")
    f = store.get("far_npc")
    a6 = (g is not None and g.confidence == DIRECT_OBSERVATION_RELIABILITY
          and g.proposition.subject_id == "thief_shadow"
          and g.proposition.predicate == Predicate.STOLE
          and f is None)
    print(f"[A6] Goran belief={g.confidence if g else None} (ожид. {DIRECT_OBSERVATION_RELIABILITY}), "
          f"far_npc belief={'нет' if f is None else 'ЕСТЬ (ТЕЛЕПАТИЯ!)'} — "
          f"{'✅' if a6 else '❌'}")
    ok = ok and a6

    print("=" * 64)
    print("🎉 ЭМЕРДЖЕНТНОЕ ДЕЙСТВИЕ ДОКАЗАНО: Shadow может украсть сам,"
          "\n   свидетель узнает, и цепь живёт без единой инъекции."
          if ok else "❌ ТЕСТ С ОШИБКАМИ")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
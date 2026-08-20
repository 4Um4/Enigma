"""
SUPERBOX-OBSERVATION (Phase C, ADR-O-360): прямой канал убеждений.

Доказывает:
  [T1] THEFT + witness с LOS → EpistemicStore[witness]: (player, STOLE, target), conf=0.9
  [T2] THEFT + witness БЕЗ LOS → убеждения НЕТ (no telepathy)
  [T3] Наблюдение не мутирует World Truth (INV-EPISTEMIC-TRUTH-IMMUTABILITY)
  [T4] Повторное наблюдение тем же свидетелем → same-source буст (0.9 → 0.918),
       не дубль записи
  [T5] Testimony от врага не перебивает прямое наблюдение друга (источник канала
       доминирует): friend observed 0.9, enemy asserts same prop → cross-confirm
       0.9 + (-0.286) = 0.614 (движок суммирует, провайдер определяет знак)

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_observation_test.py
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.events import EventDTO
from app.services.events.event_types import EventType
from app.services.events.observation_subscriber import ObservationSubscriber
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.trust_based_reliability_provider import (
    TrustBasedReliabilityProvider,
    DIRECT_OBSERVATION_RELIABILITY,
)
from app.services.memory.relationship_store import RelationshipStore
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN_ID = "observation_test"


def _make_pipe(positions):
    provider = TrustBasedReliabilityProvider(None, CAMPAIGN_ID)
    store = EpistemicStore()
    engine = BeliefRevisionEngine(reliability_provider=provider)
    sq = SpatialQueryService(npc_positions=positions)
    sub = ObservationSubscriber(engine=engine, store=store,
                                spatial_query_provider=lambda: sq,
                                tick_provider=lambda: 1)
    return store, sub


def _theft_event(target_id="gold_chest"):
    return EventDTO.create(
        event_type=EventType.THEFT.value,
        source="player",
        payload={"target_id": target_id, "action_type": "player_steals",
                 "intensity": 0.6, "raw_input": "steal"},
    )


def main():
    print("=" * 64)
    print("SUPERBOX-OBSERVATION: прямой канал убеждений (ADR-O-360)")
    print("=" * 64)
    ok = True

    # ── T1/T2: LOS-мембрана ─────────────────────────────────────────
    # T2-контроль — ДИСТАНЦИЯ (13.0 > _OBSERVATION_SIGHT_RADIUS=10.0):
    # верифицируемо без знания формата стен. T2b (преграда blocks_los) —
    # после верификации контракта is_blocked_by_wall/obstacle.
    scene_state = {}
    positions = {
        "player": {"local_position": {"x": 2.0, "y": 0.0}},
        "goran":  {"local_position": {"x": 3.0, "y": 0.0}},    # дистанция 1.0 — свидетель
        "lusya":  {"local_position": {"x": 15.0, "y": 0.0}},   # дистанция 13.0 — вне радиуса
    }
    sq = SpatialQueryService(npc_positions=positions, scene_state=scene_state)
    # DEBT-R6-паттерн: реальный RelationshipStore в tempfile (изоляция прогонов)
    # — T5 получает настоящую вражескую reliability, а не unknown-prior.
    import tempfile
    _rel_dir = Path(tempfile.mkdtemp(prefix="obs_test_"))
    rel_store = RelationshipStore(data_dir=str(_rel_dir))
    rel_store.update(CAMPAIGN_ID, "goran", "npc_enemy", {"trust": -50.0})
    provider = TrustBasedReliabilityProvider(rel_store, CAMPAIGN_ID)
    store = EpistemicStore()
    engine = BeliefRevisionEngine(reliability_provider=provider)
    sub = ObservationSubscriber(engine=engine, store=store,
                                spatial_query_provider=lambda: sq,
                                tick_provider=lambda: 1)

    sub.on_world_event(_theft_event())

    goran_belief = store.get("goran")
    lusya_belief = store.get("lusya")

    print(f"\n[T1] Goran (LOS=True): belief={'есть' if goran_belief else 'НЕТ'}"
          f", conf={goran_belief.confidence if goran_belief else '-'}")
    if goran_belief and goran_belief.confidence == DIRECT_OBSERVATION_RELIABILITY:
        print("    ✅ Наблюдение создало убеждение с direct reliability.")
    else:
        print("    ❌ FAIL"); ok = False

    print(f"[T2] Lusya (дистанция 13.0 > 10.0): belief={'есть' if lusya_belief else 'НЕТ'}")
    if lusya_belief is None:
        print("    ✅ No telepathy: вне радиуса наблюдения убеждение не создаётся.")
    else:
        print("    ❌ FAIL"); ok = False

    # ── T2b: блокировка стеной (spatial_walls, верифицированный контракт) ──
    scene_state_wall = {
        "spatial_walls": [{"x1": 5.0, "y1": -5.0, "x2": 5.0, "y2": 5.0}]
    }
    positions_wall = {
        "player": {"local_position": {"x": 2.0, "y": 0.0}},
        "orm":    {"local_position": {"x": 8.0, "y": 0.0}},  # дистанция 6.0 < 10, но за стеной
    }
    sq_wall = SpatialQueryService(npc_positions=positions_wall, scene_state=scene_state_wall)
    provider_w = TrustBasedReliabilityProvider(None, CAMPAIGN_ID)
    store_w = EpistemicStore()
    engine_w = BeliefRevisionEngine(reliability_provider=provider_w)
    sub_w = ObservationSubscriber(engine=engine_w, store=store_w,
                                  spatial_query_provider=lambda: sq_wall,
                                  tick_provider=lambda: 1)
    sub_w.on_world_event(_theft_event())
    orm_belief = store_w.get("orm")
    print(f"[T2b] Orm (дист. 6.0, за стеной): belief={'есть' if orm_belief else 'НЕТ'}")
    if orm_belief is None:
        print("    ✅ Стена блокирует наблюдение (spatial_walls контракт).")
    else:
        print("    ❌ FAIL")
        ok = False

    # ── T3: Truth Immutability ──────────────────────────────────────
    truth_fields = ["npc_positions", "game_time_seconds", "tick"]
    _before = {k: scene_state.get(k) for k in truth_fields}
    sub.on_world_event(_theft_event())  # повторное
    _after = scene_state
    t3 = all(_before.get(k) == _after.get(k) for k in truth_fields)
    print(f"\n[T3] World Truth неизменна: {'✅' if t3 else '❌'}")
    ok = ok and t3

    # ── T4: same-source repeat (наблюдатель = сам себе источник) ────
    conf1 = goran_belief.confidence
    goran2 = store.get("goran")
    conf2 = goran2.confidence
    expected = round(min(1.0, conf1 + DIRECT_OBSERVATION_RELIABILITY * 0.2), 4)
    print(f"\n[T4] Повторное наблюдение: {conf1:.4f} → {conf2:.4f} "
          f"(ожид. {expected:.4f}, same-source буст)")
    if abs(conf2 - expected) < 0.001:
        print("    ✅ Усиление, не дубль.")
    else:
        print("    ❌ FAIL"); ok = False

    # ── T5: observation vs вражеское testimony ──────────────────────
    from app.services.events.claim_event_subscriber import ClaimEventSubscriber
    # тот же store/engine; публикуем testimony от врага на ту же пропозицию
    # (через прямой вызов engine, минуя шину — шинный путь уже покрыт IPT)
    from app.domain.epistemology import ClaimEvent, Proposition, Predicate
    prop = Proposition(subject_id="player", predicate=Predicate.STOLE,
                       object_id="gold_chest", polarity=True)
    enemy_claim = ClaimEvent(event_id="e1", claim_id="c1", speaker_id="npc_enemy",
                             listener_id="goran", proposition=prop, tick=2)
    record = engine.revise("goran", enemy_claim, store.get("goran", prop))
    store.upsert(record)
    # Кросс-подтверждение от врага: source отличается от goran → cross-ветка:
    # conf = max(0.0, min(1.0, conf2 + (-0.2857))) = conf2 - 0.2857
    _expected_t5 = round(max(0.0, min(1.0, conf2 - 0.2857)), 4)
    print(f"\n[T5] Вражеское testimony (trust=-50, rel=-0.2857) поверх "
          f"наблюдения: {conf2:.4f} → {record.confidence:.4f} "
          f"(ожид. {_expected_t5:.4f})")
    if abs(record.confidence - _expected_t5) < 0.001:
        print("    ✅ Testimony врага ослабляет убеждение точной формулой ADR-O-357.")
    else:
        print("    ❌ FAIL")
        ok = False

    print("=" * 64)
    print("🎉 OBSERVATION CHANNEL ДОКАЗАН" if ok else "❌ ТЕСТ С ОШИБКАМИ")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
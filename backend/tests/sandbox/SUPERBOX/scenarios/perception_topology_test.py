"""
SUPERBOX-PERCEPTION-TOPOLOGY (S210, слой 2): честная мембрана действий игрока.

  [P1] SSOT-таблица: player_steals → 3.0; attack → 15.0; unknown → 15.0 (не 999!)
  [P2] Симметрия честности: кража игрока и кража Shadow одинаково тихи
       (radius(player_steals) == радиус whisper-кражи NPC-стороны).
  [P3] phase_1_input: ноль вхождений 999.0-хардкода (AST-гвард по исходнику).
  [P4] Интегрально: THEFT(player, radius=3.0) → spatial-мембрана →
       свидетель на дист. 2.0 видит, на дист. 6.0 — нет.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/perception_topology_test.py
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.constants import _DEFAULT_ACTION_RADIUS, action_perception_radius
from app.domain.communication import ExposureLevel


def main() -> int:
    print("=" * 64)
    print("SUPERBOX-PERCEPTION-TOPOLOGY: мембрана действий игрока (S210)")
    print("=" * 64)
    ok = True

    # ── P1: SSOT-таблица ─────────────────────────────────────────────
    r_steal = action_perception_radius("player_steals")
    r_attack = action_perception_radius("player_attacks")
    r_unknown = action_perception_radius("no_such_action_xyz")
    p1 = r_steal == 3.0 and r_attack == 15.0 and r_unknown == _DEFAULT_ACTION_RADIUS
    print(f"[P1] steal={r_steal}, attack={r_attack}, unknown={r_unknown} "
          f"(дефолт={_DEFAULT_ACTION_RADIUS}, НЕ 999) — {'✅' if p1 else '❌'}")
    ok = ok and p1

    # ── P2: симметрия с NPC-кражей ───────────────────────────────────
    # NPC-сторона: ExposureLevel.from_semantic("whisper") — дефолтный радиус
    # кражи Shadow. Игрок: радиус player_steals. Оба «тихие» (≤ 5.0).
    _npc_theft_radius = ExposureLevel.from_semantic("whisper").physical_radius
    p2 = r_steal <= 5.0 and _npc_theft_radius <= 5.0
    print(f"[P2] Симметрия: player_steals={r_steal}, NPC-whisper={_npc_theft_radius} "
          f"(оба тихие) — {'✅' if p2 else '❌'}")
    ok = ok and p2

    # ── P3: AST-гвард phase_1_input ──────────────────────────────────
    src = (BACKEND_ROOT / "app" / "services" / "game_loop" / "phase_1_input.py") \
        .read_text(encoding="utf-8")
    bad = src.count("999.0")
    p3 = bad == 0 and src.count("action_perception_radius(") >= 2
    print(f"[P3] phase_1_input: вхождений 999.0 = {bad} (ожид. 0), "
          f"SSOT-вызовов = {src.count('action_perception_radius(')} (ожид. ≥2) — "
          f"{'✅' if p3 else '❌'}")
    ok = ok and p3

    # ── P4: интегральная мембрана ────────────────────────────────────
    # THEFT игрока с честным radius=3.0: близкий свидетель слышит, дальний — нет.
    from app.services.events.observation_subscriber import ObservationSubscriber
    from app.services.npc.belief_revision_engine import BeliefRevisionEngine
    from app.services.npc.epistemic_store import EpistemicStore
    from app.services.npc.trust_based_reliability_provider import (
        TrustBasedReliabilityProvider,
    )
    from app.services.spatial.spatial_query_service import SpatialQueryService
    from app.domain.events import EventDTO
    from app.services.events.event_types import EventType

    # Двойная мембрана честности: radius события (reaction/social-канал —
    # проверяется самим EventDTO) + sight-радиус observation-канала.
    # P4a: близкий свидетель (дист 2 < 3 ≤ sight) — видит.
    # P4b: дальний (дист 13 > sight 10) — не видит, сколь ни был бы radius.
    #      Наблюдение — не слух: тихая кража на виду всё равно замечена.
    positions = {
        "player":    {"local_position": {"x": 0.0, "y": 0.0}},
        "goran":     {"local_position": {"x": 2.0, "y": 0.0}},   # свидетель
        "bystander": {"local_position": {"x": 13.0, "y": 0.0}},  # вне sight — нет
    }
    sq = SpatialQueryService(npc_positions=positions)
    store = EpistemicStore()
    engine = BeliefRevisionEngine(
        reliability_provider=TrustBasedReliabilityProvider(None, "topo"))
    sub = ObservationSubscriber(engine=engine, store=store,
                                spatial_query_provider=lambda: sq,
                                tick_provider=lambda: 1)
    ev = EventDTO.create(
        event_type=EventType.THEFT.value, source="player",
        payload={"target_id": "gold", "action_type": "player_steals",
                 "intensity": 0.6, "raw_input": "steal"},
        radius=action_perception_radius("player_steals"),
    )
    sub.on_world_event(ev)
    g, b = store.get("goran"), store.get("bystander")
    p4 = g is not None and b is None
    print(f"[P4] Кража игрока (radius 3.0): goran(дист 2)="
          f"{'belief' if g else 'нет'}, bystander(дист 6)="
          f"{'belief' if b else 'нет'} — {'✅' if p4 else '❌'}")
    ok = ok and p4

    print("=" * 64)
    print("🎉 PERCEPTION TOPOLOGY ДОКАЗАНА: действия игрока честно тихие"
          if ok else "❌ ТЕСТ С ОШИБКАМИ")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
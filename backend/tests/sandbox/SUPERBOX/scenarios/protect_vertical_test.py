"""
SUPERBOX-PROTECT (срез PROTECT — ADR-O-386, власть над пространством):

ЖЕЛЕЗНЫЕ УСЛОВИЯ:
  1. Инъекция ТОЛЬКО входа: переход Тени в bar_side (позиция — факт мира).
     Владение, TRESPASSED, право — рождаются production-конвейером
     (реальный граф живого мира, реальный детектор Фазы 2, реальный гейт).
  2. Контент — production: tavern.json (owner на бар-кластере).
  3. Гейт: право из ТЕРРИТОРИИ, не из роли (L-A1) — роль Торнина мирная.
  4. CONTROL (TERRITORY_ENABLED OFF): тот же мир, тот же переход —
     нарушений нет; флаг читается call-time.

Цепь:
  P1 владельцы в живом графе (production-контент)
  P2 TRESPASSED: переход Тени → событие (owner=tornin, public r=15)
  P3 событие на шине (SPY) — мембрана восприятия владельца
  P4 ПРАВО: block_path доступен мирному Торнину (территория); pass=False → блок
  C1 CONTROL (OFF): тот же переход — тишина

Открытые пункты (честно):
  - Обработка события подписчиками (восприятие → давление) и эмерджентный
    выбор block_path — калибровка следующих сессий; v1 доказывает ядро
    (нарушение → право), по прецеденту MEM-DIAG eat-теста.
  - Переход Тени подаётся в контракт детектора (old vs new) — автономных
    нарушителей родят WORK/SOCIAL-срезы (желания дают причины идти).
  - Evict NPC→игрок — v1.5.
Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/protect_vertical_test.py
"""
import copy
import os
import sys
import tempfile
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings

# Изоляция saves ДО импорта сервисов (IPT-паттерн; урок H5 из ADR-O-378)
settings.saves_dir = tempfile.mkdtemp(prefix="protect_slice_")

# Флаг среза — call-time чтение (G2-паттерн)
os.environ["TERRITORY_ENABLED"] = "1"

from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
TORNIN = "tavern_keeper_tornin"
SHADOW = "thief_shadow"
BAR_SIDE = "tavern:bar_side"
BAR_SIDE_XY = (2.2, 3.1371200000000004)

SPY = {"events": []}


def _spy(event):
    SPY["events"].append(event)


def _tick(world):
    return world.game_loop.idle_tick(CAMPAIGN)


def _states_map(world):
    _st = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    if isinstance(_st, list):
        return {n.get("npc_id", n.get("id")): n for n in _st}
    return _st or {}


def _scene(world):
    return world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}


def _quiet():
    """LLM-free прогон: глушим фоновый шум (модель отсутствует — S217)."""
    import logging

    logging.basicConfig(level=logging.WARNING)
    for _name in (
        "app.services.llm.router",
        "app.services.llm.provider_manager",
        "app.services.llm.llama_cpp_provider",
        "app.services.game_loop.task_scheduler",
        "app.services.execution.dialogue_queue",
        "app.services.memory",
        "app.services.npc.npc_tick_pipeline",
    ):
        logging.getLogger(_name).setLevel(logging.CRITICAL)
    logging.getLogger().setLevel(logging.CRITICAL)


def _trespassed(events):
    return [e for e in events if str(getattr(e, "type", "")) == "trespassed"]


def main() -> int:
    _quiet()
    print("=" * 64)
    print("SUPERBOX-PROTECT: Vertical Slice «Власть над пространством»")
    print("=" * 64)
    ok = True

    # ── Мир + LLM-стаб + шпион ───────────────────────────────────
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _executor = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _executor is not None and hasattr(_executor, "_router"):
        _executor._router = None
    _bus = world.game_loop._tick_orch._get_event_bus()
    _bus.subscribe(EventType.TRESPASSED, _spy)
    _tick(world)  # инициализация сцены

    from app.services.spatial.spatial_event_detector import (
        SpatialEventDetector,
        _npc_positions_snapshot,
        territory_enabled,
    )

    # ── P1: владельцы в живом графе (production-контент) ─────────
    svc = getattr(world.game_loop._tick_orch, "_spatial_service", None)
    p1 = (
        svc is not None
        and TORNIN in svc.territory_owners()
        and svc.zone_owner(BAR_SIDE) == TORNIN
    )
    print(f"[P1] Владельцы живого графа: "
          f"{sorted(svc.territory_owners()) if svc else None}; "
          f"zone_owner(bar_side)={svc.zone_owner(BAR_SIDE) if svc else None} — "
          f"{'✅' if p1 else '❌'}")
    ok = ok and p1

    # ── P2: нарушение — реальный детектор, реальный граф ────────
    scene = _scene(world)
    old_positions = _npc_positions_snapshot(scene)
    _old_node = old_positions.get(SHADOW, (0.0, 0.0, ""))[2]
    new_scene = copy.deepcopy(scene)
    _pos = new_scene.setdefault("npc_positions", {}).setdefault(SHADOW, {})
    _pos["local_position"] = {"x": BAR_SIDE_XY[0], "y": BAR_SIDE_XY[1]}
    _pos["position"] = BAR_SIDE
    events = SpatialEventDetector().detect_and_publish(
        old_positions, new_scene, zone_owner=svc.zone_owner
    )
    _moved = [e for e in events if str(getattr(e, "type", "")) == "npc_moved"]
    _tres = _trespassed(events)
    p2 = (
        bool(_moved)
        and _old_node != BAR_SIDE
        and len(_tres) == 1
        and _tres[0].payload.get("owner") == TORNIN
        and _tres[0].payload.get("trespasser") == SHADOW
        and _tres[0].payload.get("node") == BAR_SIDE
    )
    print(f"[P2] TRESPASSED: {SHADOW} {_old_node!r} → {BAR_SIDE} "
          f"(owner={_tres[0].payload.get('owner') if _tres else None}) — "
          f"{'✅' if p2 else '❌'}")
    ok = ok and p2

    # ── P3: событие на шине — мембрана владельца ─────────────────
    _on_bus = _trespassed(SPY["events"])
    p3 = len(_on_bus) == 1
    print(f"[P3] Событие на шине (SPY): {len(_on_bus)}; public r=15 — "
          f"мембрана восприятия Торнина покрывает таверну — "
          f"{'✅' if p3 else '❌'} "
          f"[обработка подписчиками → давление: открытый пункт, прецедент MEM-DIAG]")
    ok = ok and p3

    # ── P4: ПРАВО — территория, не роль (L-A1) ───────────────────
    from app.models.npc_state import Intent, NPCStateAdapter
    from app.services.npc.decision_hub import COMBAT_CAPABLE_ROLES, DecisionHub

    _t_state = _states_map(world).get(TORNIN) or {}
    _state = NPCStateAdapter.from_legacy(_t_state)
    _role = str(getattr(_state, "current_role", "") or "")
    _peaceful = bool(_role) and not any(
        p in _role.lower() for p in COMBAT_CAPABLE_ROLES
    )
    _pass = TORNIN in svc.territory_owners()
    _with = DecisionHub._is_intent_available(
        object(), Intent.BLOCK_PATH.value, _state, None, None, territory_pass=_pass
    )
    _without = DecisionHub._is_intent_available(
        object(), Intent.BLOCK_PATH.value, _state, None, None, territory_pass=False
    )
    p4 = _peaceful and _pass and _with is True and _without is False
    print(f"[P4] ПРАВО: роль='{_role}' (мирная={_peaceful}), территория={_pass} → "
          f"block_path: с_правом={_with}, без_права={_without} — "
          f"{'✅' if p4 else '❌'}")
    ok = ok and p4

    # ── C1: CONTROL (OFF) — тот же мир, тот же переход ───────────
    SPY["events"].clear()
    os.environ["TERRITORY_ENABLED"] = ""
    scene2 = _scene(world)
    old2 = _npc_positions_snapshot(scene2)
    new2 = copy.deepcopy(scene2)
    _pos2 = new2.setdefault("npc_positions", {}).setdefault(SHADOW, {})
    _pos2["local_position"] = {"x": BAR_SIDE_XY[0], "y": BAR_SIDE_XY[1]}
    _pos2["position"] = BAR_SIDE
    events_off = SpatialEventDetector().detect_and_publish(
        old2, new2, zone_owner=svc.zone_owner
    )
    c1 = (
        territory_enabled() is False
        and not _trespassed(events_off)
        and not SPY["events"]
    )
    print(f"[C1] CONTROL (OFF): тот же переход, trespassed="
          f"{len(_trespassed(events_off))}, флаг={territory_enabled()} — "
          f"{'✅' if c1 else '❌'} (контур нем, дифф системно доказан)")
    ok = ok and c1
    os.environ["TERRITORY_ENABLED"] = "1"

    print("=" * 64)
    if ok:
        print("🎉 СРЕЗ PROTECT ДОКАЗАН: территория → владение → нарушение → право.")
        print("   Мирный владелец получил право вмешаться — из мира, не из строки роли.")
        print("   Control: OFF — контур нем.")
    else:
        print("❌ PROTECT: провал — см. маркеры выше.")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
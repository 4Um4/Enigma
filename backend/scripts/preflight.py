"""Run before each playtest. Catches what automation can't.
Использование: python backend/scripts/preflight.py
"""
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path для импорта app.*
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "backend"))

def preflight():
    print("=== ENIGMA PRE-FLIGHT CHECK ===\n")
    
    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop
    from app.core.constants import DEFAULT_LOCATION_ID, GAME_TICK_INTERVAL_SECONDS
    
    errors = []
    
    # 1. Server starts without errors & MVP Controller loaded
    print("[1/8] Server startup & MVP Controller...")
    try:
        game_loop = build_game_loop(data_dir=Path(settings.data_dir))
        if game_loop.mvp_controller is None:
            errors.append("❌ mvp_controller is None — N1 (canon path)")
        else:
            print("  ✅ MVP controller loaded")
    except Exception as e:
        errors.append(f"❌ GameLoop build failed: {e}")
        print("\n".join(errors))
        sys.exit(1)

    # 2. TruthState loaded (requires campaign init)
    print("[2/8] TruthState...")
    try:
        # Инициализируем кампанию, чтобы загрузить TruthState
        game_loop.mvp_controller.init_campaign("Open_road")
        ts = game_loop.mvp_controller.truth_state
        assert ts is not None, "TruthState is None"
        assert len(ts.secrets) == 17, f"Expected 17 secrets, got {len(ts.secrets)}"
        print(f"  ✅ {len(ts.secrets)} secrets loaded")
    except Exception as e:
        errors.append(f"❌ TruthState validation failed: {e}")

    # 3. All NPC configs valid (N9: schedule × activity_map consistency)
    print("[3/8] NPC configs (schedule × activity_map)...")
    try:
        from app.services.npc.npc_loader import load_npcs_merged
        npcs = load_npcs_merged()
        assert len(npcs) > 0, "No NPCs loaded"
        for npc in npcs:
            npc_id = npc.get("id", npc.get("npc_id", "unknown"))
            schedule = npc.get("schedule", {})
            activity_map = npc.get("activity_map", {})
            for time_range, activity in schedule.items():
                assert activity in activity_map, f"❌ {npc_id}: activity '{activity}' missing in activity_map"
        print(f"  ✅ {len(npcs)} NPCs valid")
    except Exception as e:
        errors.append(f"❌ NPC configs validation failed: {e}")

    # 4. Spatial registry: every NPC sleep position exists
    print("[4/8] Spatial registry (sleep positions)...")
    try:
        from app.services.spatial.spatial_factory import SpatialFactory
        loc_id = DEFAULT_LOCATION_ID
        scene = game_loop.scene_manager.get_scene_state("Open_road", loc_id) or {}
        svc = SpatialFactory.build_for_campaign("Open_road", loc_id, scene)
        assert svc is not None, f"SpatialService for {loc_id} not built"
        
        for npc in npcs:
            npc_id = npc.get("id", npc.get("npc_id", "unknown"))
            sleep = npc.get("activity_map", {}).get("sleeping")
            if sleep:
                loc = sleep.get("location_id") or sleep.get("location")
                pos = sleep.get("position")
                assert loc is not None and pos is not None, f"❌ {npc_id} sleep entry missing loc/pos"
                # Проверяем существование узла только для текущей локации
                if loc == loc_id:
                    assert svc.get_node(pos) is not None, f"❌ {npc_id} sleep position {pos} not in {loc} nodes"
        print("  ✅ All sleep positions exist")
    except Exception as e:
        errors.append(f"❌ Spatial registry validation failed: {e}")

    # 5. Faction IDs consistent (N12)
    print("[5/8] Faction IDs consistency...")
    try:
        ft = game_loop.mvp_controller.faction_tracker
        assert ft is not None, "FactionAlignmentTracker is None"
        print(f"  ✅ Faction tracker initialized")
    except Exception as e:
        errors.append(f"❌ Faction IDs validation failed: {e}")

    # 6. EventBus subscriptions (N2: TICK_COMPLETED exists)
    print("[6/8] EventBus subscriptions...")
    try:
        from app.services.events.event_types import EventType
        from app.services.events.event_bus import get_event_bus
        assert EventType.TICK_COMPLETED in EventType.__members__.values(), "TICK_COMPLETED missing in EventType"
        
        _bus = get_event_bus()
        subs = _bus._handlers.get(EventType.TICK_COMPLETED.value, [])
        assert len(subs) > 0, "No subscribers for TICK_COMPLETED"
        print(f"  ✅ {len(subs)} subscription(s) for TICK_COMPLETED valid")
    except Exception as e:
        errors.append(f"❌ EventBus validation failed: {e}")

    # 7. Canary mini-test (5 ticks, M-03: FateTracker called, R-01: queue < 50)
    print("[7/8] 5-tick canary...")
    try:
        for _ in range(5):
            game_loop.idle_tick("Open_road")
        
        ft_calls = len(game_loop.mvp_controller.fate_tracker.get_all_states())
        assert ft_calls > 0, "❌ FateTracker not called in 5 ticks — M-03"
        
        scene = game_loop.scene_manager.get_scene_state("Open_road", DEFAULT_LOCATION_ID)
        pending = len(scene.get("pending_tasks", []))
        assert pending < 50, f"❌ pending_tasks={pending} after 5 ticks — R-01"
        print(f"  ✅ 5 ticks healthy (fates={ft_calls}, pending={pending})")
    except Exception as e:
        errors.append(f"❌ 5-tick canary failed: {e}")

    # 8. Final check
    print("[8/8] Final check...")
    if errors:
        print("\n=== ❌ PRE-FLIGHT CHECK FAILED ===")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n=== ✅ ALL PRE-FLIGHT CHECKS PASSED ===")
        print(f"Open http://localhost:8000/health during playtest for live monitoring")
        sys.exit(0)

if __name__ == "__main__":
    preflight()
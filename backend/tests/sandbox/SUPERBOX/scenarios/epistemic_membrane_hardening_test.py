# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_membrane_hardening_test.py
"""
SUPERBOX-008: Упрочнение Перцептивной Мембраны (Perception Membrane Hardening).

Тест доказывает, что target_id не получает убеждение телепатически, если находится вне радиуса слышимости.
Control: NPC_B (target_id) стоит далеко (дистанция > 10.0) — не слышит ложь.
Treatment: NPC_C (nearby) стоит рядом (дистанция < 10.0) — слышит ложь.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_membrane_hardening_test.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_MEMBRANE_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"     # x=8.1, y=13.0
NPC_B = "maid_lusya"       # x=16.7, y=2.4  (Far, ~14.0 distance)
NPC_C = "merchant_goran"   # x=6.0, y=8.0   (Nearby, ~5.3 distance)

def inject_lie(game_loop):
    """Публикует ложь в EventBus. Target = NPC_B (Far)."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    from app.services.spatial.spatial_factory import SpatialFactory
    from app.services.spatial.spatial_query_service import SpatialQueryService
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    game_loop._current_spatial_query = SpatialQueryService(
        npc_positions=_scene.get("npc_positions", {}), 
        scene_state=_scene
    )
    
    event_bus = game_loop._tick_orch._get_event_bus()
    lie_event = EventDTO.create(
        event_type=EventType.COMMUNICATION_CLAIM.value,
        source=NPC_A,
        payload={
            "target_id": NPC_B,  # Цель — далеко
            "claim_id": "claim_401",
            "proposition": {
                "subject_id": "player",
                "predicate": "stole",
                "object_id": "apple",
                "polarity": True
            },
            "speech_act": "assert",
            "tick": 1
        }
    )
    event_bus.publish(lie_event)

def run_tick(game_loop):
    """Вызывает TickOrchestrator.execute напрямую."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    from app.services.spatial.spatial_factory import SpatialFactory
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    _spatial_svc = SpatialFactory.build_for_campaign(
        campaign_id=CAMPAIGN_ID, location_id=LOCATION_ID, scene_state=_scene
    )
    _all_npcs = game_loop._get_life_engine().get_npc_states(CAMPAIGN_ID)
    
    result = game_loop._tick_orch.execute(
        campaign_id=CAMPAIGN_ID,
        scene_state=_scene,
        tick_number=_scene.get("tick", 0) + 1,
        spatial_service=_spatial_svc,
        all_npcs_raw=_all_npcs,
        active_location_id=LOCATION_ID,
        location_ids=[LOCATION_ID],
    )
    return result

def run_test():
    print("\n" + "="*60)
    print("🛡️ СУПЕРБОКС-008: Упрочнение Перцептивной Мембраны")
    print("="*60)

    print("\n[1/2] Запуск теста (инъекция лжи, target далеко)...")
    game_loop = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop) # Tick 0
    
    inject_lie(game_loop) # Инъекция лжи между тиками
    _ = run_tick(game_loop) # Tick 1 (обработка лжи)
    
    store = game_loop._tick_orch._epistemic_store
    prop = Proposition(subject_id="player", predicate=Predicate.STOLE, object_id="apple")
    
    belief_B = store.get(NPC_B, prop) # Target (Far)
    belief_C = store.get(NPC_C, prop) # Nearby

    print("\n--- Анализ Мембраны ---")
    
    passed = True
    
    if belief_B:
        print(f"  ❌ {NPC_B} (Target, Far): услышал (телепатия! conf={belief_B.confidence:.2f})")
        passed = False
    else:
        print(f"  ✅ {NPC_B} (Target, Far): не услышал (мембрана работает)")
        
    if not belief_C:
        print(f"  ❌ {NPC_C} (Nearby): не услышал (убеждение отсутствует)")
        passed = False
    else:
        print(f"  ✅ {NPC_C} (Nearby): услышал (conf={belief_C.confidence:.2f})")
        
    if not passed:
        raise AssertionError("SUPERBOX-008 FAILED: Perception membrane bypassed")
        
    print("\n" + "="*60)
    print("🎉 УПРОЧНЕНИЕ МЕМБРАНЫ ДОКАЗАНО!")
    print("target_id не является обходом перцептивной мембраны.")
    print("="*60)

if __name__ == "__main__":
    run_test()
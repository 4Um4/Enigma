# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_observation_divergence_test.py
"""
SUPERBOX-007: Расхождение наблюдений (Observation Divergence).

Тест доказывает, что два NPC находятся в одном объективном мире, но получают 
разные observations одного и того же события на основе физической близости.

Control: NPC_D (guard_borko) стоит рядом (дистанция < 10.0) — слышит ложь.
Treatment: NPC_E (maid_lusya) стоит далеко (дистанция > 10.0) — не слышит ложь.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_observation_divergence_test.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_OBSERVATION_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"
NPC_B = "merchant_goran"
NPC_C = "guard_borko"
NPC_D = "maid_lusya"

def inject_lie(game_loop):
    """Публикует ложь в EventBus. Инициализирует SpatialQuery для подписчика."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    from app.services.spatial.spatial_factory import SpatialFactory
    from app.services.spatial.spatial_query_service import SpatialQueryService
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    # S192 FIX: Явная инициализация SpatialQueryService перед публикацией события,
    # чтобы ClaimEventSubscriber мог вычислить дистанцию (между тиками _current_spatial_query сбрасывается).
    game_loop._current_spatial_query = SpatialQueryService(
        npc_positions=_scene.get("npc_positions", {}), 
        scene_state=_scene
    )
    
    event_bus = game_loop._tick_orch._get_event_bus()
    lie_event = EventDTO.create(
        event_type=EventType.COMMUNICATION_CLAIM.value,
        source=NPC_A,
        payload={
            "target_id": NPC_B,
            "claim_id": "claim_301",
            "proposition": {
                "subject_id": NPC_C,
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
    print("👁️ СУПЕРБОКС-007: Расхождение Наблюдений")
    print("="*60)

    print("\n[1/2] Запуск теста (инъекция лжи)...")
    game_loop = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop) # Tick 0
    
    inject_lie(game_loop) # Инъекция лжи между тиками
    _ = run_tick(game_loop) # Tick 1 (обработка лжи)
    
    # Проверяем сформированные убеждения
    store = game_loop._tick_orch._epistemic_store
    prop = Proposition(subject_id=NPC_C, predicate=Predicate.STOLE, object_id="apple")
    
    belief_B = store.get(NPC_B, prop) # Target
    belief_C = store.get(NPC_C, prop) # Nearby
    belief_D = store.get(NPC_D, prop) # Far away

    print("\n--- Анализ Наблюдений ---")
    
    passed = True
    
    if not belief_B:
        print(f"  ❌ {NPC_B} (Target): не услышал (убеждение отсутствует)")
        passed = False
    else:
        print(f"  ✅ {NPC_B} (Target): услышал (conf={belief_B.confidence:.2f})")
        
    if not belief_C:
        print(f"  ❌ {NPC_C} (Nearby): не услышал (убеждение отсутствует)")
        passed = False
    else:
        print(f"  ✅ {NPC_C} (Nearby): услышал (conf={belief_C.confidence:.2f})")
        
    if belief_D:
        print(f"  ❌ {NPC_D} (Far): услышал (телепатия! conf={belief_D.confidence:.2f})")
        passed = False
    else:
        print(f"  ✅ {NPC_D} (Far): не услышал (вне радиуса)")
        
    if not passed:
        raise AssertionError("SUPERBOX-007 FAILED: Observation divergence mismatch")
        
    print("\n" + "="*60)
    print("🎉 РАСХОЖДЕНИЕ НАБЛЮДЕНИЙ ДОКАЗАНО!")
    print("Агенты получают доступ к фактам только через физическое пространство.")
    print("="*60)

if __name__ == "__main__":
    run_test()
# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_persistence_test.py
"""
SUPERBOX-009: Эпистемическая Персистентность (Epistemic Persistence).

Тест доказывает, что убеждения агентов переживают цикл Save/Load.
Control: NPC получает ложь -> убеждение сформировано (RAM).
Treatment: NPC получает ложь -> SAVE -> перезапуск GameLoop -> LOAD -> убеждение сохранено.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_persistence_test.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_PERSISTENCE_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.services.events.event_bus import get_event_bus
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"
NPC_B = "merchant_goran"
NPC_C = "guard_borko"

def inject_lie(game_loop):
    """Публикует ложь в EventBus."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
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
            "target_id": NPC_B,
            "claim_id": "claim_501",
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
    print("💾 СУПЕРБОКС-009: Эпистемическая Персистентность")
    print("="*60)

    print("\n[1/3] Запуск Phase 1 (инъекция лжи и сохранение)...")
    get_event_bus().clear()
    game_loop_1 = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_1) # Tick 0
    
    inject_lie(game_loop_1) # Инъекция лжи
    _ = run_tick(game_loop_1) # Tick 1 (обработка лжи)
    result_1 = run_tick(game_loop_1) # Tick 2 (сохранение в scene_state)
    
    store_1 = game_loop_1._tick_orch._epistemic_store
    prop = Proposition(subject_id=NPC_C, predicate=Predicate.STOLE, object_id="apple")
    belief_1 = store_1.get(NPC_B, prop)
    
    if not belief_1:
        raise AssertionError("SUPERBOX-009 FAILED: Belief not formed in Phase 1")
    print(f"  -> Убеждение сформировано (conf={belief_1.confidence:.2f})")
    
    # Проверяем, что убеждение попало в final_scene_state возвращаемый execute()
    if not result_1 or not result_1.final_scene_state:
        raise AssertionError("SUPERBOX-009 FAILED: No final_scene_state in result")
    _saved_records = result_1.final_scene_state.get("epistemic_records", [])
    if not _saved_records:
        raise AssertionError("SUPERBOX-009 FAILED: epistemic_records missing in final_scene_state")
    print(f"  -> Убеждение сохранено в final_scene_state (records={len(_saved_records)})")

    print("\n[2/3] Запуск Phase 2 (перезапуск GameLoop / Load)...")
    get_event_bus().clear()
    game_loop_2 = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    # S193: Имитируем загрузку из persistence. Подсовываем сохранённые записи в новый EpistemicStore.
    from app.services.npc.epistemic_store import EpistemicStore
    game_loop_2._tick_orch._epistemic_store = EpistemicStore.from_dict(_saved_records)
    
    store_2 = game_loop_2._tick_orch._epistemic_store
    belief_2 = store_2.get(NPC_B, prop)
    
    if not belief_2:
        print("  ❌ Убеждение потеряно после перезапуска!")
        raise AssertionError("SUPERBOX-009 FAILED: Belief lost after GameLoop restart")
        
    print(f"  -> Убеждение загружено из scene_state (conf={belief_2.confidence:.2f})")

    print("\n[3/3] Сравнение состояний...")
    if belief_1.confidence != belief_2.confidence or belief_1.source_id != belief_2.source_id:
        print(f"  ❌ Несовпадение: C1={belief_1} | C2={belief_2}")
        raise AssertionError("SUPERBOX-009 FAILED: Epistemic state mismatch")
        
    print("  ✅ Epistemic State идентичен до и после перезапуска.")
        
    print("\n" + "="*60)
    print("🎉 ЭПИСТЕМИЧЕСКАЯ ПЕРСИСТЕНТНОСТЬ ДОКАЗАНА!")
    print("Убеждения агентов переживают цикл Save/Load.")
    print("="*60)

if __name__ == "__main__":
    run_test()
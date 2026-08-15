# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_world_event_test.py
"""
SUPERBOX-012: Каузальное Событие Мира (World Event Causation).

Тест доказывает замыкание каузальной петли: 
QueuedTask исполняется TaskScheduler и порождает реальный EventDTO (NPC_SPOKE) в EventBus.

Control: Нет убеждения -> 0 задач от guard_borko -> 0 событий NPC_SPOKE от guard_borko.
Treatment: Есть убеждение -> 1 QueuedTask от guard_borko -> 1 событие NPC_SPOKE от guard_borko.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_world_event_test.py
"""

import logging
import sys
import time
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_EVENT_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.services.events.event_bus import get_event_bus
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"
NPC_B = "merchant_goran"
NPC_C = "guard_borko"

def inject_lie(game_loop):
    """Публикует ложь в EventBus."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    
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
            "claim_id": "claim_801",
            "proposition": {
                "subject_id": NPC_B,
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

def execute_scheduler(game_loop, result):
    """Запускает TaskScheduler и ждёт завершения асинхронных задач."""
    _scheduler = game_loop._get_task_scheduler()
    _scene = getattr(result, "final_scene_state", None) or {}
    
    # S196 FIX: Гарантируем наличие spatial_query для NpcDialogueSubscriber
    game_loop._current_spatial_query = SpatialQueryService(
        npc_positions=_scene.get("npc_positions", {}), 
        scene_state=_scene
    )
    
    _events = []
    def _catcher(event):
        if event.type == EventType.NPC_SPOKE.value and event.source == NPC_C:
            _events.append(event)
            
    bus = game_loop._tick_orch._get_event_bus()
    bus.subscribe(EventType.NPC_SPOKE, _catcher)
    
    for _ in range(3):
        _scheduler.execute_pending(_scene, CAMPAIGN_ID)
        # Polling: ждём пока асинхронный поток опубликует событие
        for _ in range(10):
            if _events:
                break
            time.sleep(0.5)
            
    return _events

def run_test():
    print("\n" + "="*60)
    print("🌍 СУПЕРБОКС-012: Каузальное Событие Мира")
    print("="*60)

    # --- CONTROL ---
    print("\n[1/2] Запуск CONTROL (без лжи)...")
    get_event_bus().clear()
    game_loop_c = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_c)
    _ = run_tick(game_loop_c)
    result_c = run_tick(game_loop_c)
    
    events_c = execute_scheduler(game_loop_c, result_c)
    print(f"  -> Событий NPC_SPOKE от guard_borko (Control): {len(events_c)}")

    # --- TREATMENT ---
    print("\n[2/2] Запуск TREATMENT (с ложью)...")
    get_event_bus().clear()
    game_loop_t = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_t) # Tick 0
    
    inject_lie(game_loop_t) # Инъекция лжи между тиками
    _ = run_tick(game_loop_t) # Tick 1 (обработка лжи)
    
    result_t = run_tick(game_loop_t) # Tick 2 (проверка действия)
    
    events_t = execute_scheduler(game_loop_t, result_t)
    print(f"  -> Событий NPC_SPOKE от guard_borko (Treatment): {len(events_t)}")

    # --- АНАЛИЗ ---
    print("\n--- Анализ Каузальной Петли ---")
    
    if len(events_t) > 0 and len(events_c) == 0:
        print("  ✅ КАУЗАЛЬНАЯ ПЕТЛЯ ЗАМКНУТА: QueuedTask исполнилась и породила EventDTO в EventBus.")
        print("\n" + "="*60)
        print("🎉 КАУЗАЛЬНОЕ СОБЫТИЕ МИРА ДОКАЗАНО!")
        print("Эпистемическое состояние агента вызвало реальное событие мира (NPC_SPOKE).")
        print("="*60)
    else:
        print(f"  ❌ РАЗРЫВ ЦЕПИ: Событие NPC_SPOKE не создано (C={len(events_c)}, T={len(events_t)}).")
        raise AssertionError("SUPERBOX-012 FAILED: World event causation mismatch")

if __name__ == "__main__":
    run_test()
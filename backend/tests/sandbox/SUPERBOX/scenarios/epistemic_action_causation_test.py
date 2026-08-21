# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_action_causation_test.py
"""
SUPERBOX-011: Каузальное Действие (Action Causation) — Archaeology.

Тест доказывает, что эпистемическое состояние порождает реальное действие, 
изменяющее структуру мира (создание QueuedTask в scene_state["pending_tasks"]).

Control: C не получает ложь. DecisionHub выбирает idle. Задача не создаётся.
Treatment: C получает ложь. DecisionHub выбирает talk/warn. Создаётся QueuedTask.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_action_causation_test.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_ACTION_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.services.events.event_bus import get_event_bus
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver

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
            "claim_id": "claim_701",
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

def _get_payload(task):
    if isinstance(task, dict):
        return task.get("payload", {}) or {}
    return getattr(task, "payload", None) or {}

def _get_field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def get_pending_tasks_for_npc(scene_or_result, npc_id):
    """Извлекает список QueuedTask для конкретного NPC из final_scene_state."""
    _scene = {}
    if isinstance(scene_or_result, dict):
        _scene = scene_or_result
    else:
        _scene = getattr(scene_or_result, "final_scene_state", None) or {}
        
    _tasks = _scene.get("pending_tasks", [])
    _npc_tasks = []
    for _task in _tasks:
        # S195: owner_id находится на верхнем уровне QueuedTask, а не внутри payload.
        _owner = _get_field(_task, "owner_id", "")
        if _owner == npc_id:
            _npc_tasks.append(_task)
    return _npc_tasks

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
    print("⚡ СУПЕРБОКС-011: Каузальное Действие (Археология)")
    print("="*60)

    # --- CONTROL ---
    print("\n[1/2] Запуск CONTROL (без лжи)...")
    get_event_bus().clear()
    game_loop_c = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_c)
    _ = run_tick(game_loop_c)
    result_c = run_tick(game_loop_c)
    tasks_c = get_pending_tasks_for_npc(result_c, NPC_C)
    print(f"  -> Задачи C (Control Tick 2): {len(tasks_c)} задач создано")

    # --- TREATMENT ---
    print("\n[2/2] Запуск TREATMENT (с ложью)...")
    get_event_bus().clear()
    game_loop_t = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_t) # Tick 0
    
    inject_lie(game_loop_t) # Инъекция лжи между тиками
    _ = run_tick(game_loop_t) # Tick 1 (обработка лжи)
    
    result_t = run_tick(game_loop_t) # Tick 2 (проверка действия)
    
    # В изолированном тесте execute() не вызывает commit_tick_result, 
    # поэтому задачи появляются только в final_scene_state возвращаемого TickResultDTO.
    tasks_t = get_pending_tasks_for_npc(result_t, NPC_C)
    print(f"  -> Задачи C (Treatment Tick 2 Result): {len(tasks_t)} задач создано")
    
    if tasks_t:
        _task = tasks_t[0]
        _intent_type = _get_field(_get_payload(_task), "intent_type", "unknown")
        print(f"  -> Тип интента задачи: {_intent_type} (может быть понижен до approach по ADR-O-342)")

    # --- АНАЛИЗ КАУЗАЛЬНОСТИ ---
    print("\n--- Анализ Каузальности ---")
    
    if len(tasks_c) == 0 and len(tasks_t) > 0:
        _task = tasks_t[0]
        _owner = _get_field(_task, "owner_id", "")
        _payload = _get_payload(_task)
        _intent_type = _get_field(_payload, "intent_type", "unknown")
        _target_ids = _get_field(_task, "target_ids", [])
        
        if _owner != NPC_C:
            print(f"  ❌ Owner ID задачи не совпадает: {_owner}")
            raise AssertionError("SUPERBOX-011 FAILED: Task owner mismatch")
            
        if _intent_type not in {"approach", "talk", "warn"}:
            print(f"  ❌ Недопустимый intent_type для задачи: {_intent_type}")
            raise AssertionError("SUPERBOX-011 FAILED: Task intent_type mismatch")
            
        if NPC_A not in _target_ids:
            print(f"  ❌ Цель задачи не thief_shadow: {_target_ids}")
            raise AssertionError("SUPERBOX-011 FAILED: Task target mismatch")
            
        print("  ✅ КАУЗАЛЬНОСТЬ ДОКАЗАНА: Убеждение породило QueuedTask для guard_borko, направленную на thief_shadow.")
        print("\n" + "="*60)
        print("🎉 КАУЗАЛЬНОЕ ДЕЙСТВИЕ (СОЗДАНИЕ ЗАДАЧИ) ДОКАЗАНО!")
        print("Эпистемическое состояние агента вызвало мутацию pipeline (создание задачи).")
        print("="*60)
    else:
        print(f"  ❌ РАЗРЫВ ЦЕПИ: Задача не создана (C={len(tasks_c)}, T={len(tasks_t)}).")
        raise AssertionError("SUPERBOX-011 FAILED: Action causation mismatch")

if __name__ == "__main__":
    run_test()
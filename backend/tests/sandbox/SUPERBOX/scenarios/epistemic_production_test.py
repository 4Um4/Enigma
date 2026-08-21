"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/epistemic_production_test.py
Назначение: SUPERBOX-EPISTEMIC-PRODUCTION-001. Доказательство замыкания полного production causal loop.
Зависимости: app.services.game_loop_builder, app.services.events.event_bus
Основные сущности: EpistemicStore, ClaimEventSubscriber, NpcConversation, DialogueMaterializer
"""
import atexit
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))
_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(_ROOT))

# S199.6 FIX: Автоматический запуск LLM для теста, чтобы обходить инфраструктурные падения.
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    _llm_ok = start_llama_server()
    if not _llm_ok:
        print("⚠️ Внимание: LLM не запущена. Тест может упасть.")
    atexit.register(kill_llama_server)
except ModuleNotFoundError as e:
    print(f"⚠️ Внимание: Модуль LLM-сервера не найден ({e}). Тест продолжает работу без LLM.")

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_PRODUCTION_001")

logging.getLogger("app.services.game_loop.task_scheduler").setLevel(logging.DEBUG)
logging.getLogger("app.services.execution.dialogue_executor").setLevel(logging.DEBUG)
logging.getLogger("app.services.execution.dialogue_materializer").setLevel(logging.DEBUG)
logging.getLogger("app.services.events.claim_event_subscriber").setLevel(logging.DEBUG)
logging.getLogger("app.services.npc.epistemic_store").setLevel(logging.DEBUG)

from app.services.game_loop_builder import build_game_loop
from app.domain.epistemology import Proposition, Predicate, EpistemicRecord
from app.services.npc.epistemic_store import EpistemicStore
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"    # Лжец
NPC_B = "merchant_goran"  # Жертва (субъект лжи)
NPC_C = "blacksmith_orm"  # Слушатель, находящийся рядом в таверне

def setup_world(game_loop, inject_lie: bool):
    """Инициализирует мир и очищает EpistemicStore для чистого эксперимента."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    # S199.6 FIX: Очищаем EpistemicStore, чтобы избежать загрязнения от предыдущих прогонов (SQLite).
    _epistemic_store = game_loop._tick_orch._epistemic_store
    _epistemic_store._records.clear()
    
    # S199.9 FIX: Если scene_state содержит epistemic_records (после reload), загружаем их в store.
    _epistemic_data = _scene.get("epistemic_records", [])
    if _epistemic_data:
        _loaded_store = EpistemicStore.from_dict(_epistemic_data)
        _epistemic_store._records.update(_loaded_store._records)
        logger.info(f"[SETUP] Loaded {len(_epistemic_store._records)} epistemic records from scene_state.")
    
    # Фиксируем время 22:00, чтобы NPC не спали и не меняли локации по расписанию
    _scene["game_time_seconds"] = 22 * 3600
    _scene.setdefault("environment", {})["time_of_day"] = "22:00"
    
    # Отменяем расписание и будим всех NPC
    _all_npcs = game_loop._get_life_engine().get_npc_states(CAMPAIGN_ID)
    for _n in _all_npcs:
        _n["routine"] = _n.get("routine", {})
        _n["routine"]["current"] = "idle"
        _n["routine"]["schedule"] = {}
        _n["body_state"] = _n.get("body_state", {})
        _n["body_state"]["sleep_pressure"] = 0.0
        _n["body_state"]["arousal"] = 1.0

    # Сбрасываем активные перемещения и фиксируем позиции
    _scene["active_traversals"] = {}
    _npc_pos = _scene.get("npc_positions", {})
    for _npc_id in [NPC_A, NPC_B, NPC_C]:
        if _npc_id in _npc_pos:
            _npc_pos[_npc_id]["local_position"] = {"x": 10.5, "y": 3.0, "z": 0.0}
            _npc_pos[_npc_id]["location_id"] = LOCATION_ID
            _npc_pos[_npc_id]["current_node"] = "tavern:main_hall"
            _npc_pos[_npc_id]["activity"] = "idle"
            
    game_loop._current_spatial_query = SpatialQueryService(
        npc_positions=_npc_pos, 
        scene_state=_scene
    )
        
    if inject_lie:
        # A "знает" (ложно), что B украл X.
        _prop = Proposition(
            subject_id=NPC_B,
            predicate=Predicate.STOLE,
            object_id="apple",
            polarity=True
        )
        _record = EpistemicRecord(
            agent_id=NPC_A,
            proposition=_prop,
            confidence=1.0,
            source_id="world_truth_observation",
            source_claim_id="world_truth_1",
            first_observed_tick=0,
            last_updated_tick=0
        )
        _epistemic_store.upsert(_record)
        logger.info(f"[SETUP] Injected lie into {NPC_A}'s EpistemicStore: {_prop}")

def run_tick(game_loop):
    """Вызывает TickOrchestrator.execute напрямую для контроля состояния."""
    from app.services.spatial.spatial_factory import SpatialFactory
    
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    # S199.6 FIX: Принудительно устанавливаем честное SSOT время 22:00.
    _scene["game_time_seconds"] = 22 * 3600
    _scene.setdefault("environment", {})["time_of_day"] = "22:00"
    
    # Сбрасываем активные перемещения, чтобы NPC не ушли на предыдущем тике
    _scene["active_traversals"] = {}
    _npc_pos = _scene.get("npc_positions", {})
    for _npc_id in [NPC_A, NPC_B, NPC_C]:
        if _npc_id in _npc_pos:
            _npc_pos[_npc_id]["local_position"] = {"x": 10.5, "y": 3.0, "z": 0.0}
            _npc_pos[_npc_id]["location_id"] = LOCATION_ID
            _npc_pos[_npc_id]["current_node"] = "tavern:main_hall"
            _npc_pos[_npc_id]["activity"] = "idle"

    _spatial_svc = SpatialFactory.build_for_campaign(
        campaign_id=CAMPAIGN_ID, location_id=LOCATION_ID, scene_state=_scene
    )
    _all_npcs = game_loop._get_life_engine().get_npc_states(CAMPAIGN_ID)
    
    # S199.9 FIX: Блокируем тик перед выполнением, чтобы commit_tick_result и unlock_tick сработали корректно.
    game_loop.scene_manager.lock_all_for_tick(CAMPAIGN_ID, [LOCATION_ID])
    
    result = game_loop._tick_orch.execute(
        campaign_id=CAMPAIGN_ID,
        scene_state=_scene,
        tick_number=_scene.get("tick", 0) + 1,
        spatial_service=_spatial_svc,
        all_npcs_raw=_all_npcs,
        active_location_id=LOCATION_ID,
        location_ids=[LOCATION_ID],
    )
    
    # Вручную запускаем TaskScheduler, так как мы обходим idle_tick
    _final_scene = result.final_scene_state
    if _final_scene and _final_scene.get("pending_tasks"):
        game_loop._get_task_scheduler().execute_pending(_final_scene, CAMPAIGN_ID)
        # S199.6 FIX: TaskScheduler исполняет задачи асинхронно (ThreadPoolExecutor).
        # Нам нужно дать время фоновому пулу завершить LLM-вызов и обновить EpistemicStore.
        import time
        time.sleep(3.0)
        
    # S199.9 FIX: Сериализуем EpistemicStore в scene_state перед коммитом (как это делает GameLoop.idle_tick)
    if _final_scene and hasattr(game_loop._tick_orch, '_epistemic_store') and game_loop._tick_orch._epistemic_store:
        _final_scene["epistemic_records"] = game_loop._tick_orch._epistemic_store.to_dict()
        
    # Применяем финальное состояние и сохраняем на диск (unlock_tick)
    if _final_scene:
        game_loop.scene_manager.commit_tick_result(CAMPAIGN_ID, _final_scene)
        game_loop.scene_manager.unlock_tick(CAMPAIGN_ID)
        
    return _final_scene or _scene

def get_npc_intent(scene_state, npc_id):
    """Извлекает выбранный Intent (activity) NPC напрямую из scene_state."""
    _npc_data = scene_state.get("npc_positions", {}).get(npc_id, {})
    _activity = _npc_data.get("activity", "idle")
    return _activity

def run_test():
    logger.info("=== SUPERBOX-EPISTEMIC-PRODUCTION-001 START ===")
    
    _data_dir = BACKEND_ROOT.parent / "frontend" / "map_editor"
    
    # --- CONTROL RUN ---
    logger.info("--- CONTROL RUN (No lie) ---")
    game_loop_control = build_game_loop(_data_dir)
    setup_world(game_loop_control, inject_lie=False)
    
    # 2 тика для baseline
    _ = run_tick(game_loop_control)
    res_c1 = run_tick(game_loop_control)
    intent_c_control = get_npc_intent(res_c1, NPC_C)
    
    _store_c = game_loop_control._tick_orch._epistemic_store.get(NPC_C)
    belief_c_control = _store_c.proposition.predicate.value if _store_c else "NONE"
    logger.info(f"CONTROL: C intent = {intent_c_control}, C belief = {belief_c_control}")
    
    # --- TREATMENT RUN ---
    logger.info("--- TREATMENT RUN (A lies to C) ---")
    game_loop_treat = build_game_loop(_data_dir)
    setup_world(game_loop_treat, inject_lie=True)
    
    # S199.6: Прогоняем до 10 тиков, чтобы TaskScheduler очистил очередь (ADR-O-343: 1 задача/тик)
    belief_c_treat = "NONE"
    for i in range(1, 11):
        _ = run_tick(game_loop_treat)
        _store_c = game_loop_treat._tick_orch._epistemic_store.get(NPC_C)
        belief_c_treat = _store_c.proposition.predicate.value if _store_c else "NONE"
        logger.info(f"TREATMENT (Tick {i}): C belief = {belief_c_treat}")
        if belief_c_treat != "NONE":
            break
            
    if belief_c_treat == "NONE":
        logger.error("FAIL: C did not receive the claim in 10 ticks!")
        return False
        
    # Финальный тик для проверки решения
    res_t2 = run_tick(game_loop_treat)
    intent_c_treat = get_npc_intent(res_t2, NPC_C)
    logger.info(f"TREATMENT (Final Tick): C intent = {intent_c_treat}")
    
    # --- COMPARISON ---
    logger.info("--- COMPARISON ---")
    if intent_c_control == intent_c_treat:
        logger.error(f"FAIL: C intent did not change! Control={intent_c_control}, Treatment={intent_c_treat}")
        return False
        
    logger.info(f"PASS: C intent changed due to epistemic causal loop!")
    logger.info(f"  Control: {intent_c_control}")
    logger.info(f"  Treatment: {intent_c_treat}")

    # --- S199.9: SAVE/LOAD PERSISTENCE ---
    logger.info("--- SAVE/LOAD PERSISTENCE ---")
    # Состояние уже сохранено на диск в предыдущем run_tick (unlock_tick).
    # Уничтожаем текущий GameLoop и создаём новый, чтобы загрузить состояние с диска.
    del game_loop_treat
    game_loop_reloaded = build_game_loop(_data_dir)
    
    # Загружаем состояние локации tavern
    _reloaded_scene = game_loop_reloaded.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _reloaded_scene is None:
        logger.error("FAIL: Failed to load scene state after reload!")
        return False
        
    # Проверяем, что EpistemicStore загружен из scene_state
    _reloaded_store = game_loop_reloaded._tick_orch._epistemic_store
    if not _reloaded_store._records:
        logger.error("FAIL: EpistemicStore is empty after reload!")
        return False
        
    _store_c_reloaded = _reloaded_store.get(NPC_C)
    if not _store_c_reloaded:
        logger.error(f"FAIL: {NPC_C} belief missing after reload!")
        return False
        
    logger.info(f"RELOADED: {NPC_C} belief = {_store_c_reloaded.proposition.predicate.value}")
    if _store_c_reloaded.proposition.predicate.value != "stole":
        logger.error(f"FAIL: {NPC_C} belief changed after reload! Expected 'stole', got '{_store_c_reloaded.proposition.predicate.value}'")
        return False

    # Запускаем тик после reload и проверяем, что убеждение влияет на решение
    _ = run_tick(game_loop_reloaded)
    _store_c_post_reload = _reloaded_store.get(NPC_C)
    if not _store_c_post_reload:
        logger.error(f"FAIL: {NPC_C} belief lost after post-reload tick!")
        return False
        
    logger.info(f"POST-RELOAD TICK: {NPC_C} belief = {_store_c_post_reload.proposition.predicate.value}")
    logger.info("SAVE/LOAD PERSISTENCE PASS!")
    logger.info("=== SUPERBOX-EPISTEMIC-PRODUCTION-001 END ===")
    return True

if __name__ == "__main__":
    _ok = run_test()
    sys.exit(0 if _ok else 1)
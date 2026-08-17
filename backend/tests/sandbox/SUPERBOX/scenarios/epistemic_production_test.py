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

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_PRODUCTION_001")

logging.getLogger("app.services.game_loop.task_scheduler").setLevel(logging.DEBUG)
logging.getLogger("app.services.execution.dialogue_executor").setLevel(logging.DEBUG)
logging.getLogger("app.services.execution.dialogue_materializer").setLevel(logging.DEBUG)
logging.getLogger("app.services.events.claim_event_subscriber").setLevel(logging.DEBUG)
logging.getLogger("app.services.npc.epistemic_store").setLevel(logging.DEBUG)

from app.services.game_loop_builder import build_game_loop
from app.domain.epistemology import Proposition, Predicate, EpistemicRecord
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"    # Лжец
NPC_B = "merchant_goran"  # Жертва (не участвует активно, но нужен как субъект лжи)
NPC_C = "guard_borko"     # Слушатель, меняющий решение

def setup_world(game_loop, inject_lie: bool):
    """Инициализирует мир и фиксирует всех NPC в одной локации для проверки слуха."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    # S199.6 FIX: Жёстко фиксируем A, B, C в одной точке tavern:main_hall, чтобы они слышали друг друга.
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
    
    # Будим всех NPC и отменяем расписание, чтобы они не разбегались по локациям
    _all_npcs = game_loop._get_life_engine().get_npc_states(CAMPAIGN_ID)
    for _n in _all_npcs:
        _n["routine"] = _n.get("routine", {})
        _n["routine"]["current"] = "idle"
        _n["routine"]["schedule"] = {}
        _n["body_state"] = _n.get("body_state", {})
        _n["body_state"]["sleep_pressure"] = 0.0
        _n["body_state"]["arousal"] = 1.0
        
    if inject_lie:
        # A "знает" (ложно), что B украл X.
        _epistemic_store = game_loop._tick_orch._epistemic_store
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
    """Вызывает production GameLoop.idle_tick() и возвращает обновлённый scene_state."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    _scene["game_time_seconds"] = 22 * 3600
    _scene.setdefault("environment", {})["time_of_day"] = "22:00"
    
    # Вызываем production idle_tick (он тикает все локации, но мы читаем только tavern)
    game_loop.idle_tick(CAMPAIGN_ID, LOCATION_ID)
    
    # Возвращаем актуальный scene_state для tavern
    return game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)

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
    
    # Tick 1: Ничего не должно произойти
    _ = run_tick(game_loop_control)
    # Tick 2: Проверяем базовое поведение C
    res_c1 = run_tick(game_loop_control)
    intent_c_control = get_npc_intent(res_c1, NPC_C)
    
    _store_c = game_loop_control._tick_orch._epistemic_store.get(NPC_C)
    belief_c_control = _store_c.proposition.predicate.value if _store_c else "NONE"
    
    logger.info(f"CONTROL: C intent = {intent_c_control}, C belief = {belief_c_control}")
    
    _store_c = game_loop_control._tick_orch._epistemic_store.get(NPC_C)
    belief_c_control = _store_c.proposition.predicate.value if _store_c else "NONE"
    
    logger.info(f"CONTROL: C intent = {intent_c_control}, C belief = {belief_c_control}")
    
    # --- TREATMENT RUN ---
    logger.info("--- TREATMENT RUN (A lies to C) ---")
    game_loop_treat = build_game_loop(_data_dir)
    setup_world(game_loop_treat, inject_lie=True)
    
    # S199.6: Прогоняем 5 тиков, чтобы TaskScheduler очистил очередь (ADR-O-343: 1 задача/тик)
    belief_c_treat = "NONE"
    for i in range(1, 6):
        _ = run_tick(game_loop_treat)
        _store_c = game_loop_treat._tick_orch._epistemic_store.get(NPC_C)
        belief_c_treat = _store_c.proposition.predicate.value if _store_c else "NONE"
        logger.info(f"TREATMENT (Tick {i}): C belief = {belief_c_treat}")
        if belief_c_treat != "NONE":
            break
            
    if belief_c_treat == "NONE":
        logger.error("FAIL: C did not receive the claim in 5 ticks!")
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
    logger.info("=== SUPERBOX-EPISTEMIC-PRODUCTION-001 END ===")
    return True

if __name__ == "__main__":
    _ok = run_test()
    sys.exit(0 if _ok else 1)
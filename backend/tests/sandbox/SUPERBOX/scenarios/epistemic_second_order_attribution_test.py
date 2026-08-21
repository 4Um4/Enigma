"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/epistemic_second_order_attribution_test.py
Назначение: SUPERBOX-014. Доказательство Second-Order Theory of Mind.
             B верит, что A утверждает P (а не просто перенимает P как истину).
Зависимости: app.services.game_loop_builder, app.services.events.event_bus
Основные сущности: EpistemicStore, ClaimEventSubscriber, NpcConversation, DialogueMaterializer

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_second_order_attribution_test.py
"""
import atexit
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))
_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(_ROOT))

# S198 FIX: Автоматический запуск LLM для теста, чтобы обходить инфраструктурные падения.
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    _llm_ok = start_llama_server()
    if not _llm_ok:
        print("⚠️ Внимание: LLM не запущена. Тест может упасть.")
    atexit.register(kill_llama_server)
except ModuleNotFoundError as e:
    print(f"⚠️ Внимание: Модуль LLM-сервера не найден ({e}). Тест продолжает работу без LLM.")

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_SECOND_ORDER_ATTRIBUTION")
logger.setLevel(logging.INFO)

logging.getLogger("app.services.npc.npc_tick_pipeline").setLevel(logging.DEBUG)
logging.getLogger("app.services.npc.decision_hub").setLevel(logging.DEBUG)
logging.getLogger("app.services.npc.epistemic_context_resolver").setLevel(logging.DEBUG)
logging.getLogger("app.services.phases.post_decision").setLevel(logging.DEBUG)
logging.getLogger("app.services.game_loop.task_scheduler").setLevel(logging.DEBUG)
logging.getLogger("app.services.execution.dialogue_executor").setLevel(logging.DEBUG)
logging.getLogger("app.services.execution.npc_conversation").setLevel(logging.DEBUG)
logging.getLogger("app.services.execution.dialogue_materializer").setLevel(logging.DEBUG)
logging.getLogger("app.services.events.claim_event_subscriber").setLevel(logging.DEBUG)
logging.getLogger("app.services.npc.epistemic_store").setLevel(logging.DEBUG)
logging.getLogger("app.services.npc.belief_revision_engine").setLevel(logging.DEBUG)

from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.services.events.event_bus import get_event_bus
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate, EpistemicRecord
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"
NPC_B = "merchant_goran"
NPC_C = "guard_borko"

def inject_lie(game_loop):
    """Инъецирует ложное убеждение напрямую в EpistemicStore NPC_A (thief_shadow)."""
    from app.services.game_loop.scene_init import ensure_scene_initialized
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    game_loop._current_spatial_query = SpatialQueryService(
        npc_positions=_scene.get("npc_positions", {}), 
        scene_state=_scene
    )
    
    _all_npcs = game_loop._get_life_engine().get_npc_states(CAMPAIGN_ID)
    for _n in _all_npcs:
        if _n.get("npc_id") == NPC_A:
            _n["routine"] = _n.get("routine", {})
            _n["routine"]["current"] = "idle"
            _n["routine"]["schedule"] = {}
            _n["body_state"] = _n.get("body_state", {})
            _n["body_state"]["sleep_pressure"] = 0.0
            _n["body_state"]["arousal"] = 1.0
            
    _mem_mgr = getattr(game_loop._tick_orch, "_memory_manager", None)
    if _mem_mgr:
        _mem_mgr.add_dialogue_turn(
            campaign_id=CAMPAIGN_ID, npc_id=NPC_A, partner_id=NPC_B,
            speaker=NPC_A, text="Я видел, что ты сделал.", target_id=NPC_B,
            intent="talk", tone="serious", tick=1
        )
        _mem_mgr.add_dialogue_turn(
            campaign_id=CAMPAIGN_ID, npc_id=NPC_B, partner_id=NPC_A,
            speaker=NPC_B, text="О чём ты говоришь?", target_id=NPC_A,
            intent="talk", tone="neutral", tick=1
        )
    
    _epistemic_store = game_loop._tick_orch._epistemic_store
    _prop = Proposition(
        subject_id=NPC_B, predicate=Predicate.STOLE, object_id="apple", polarity=True
    )
    _record = EpistemicRecord(
        agent_id=NPC_A, proposition=_prop, confidence=1.0,
        source_id="test_injector", source_claim_id="test_claim_1",
        first_observed_tick=1, last_updated_tick=1
    )
    _epistemic_store.upsert(_record)

def run_tick(game_loop):
    from app.services.game_loop.scene_init import ensure_scene_initialized
    from app.services.spatial.spatial_factory import SpatialFactory
    
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    _scene = game_loop.scene_manager.get_scene_state(CAMPAIGN_ID, LOCATION_ID)
    if _scene is None:
        _scene = game_loop.scene_manager.initialize_scene(CAMPAIGN_ID, LOCATION_ID, "02:00")
        
    _scene["game_time_seconds"] = 22 * 3600
    _scene.setdefault("environment", {})["time_of_day"] = "22:00"
    
    _spatial_svc = SpatialFactory.build_for_campaign(
        campaign_id=CAMPAIGN_ID, location_id=LOCATION_ID, scene_state=_scene
    )
    _all_npcs = game_loop._get_life_engine().get_npc_states(CAMPAIGN_ID)
    
    result = game_loop._tick_orch.execute(
        campaign_id=CAMPAIGN_ID, scene_state=_scene,
        tick_number=_scene.get("tick", 0) + 1, spatial_service=_spatial_svc,
        all_npcs_raw=_all_npcs, active_location_id=LOCATION_ID, location_ids=[LOCATION_ID],
    )
    return result

def execute_scheduler(game_loop, result):
    _scene = getattr(result, "final_scene_state", None) or {}
    game_loop._current_spatial_query = SpatialQueryService(
        npc_positions=_scene.get("npc_positions", {}), scene_state=_scene
    )
    game_loop._task_scheduler.execute_pending(scene_state=_scene, campaign_id=CAMPAIGN_ID)

def test_superbox_014_second_order_attribution():
    logger.info("=== SUPERBOX-014: SECOND-ORDER ATTRIBUTION TEST ===")
    
    logger.info("[1/4] Treatment Run: Injecting lie into NPC_A.")
    game_loop_treat = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_treat) # Прогрев
    inject_lie(game_loop_treat)
    
    logger.info("[2/4] Running tick for Treatment...")
    result_treat = run_tick(game_loop_treat)
    
    logger.info("[3/4] Executing TaskScheduler for Treatment...")
    execute_scheduler(game_loop_treat, result_treat)
    
    # --- VALIDATION ---
    _epistemic_store = game_loop_treat._tick_orch._epistemic_store
    
    rec_A = _epistemic_store.get(NPC_A)
    assert rec_A is not None, "NPC_A must have the injected belief"
    assert rec_A.proposition.subject_id == NPC_B, "NPC_A's belief must be about NPC_B"
    logger.info(f"[VALIDATION] NPC_A belief: {rec_A.proposition.subject_id} {rec_A.proposition.predicate.value}")
    
    import time
    rec_B = None
    for _ in range(20):
        rec_B = _epistemic_store.get(NPC_B)
        if rec_B is not None:
            break
        time.sleep(0.25)
        
    assert rec_B is not None, "NPC_B MUST have the 2nd-order belief!"
    
    # S199: Проверяем, что убеждение B является вторым порядком (B believes A asserts P)
    assert rec_B.proposition.subject_id == NPC_A, "NPC_B's belief must be about NPC_A (the speaker)"
    assert rec_B.proposition.predicate == Predicate.ASSERTS, "NPC_B's belief must be 'asserts'"
    assert rec_B.source_id == NPC_A, "NPC_B's belief source must be NPC_A"
    
    assert "stole" in rec_B.proposition.object_id, "NPC_B's belief must contain the original proposition"
    
    logger.info(f"[VALIDATION] NPC_B 2nd-order belief: {rec_B.proposition.subject_id} {rec_B.proposition.predicate.value} {rec_B.proposition.object_id}")
    
    logger.info("=== SUPERBOX-014: PASS ===")
    logger.info("Second-Order Attribution proven: NPC_B believes NPC_A asserts P.")
    print("\n✅ SUPERBOX-014: PASS — Second-Order Attribution proven.")
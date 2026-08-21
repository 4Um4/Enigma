# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_decision_divergence_test.py
"""
SUPERBOX-010: Расхождение Решений (Decision Divergence).

Тест доказывает, что убеждение агента является причинной переменной поведения, 
а не просто изменением числового score.
Одинаковый мир + разные beliefs → разные выбранные Intent.

Control: C не получает ложь. DecisionHub выбирает базовое действие.
Treatment: C получает ложь (B украл). DecisionHub выбирает другое действие.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_decision_divergence_test.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_DECISION_TEST")
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
    """Публикует ложь в EventBus. Инициализирует SpatialQuery из scene_manager."""
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
            "claim_id": "claim_601",
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

def get_npc_intent_and_scores(tick_result, npc_id):
    """Извлекает выбранный Intent и scores_trace NPC из результатов тика."""
    if getattr(tick_result, "status", "ok") == "error":
        raise RuntimeError(f"TICK_CRASH detected in test: {getattr(tick_result, 'error', 'Unknown error')}")

    if hasattr(tick_result, 'npc_contexts'):
        for ctx in tick_result.npc_contexts:
            if ctx.get("npc_id") == npc_id:
                _decision = ctx.get("decision_result")
                _intent_str = "idle"
                if _decision:
                    _intent = getattr(_decision, "intent", None)
                    if _intent:
                        _intent_str = getattr(_intent, "value", str(_intent))
                
                _scores = ctx.get("scores_trace", {})
                return _intent_str, _scores
    return "idle", {}

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
    print("⚔️ СУПЕРБОКС-010: Расхождение Решений")
    print("="*60)

    # --- CONTROL ---
    print("\n[1/2] Запуск CONTROL (без лжи)...")
    get_event_bus().clear()
    game_loop_c = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_c)
    _ = run_tick(game_loop_c)
    result_c = run_tick(game_loop_c)
    intent_c, scores_c = get_npc_intent_and_scores(result_c, NPC_C)
    print(f"  -> Решение C (Control): {intent_c} (scores: warn={scores_c.get('warn', 0.0):.3f}, flee={scores_c.get('flee', 0.0):.3f})")

    # --- TREATMENT ---
    print("\n[2/2] Запуск TREATMENT (с ложью)...")
    get_event_bus().clear()
    game_loop_t = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_t) # Tick 0
    
    inject_lie(game_loop_t) # Инъекция лжи между тиками
    _ = run_tick(game_loop_t) # Tick 1 (обработка лжи)
    
    # CHECKPOINTS
    store_t = game_loop_t._tick_orch._epistemic_store
    print(f"[CP1] store records: {len(store_t._records)}")
    for key, record in store_t._records.items():
        print(f"[CP2] {key} conf={record.confidence:.2f}")
        
    resolver = EpistemicContextResolver(store_t)
    ctx = resolver.resolve(NPC_C)
    print(f"[CP3] epistemic context: {ctx}")
    
    epistemic_mods = EpistemicContextResolver.to_modifiers(ctx)
    print(f"[CP4] modifiers: {epistemic_mods}")

    result_t = run_tick(game_loop_t) # Tick 2 (проверка решения)
    intent_t, scores_t = get_npc_intent_and_scores(result_t, NPC_C)
    print(f"  -> Решение C (Treatment): {intent_t} (scores: warn={scores_t.get('warn', 0.0):.3f}, flee={scores_t.get('flee', 0.0):.3f})")

    # --- АНАЛИЗ ---
    print("\n--- Анализ Расхождения ---")
    
    if intent_c != intent_t:
        print(f"  ✅ ПРИЧИННОСТЬ ДОКАЗАНА: Intent изменился ({intent_c} -> {intent_t}).")
        print("\n" + "="*60)
        print("🎉 РАСХОЖДЕНИЕ РЕШЕНИЙ ДОКАЗАНО!")
        print("Убеждение напрямую повлияло на выбранный Intent агента.")
        print("="*60)
    else:
        print(f"  ❌ РАЗРЫВ ЦЕПИ: Intent не изменился ({intent_c} -> {intent_t}).")
        raise AssertionError("SUPERBOX-010 FAILED: Decision divergence mismatch")

if __name__ == "__main__":
    run_test()
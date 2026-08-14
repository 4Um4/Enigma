# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_modifier_attribution_test.py
"""
SUPERBOX-005: Эпистемическая атрибуция модификатора.

Тест доказывает математическую атрибуцию: epistemic_modifier аддитивно добавляется к base_score.
Control: base_score (без лжи).
Treatment: final_score (с ложью).
Инвариант: final_score = base_score + epistemic_modifier.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_modifier_attribution_test.py
"""

import logging
import sys
from pathlib import Path
from math import isclose

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_ATTRIBUTION_TEST")
logger.setLevel(logging.INFO)

from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

NPC_A = "thief_shadow"
NPC_B = "merchant_goran"
NPC_C = "guard_borko"

def inject_lie(game_loop):
    event_bus = game_loop._tick_orch._get_event_bus()
    lie_event = EventDTO.create(
        event_type=EventType.COMMUNICATION_CLAIM.value,
        source=NPC_A,
        payload={
            "target_id": NPC_C,
            "claim_id": "claim_201",
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

def get_npc_scores_trace(tick_result, npc_id):
    if getattr(tick_result, "status", "ok") == "error":
        raise RuntimeError(f"TICK_CRASH detected in test: {getattr(tick_result, 'error', 'Unknown error')}")

    if hasattr(tick_result, 'npc_contexts'):
        for ctx in tick_result.npc_contexts:
            if ctx.get("npc_id") == npc_id:
                return ctx.get("scores_trace", {})
    return {}

def run_tick(game_loop):
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
    print("🧮 СУПЕРБОКС-005: Эпистемическая Атрибуция Модификатора")
    print("="*60)

    # --- CONTROL ---
    print("\n[1/2] Запуск CONTROL (без лжи)...")
    game_loop_c = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_c)
    _ = run_tick(game_loop_c)
    result_c = run_tick(game_loop_c)
    scores_c = get_npc_scores_trace(result_c, NPC_C)
    print(f"  -> Scores C (Control): {scores_c}")

    # --- TREATMENT ---
    print("\n[2/2] Запуск TREATMENT (с ложью)...")
    game_loop_t = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_t) # Tick 0
    
    inject_lie(game_loop_t) # Инъекция лжи
    _ = run_tick(game_loop_t) # Tick 1 (обработка)
    
    # Вычисляем ожидаемый epistemic_modifier
    store_t = game_loop_t._tick_orch._epistemic_store
    resolver = EpistemicContextResolver(store_t)
    ctx = resolver.resolve(NPC_C)
    epistemic_mods = EpistemicContextResolver.to_modifiers(ctx)
    print(f"  -> Epistemic Modifiers: {epistemic_mods}")

    result_t = run_tick(game_loop_t) # Tick 2
    scores_t = get_npc_scores_trace(result_t, NPC_C)
    print(f"  -> Scores C (Treatment): {scores_t}")

    # --- АНАЛИЗ АТРИБУЦИИ ---
    print("\n--- Анализ Атрибуции ---")
    
    if not scores_c:
        raise AssertionError("SUPERBOX-005: Control scores_trace is empty")

    all_intents = set(scores_c.keys()).union(set(scores_t.keys()))
    attribution_passed = True
    
    for intent in all_intents:
        if intent not in scores_c:
            print(f"  ❌ {intent}: отсутствует в Control scores_trace")
            attribution_passed = False
            continue
            
        base_score = scores_c.get(intent, 0.0)
        final_score = scores_t.get(intent, 0.0)
        modifier = epistemic_mods.get(intent, 0.0)
        
        expected_final = round(base_score + modifier, 4)
        
        if not isclose(final_score, expected_final, rel_tol=1e-3, abs_tol=1e-3):
            print(f"  ❌ {intent}: base({base_score}) + mod({modifier}) = {expected_final} != final({final_score})")
            attribution_passed = False
        else:
            print(f"  ✅ {intent}: base({base_score}) + mod({modifier}) = {final_score}")
            
    if not attribution_passed:
        raise AssertionError("SUPERBOX-005 FAILED: epistemic modifier attribution mismatch")
        
    print("\n" + "="*60)
    print("🎉 АТРИБУЦИЯ МОДИФИКАТОРА ДОКАЗАНА!")
    print("final_score = base_score + epistemic_modifier для всех интентов.")
    print("="*60)

if __name__ == "__main__":
    run_test()
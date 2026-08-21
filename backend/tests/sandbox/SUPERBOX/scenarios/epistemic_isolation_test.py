# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_isolation_test.py
"""
SUPERBOX-006: Эпистемическая изоляция атрибуции (Attribution Isolation).

Тест доказывает, что Control и Treatment различаются *только* EpistemicContext.
Убеждения не "протекают" в базовую функцию utility (base_score), а добавляются 
исключительно как аддитивный модификатор.

Control: C не получает ложь. EpistemicContext пуст, модификатор = 0.
Treatment: C получает ложь (B украл). EpistemicContext сформирован, модификатор != 0.
Инвариант: treatment_final[i] == control_final[i] + epistemic_modifier[i] для всех интентов.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_isolation_test.py
"""

import logging
import sys
from pathlib import Path
from math import isclose

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_ISOLATION_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
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
    """Публикует ложь в EventBus."""
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
    """Извлекает scores_trace NPC из результатов тика (TickResultDTO)."""
    if getattr(tick_result, "status", "ok") == "error":
        raise RuntimeError(f"TICK_CRASH detected in test: {getattr(tick_result, 'error', 'Unknown error')}")

    if hasattr(tick_result, 'npc_contexts'):
        for ctx in tick_result.npc_contexts:
            if ctx.get("npc_id") == npc_id:
                return ctx.get("scores_trace", {})
    return {}

def run_tick(game_loop):
    """Вызывает TickOrchestrator.execute напрямую для получения TickResultDTO."""
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
    print("🛡️ СУПЕРБОКС-006: Эпистемическая Изоляция Атрибуции")
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
    
    inject_lie(game_loop_t) # Инъекция лжи между тиками
    _ = run_tick(game_loop_t) # Tick 1 (обработка лжи)
    
    # Вычисляем ожидаемый epistemic_modifier
    store_t = game_loop_t._tick_orch._epistemic_store
    resolver = EpistemicContextResolver(store_t)
    ctx = resolver.resolve(NPC_C)
    epistemic_mods = EpistemicContextResolver.to_modifiers(ctx)
    print(f"  -> Epistemic Modifiers: {epistemic_mods}")

    result_t = run_tick(game_loop_t) # Tick 2 (проверка решения)
    scores_t = get_npc_scores_trace(result_t, NPC_C)
    print(f"  -> Scores C (Treatment): {scores_t}")

    # --- АНАЛИЗ ИЗОЛЯЦИИ ---
    print("\n--- Анализ Изоляции ---")
    
    if not scores_c or not scores_t:
        raise AssertionError("SUPERBOX-006: scores_trace пуст в Control или Treatment")

    all_intents = set(scores_c.keys()).union(set(scores_t.keys()))
    isolation_passed = True
    
    for intent in all_intents:
        if intent not in scores_c or intent not in scores_t:
            print(f"  ❌ {intent}: отсутствует в одном из прогонов (C={scores_c.get(intent)}, T={scores_t.get(intent)})")
            isolation_passed = False
            continue
            
        control_final = scores_c[intent]
        treatment_final = scores_t[intent]
        modifier = epistemic_mods.get(intent, 0.0)
        
        expected_treatment = round(control_final + modifier, 4)
        
        if not isclose(treatment_final, expected_treatment, rel_tol=1e-3, abs_tol=1e-3):
            print(f"  ❌ {intent}: T_final({treatment_final}) != C_final({control_final}) + mod({modifier}) = {expected_treatment}")
            isolation_passed = False
        else:
            if modifier == 0.0:
                print(f"  ✅ {intent}: C({control_final}) == T({treatment_final}) [модификатор отсутствует, база идентична]")
            else:
                print(f"  ✅ {intent}: T({treatment_final}) == C({control_final}) + mod({modifier}) [атрибуция изолирована]")
            
    if not isolation_passed:
        raise AssertionError("SUPERBOX-006 FAILED: epistemic isolation mismatch")
        
    print("\n" + "="*60)
    print("🎉 ИЗОЛЯЦИЯ АТРИБУЦИИ ДОКАЗАНА!")
    print("Control и Treatment различаются *только* эпистемическим модификатором.")
    print("Базовая utility (base_score) не подвержена утечке эпистемических данных.")
    print("="*60)

if __name__ == "__main__":
    run_test()
# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_causal_test.py
"""
SUPERBOX-004: Эпистемическая причинность (Belief -> Decision).

Тест доказывает (или опровергает), способно ли ядро ENIGMA в текущем виде
изменить решение NPC на основе субъективного убеждения (EpistemicRecord).

Control: C не получает ложь. DecisionHub выбирает базовое действие.
Treatment: C получает ложь (B украл). EpistemicStore обновляется. DecisionHub должен выбрать враждебное действие.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_causal_test.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_CAUSAL_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.events.claim_event_subscriber import ClaimEventSubscriber

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

def get_npc_decision(tick_result):
    """Извлекает решение NPC_C из результатов тика (TickResultDTO)."""
    # S189 FIX: Тест должен падать при TICK_CRASH, а не возвращать idle.
    if getattr(tick_result, "status", "ok") == "error":
        raise RuntimeError(f"TICK_CRASH detected in test: {getattr(tick_result, 'error', 'Unknown error')}")

    if hasattr(tick_result, 'npc_contexts'):
        for ctx in tick_result.npc_contexts:
            if ctx.get("npc_id") == NPC_C:
                _intent = ctx.get("communication_intent")
                if _intent:
                    _intent_type = getattr(_intent, "intent_type", "idle")
                    # P1 FIX: Нормализация Enum в строку для безопасного сравнения
                    if hasattr(_intent_type, "value"):
                        return _intent_type.value
                    if hasattr(_intent_type, "name"):
                        return _intent_type.name
                    return str(_intent_type)
    return "idle"

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
    print("🧠 СУПЕРБОКС-004: Эпистемическая Причинность")
    print("="*60)

    # --- CONTROL ---
    print("\n[1/2] Запуск CONTROL (без лжи)...")
    game_loop_c = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_c)
    _ = run_tick(game_loop_c)
    result_c = run_tick(game_loop_c)
    decision_c = get_npc_decision(result_c)
    print(f"  -> Решение C (Control): {decision_c}")

    # --- TREATMENT ---
    print("\n[2/2] Запуск TREATMENT (с ложью)...")
    game_loop_t = build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    
    _ = run_tick(game_loop_t) # Tick 0
    
    inject_lie(game_loop_t) # Инъекция лжи между тиками
    _ = run_tick(game_loop_t) # Tick 1 (обработка лжи)
    
    # Проверяем, что убеждение сформировалось
    store_t = game_loop_t._tick_orch._epistemic_store
    belief = store_t.get(NPC_C, Proposition(subject_id=NPC_B, predicate=Predicate.STOLE, object_id="apple"))
    if belief:
        print(f"  -> Убеждение C сформировано: conf={belief.confidence:.2f}")
    else:
        print("  ❌ Убеждение не сформировано!")

    result_t = run_tick(game_loop_t) # Tick 2 (проверка решения)
    decision_t = get_npc_decision(result_t)
    print(f"  -> Решение C (Treatment): {decision_t}")

    # --- АНАЛИЗ ---
    print("\n--- Анализ ---")
    hostile_intents = ["attack", "warn", "threaten", "block_path", "ambush"]
    
    if decision_c != decision_t and decision_t in hostile_intents:
        print(f"  ✅ ПРИЧИННОСТЬ ДОКАЗАНА: Decision изменилось ({decision_c} -> {decision_t}).")
        print("\n" + "="*60)
        print("🎉 ЭПИСТЕМИЧЕСКАЯ ПРИЧИННОСТЬ ПОДТВЕРЖДЕНА!")
        print("Убеждение напрямую повлияло на решение DecisionHub.")
        print("="*60)
    else:
        print(f"  ❌ РАЗРЫВ ЦЕПИ: Decision не изменилось или не стало враждебным ({decision_c} -> {decision_t}).")
        print("\n" + "="*60)
        print("⚠️ ВЫВОД: EpistemicContextResolver не пробросил модификаторы в DecisionHub.")
        print("="*60)

if __name__ == "__main__":
    run_test()
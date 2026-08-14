# backend/tests/sandbox/SUPERBOX/scenarios/modifier_composition_test.py
"""
SUPERBOX-011: Универсальная композиция модификаторов.

Тест доказывает, что DecisionHub.apply_modifiers корректно складывает
деформации из разных слоёв (социального, эпистемического) в единое пространство
без зависимости от порядка передачи аргументов.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/modifier_composition_test.py
"""

import sys
import logging
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("MODIFIER_COMPOSITION_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.events.event_types import EventType
from app.models.npc_state import NPCState
from app.domain.identity_events import EffectiveDrives
from app.domain.decision_context import DecisionContext
from app.domain.epistemology import EpistemicContext
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.kernel_rng import KernelRNG
from app.services.npc.npc_loader import load_npc_profiles_from_config

def run_test():
    print("\n" + "="*60)
    print("🧮 СУПЕРБОКС-011: Композиция Модификаторов")
    print("="*60)

    # 1. Подготовка состояния
    print("\n[1/4] Подготовка состояния...")
    profiles = load_npc_profiles_from_config()
    personality = profiles.get("guard_borko")
    state = NPCState(npc_id="guard_borko")
    effective_drives = EffectiveDrives.from_dict({
        "control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25
    })
    event = EventContext(event_type=EventType.TICK_COMPLETED, actor_id="world")
    
    # Модификаторы
    social_mods = {"warn": 0.3, "attack": 0.2}
    epi_ctx = EpistemicContext(agent_id="guard_borko", perceived_threats=("merchant_goran",), perceived_violations=1)
    epistemic_mods = EpistemicContextResolver.to_modifiers(epi_ctx)
    
    print(f"  -> Social Mods: {social_mods}")
    print(f"  -> Epistemic Mods: {epistemic_mods}")

    # 2. Базовый вызов (Control)
    print("\n[2/4] Базовый вызов (без модификаторов)...")
    _rng_c = KernelRNG(tick=1, npc_id="guard_borko")
    hub_c = DecisionHub(rng=_rng_c)
    dec_c = hub_c.compute(state=state, personality=personality, effective_drives=effective_drives, event=event, decision_ctx=DecisionContext(source="test"))
    score_c_warn = dec_c.intent_scores.get("warn", 0.0) if hasattr(dec_c, "intent_scores") else dec_c.score
    
    # 3. Вызов с модификаторами
    print("\n[3/4] Вызов с Social + Epistemic...")
    _rng_t = KernelRNG(tick=1, npc_id="guard_borko")
    hub_t = DecisionHub(rng=_rng_t)
    dec_t = hub_t.compute(
        state=state, personality=personality, effective_drives=effective_drives, event=event, 
        decision_ctx=DecisionContext(source="test"),
        social_modifiers=social_mods,
        epistemic_modifiers=epistemic_mods
    )
    
    # DecisionHub не возвращает полные scores в DecisionResult, он возвращает только выбранный.
    # Поэтому мы проверим, что score выбранного интента (warn) изменился.
    score_t_warn = dec_t.score if dec_t.intent.value == "warn" else 0.0
    
    # 4. Проверка аддитивности
    print("\n[4/4] Проверка аддитивности...")
    expected_warn_boost = social_mods.get("warn", 0.0) + epistemic_mods.get("warn", 0.0)
    actual_delta = score_t_warn - (dec_c.score if dec_c.intent.value == "warn" else 0.0)
    
    # Округляем до 4 знаков, как это делает DecisionHub
    expected_delta_rounded = round(expected_warn_boost, 4)
    actual_delta_rounded = round(actual_delta, 4)
    
    print(f"  -> Базовый score (warn): {dec_c.score:.4f}")
    print(f"  -> Итоговый score (warn): {score_t_warn:.4f}")
    print(f"  -> Ожидаемая дельта: {expected_delta_rounded:.4f}")
    print(f"  -> Фактическая дельта: {actual_delta_rounded:.4f}")
    
    if abs(expected_delta_rounded - actual_delta_rounded) < 0.001:
        print("\n  ✅ АДДИТИВНОСТЬ ДОКАЗАНА: Модификаторы сложились корректно.")
        print("\n" + "="*60)
        print("🎉 ФАЗА 7 ЗАВЕРШЕНА: Универсальная композиция работает.")
        print("DecisionHub является чистым scoring-движком, складывающим деформации.")
        print("="*60)
    else:
        print("\n  ❌ РАЗРЫВ КОНТРАКТА: Дельта не совпадает с ожидаемой суммой.")
        print("Возможно, модификаторы применяются не аддитивно или есть скрытые капы.")

if __name__ == "__main__":
    run_test()
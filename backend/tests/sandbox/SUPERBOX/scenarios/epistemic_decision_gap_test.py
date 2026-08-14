# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_decision_gap_test.py
"""
SUPERBOX-009: Доказательство RED разрыва EpistemicContext -> DecisionHub.

Тест вызывает DecisionHub.compute() напрямую с двумя вариантами DecisionContext:
1. Control: EpistemicContext отсутствует.
2. Treatment: EpistemicContext содержит perceived_threats.

Ожидаемый результат (RED): DecisionHub вернёт одинаковые решения,
так как он пока не читает поле epistemic_context.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_decision_gap_test.py
"""

import sys
import logging
import dataclasses
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_GAP_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.events.event_types import EventType
from app.models.npc_state import NPCState
from app.domain.identity_events import EffectiveDrives
from app.domain.decision_context import DecisionContext
from app.domain.epistemology import EpistemicContext

def run_test():
    print("\n" + "="*60)
    print("🔌 СУПЕРБОКС-009: Разрыв EpistemicContext -> DecisionHub")
    print("="*60)

    # 1. Подготовка изолированного состояния
    print("\n[1/3] Подготовка состояния агента...")
    
    # Загружаем реальный профиль из конфига
    from app.services.npc.npc_loader import load_npc_profiles_from_config
    profiles = load_npc_profiles_from_config()
    personality = profiles.get("guard_borko")
    if not personality:
        print("❌ Could not load NPC profile for guard_borko")
        return
        
    state = NPCState(npc_id="guard_borko")
    effective_drives = EffectiveDrives.from_dict({
        "control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25
    })
    event = EventContext(event_type=EventType.TICK_COMPLETED, actor_id="world")

    # 2. Вызов DecisionHub (Control)
    print("\n[2/3] Вызов DecisionHub (Control - без EpistemicContext)...")
    
    from app.services.npc.kernel_rng import KernelRNG
    _rng_c = KernelRNG(tick=1, npc_id="guard_borko")
    hub_c = DecisionHub(rng=_rng_c)
    
    ctx_control = DecisionContext(source="test_control")
    
    try:
        decision_c = hub_c.compute(
            state=state,
            personality=personality,
            effective_drives=effective_drives,
            event=event,
            decision_ctx=ctx_control,
            epistemic_modifiers=None # Control: без модификаторов
        )
        print(f"  -> Решение (Control): {decision_c.intent.value} (score: {decision_c.score:.2f})")
    except Exception as e:
        print(f"  ❌ КРАШ при вызове DecisionHub (Control): {e}")
        return

    # 3. Вызов DecisionHub (Treatment)
    print("\n[3/3] Вызов DecisionHub (Treatment - с EpistemicContext)...")
    
    _rng_t = KernelRNG(tick=1, npc_id="guard_borko") # Тот же seed для детерминизма
    hub_t = DecisionHub(rng=_rng_t)
    
    epistemic_ctx = EpistemicContext(
        agent_id="guard_borko",
        perceived_threats=("merchant_goran",),
        perceived_violations=1
    )
    
    # Вычисляем модификаторы через Resolver
    from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
    # Создаем временный пустой store для инициализации resolver, т.к. to_modifiers работает с context
    resolver = EpistemicContextResolver(store=None) 
    epistemic_mods = resolver.to_modifiers(epistemic_ctx)
    
    try:
        decision_t = hub_t.compute(
            state=state,
            personality=personality,
            effective_drives=effective_drives,
            event=event,
            decision_ctx=ctx_control,
            epistemic_modifiers=epistemic_mods # Treatment: с модификаторами
        )
        print(f"  -> Решение (Treatment): {decision_t.intent.value} (score: {decision_t.score:.2f})")
    except Exception as e:
        print(f"  ❌ КРАШ при вызове DecisionHub (Treatment): {e}")
        return

    # 4. Анализ
    print("\n--- Анализ ---")
    hostile_intents = ["attack", "warn", "threaten", "block_path"]
    
    # Проверяем изменение score
    score_c = decision_c.score
    score_t = decision_t.score
    
    if decision_t.intent.value in hostile_intents and decision_t.intent.value != decision_c.intent.value:
        print(f"  ✅ ПРИЧИННОСТЬ ДОКАЗАНА: Decision изменилось ({decision_c.intent.value} -> {decision_t.intent.value}).")
        print("\n" + "="*60)
        print("🎉 ЭПИСТЕМИЧЕСКАЯ ПРИЧИННОСТЬ ПОДТВЕРЖДЕНА!")
        print("DecisionHub отреагировал на EpistemicContext без прямой зависимости от EpistemicStore.")
        print("="*60)
    elif decision_t.intent.value == decision_c.intent.value and score_t > score_c:
        print(f"  ✅ ПРИЧИННОСТЬ ДОКАЗАНА (по Score): Intent остался {decision_c.intent.value}, но score вырос ({score_c:.2f} -> {score_t:.2f}).")
        print("\n" + "="*60)
        print("🎉 ЭПИСТЕМИЧЕСКАЯ ПРИЧИННОСТЬ ПОДТВЕРЖДЕНА (по весу решения)!")
        print("="*60)
    else:
        print(f"  ❌ РАЗРЫВ ПОДТВЕРЖДЁН: DecisionHub проигнорировал EpistemicContext.")
        print(f"     Оба решения: {decision_c.intent.value} (score: {score_c:.2f} vs {score_t:.2f})")
        print("\n" + "="*60)
        print("⚠️ ВЫВОД: DecisionHub не имеет кода для обработки epistemic_context.")
        print("="*60)

if __name__ == "__main__":
    run_test()
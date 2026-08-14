# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_decision_test.py
"""
SUPERBOX-005: Изолированный тест Belief -> Decision.

Доказывает архитектурный разрыв: DecisionHub физически не имеет входа
для чтения EpistemicStore. Даже если агент имеет убеждение, DecisionHub
вернёт одинаковое решение (idle), так как слеп к содержанию убеждений.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_decision_test.py
"""

import sys
import logging
from pathlib import Path
from types import MappingProxyType
import inspect

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_DECISION_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.events.event_types import EventType
from app.models.npc_state import NPCState
from app.models.npc_profile import NPCProfileL0
from app.domain.identity_events import EffectiveDrives
from app.domain.epistemology import Proposition, Predicate, EpistemicRecord
from app.services.npc.epistemic_store import EpistemicStore

def run_test():
    print("\n" + "="*60)
    print("🎯 СУПЕРБОКС-005: Изолированный тест Belief -> Decision")
    print("="*60)

    # 1. Проверка контракта DecisionHub.compute()
    print("\n[1/3] Проверка сигнатуры DecisionHub.compute()...")
    sig = inspect.signature(DecisionHub.compute)
    params = list(sig.parameters.keys())
    
    has_epistemic_input = any("epistemic" in p or "belief" in p for p in params)
    
    if not has_epistemic_input:
        print("  ❌ РАЗРЫВ КОНТРАКТА: В сигнатуре compute() нет параметров для epistemic_state или belief.")
        print(f"  Текущие параметры: {params}")
    else:
        print("  ✅ Контракт принимает epistemic_context.")

    # 2. Подготовка изолированного состояния
    print("\n[2/3] Подготовка изолированного состояния агента...")
    
    # Минимальный Mock NPCState
    state = NPCState(npc_id="guard_borko")
    
    # Загружаем реальный профиль из конфига
    from app.services.npc.npc_loader import load_npc_profiles_from_config
    profiles = load_npc_profiles_from_config()
    personality = profiles.get("guard_borko")
    if not personality:
        print("❌ Could not load NPC profile for guard_borko")
        return
    
    # Минимальный Mock EffectiveDrives
    effective_drives = EffectiveDrives.from_dict({
        "control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25
    })
    
    # Минимальный Mock EventContext
    event = EventContext(
        event_type=EventType.TICK_COMPLETED,
        actor_id="world"
    )
    
    # Эпистемическое состояние (Убеждение, что B украл)
    store = EpistemicStore()
    prop = Proposition(subject_id="merchant_goran", predicate=Predicate.STOLE, object_id="apple")
    record = EpistemicRecord(
        agent_id="guard_borko",
        proposition=prop,
        confidence=0.9,
        source_id="thief_shadow",
        source_claim_id="claim_1",
        first_observed_tick=1,
        last_updated_tick=1
    )
    store.upsert(record)
    print(f"  -> EpistemicStore заполнен: {store.get('guard_borko', prop)}")

    # 3. Вызов DecisionHub
    print("\n[3/3] Вызов DecisionHub.compute() (попытка передать убеждение)...")
    
    from app.services.npc.kernel_rng import KernelRNG
    _rng = KernelRNG(tick=1, npc_id="guard_borko")
    hub = DecisionHub(rng=_rng)
    
    # Поскольку у нас нет epistemic_context, мы вызываем compute как есть.
    # Если бы контекст был, мы бы передали его сюда.
    try:
        decision = hub.compute(
            state=state,
            personality=personality,
            effective_drives=effective_drives,
            event=event
        )
        print(f"  -> Решение DecisionHub: {decision.intent.value} (score: {decision.score:.2f})")
        
        # Мы не можем передать epistemic_context, поэтому решение будет базовым (idle).
        if decision.intent.value == "idle":
            print("\n  ❌ РАЗРЫВ ПРИЧИННОСТИ: DecisionHub вернул 'idle', проигнорировав EpistemicStore.")
            print("\n" + "="*60)
            print("⚠️ ВЫВОД: Требуется EpistemicContextResolver.")
            print("EpistemicStore должен проецироваться в DecisionContext (или social_modifiers),")
            print("чтобы DecisionHub мог реагировать на убеждения.")
            print("="*60)
        else:
            print("\n  ✅ DecisionHub отреагировал (но это случайно, так как контракта нет).")
            
    except Exception as e:
        print(f"\n  ❌ КРАШ при вызове DecisionHub: {e}")
        print("Это доказывает, что DecisionHub требует больше зависимостей, чем мы передали,")
        print("но отсутствие epistemic_input остаётся фактом.")

if __name__ == "__main__":
    run_test()
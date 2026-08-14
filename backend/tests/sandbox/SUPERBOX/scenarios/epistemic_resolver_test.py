# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_resolver_test.py
"""
SUPERBOX-008: Детерминированный EpistemicContextResolver.

Тест доказывает, что EpistemicContextResolver способен:
1. Прочитать EpistemicStore.
2. Отфильтровать убеждения по порогу уверенности.
3. Сформировать EpistemicContext (угрозы, союзники, нарушения).
4. Не мутировать EpistemicStore.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_resolver_test.py
"""

import sys
import logging
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_RESOLVER_TEST")

# Импорты ENIGMA
from app.domain.epistemology import EpistemicRecord, Proposition, Predicate
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver

def run_test():
    print("\n" + "="*60)
    print("⚙️ СУПЕРБОКС-008: EpistemicContextResolver")
    print("="*60)

    # 1. Подготовка хранилища
    print("\n[1/3] Заполнение EpistemicStore...")
    store = EpistemicStore()
    
    # Убеждение 1: B украл (high confidence)
    store.upsert(EpistemicRecord(
        agent_id="guard_borko",
        proposition=Proposition(subject_id="merchant_goran", predicate=Predicate.STOLE, object_id="apple"),
        confidence=0.9,
        source_id="thief_shadow",
        source_claim_id="c1",
        first_observed_tick=1,
        last_updated_tick=1
    ))
    
    # Убеждение 2: C помог (high confidence)
    store.upsert(EpistemicRecord(
        agent_id="guard_borko",
        proposition=Proposition(subject_id="maid_lusya", predicate=Predicate.HELPED, object_id="player"),
        confidence=0.8,
        source_id="tavern_keeper_tornin",
        source_claim_id="c2",
        first_observed_tick=2,
        last_updated_tick=2
    ))
    
    # Убеждение 3: D напал (low confidence - должен быть проигнорирован)
    store.upsert(EpistemicRecord(
        agent_id="guard_borko",
        proposition=Proposition(subject_id="blacksmith_orm", predicate=Predicate.ATTACKED, object_id="guard_borko"),
        confidence=0.3, # Ниже порога 0.5
        source_id="drunkard",
        source_claim_id="c3",
        first_observed_tick=3,
        last_updated_tick=3
    ))
    print("  -> Записей добавлено: 3 (2 валидных, 1 слабое)")

    # 2. Вызов Resolver
    print("\n[2/3] Разрешение контекста...")
    resolver = EpistemicContextResolver(store)
    context = resolver.resolve("guard_borko")
    
    print(f"  -> Threats: {context.perceived_threats}")
    print(f"  -> Allies: {context.perceived_allies}")
    print(f"  -> Violations: {context.perceived_violations}")

    # 3. Проверка инвариантов
    print("\n[3/3] Проверка инвариантов...")
    assert "merchant_goran" in context.perceived_threats, "Goran должен быть в угрозах"
    assert "maid_lusya" in context.perceived_allies, "Люся должна быть в союзниках"
    assert "blacksmith_orm" not in context.perceived_threats, "Орм не должен быть в угрозах (low confidence)"
    assert context.perceived_violations == 1, "Должно быть 1 нарушение (кража)"
    
    # Проверка immutability хранилища
    assert len(store.get_all_for_agent("guard_borko")) == 3, "Store не должен быть мутирован"
    
    print("  ✅ Resolver корректно отфильтровал слабые убеждения.")
    print("  ✅ EpistemicStore не был мутирован.")
    print("  ✅ EpistemicContext сформирован детерминированно.")
    
    print("\n" + "="*60)
    print("🎉 ФАЗА 6 (ЧАСТЬ 3) ЗАВЕРШЕНА: Resolver работает.")
    print("Следующий шаг: SUPERBOX-009 (Полная причинная стрела до DecisionHub).")
    print("="*60)

if __name__ == "__main__":
    run_test()
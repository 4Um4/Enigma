# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_integration_test.py
"""
SUPERBOX-007: Контрактная интеграция EpistemicContext в DecisionContext.

Тест доказывает, что EpistemicContext может быть композиционно встроен
в DecisionContext без нарушения чистоты слоёв.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_integration_test.py
"""

import sys
import logging
import dataclasses
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_INTEGRATION_TEST")

# Импорты ENIGMA
from app.domain.decision_context import DecisionContext
from app.domain.epistemology import EpistemicContext, EpistemicRecord, Proposition

def run_test():
    print("\n" + "="*60)
    print("🔗 СУПЕРБОКС-007: Интеграция EpistemicContext -> DecisionContext")
    print("="*60)

    # 1. Создание базового DecisionContext (как в реальном пайплайне)
    print("\n[1/3] Создание базового DecisionContext...")
    base_context = DecisionContext(source="test")
    print(f"  -> Базовый контекст создан: {base_context.source}")

    # 2. Создание EpistemicContext (субъективная реальность)
    print("\n[2/3] Создание EpistemicContext...")
    epistemic_ctx = EpistemicContext(
        agent_id="guard_borko",
        perceived_threats=("merchant_goran",),
        perceived_violations=1
    )
    print(f"  -> Угрозы: {epistemic_ctx.perceived_threats}")

    # 3. Композиционная инъекция (без мутации)
    print("\n[3/3] Инъекция в DecisionContext (композиция)...")
    # Так как DecisionContext frozen, используем replace
    merged_context = dataclasses.replace(base_context, epistemic_context=epistemic_ctx)
    
    assert merged_context.epistemic_context is not None, "EpistemicContext должен быть внедрён"
    assert merged_context.source == "test", "Базовые поля не должны сломаться"
    
    # Проверка чистоты: EpistemicContext не должен содержать EpistemicRecord
    # Проверяем, что в полях EpistemicContext нет ссылок на сырые записи
    ctx_fields = [f.name for f in dataclasses.fields(merged_context.epistemic_context)]
    assert "records" not in ctx_fields, "EpistemicContext не должен содержать сырые records"
    assert "propositions" not in ctx_fields, "EpistemicContext не должен содержать сырые propositions"
    
    print("  ✅ EpistemicContext успешно встроен в DecisionContext.")
    print("  ✅ Базовые поля DecisionContext сохранены.")
    print("  ✅ EpistemicContext не содержит сырых EpistemicRecord (инкапсуляция соблюдена).")
    
    print("\n" + "="*60)
    print("🎉 ФАЗА 6 (ЧАСТЬ 2) ЗАВЕРШЕНА: Контракт интеграции доказан.")
    print("DecisionHub теперь может читать merged_context.epistemic_context.perceived_threats")
    print("без знания о существовании EpistemicStore или Proposition.")
    print("Следующий шаг: SUPERBOX-008 (Полная причинная стрела).")
    print("="*60)

if __name__ == "__main__":
    run_test()
# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_context_test.py
"""
SUPERBOX-006: Контракт EpistemicContext.

Тест доказывает, что мы можем создать минимальный семантический объект
(EpistemicContext), который переводит сырые убеждения (EpistemicRecord)
в decision-relevant состояние (угрозы, нарушения) без прямой зависимости
от DecisionHub или GameLoop.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_context_test.py
"""

import sys
import logging
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_CONTEXT_TEST")

# Импорты ENIGMA
from app.domain.epistemology import (
    EpistemicRecord, Proposition, Predicate, EpistemicContext
)

def project_beliefs_to_context(agent_id: str, beliefs: list) -> EpistemicContext:
    """
    Временная функция-проектор (будущий EpistemicContextResolver).
    Преобразует список EpistemicRecord в EpistemicContext.
    """
    threats = []
    allies = []
    violations = 0

    for record in beliefs:
        # Фильтруем по уверености (например, > 0.5)
        if record.confidence < 0.5:
            continue
            
        if record.proposition.predicate in [Predicate.STOLE, Predicate.ATTACKED]:
            threats.append(record.proposition.subject_id)
            violations += 1
        elif record.proposition.predicate == Predicate.HELPED:
            allies.append(record.proposition.subject_id)

    return EpistemicContext(
        agent_id=agent_id,
        perceived_threats=tuple(threats),
        perceived_allies=tuple(allies),
        perceived_violations=violations
    )

def run_test():
    print("\n" + "="*60)
    print("🧩 СУПЕРБОКС-006: Контракт EpistemicContext")
    print("="*60)

    # 1. Подготовка убеждений
    print("\n[1/2] Формирование сырых убеждений (EpistemicRecord)...")
    beliefs = [
        EpistemicRecord(
            agent_id="guard_borko",
            proposition=Proposition(subject_id="merchant_goran", predicate=Predicate.STOLE, object_id="apple"),
            confidence=0.9,
            source_id="thief_shadow",
            source_claim_id="claim_1",
            first_observed_tick=1,
            last_updated_tick=1
        ),
        EpistemicRecord(
            agent_id="guard_borko",
            proposition=Proposition(subject_id="maid_lusya", predicate=Predicate.HELPED, object_id="player"),
            confidence=0.8,
            source_id="tavern_keeper_tornin",
            source_claim_id="claim_2",
            first_observed_tick=2,
            last_updated_tick=2
        )
    ]
    print(f"  -> Убеждений сформировано: {len(beliefs)}")

    # 2. Проекция в EpistemicContext
    print("\n[2/2] Проекция в EpistemicContext...")
    context = project_beliefs_to_context("guard_borko", beliefs)
    
    print(f"  -> Agent: {context.agent_id}")
    print(f"  -> Perceived Threats: {context.perceived_threats}")
    print(f"  -> Perceived Allies: {context.perceived_allies}")
    print(f"  -> Perceived Violations: {context.perceived_violations}")

    # 3. Проверка контракта
    assert "merchant_goran" in context.perceived_threats, "Goran должен быть в угрозах"
    assert "maid_lusya" in context.perceived_allies, "Люся должна быть в союзниках"
    assert context.perceived_violations == 1, "Должно быть 1 нарушение (кража)"
    
    print("\n  ✅ КОНТРАКТ ДОКАЗАН: EpistemicContext успешно абстрагирует убеждения.")
    print("  DecisionHub сможет читать perceived_threats, не зная о Proposition/EpistemicStore.")
    print("\n" + "="*60)
    print("🎉 ФАЗА 6 (ЧАСТЬ 1) ЗАВЕРШЕНА: Контракт EpistemicContext готов.")
    print("Следующий шаг: Интеграция EpistemicContext в DecisionContext (SUPERBOX-007).")
    print("="*60)

if __name__ == "__main__":
    run_test()
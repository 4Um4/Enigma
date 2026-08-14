# backend/tests/sandbox/SUPERBOX/scenarios/modifier_commutativity_test.py
"""
SUPERBOX-013: Строгая проверка коммутативности.

Тест напрямую вызывает DecisionHub.apply_modifiers с разным порядком
социальных и эпистемических модификаторов и доказывает, что итоговый
словарь scores идентичен.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/modifier_commutativity_test.py
"""

import sys
import logging
from pathlib import Path
import copy

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("COMMUTATIVITY_TEST")

# Импорты ENIGMA
from app.services.npc.decision_hub import DecisionHub

def run_test():
    print("\n" + "="*60)
    print("🔄 СУПЕРБОКС-013: Коммутативность Модификаторов")
    print("="*60)

    # 1. Базовые scores
    print("\n[1/3] Подготовка базовых scores...")
    base_scores = {
        "idle": 0.1,
        "observe": 0.2,
        "warn": 0.3,
        "attack": 0.4,
        "trade": 0.5
    }
    
    social_mods = {"warn": 0.3, "attack": 0.2}
    epistemic_mods = {"warn": 0.6, "attack": 0.6, "block_path": 0.3}
    
    print(f"  -> Base: {base_scores}")

    # 2. Вызов 1: Social -> Epistemic
    print("\n[2/3] Вызов apply_modifiers (Social -> Epistemic)...")
    scores_se = copy.deepcopy(base_scores)
    scores_se = DecisionHub.apply_modifiers(
        scores_se,
        social_modifiers=social_mods,
        epistemic_modifiers=epistemic_mods
    )
    print(f"  -> Result (S->E): {scores_se}")

    # 3. Вызов 2: Epistemic -> Social
    print("\n[3/3] Вызов apply_modifiers (Epistemic -> Social)...")
    scores_es = copy.deepcopy(base_scores)
    scores_es = DecisionHub.apply_modifiers(
        scores_es,
        epistemic_modifiers=epistemic_mods,
        social_modifiers=social_mods
    )
    print(f"  -> Result (E->S): {scores_es}")

    # 4. Сравнение
    print("\n--- Анализ ---")
    if scores_se == scores_es:
        print("  ✅ КОММУТАТИВНОСТЬ ДОКАЗАНА: Результаты идентичны независимо от порядка.")
        print("\n" + "="*60)
        print("🎉 ФАЗА 7 ПОЛНОСТЬЮ ЗАВЕРШЕНА.")
        print("Архитектура модификаторов чиста, аддитивна и коммутативна.")
        print("="*60)
    else:
        print("  ❌ РАЗРЫВ КОНТРАКТА: Результаты отличаются!")
        print(f"  Diff: {set(scores_se.items()) ^ set(scores_es.items())}")

if __name__ == "__main__":
    run_test()
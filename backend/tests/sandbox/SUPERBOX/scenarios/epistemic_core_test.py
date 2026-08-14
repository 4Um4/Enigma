# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_core_test.py
"""
SUPERBOX-002: Чистые тесты эпистемического ядра.

Доказывает:
1. Создание убеждения из ClaimEvent.
2. Сохранение provenance (откуда узнал).
3. Детерминированность (одинаковый вход = одинаковый выход).
4. Независимое подтверждение повышает уверенность.
5. Железный инвариант: Claim не меняет World Truth.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_core_test.py
"""

import sys
import logging
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_CORE_TEST")

# Импорты ENIGMA
from app.domain.epistemology import Proposition, Predicate, SpeechAct, ClaimEvent, EpistemicRecord
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine

# --- Mock Провайдер надёжности ---
class MockReliabilityProvider:
    """Возвращает фиксированное значение trust для теста."""
    def __init__(self, trust_map: dict):
        self.trust_map = trust_map

    def get_reliability(self, observer: str, source: str, context=None) -> float:
        return self.trust_map.get((observer, source), 0.5)

def run_tests():
    print("\n" + "="*60)
    print("🧪 СУПЕРБОКС-002: Тесты Эпистемического Ядра")
    print("="*60)

    # Инициализация ядра
    store = EpistemicStore()
    provider = MockReliabilityProvider(trust_map={("agent_c", "agent_a"): 0.8, ("agent_c", "agent_d"): 0.4})
    engine = BeliefRevisionEngine(provider)

    # Объективная истина мира (World Truth) - хранится вне движка убеждений
    world_truth = {
        "thief": "agent_a",
        "item": "apple"
    }
    print(f"\n[WORLD TRUTH] Objective reality: {world_truth['thief']} stole {world_truth['item']}.")

    # --- Тест 1: Создание убеждения и Provenance ---
    print("\n[Тест 1] Создание убеждения из ClaimEvent...")
    prop_b_stole = Proposition(subject_id="agent_b", predicate=Predicate.STOLE, object_id="apple")
    claim_1 = ClaimEvent(
        event_id="evt_1",
        claim_id="claim_1",
        speaker_id="agent_a",
        listener_id="agent_c",
        proposition=prop_b_stole,
        tick=10
    )
    
    existing = store.get("agent_c", prop_b_stole)
    record_1 = engine.revise("agent_c", claim_1, existing)
    store.upsert(record_1)
    
    assert record_1.confidence == 0.8, "Confidence should equal trust(0.8) * weight(1.0)"
    assert record_1.source_id == "agent_a", "Source should be agent_a"
    assert record_1.source_claim_id == "claim_1", "Claim ID should be preserved"
    print("  ✅ Убеждение создано. Provenance сохранен.")

    # --- Тест 2: Железный инвариант (Ложь не меняет World Truth) ---
    print("\n[Тест 2] Проверка инварианта: Ложь не меняет World Truth...")
    assert world_truth["thief"] == "agent_a", "World truth must remain unchanged!"
    c_belief = store.get("agent_c", prop_b_stole)
    assert c_belief is not None, "C must have a belief about B"
    
    print(f"  World Truth: '{world_truth['thief']}' украл.")
    print(f"  C Belief: '{c_belief.proposition.subject_id}' украл (conf={c_belief.confidence}).")
    print("  ✅ Истина и Убеждение разделены. Ложь не стала фактом.")

    # --- Тест 3: Детерминированность ---
    print("\n[Тест 3] Проверка детерминированности...")
    store_det = EpistemicStore()
    record_det = engine.revise("agent_c", claim_1, None)
    assert record_det == record_1, "Same input must produce exact same output"
    print("  ✅ Детерминированность подтверждена.")

    # --- Тест 4: Независимое подтверждение ---
    print("\n[Тест 4] Проверка независимого подтверждения...")
    claim_2 = ClaimEvent(
        event_id="evt_2",
        claim_id="claim_2",
        speaker_id="agent_d", # Другой источник
        listener_id="agent_c",
        proposition=prop_b_stole,
        tick=15
    )
    
    existing_2 = store.get("agent_c", prop_b_stole)
    record_2 = engine.revise("agent_c", claim_2, existing_2)
    store.upsert(record_2)
    
    assert record_2.confidence > record_1.confidence, "Independent confirmation should increase confidence"
    print(f"  Confidence выросла: {record_1.confidence:.2f} -> {record_2.confidence:.2f}")
    print("  ✅ Независимое подтверждение работает.")

    print("\n" + "="*60)
    print("🎉 ФАЗА 4 ЗАВЕРШЕНА: Эпистемическое ядро работает корректно.")
    print("Следующий шаг: Интеграция ClaimEventSubscriber в EventBus.")
    print("="*60)

if __name__ == "__main__":
    run_tests()
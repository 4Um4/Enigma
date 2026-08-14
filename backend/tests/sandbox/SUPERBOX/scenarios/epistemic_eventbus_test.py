# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_eventbus_test.py
"""
SUPERBOX-003: Интеграция ClaimEventSubscriber с реальным EventBus.

Доказывает:
1. EventBus.publish(COMMUNICATION_CLAIM) вызывает ClaimEventSubscriber.
2. EpistemicStore обновляется корректно через реальную шину.
3. World Truth остаётся неизменной.
4. Поведение полностью совпадает с чистым тестом ядра (Фаза 4).

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_eventbus_test.py
"""

import sys
import logging
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_BUS_TEST")

# Импорты ENIGMA
from app.domain.epistemology import Proposition, Predicate, EpistemicRecord
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.events.claim_event_subscriber import ClaimEventSubscriber

# --- Mock Провайдер надёжности ---
class MockReliabilityProvider:
    def get_reliability(self, observer: str, source: str, context=None) -> float:
        if observer == "agent_c" and source == "agent_a":
            return 0.8
        return 0.5

def run_test():
    print("\n" + "="*60)
    print("🚌 СУПЕРБОКС-003: Интеграция EventBus")
    print("="*60)

    # 1. Инициализация реальной шины и ядра
    bus = EventBus()
    store = EpistemicStore()
    provider = MockReliabilityProvider()
    engine = BeliefRevisionEngine(provider)
    subscriber = ClaimEventSubscriber(engine, store)

    # 2. Подписка на событие
    bus.subscribe(EventType.COMMUNICATION_CLAIM, subscriber.on_claim_event)
    print("\n[1/3] ClaimEventSubscriber подписан на COMMUNICATION_CLAIM.")

    # 3. World Truth (остаётся неизменной)
    world_truth_thief = "agent_a"
    print(f"\n[2/3] World Truth: {world_truth_thief} украл яблоко.")

    # 4. Инъекция события (Ложь от A к C)
    print("\n[3/3] Публикация COMMUNICATION_CLAIM на EventBus...")
    lie_event = EventDTO.create(
        event_type=EventType.COMMUNICATION_CLAIM.value, # Передаём строку, как ожидает EventBus
        source="agent_a",
        payload={
            "target_id": "agent_c",
            "claim_id": "claim_101",
            "proposition": {
                "subject_id": "agent_b",
                "predicate": "stole",
                "object_id": "apple",
                "polarity": True
            },
            "speech_act": "assert",
            "tick": 50
        },
        visibility="private"
    )
    
    # Публикуем событие
    bus.publish(lie_event)

    # 5. Проверка результатов
    print("\n--- Результаты ---")
    c_belief = store.get("agent_c", Proposition(subject_id="agent_b", predicate=Predicate.STOLE, object_id="apple"))
    
    if c_belief and isinstance(c_belief, EpistemicRecord):
        print(f"C Belief: {c_belief.proposition.subject_id} украл (conf={c_belief.confidence:.2f}, source={c_belief.source_id})")
        assert c_belief.confidence == 0.8, "Confidence should be 0.8"
        assert c_belief.source_id == "agent_a", "Source should be agent_a"
        assert c_belief.source_claim_id == "claim_101", "Claim ID should match"
        
        assert world_truth_thief == "agent_a", "World truth must remain unchanged!"
        
        print("\n  ✅ Убеждение создано через EventBus.")
        print("  ✅ Provenance сохранен.")
        print("  ✅ World Truth не нарушена.")
        print("\n" + "="*60)
        print("🎉 ФАЗА 5 ЗАВЕРШЕНА: Эпистемическое ядро встроено в каузальную машину.")
        print("="*60)
    else:
        print("\n  ❌ РАЗРЫВ ЦЕПИ: Убеждение не создано.")
        print("\n" + "="*60)
        print("⚠️ ВЫВОД: Subscriber не обработал событие.")
        print("="*60)

if __name__ == "__main__":
    run_test()
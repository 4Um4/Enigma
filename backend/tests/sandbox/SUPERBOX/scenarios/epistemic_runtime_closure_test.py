"""
SUPERBOX-015: Runtime Epistemic Closure for Player.

Тест доказывает, что реальный рантайм (DialogueMaterializer -> EventBus -> ClaimEventSubscriber) 
замыкает эпистемическую петлю для игрока без ручных вызовов подписчиков.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_runtime_closure_test.py
"""

import logging
import sys
import time
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_RUNTIME_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.domain.events import EventDTO
from app.domain.execution import Artifact
from app.domain.epistemology import Predicate
from app.services.events.event_types import EventType
from app.services.events.event_bus import get_event_bus
from app.services.events.claim_event_subscriber import ClaimEventSubscriber, RelationshipReliabilityProvider
from app.services.memory.relationship_store import RelationshipStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN_ID = "Open_road"
NPC_A = "guard_borko"
NPC_B = "thief_shadow"

def run_test():
    print("\n" + "="*60)
    print("SUPERBOX-015: Runtime Epistemic Closure for Player")
    print("="*60)

    # 1. Инициализация изолированных сервисов
    rel_store = RelationshipStore(data_dir=str(BACKEND_ROOT.parent / "saves" / "test_sandbox"))
    rel_store.update(CAMPAIGN_ID, "player", NPC_A, {"trust": 80.0})  # NPC_A - друг
    
    reliability_provider = RelationshipReliabilityProvider(rel_store, CAMPAIGN_ID)
    engine = BeliefRevisionEngine(reliability_provider=reliability_provider)
    store = EpistemicStore()
    
    mock_positions = {
        "player": {"local_position": {"x": 0.0, "y": 0.0}},
        NPC_A: {"local_position": {"x": 1.0, "y": 1.0}},
    }
    spatial_query = SpatialQueryService(npc_positions=mock_positions)
    
    subscriber = ClaimEventSubscriber(
        engine=engine, 
        store=store, 
        spatial_query_provider=lambda: spatial_query
    )

    # 2. Регистрация подписчика на EventBus (РЕАЛЬНЫЙ РАНТАЙМ)
    bus = get_event_bus()
    bus.clear()
    bus.subscribe(EventType.NPC_SPOKE, subscriber.on_npc_spoke)
    bus.subscribe(EventType.COMMUNICATION_CLAIM, subscriber.on_claim_event)

    # 3. Публикация Artifact (как это сделал бы TaskScheduler)
    print("\n[1/1] Публикация Artifact (accuse) через DialogueMaterializer...")
    from app.services.execution.dialogue_materializer import DialogueMaterializer
    materializer = DialogueMaterializer()
    
    artifact = Artifact(
        task_id="test_task_1",
        result_type="dialogue_line",
        success=True,
        data={
            "speaker_id": NPC_A,
            "target_id": NPC_B,
            "text": "Тень украл яблоко!",
            "intent_type": "accuse"
        }
    )
    
    events = materializer.materialize(artifact)
    for ev in events:
        bus.publish(ev)

    # 4. Анализ результатов
    print("\n--- Анализ EpistemicStore ---")
    player_beliefs = store.get_all_for_agent("player")
    print(f"  Найдено убеждений игрока: {len(player_beliefs)}")

    if len(player_beliefs) != 1:
        print("  ❌ ОШИБКА: Ожидалось 1 убеждение (от друга).")
        raise AssertionError("SUPERBOX-015 FAILED: Incorrect number of player beliefs")

    belief_from_friend = player_beliefs[0]

    if belief_from_friend:
        print(f"  Убеждение от друга (NPC_A): confidence={belief_from_friend.confidence:.2f}")
        if belief_from_friend.confidence > 0.5:
            print("  ✅ Runtime труба работает: DialogueMaterializer -> EventBus -> EpistemicStore[player].")
        else:
            print("  ❌ ОШИБКА: Confidence от друга слишком низкое!")
            raise AssertionError("SUPERBOX-015 FAILED: Low confidence")
    else:
        print("  ❌ ОШИБКА: Убеждение от друга не найдено!")
        raise AssertionError("SUPERBOX-015 FAILED: Belief not found")

    print("\n" + "="*60)
    print("🎉 RUNTIME ЭПИСТЕМИЧЕСКОЕ ЗАМЫКАНИЕ ДОКАЗАНО!")
    print("Реальная каузальная труба диалогов обновляет убеждения игрока.")
    print("="*60)

if __name__ == "__main__":
    run_test()
"""
SUPERBOX-016: Runtime TaskScheduler Epistemic Closure.

Тест доказывает, что полная рантайм-труба (TaskScheduler -> DialogueExecutor -> DialogueMaterializer -> EventBus -> ClaimEventSubscriber) 
замыкает эпистемическую петлю для игрока без ручных вызовов materializer.publish().

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_scheduler_closure_test.py
"""

import logging
import sys
import time
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_SCHEDULER_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.domain.events import EventDTO
from app.domain.execution import QueuedTask, TaskState
from app.domain.communication import DialogueRequest, ExposureLevel
from app.domain.epistemology import Predicate
from app.services.events.event_types import EventType
from app.services.events.event_bus import get_event_bus
from app.services.events.claim_event_subscriber import ClaimEventSubscriber, RelationshipReliabilityProvider
from app.services.memory.relationship_store import RelationshipStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore
from app.services.spatial.spatial_query_service import SpatialQueryService
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.game_loop.task_scheduler import TaskScheduler

CAMPAIGN_ID = "Open_road"
NPC_A = "guard_borko"
NPC_B = "thief_shadow"

def run_test():
    print("\n" + "="*60)
    print("SUPERBOX-016: Runtime TaskScheduler Epistemic Closure")
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

    # 2. Регистрация подписчика на EventBus
    bus = get_event_bus()
    bus.clear()
    bus.subscribe(EventType.NPC_SPOKE, subscriber.on_npc_spoke)
    bus.subscribe(EventType.COMMUNICATION_CLAIM, subscriber.on_claim_event)

    # 3. Инициализация TaskScheduler с реальными Executor и Materializer
    # Передаём router=None, чтобы сработал детерминированный fallback без LLM
    executor = DialogueExecutor(router=None)
    materializer = DialogueMaterializer()
    
    scheduler = TaskScheduler(
        memory_manager=None, 
        economy_tracker=None
    )
    scheduler._executors = {"dialogue": executor}
    scheduler._materializers = {"dialogue_line": materializer}

    # 4. Создание QueuedTask с intent_type="accuse"
    print("\n[1/1] Создание QueuedTask (intent=accuse) и запуск TaskScheduler...")
    req = DialogueRequest(
        target_id=NPC_B,
        topic="кража",
        intent_type="accuse",
        emotional_state="angry",
        exposure=ExposureLevel.from_semantic("normal")
    )
    task = QueuedTask(
        task_id="test_task_1",
        kind="dialogue",
        owner_id=NPC_A,
        payload=req,
        tick=1
    )

    # Подготавливаем scene_state для TaskScheduler
    scene_state = {
        "campaign_id": CAMPAIGN_ID,
        "tick": 1,
        "game_time_seconds": 10.0,
        "pending_tasks": [task.__dict__], # TaskScheduler ожидает список словарей
        "npc_positions": mock_positions
    }

    # Вызываем execute_pending, который запустит асинхронную обработку
    scheduler.execute_pending(scene_state, CAMPAIGN_ID)

    # Ждём завершения асинхронной задачи (pool.submit)
    # В реальном рантайме это происходит за 1-2 тика
    time.sleep(0.5)

    # 5. Анализ результатов
    print("\n--- Анализ EpistemicStore ---")
    player_beliefs = store.get_all_for_agent("player")
    print(f"  Найдено убеждений игрока: {len(player_beliefs)}")

    if len(player_beliefs) != 1:
        print("  ❌ ОШИБКА: Ожидалось 1 убеждение (от друга).")
        raise AssertionError("SUPERBOX-016 FAILED: Incorrect number of player beliefs")

    belief_from_friend = player_beliefs[0]

    if belief_from_friend:
        print(f"  Убеждение от друга (NPC_A): confidence={belief_from_friend.confidence:.2f}")
        if belief_from_friend.confidence > 0.5:
            print("  ✅ Runtime труба работает: TaskScheduler -> Executor -> Materializer -> EventBus -> EpistemicStore[player].")
        else:
            print("  ❌ ОШИБКА: Confidence от друга слишком низкое!")
            raise AssertionError("SUPERBOX-016 FAILED: Low confidence")
    else:
        print("  ❌ ОШИБКА: Убеждение от друга не найдено!")
        raise AssertionError("SUPERBOX-016 FAILED: Belief not found")

    print("\n" + "="*60)
    print("🎉 RUNTIME TASKSCHEDULER ЭПИСТЕМИЧЕСКОЕ ЗАМЫКАНИЕ ДОКАЗАНО!")
    print("Полная каузальная труба от Intent до EpistemicStore работает без ручных вызовов.")
    print("="*60)

if __name__ == "__main__":
    run_test()
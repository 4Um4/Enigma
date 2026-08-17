"""
SUPERBOX-014: Эпистемическое замыкание для игрока (Player Epistemic Closure).

Тест доказывает, что реплики NPC (NPC_SPOKE) порождают убеждения (EpistemicRecord) 
в EpistemicStore игрока, и что confidence зависит от доверия (trust) игрока к говорящему.

Control: NPC_A (друг, trust=80) обвиняет (accuse) NPC_B -> confidence > 0.5
Treatment: NPC_B (враг, trust=-50) обвиняет (accuse) NPC_A -> confidence == 0.0 (из-за max(0.0, ...))

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_player_belief_test.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_PLAYER_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.domain.events import EventDTO
from app.domain.epistemology import Predicate
from app.services.events.event_types import EventType
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
    print("SUPERBOX-014: Эпистемическое замыкание для игрока")
    print("="*60)

    # 1. Инициализация изолированных сервисов
    rel_store = RelationshipStore(data_dir=str(BACKEND_ROOT.parent / "saves" / "test_sandbox"))
    
    # Устанавливаем отношения игрока к NPC
    rel_store.update(CAMPAIGN_ID, "player", NPC_A, {"trust": 80.0})  # NPC_A - друг
    rel_store.update(CAMPAIGN_ID, "player", NPC_B, {"trust": -50.0}) # NPC_B - враг
    
    reliability_provider = RelationshipReliabilityProvider(rel_store, CAMPAIGN_ID)
    engine = BeliefRevisionEngine(reliability_provider=reliability_provider)
    store = EpistemicStore()
    
    # Мокаем SpatialQueryService: игрок и оба NPC в радиусе 10.0
    mock_positions = {
        "player": {"local_position": {"x": 0.0, "y": 0.0}},
        NPC_A: {"local_position": {"x": 1.0, "y": 1.0}},
        NPC_B: {"local_position": {"x": 2.0, "y": 2.0}},
    }
    spatial_query = SpatialQueryService(npc_positions=mock_positions)
    
    subscriber = ClaimEventSubscriber(
        engine=engine, 
        store=store, 
        spatial_query_provider=lambda: spatial_query
    )

    # 2. Публикуем NPC_SPOKE от друга (NPC_A) с intent_type="accuse"
    print("\n[1/2] Обработка реплики от друга (NPC_A, trust=80)...")
    event_friend = EventDTO.create(
        event_type=EventType.NPC_SPOKE.value,
        source=NPC_A,
        payload={
            "target_id": NPC_B,
            "text": "Тень украл яблоко!",
            "intent_type": "accuse"
        }
    )
    subscriber.on_npc_spoke(event_friend)

    # 3. Публикуем NPC_SPOKE от врага (NPC_B) с intent_type="accuse"
    print("\n[2/2] Обработка реплики от врага (NPC_B, trust=-50)...")
    event_enemy = EventDTO.create(
        event_type=EventType.NPC_SPOKE.value,
        source=NPC_B,
        payload={
            "target_id": NPC_A,
            "text": "Стражник украл золото!",
            "intent_type": "accuse"
        }
    )
    subscriber.on_npc_spoke(event_enemy)

    # 4. Анализ результатов
    print("\n--- Анализ EpistemicStore ---")
    player_beliefs = store.get_all_for_agent("player")
    print(f"  Найдено убеждений игрока: {len(player_beliefs)}")

    if len(player_beliefs) != 2:
        print("  ❌ ОШИБКА: Ожидалось 2 убеждения (от друга и от врага).")
        raise AssertionError("SUPERBOX-014 FAILED: Incorrect number of player beliefs")

    # Проверяем confidence
    belief_from_friend = next((b for b in player_beliefs if b.source_id == NPC_A), None)
    belief_from_enemy = next((b for b in player_beliefs if b.source_id == NPC_B), None)

    success = True

    if belief_from_friend:
        print(f"  Убеждение от друга (NPC_A): confidence={belief_from_friend.confidence:.2f}")
        # NPC_A друг (trust=80 -> reliability=0.8). Confidence должна быть 0.8.
        if belief_from_friend.confidence > 0.5:
            print("  ✅ Доверие к другу корректно повышает confidence.")
        else:
            print("  ❌ ОШИБКА: Confidence от друга слишком низкое!")
            success = False
    else:
        print("  ❌ ОШИБКА: Убеждение от друга не найдено!")
        success = False

    if belief_from_enemy:
        print(f"  Убеждение от врага (NPC_B): confidence={belief_from_enemy.confidence:.2f}")
        # NPC_B враг (trust=-50 -> reliability=-0.5). 
        # incoming_confidence = -0.5. Обновление: max(0.0, 0.0 + (-0.5 * 0.2)) = 0.0
        if belief_from_enemy.confidence == 0.0:
            print("  ✅ Недоверие к врагу корректно обнуляет confidence (защита от ухода в минус).")
        else:
            print("  ❌ ОШИБКА: Confidence от врага не равно 0.0!")
            success = False
    else:
        print("  ❌ ОШИБКА: Убеждение от врага не найдено!")
        success = False

    # Проверяем сериализацию (to_dict)
    print("\n--- Проверка сериализации (to_dict) ---")
    serialized = store.to_dict()
    player_serialized = [s for s in serialized if s.get("agent_id") == "player"]
    print(f"  Сериализованных убеждений игрока: {len(player_serialized)}")
    if len(player_serialized) == 2:
        print("  ✅ Сериализация работает корректно.")
    else:
        print("  ❌ ОШИБКА: Сериализация не вернула ожидаемое количество убеждений!")
        success = False

    print("\n" + "="*60)
    if success:
        print("🎉 ЭПИСТЕМИЧЕСКОЕ ЗАМЫКАНИЕ ДЛЯ ИГРОКА ДОКАЗАНО!")
        print("Игрок слышит реплики NPC и формирует убеждения в зависимости от доверия.")
        print("="*60)
    else:
        print("❌ ТЕСТ ЗАВЕРШЁН С ОШИБКАМИ.")
        print("="*60)
        raise AssertionError("SUPERBOX-014 FAILED: Epistemic closure test failed")

if __name__ == "__main__":
    run_test()
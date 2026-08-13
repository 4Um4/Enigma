# backend/tests/sandbox/SUPERBOX/scenarios/epistemic_divergence.py
"""
SUPERBOX-EPISTEMIC-001: Три Агента / Двойная Истина.

Тест доказывает (или опровергает), способна ли существующая архитектура ENIGMA
породить эпистемическое расхождение без новых когнитивных слоёв.

Сценарий:
1. Мир: Трое NPC (agent_a, agent_b, agent_c). A и B не дружат.
2. Коммуникация: A подходит к C и говорит: "B украл яблоко" (ложь, tone=MANIPULATIVE).
3. Ожидание: C меняет своё отношение к B (trust падает) в RelationshipStore.
4. Решение: В следующем тике DecisionHub C выбирает враждебный intent к B.
5. Действие: ImpactEngine наносит урон B.

Тест не инъецирует belief напрямую. Он инъецирует только причину (событие коммуникации).

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_divergence.py
"""

import logging
import sys
from pathlib import Path

# Настройка путей
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

# Настройка логирования
logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("EPISTEMIC_TEST")
logger.setLevel(logging.INFO)

# Импорты ENIGMA
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_types import EventType
from app.domain.events import EventDTO

CAMPAIGN_ID = "Open_road"
LOCATION_ID = "tavern"

# NPC ID в кампании Open_road
NPC_A = "thief_shadow"      # Кто лжёт
NPC_B = "merchant_goran"    # На кого лгут (жертва клеветы)
NPC_C = "guard_borko"       # Кто слушает (будет враждебен к B)

def run_epistemic_test():
    print("\n" + "="*60)
    print("🔬 СУПЕРБОКС-ЭПИСТЕМИЧЕСКИЙ ТЕСТ 001: Двойная Истина")
    print("="*60)

    # Инициализация ядра
    print("\n[1/5] Инициализация симуляции...")
    data_dir = BACKEND_ROOT.parent / "data"
    game_loop = build_game_loop(data_dir=str(data_dir))
    
    # Убедимся, что сцена инициализирована
    from app.services.game_loop.scene_init import ensure_scene_initialized
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    
    # Получаем доступ к шине событий и хранилищу отношений
    event_bus = game_loop._tick_orch._get_event_bus()
    relationship_store = game_loop.memory_manager._relationships

    # Базовый замер (Tick 0)
    print(f"\n[2/5] Замер базовых отношений (C -> B)...")
    _ = game_loop.idle_tick(CAMPAIGN_ID, LOCATION_ID)
    _pair_data = relationship_store.get_pair(CAMPAIGN_ID, NPC_C, NPC_B)
    baseline_trust = _pair_data.get("trust", 0.0) if _pair_data else 0.0
    print(f"  -> Базовый trust({NPC_C} -> {NPC_B}): {baseline_trust:.2f}")

    # Инъекция коммуникации (Ложь)
    print(f"\n[3/5] Инъекция коммуникации: {NPC_A} говорит {NPC_C}, что {NPC_B} вор...")
    
    lie_event = EventDTO.create(
        event_type=EventType.NPC_SPOKE,
        source=NPC_A,
        payload={
            "target_id": NPC_C,
            "text": "B украл яблоко, я видел это!",  # Текст (для STM)
            "tone": "MANIPULATIVE",                  # Тон (триггерит -trust)
            "topic": "theft",
            "tick": 1
        },
        visibility="private",
        radius=2.0
    )
    
    event_bus.publish(lie_event)
    print("  -> Событие NPC_SPOKE опубликовано в EventBus.")

    # Обработка тика (Tick 1)
    print("\n[4/5] Симуляция тика (обработка лжи)...")
    _ = game_loop.idle_tick(CAMPAIGN_ID, LOCATION_ID)
    
    # Проверка изменения убеждений (RelationshipStore)
    _pair_data = relationship_store.get_pair(CAMPAIGN_ID, NPC_C, NPC_B)
    post_lie_trust = _pair_data.get("trust", 0.0) if _pair_data else 0.0
    print(f"  -> Trust после лжи: {post_lie_trust:.2f}")
    
    if post_lie_trust < baseline_trust:
        print("  ✅ УБЕЖДЕНИЕ ИЗМЕНИЛОСЬ: C теперь меньше доверяет B.")
    else:
        print("  ❌ РАЗРЫВ ЦЕПИ: Trust не изменился. NPCDialogueSubscriber не сработал.")

    # Проверка решения (Tick 2)
    print("\n[5/5] Проверка решения NPC C в следующем тике...")
    # Прогоняем ещё один тик, чтобы DecisionHub увидел новое отношение
    tick_result = game_loop.idle_tick(CAMPAIGN_ID, LOCATION_ID)
    
    # Анализируем интенты C
    c_intents = []
    if hasattr(tick_result, 'tick_mutation') and tick_result.tick_mutation:
        for intent in tick_result.tick_mutation.movement_intents or []:
            if getattr(intent, 'actor_id', None) == NPC_C:
                c_intents.append(intent)
        for intent in tick_result.tick_mutation.communication_intents or []:
            if getattr(intent, 'speaker', None) == NPC_C:
                c_intents.append(intent)

    hostile_intents = [i for i in c_intents if getattr(i, 'intent_type', '') in ['attack', 'warn', 'threaten']]
    
    print(f"  -> Интенты {NPC_C}: {[getattr(i, 'intent_type', '?') for i in c_intents]}")
    
    if hostile_intents:
        print("  ✅ РЕШЕНИЕ ИЗМЕНИЛОСЬ: C выбрал враждебный интент.")
        print("\n" + "="*60)
        print("🎉 ЭПИСТЕМИЧЕСКОЕ РАСХОЖДЕНИЕ ДОКАЗАНО!")
        print("Существующая архитектура способна порождать разные убеждения")
        print("из одной объективной истины через коммуникацию.")
        print("="*60)
    else:
        print("  ❌ РАЗРЫВ ЦЕПИ: C не проявил агрессию, несмотря на падение trust.")
        print("\n" + "="*60)
        print("⚠️ ВЫВОД: Слой убеждений работает, но DecisionHub его игнорирует.")
        print("="*60)

if __name__ == "__main__":
    run_epistemic_test()
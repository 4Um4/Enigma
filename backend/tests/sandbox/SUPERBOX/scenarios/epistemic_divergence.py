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
    
    from app.services.game_loop.scene_init import ensure_scene_initialized
    ensure_scene_initialized(game_loop, CAMPAIGN_ID)
    
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
            "text": "B украл яблоко, я видел это!",
            "tone": "MANIPULATIVE",
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
    
    _pair_data = relationship_store.get_pair(CAMPAIGN_ID, NPC_C, NPC_B)
    post_lie_trust = _pair_data.get("trust", 0.0) if _pair_data else 0.0
    print(f"  -> Trust({NPC_C} -> {NPC_B}) после лжи: {post_lie_trust:.2f}")
    
    # Проверяем, изменилось ли отношение C к A (так как tone=MANIPULATIVE)
    _pair_data_ca = relationship_store.get_pair(CAMPAIGN_ID, NPC_C, NPC_A)
    trust_ca = _pair_data_ca.get("trust", 0.0) if _pair_data_ca else 0.0
    print(f"  -> Trust({NPC_C} -> {NPC_A}) после лжи: {trust_ca:.2f}")

    if post_lie_trust < baseline_trust:
        print("  ✅ УБЕЖДЕНИЕ ИЗМЕНИЛОСЬ: C теперь меньше доверяет B.")
    elif trust_ca < 0.0:
        print("  ❌ АРХИТЕКТУРНЫЙ РАЗРЫВ: C меньше доверяет A (из-за тона), но НЕ B.")
        print("     Существующая архитектура слепа к содержанию речи (Proposition).")
        print("     Она реагирует только на тон (tone), не создавая эпистемического расхождения.")
    else:
        print("  ❌ РАЗРЫВ ЦЕПИ: Trust не изменился вообще.")

    print("\n" + "="*60)
    print("⚠️ ВЫВОД: Эпистемическое расхождение не доказано.")
    print("Требуется минимальный канонический слой Proposition:")
    print("  CommunicationEvent -> Proposition -> L1Chronicle -> BeliefEngine")
    print("="*60)

if __name__ == "__main__":
    run_epistemic_test()
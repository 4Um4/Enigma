# backend/tests/test_dm_facade.py
# python -m pytest backend/tests/test_dm_facade.py -v --tb=short
"""
Интеграционные тесты для DM Execution Facade (Этап 5).
Проверяем, что мост между чистой архитектурой данных (L0/L2) 
и ядром интеллекта (DecisionHub) работает без сбоев.
Назначение: Проверка сквозного моста JSON -> L0/L2 -> DecisionHub (Этап 5).
Зависимости: npc_loader, npc_profile, decision_hub.
"""

import pytest
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.npc.npc_loader import load_profile_from_legacy_json
from app.models.npc_profile import NPCStateL2

# Минимальный словарь, имитирующий кусок major_npcs.json
MOCK_RAW_TORNIN = {
    "id": "tavern_keeper_tornin",
    "name": "Торнин",
    "tier": "major",
    "drives": {"control": 0.5, "significance": 0.25, "fear": 0.15, "desire": 0.1},
    "psyche": {"willpower": 65, "breakpoint": 80, "loyalty_true": 60},
    "memory_trace": ["Столовые приборы? Не дождишься..."]  # Мусор, который будет отсечен
}


class TestDMFacadeBridge:
    
    def test_json_to_l0_to_hub_produces_result(self):
        """
        Сценарий: Игрок атакует Торнина.
        1. Фасад парсит JSON -> NPCProfileL0.
        2. Фасад берет/создает NPCStateL2.
        3. Фасад формирует EventContext.
        4. DecisionHub считает результат.
        """
        # 1. Загрузка в чистый L0
        profile_l0 = load_profile_from_legacy_json(MOCK_RAW_TORNIN)
        assert profile_l0.id == "tavern_keeper_tornin"
        assert profile_l0.drives_base["control"] == 0.5

        # 2. Получение состояния L2 (в реальности достается из памяти кэша)
        state_l2 = NPCStateL2()
        
        # 3. Формирование события от игрока (имитация работы DM Router)
        event_ctx = EventContext(
            event_type="player_attacks",
            actor_id="player_1",
            intensity=1.0,
            distance=2.0,
            visible_threat_markers=["sword_drawn"]
        )

        # 4. Вызов DecisionHub (seed=42 для детерминированности теста)
        hub = DecisionHub(seed=42)
        result = hub.compute(
            state=state_l2,
            personality=profile_l0,
            event=event_ctx
        )

        # 5. Проверки
        assert result is not None
        # Проверяем, что DecisionHub вернул валидный Enum (а не строку-мусор)
        from app.services.npc.npc_state import Intent
        assert isinstance(result.intent, Intent)
        
        # Убеждаемся, что scores_trace посчитался (черный ящик работает)
        assert len(result.scores_trace) > 0

    def test_l2_mutation_isolation(self):
        """
        Критический тест: DecisionHub НЕ должен мутировать исходный L2 state.
        Если мутирует — архитектура сломана.
        """
        profile_l0 = load_profile_from_legacy_json(MOCK_RAW_TORNIN)
        state_l2 = NPCStateL2(stress=10.0)
        
        event_ctx = EventContext(event_type="player_insults", actor_id="player_1")
        
        DecisionHub(seed=1).compute(state_l2, profile_l0, event_ctx)
        
        # Стресс должен остаться 10.0, так как StateApplicator здесь не вызывался
        assert state_l2.stress == 10.0
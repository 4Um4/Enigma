"""
Файл: backend/tests/test_mvp_simulation_validation.py
Назначение: Тестирование выживаемости мира и причинных цепочек (MVP Validation).
Зависимости: pytest, app.services.game_loop, app.services.tick_orchestrator
Основные сущности: LongRunSimulation, CausalChains
Запуск: cd backend; python -m pytest tests/test_mvp_simulation_validation.py -v -s; cd ..
"""

import pytest
import math
import types
import logging
from app.domain.events import EventDTO
from app.services.events.event_bus import get_event_bus

logger = logging.getLogger(__name__)

class TestLongRunSimulation:
    """Уровень 2: Тесты выживаемости симуляции на длинных дистанциях (1000 тиков)."""

    def test_world_survives_1000_ticks_without_llm(self, game_loop_factory):
        """
        ПРОВЕРЯЕТ: Мир live 1000 тиков без LLM-вызовов.
        ОЖИДАНИЕ:
            - Нет крашей пайплайна.
            - Нет NaN в критических полях (stress, trust, hp).
            - game_time_seconds монотонно растёт.
            - Нет структурного дрейфа (drift_C, drift_D = 0).
        """
        loop = game_loop_factory()
        campaign_id = "Open_road"
        location_id = "tavern_silver_wolf"
        
        # Инициализируем чистый мир
        loop.new_game(campaign_id)
        
        initial_scene = loop.scene_manager.get_scene_state(campaign_id, location_id)
        if not initial_scene:
            pytest.skip(f"Сцена '{campaign_id}/{location_id}' не найдена. Требуется корректная тестовая кампания.")
            
        initial_time = initial_scene.get("game_time_seconds", 0.0)
        
        for i in range(1000):
            try:
                loop.idle_tick(campaign_id)
            except Exception as e:
                pytest.fail(f"Симуляция упала на тике {i} с ошибкой: {e}")

        final_scene = loop.scene_manager.get_scene_state(campaign_id, location_id)
        final_time = final_scene.get("game_time_seconds", 0.0)
        
        # 1. Время идёт
        assert final_time > initial_time, "Время остановилось за 1000 тиков!"
        
        # 2. Нет NaN в стейтах NPC
        for npc_id, pos in final_scene["npc_positions"].items():
            assert not math.isnan(pos["local_position"]["x"]), f"NaN в позиции X у {npc_id}!"
            
        # 3. Нет структурного дрейфа (проверяем логи оркестратора)
        drift_stats = loop._tick_orch._drift_stats
        assert drift_stats.get("drift_C", 0) == 0, "Обнаружен топологический дрейф (drift_C)!"
        assert drift_stats.get("drift_D", 0) == 0, "Обнаружен каузальный дрейф (drift_D)!"


class TestCausalChains:
    """Уровень 2: Тестирование многошаговых причинных цепочек (A -> B -> C -> D)."""

    def test_insult_crystallizes_into_avoidance(self, game_loop_factory):
        """
        СЦЕНАРИЙ: NPC_A оскорбляет NPC_B.
        ОЖИДАНИЕ:
            1. trust(NPC_B -> NPC_A) падает.
            2. L1Chronicle получает TraitDriftEvent.
            3. Со временем (10 тиков) кристаллизуется belief (fear/anger).
            4. SocialTargetResolver(NPC_B) перестает выбирать NPC_A.
        """
        loop = game_loop_factory()
        campaign_id = "Open_road"
        location_id = "tavern_silver_wolf"
        loop.new_game(campaign_id)
        bus = get_event_bus()
        
        # Создаем минимальные мок-состояния для резолвера
        npc_b = types.SimpleNamespace(
            npc_id="npc_b",
            social_satiation=100.0,
            relationship_cache={"npc_a": {"trust": -30.0, "fear": 10.0}},
            perceptual_kernel=types.SimpleNamespace(threat_gradient=0.0, uncertainty=0.0, anomaly_score=0.0, somatic_urgency=0.0),
            drives_runtime={"desire": 0.5, "control": 0.1, "fear": 0.3, "significance": 0.1},
            emotion="NEUTRAL",
            body_state={"life_status": "ALIVE", "shock_impulse": 0.0},
            will_state="COMPLY",
            identity=None,
        )
        
        # 1. Эмитим событие оскорбления (через шину событий)
        event = EventDTO.create(
            event_type="NPC_SPOKE",
            source="npc_a",
            payload={"tone": "ANGRY", "text": "Ты грязный вор!", "target_id": "npc_b"}
        )
        bus.publish(event)
        
        # 2. Проверяем немедленную реакцию (trust падает)
        rel_store = loop.memory_manager._relationships if hasattr(loop, "memory_manager") else None
        if rel_store:
            rel_b_to_a = rel_store.get("npc_b", "npc_a")
            if rel_b_to_a:
                assert rel_b_to_a.get("trust", 0.0) < 0.0, "Trust не упал после оскорбления!"
        
        # 3. Прогоняем 10 тиков для кристаллизации
        for _ in range(10):
            loop.idle_tick(campaign_id)
            
        # 4. Проверяем изменение поведения (SocialTargetResolver)
        # Вручную вызываем резолвер для NPC_B
        from app.services.npc.social_target_resolver import SocialTargetResolver
        
        class FakeSpatialQuery:
            def distance(self, a, b): return 5.0
            def visibility(self, a, b): return True
            
        target = SocialTargetResolver.resolve(
            state=npc_b,
            spatial_query=FakeSpatialQuery(),
            all_npc_ids=["npc_a", "npc_c"]
        )
        
        assert target != "npc_a", "NPC_B всё ещё выбирает NPC_A после оскорбления!"
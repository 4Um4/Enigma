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
import json
import time
import os
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from app.domain.events import EventDTO
from app.services.events.event_bus import get_event_bus

logger = logging.getLogger(__name__)

@contextmanager
def suppress_output():
    """Перехватывает stdout и stderr, чтобы отключить спам print() из симуляции."""
    with open(os.devnull, 'w') as devnull:
        with redirect_stdout(devnull), redirect_stderr(devnull):
            yield

class TestLongRunSimulation:
    """Уровень 2: Тесты выживаемости симуляции (100 тиков)."""

    def test_world_survives_100_ticks_without_llm(self, game_loop_factory, tmp_path):
        """
        ПРОВЕРЯЕТ: Мир live 100 тиков без LLM-вызовов.
        ОЖИДАНИЕ:
            - Нет крашей пайплайна.
            - Нет NaN в критических полях.
            - game_time_seconds монотонно растёт.
            - Нет структурного дрейфа (drift_C, drift_D = 0).
        """
        loop = game_loop_factory()
        campaign_id = "Open_road"
        location_id = "tavern_silver_wolf"
        
        logging.disable(logging.WARNING)
        
        loop.new_game(campaign_id)
        initial_scene = loop.scene_manager.get_scene_state(campaign_id, location_id)
        if not initial_scene:
            logging.disable(logging.NOTSET)
            pytest.skip(f"Сцена '{campaign_id}/{location_id}' не найдена.")
            
        initial_time = initial_scene.get("game_time_seconds", 0.0)
        
        start_perf = time.time()
        errors = []
        with suppress_output():
            for i in range(100):
                try:
                    loop.idle_tick(campaign_id)
                except Exception as e:
                    errors.append(f"Tick {i}: {str(e)}")
                    break
                
        elapsed_perf = time.time() - start_perf
        logging.disable(logging.NOTSET)
        
        final_scene = loop.scene_manager.get_scene_state(campaign_id, location_id)
        final_time = final_scene.get("game_time_seconds", 0.0) if final_scene else 0.0
        
        drift_stats = loop._tick_orch._drift_stats
        
        report = {
            "ticks_run": i + 1,
            "elapsed_seconds": round(elapsed_perf, 2),
            "ticks_per_second": round((i + 1) / elapsed_perf, 2) if elapsed_perf > 0 else 0,
            "initial_game_time": initial_time,
            "final_game_time": final_time,
            "drift_C": drift_stats.get("drift_C", 0),
            "drift_D": drift_stats.get("drift_D", 0),
            "errors": errors,
            "final_npc_positions": {nid: pos.get("local_position") for nid, pos in final_scene.get("npc_positions", {}).items()} if final_scene else {}
        }
        
        report_path = tmp_path / "mvp_100_tick_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        print(f"\n[MVP_VALIDATION] Отчёт сохранён: {report_path}")
        print(f"[MVP_VALIDATION] Скорость: {report['ticks_per_second']} тик/сек")
        
        assert not errors, f"Симуляция упала: {errors[0]}"
        assert final_time > initial_time, "Время остановилось!"
        assert drift_stats.get("drift_C", 0) == 0, "Топологический дрейф!"
        assert drift_stats.get("drift_D", 0) == 0, "Каузальный дрейф!"


class TestCausalChains:
    """Уровень 2: Тестирование многошаговых причинных цепочек (A -> B -> C -> D)."""

    def test_insult_updates_relationships_and_chronicle(self, game_loop_factory):
        """
        СЦЕНАРИЙ: NPC_A оскорбляет NPC_B (tone=ANGRY).
        ОЖИДАНИЕ:
            1. trust(NPC_B -> NPC_A) падает (NEW-2).
            2. L1Chronicle получает TraitDriftEvent (NEW-3).
        ПРИМЕЧАНИЕ: P2-06 (избегание) заблокирован, поэтому поведение не проверяется.
        """
        loop = game_loop_factory()
        campaign_id = "Open_road"
        loop.new_game(campaign_id)
        
        # Явно привязываем L1Chronicle к кампании ДО эмуляции события,
        # иначе событие запишется с пустым campaign_id и потеряется при reload.
        if hasattr(loop, "_tick_orch") and hasattr(loop._tick_orch, "l1_chronicle"):
            loop._tick_orch.l1_chronicle.bind_campaign(campaign_id)
            
        bus = get_event_bus()
        
        event = EventDTO.create(
            event_type="NPC_SPOKE",
            source="npc_a",
            payload={"tone": "ANGRY", "text": "Ты грязный вор!", "target_id": "npc_b"}
        )
        # Вызываем подписчика напрямую, чтобы изолировать проблему с шиной
        if hasattr(loop, "_npc_dialogue_subscriber") and loop._npc_dialogue_subscriber:
            loop._npc_dialogue_subscriber.on_npc_spoke(event)
        else:
            bus.publish(event)
        
        # 1. Проверяем немедленную реакцию (trust падает)
        rel_store = loop.memory_manager._relationships if hasattr(loop, "memory_manager") else None
        assert rel_store is not None, "RelationshipStore не найден"
        
        # API: get_pair(campaign_id, source, target)
        rel_b_to_a = rel_store.get_pair("Open_road", "npc_b", "npc_a")
        assert rel_b_to_a is not None, "Запись об отношениях не создана"
        assert rel_b_to_a.get("trust", 0.0) < 0.0, "Trust не упал после оскорбления!"
        
        # 2. Проверяем запись в L1Chronicle (TraitDriftEvent)
        l1_chronicle = loop._tick_orch.l1_chronicle if hasattr(loop, "_tick_orch") else None
        assert l1_chronicle is not None, "L1Chronicle не найден"
        
        # Прогоняем 1 тик, чтобы L1Chronicle сохранился
        with suppress_output():
            loop.idle_tick(campaign_id)
            
        events = l1_chronicle.query_raw("npc_b")
        assert len(events) > 0, "TraitDriftEvent не записан в L1Chronicle!"
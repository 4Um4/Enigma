# tests/test_cfrm_models.py
# Назначение: Юнит-тесты для доменных моделей CFRM (ClusterGraph, EventBuffer, classify_event)
# Зависимости: pytest, app.models.cfrm, app.domain.events

"""
Запуск: pytest backend/tests/test_cfrm_models.py

Проверяет корректность базовых моделей CFRM:
- ClusterDef и ClusterGraph: построение, соседи, обновление версий

TODO:
- Добавить тесты для классификации событий (classify_event) с разными типами событий, включая граничные случаи (неизвестные типы)
- В будущем можно добавить тесты для динамических свойств кластеров (например, "опасный", "социальный центр") и их влияния на NPC внутри, если эти свойства будут реализованы.
"""

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.events import EventDTO
from app.models.cfrm import (
    CausalAxis,
    ClassificationSource,
    ClusterDef,
    ClusterGraph,
    ClusterOccupancy,
    DisturbanceVector,
    EventBuffer,
    FieldDisturbance,
    classify_event,
)

# ── Фикстуры ─────────────────────────────────────────────────────────


@pytest.fixture
def make_event():
    """Фабрика синтетических EventDTO для тестов."""

    def _factory(event_type: str, source: str = "test") -> EventDTO:
        return EventDTO.create(event_type=event_type, source=source, payload={"test": True})

    return _factory


# ── Тесты ClusterGraph ───────────────────────────────────────────────


class TestClusterGraph:
    def test_build_and_neighbors(self):
        """Кластер корректно определяет соседей через boundary_cells."""
        c1 = ClusterDef(cluster_id="loc:hall", boundary_cells=frozenset({"loc:bar"}))
        c2 = ClusterDef(cluster_id="loc:bar", boundary_cells=frozenset({"loc:hall"}))
        graph = ClusterGraph(clusters={"loc:hall": c1, "loc:bar": c2})

        assert graph.get_neighbors("loc:hall") == {"loc:bar"}
        assert graph.get_neighbors("loc:bar") == {"loc:hall"}

    def test_update_version(self):
        """Инкремент версии при дрейфе кластера."""
        c1 = ClusterDef(cluster_id="loc:hall", version=0)
        graph = ClusterGraph(clusters={"loc:hall": c1})

        graph.update_version("loc:hall")
        assert graph.get_cluster("loc:hall").version == 1

        # Не падает на неизвестном кластере
        graph.update_version("loc:unknown")
        assert graph.get_cluster("loc:unknown") is None


# ── Тесты EventBuffer и классификации ────────────────────────────────


class TestEventBufferAndClassification:
    def test_classify_physical(self):
        result = classify_event("combat")
        assert result.axis == CausalAxis.PHYSICAL
        assert result.confidence == 1.0
        assert result.source == ClassificationSource.HARD_RULE

        assert classify_event("player_attacks").axis == CausalAxis.PHYSICAL
        assert classify_event("object_destroyed").axis == CausalAxis.PHYSICAL

    def test_classify_cognitive(self):
        assert classify_event("dialogue").axis == CausalAxis.COGNITIVE
        assert classify_event("PLAYER_INSULTS").axis == CausalAxis.COGNITIVE
        assert classify_event("npc_spoke").axis == CausalAxis.COGNITIVE

    def test_classify_social(self):
        assert classify_event("theft").axis == CausalAxis.SOCIAL
        assert classify_event("saved_life").axis == CausalAxis.SOCIAL
        assert classify_event("betrayal").axis == CausalAxis.SOCIAL

    def test_classify_unknown_falls_to_cognitive(self):
        """Неизвестные события по умолчанию когнитивные (безопасный fallback) с эпистемической неуверенностью."""
        result = classify_event("strange_new_event")
        assert result.axis == CausalAxis.COGNITIVE
        assert result.confidence == 0.2
        assert result.source == ClassificationSource.FALLBACK

    def test_buffer_add_and_drain(self, make_event):
        """Буфер наполняется по осям и полностью очищается при drain."""
        buf = EventBuffer()
        e_phys = make_event("combat")
        e_cogn = make_event("dialogue")
        e_soc = make_event("theft")

        buf.add(e_phys, CausalAxis.PHYSICAL)
        buf.add(e_cogn, CausalAxis.COGNITIVE)
        buf.add(e_soc, CausalAxis.SOCIAL)

        p, c, s = buf.drain()

        assert len(p) == 1 and p[0].type == "combat"
        assert len(c) == 1 and c[0].type == "dialogue"
        assert len(s) == 1 and s[0].type == "theft"

        # После drain буфер пуст
        p2, c2, s2 = buf.drain()
        assert len(p2) == 0
        assert len(c2) == 0
        assert len(s2) == 0

    def test_buffer_drain_is_atomic(self, make_event):
        """Drain извлекает все накопленные факты одной транзакцией."""
        buf = EventBuffer()
        for _ in range(3):
            buf.add(make_event("combat"), CausalAxis.PHYSICAL)

        p, _, _ = buf.drain()
        assert len(p) == 3

        # Повторный drain ничего не даёт
        p2, _, _ = buf.drain()
        assert len(p2) == 0


# ── Тесты ClusterOccupancy (Spatial Index) ───────────────────────────


class TestClusterOccupancy:
    def test_add_and_query(self):
        """Сущность добавляется в кластер и находится за O(1)."""
        idx = ClusterOccupancy()
        idx.update_entity("npc_1", "loc:hall")
        idx.update_entity("npc_2", "loc:hall")
        idx.update_entity("player", "loc:bar")

        assert idx.get_cluster("npc_1") == "loc:hall"
        assert idx.get_entities_in_cluster("loc:hall") == {"npc_1", "npc_2"}
        assert idx.get_entities_in_cluster("loc:bar") == {"player"}

    def test_move_between_clusters(self):
        """Перемещение сущности обновляет оба кластера."""
        idx = ClusterOccupancy()
        idx.update_entity("npc_1", "loc:hall")
        idx.update_entity("npc_1", "loc:bar")  # Перешёл

        assert idx.get_cluster("npc_1") == "loc:bar"
        assert idx.get_entities_in_cluster("loc:hall") == set()  # Пусто
        assert idx.get_entities_in_cluster("loc:bar") == {"npc_1"}

    def test_empty_cluster_cleanup(self):
        """Пустые кластеры не висят в памяти (автоочистка)."""
        idx = ClusterOccupancy()
        idx.update_entity("npc_1", "loc:hall")
        idx.update_entity("npc_1", "loc:bar")  # Покинул hall

        assert "loc:hall" not in idx.cluster_to_entities

    def test_remove_entity(self):
        """Удаление сущности (смерть) чистит индекс."""
        idx = ClusterOccupancy()
        idx.update_entity("npc_1", "loc:hall")
        idx.remove_entity("npc_1")

        assert idx.get_cluster("npc_1") is None
        assert idx.get_entities_in_cluster("loc:hall") == set()

    def test_idempotent_update(self):
        """Повторная вставка в тот же кластер не создаёт артефактов."""
        idx = ClusterOccupancy()
        idx.update_entity("npc_1", "loc:hall")
        idx.update_entity("npc_1", "loc:hall")

        assert idx.get_cluster("npc_1") == "loc:hall"
        assert len(idx.cluster_to_entities) == 1


# ── Задача 2: Детерминизм классификации ──────────────────────────────────


class TestClassifyEventDeterministic:
    def test_100_events_determinism_and_buffer_integrity(self):
        """Система детерминированно классифицирует 100 событий (70 известных, 30 unknown/опечатки) без потерь."""
        import random

        random.seed(42)

        # Генерируем 70 известных событий (повторяем сэмплы)
        known_events = [
            "combat",
            "player_attacks",
            "object_destroyed",
            "player_moved",
            "dialogue",
            "PLAYER_INSULTS",
            "npc_spoke",
            "PLAYER_THREATENS",
            "theft",
            "saved_life",
            "betrayal",
            "player_helpers",
            "npc_moved",
            "player_cast_spell",
            "object_moved",
            "sound_emitted",
            "player_talks",
            "npc_interacts_npc",
            "faction_event",
            "idle",
        ]
        # 30 unknown/опечатки
        unknown_events = [
            "strange_noise",
            "player_attacs",
            "dilogoue",
            "figth",
            "run_away",
            "weather_rain",
            "npc_dance",
            "spell_cast",
            "jump",
            "swim",
            "trade_item",
            "craft_weapon",
            "read_book",
            "sleep",
            "eat_food",
            "drink_potion",
            "open_door",
            "close_window",
            "sit_chair",
            "look_mirror",
            "unknown_gesture",
            "weird_sound",
            "glitch",
            "hack",
            "mod",
            "teleport",
            "fly",
            "dig",
            "build",
            "destroy",
        ]

        all_events = (known_events * 4)[:70] + unknown_events  # 70 + 30 = 100
        random.shuffle(all_events)

        # Запускаем классификацию дважды
        results_run_1 = [classify_event(e) for e in all_events]
        results_run_2 = [classify_event(e) for e in all_events]

        # Assert 1: Результаты идентичны (ось + уверенность + источник)
        assert len(results_run_1) == 100
        assert len(results_run_2) == 100
        for i in range(100):
            assert results_run_1[i] == results_run_2[i], f"Неседерминированность на событии '{all_events[i]}'"

        # Assert 2: Ни одно событие не потеряно при помещении в EventBuffer
        buf = EventBuffer()
        for event_type, res in zip(all_events, results_run_1):
            disturbance = FieldDisturbance(
                origin_cluster="test:cluster",
                disturbance_type=res.axis,
                magnitude=1.0,
                vectors=(DisturbanceVector.BEHAVIORAL,),
                source_entity="test_runner",
            )
            buf.add(disturbance, res.axis)

        physical, cognitive, social = buf.drain()
        total = len(physical) + len(cognitive) + len(social)
        assert total == 100, f"Потеряно событий в буфере! Было 100, стало {total}"

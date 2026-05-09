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
from uuid import uuid4

from app.domain.events import EventDTO
from app.models.cfrm import (
    CausalAxis,
    ClusterDef,
    ClusterGraph,
    ClusterOccupancy,
    EventBuffer,
    classify_event,
)


# ── Фикстуры ─────────────────────────────────────────────────────────

@pytest.fixture
def make_event():
    """Фабрика синтетических EventDTO для тестов."""
    def _factory(event_type: str, source: str = "test") -> EventDTO:
        return EventDTO.create(
            event_type=event_type,
            source=source,
            payload={"test": True}
        )
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
        assert classify_event("combat") == CausalAxis.PHYSICAL
        assert classify_event("player_attacks") == CausalAxis.PHYSICAL
        assert classify_event("object_destroyed") == CausalAxis.PHYSICAL

    def test_classify_cognitive(self):
        assert classify_event("dialogue") == CausalAxis.COGNITIVE
        assert classify_event("PLAYER_INSULTS") == CausalAxis.COGNITIVE
        assert classify_event("npc_spoke") == CausalAxis.COGNITIVE

    def test_classify_social(self):
        assert classify_event("theft") == CausalAxis.SOCIAL
        assert classify_event("saved_life") == CausalAxis.SOCIAL
        assert classify_event("betrayal") == CausalAxis.SOCIAL

    def test_classify_unknown_falls_to_cognitive(self):
        """Неизвестные события по умолчанию когнитивные (безопасный fallback)."""
        assert classify_event("strange_new_event") == CausalAxis.COGNITIVE

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
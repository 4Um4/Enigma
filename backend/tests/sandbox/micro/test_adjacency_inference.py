"""
path: backend/tests/sandbox/micro/test_adjacency_inference.py
Назначение: Верификация ADR-073 (Граф выводится из смежности без ручных passages)
Зависимости: app.services.spatial.graph_compiler
Основные сущности: compile_graph

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_adjacency_inference.py -v --tb=short; cd ..
"""

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.spatial.graph_compiler import compile_graph


def test_adjacency_inference_without_passages():
    """ДОКАЗЫВАЕТ: Компилятор графа выводит связи из смежности комнат при отсутствии passages (ADR-073).

    Без этого NPC не могут перемещаться между комнатами, если редактор не указал двери явно.
    Зависимость от ручной простановки passages запрещена.
    """
    # Две комнаты с общей стеной (смежные bounding box-ы), без поля passages
    editor_data = {
        "rooms": [
            {"id": "hall", "x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0, "polygon": []},
            {"id": "kitchen", "x": 10.0, "y": 0.0, "width": 10.0, "height": 10.0, "polygon": []},
        ]
    }

    graph, connections, alias_map, _boundary_map, _rooms_geometry = compile_graph(editor_data, location_id="tavern")

    # Граф должен содержать обе комнаты
    assert "tavern:hall" in graph, "Комната hall не попала в граф"
    assert "tavern:kitchen" in graph, "Комната kitchen не попала в граф"

    # ADR-073: Комнаты должны быть связаны через инференс смежности
    # connections — словарь множеств связей {node_id: {neighbor_ids}}
    hall_neighbors = connections.get("tavern:hall", set())
    kitchen_neighbors = connections.get("tavern:kitchen", set())

    assert "tavern:kitchen" in hall_neighbors, (
        "ADR-073 Нарушено: Смежные комнаты не связаны при отсутствии passages (hall → kitchen)"
    )
    assert "tavern:hall" in kitchen_neighbors, (
        "ADR-073 Нарушено: Смежные комнаты не связаны при отсутствии passages (kitchen → hall)"
    )

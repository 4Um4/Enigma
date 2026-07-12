"""
Назначение: Тесты для функции _get_builtin_fallback в модуле graph_compiler.py, которая возвращает предопределённые структуры локаций для определённых идентификаторов локаций, таких как "tavern". Тесты проверяют корректность возвращаемых данных, а также обработку различных входных данных, включая граничные случаи и некорректные типы.

Запуск: pytest backend/tests/Graph.py

TODO:
- Добавить тесты для проверки производительности функции при большом количестве вызовов.
- Добавить тесты для проверки поведения функции при изменении внутренней структуры возвращаемых данных (например, добавление новых полей в комнаты или проходы).
"""

import pytest
from app.services.spatial.graph_compiler import _get_builtin_fallback


@pytest.mark.parametrize(
    "location_id, expected_is_none",
    [
        pytest.param(
            "tavern",
            False,
            id="tavern_exact-match_returns-fallback",
        ),
        pytest.param(
            "north_tavern_level_1",
            False,
            id="tavern_substring-in-middle_returns-fallback",
        ),
        pytest.param(
            "TAVERN_uppercase-no-match",
            True,
            id="tavern_case-sensitive_no-fallback",
        ),
        pytest.param(
            "inn-taverna-similar-word",
            True,
            id="tavern_similar-word-no-substring_no-fallback",
        ),
        pytest.param(
            "house",
            True,
            id="non-tavern-location_returns-none",
        ),
        pytest.param(
            "",
            True,
            id="empty-location_id_returns-none",
        ),
    ],
)
def test_get_builtin_fallback_happy_and_edge_cases(location_id, expected_is_none):
    # Act

    result = _get_builtin_fallback(location_id)

    # Assert

    if expected_is_none:
        assert result is None
    else:
        assert isinstance(result, dict)
        assert "rooms" in result
        assert "passages" in result


@pytest.mark.parametrize(
    "location_id",
    [
        pytest.param("tavern", id="structure_tavern_check-rooms-and-passages"),
        pytest.param("my_tavern_location", id="structure_my_tavern_location_check-rooms-and-passages"),
    ],
)
def test_get_builtin_fallback_structure(location_id):
    # Act

    result = _get_builtin_fallback(location_id)

    # Assert

    # Basic shape
    assert isinstance(result, dict)
    assert set(result.keys()) == {"rooms", "passages"}

    rooms = result["rooms"]
    passages = result["passages"]

    # Rooms structure
    expected_room_ids = {
        "main_hall",
        "kitchen",
        "entrance",
        "bar_area",
        "corner_table",
    }
    assert set(rooms.keys()) == expected_room_ids

    for room_id, room_data in rooms.items():
        assert isinstance(room_data, dict), f"Room '{room_id}' should be a dict"
        assert set(room_data.keys()) == {"x", "y", "aliases"}, f"Room '{room_id}' keys mismatch"
        assert isinstance(room_data["x"], (int, float)), f"Room '{room_id}' x should be numeric"
        assert isinstance(room_data["y"], (int, float)), f"Room '{room_id}' y should be numeric"
        assert isinstance(room_data["aliases"], list), f"Room '{room_id}' aliases should be a list"
        assert room_data["aliases"], f"Room '{room_id}' should have at least one alias"

    # Passages structure
    assert isinstance(passages, list)
    expected_passages = [
        {"from": "main_hall", "to": "kitchen"},
        {"from": "main_hall", "to": "entrance"},
        {"from": "main_hall", "to": "bar_area"},
        {"from": "main_hall", "to": "corner_table"},
        {"from": "bar_area", "to": "kitchen"},
    ]
    # Order is significant in the implementation, so we compare directly
    assert passages == expected_passages


@pytest.mark.parametrize(
    "location_id",
    [
        pytest.param(123, id="non-string_int-location_id_raises-type-error"),
        pytest.param(None, id="non-string_none-location_id_raises-type-error"),
        pytest.param(3.14, id="non-string_float-location_id_raises-type-error"),
        pytest.param(
            ["tavern"],
            id="non-string_list-location_id_raises-type-error",
        ),
    ],
)
def test_get_builtin_fallback_error_non_string_location_id(location_id):
    # Arrange

    def call():
        return _get_builtin_fallback(location_id)  # type: ignore[arg-type]

    # Act

    with pytest.raises(TypeError):
        _ = call()

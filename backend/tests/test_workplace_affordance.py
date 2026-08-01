# -*- coding: utf-8 -*-
"""
Кросс-доменный тест ADR-O-326: Workplace Affordance Contract.
Проверяет связь: JSON-данные (tags) → GraphCompiler → SpatialService → LifeEngine.
Запуск: pytest backend/tests/test_workplace_affordance.py -v
"""
import sys
from pathlib import Path

# Поднимаемся на уровень корня проекта
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root / "backend"))

from app.models.spatial_contracts import SpatialOverlay
from app.services.npc.life_engine import LifeEngine
from app.services.spatial.graph_compiler import compile_graph, load_editor_json
from app.services.spatial.spatial_service import SpatialService

_search_dirs = [
    _project_root / "frontend" / "map_editor" / "campaigns" / "Open_road" / "locations",
    _project_root / "frontend" / "map_editor" / "campaigns" / "Open_road",
    _project_root / "frontend" / "map_editor" / "location_templates",
]


def test_guard_borko_finds_guard_post_via_workplace_tag():
    """Борко должен находить узел guard_post через тег workplace:guard, а не случайно."""
    editor = load_editor_json("Open_road", "city_gate", search_dirs=_search_dirs)
    graph, conns, alias_map, _, _, _, _, _ = compile_graph(editor, "city_gate")
    overlay = SpatialOverlay()
    svc = SpatialService(graph, conns, alias_map, overlay)

    engine = LifeEngine(data_dir="/tmp/enigma_test")
    engine._spatial_service = svc

    npc_borko = {
        "id": "guard",
        "name": "Борко",
        "location_id": "city_gate",
        "position": "entrance",
        "routine": {"current": "guarding_gate"},
    }

    result = engine._resolve_position(npc_borko, "guarding_gate")
    assert result is not None, "Борко не смог найти позицию для guarding_gate"
    location_id, position, activity = result
    assert "guard_post" in position, f"Ожидался guard_post, получено {position}"
    print("PASS: Борко нашёл guard_post через тег workplace:guard")


def test_maid_lusya_finds_kitchen_via_workplace_tag():
    """Люся должна находить узел kitchen через тег workplace:maid."""
    editor = load_editor_json("Open_road", "tavern", search_dirs=_search_dirs)
    graph, conns, alias_map, _, _, _, _, _ = compile_graph(editor, "tavern")
    overlay = SpatialOverlay()
    svc = SpatialService(graph, conns, alias_map, overlay)

    engine = LifeEngine(data_dir="/tmp/enigma_test")
    engine._spatial_service = svc

    npc_lusya = {
        "id": "maid_lusya",
        "name": "Люся",
        "location_id": "tavern",
        "position": "main_hall",
        "routine": {"current": "working"},
    }

    # Активности working нет в activity_map тестового NPC, поэтому должен сработать fallback на роль SERVING_STATION
    # и затем фильтр по тегу workplace:maid
    result = engine._resolve_position(npc_lusya, "serving_tables")
    assert result is not None, "Люся не смогла найти позицию для serving_tables"
    location_id, position, activity = result
    assert "kitchen" in position, f"Ожидался kitchen, получено {position}"
    print("PASS: Люся нашла kitchen через тег workplace:maid")
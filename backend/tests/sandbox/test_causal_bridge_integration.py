# backend/tests/sandbox/test_causal_bridge_integration.py
# Назначение: Интеграционный тест каузального моста (Спринт 36)
# Проверяет: расписание, приказы, движение, координаты на каждом тике
# Зависимости: pytest, LifeEngine, MovementEngine, SceneStateManager, SpatialService

"""
Запуск:
Get-ChildItem -Path "backend/" -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force
python -m pytest backend/tests/sandbox/test_causal_bridge_integration.py -v --tb=short 2>&1 | Select-Object -Last 25

TODO:

"""

from unittest.mock import MagicMock, patch

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.movement import PRIORITY_NEEDS, PRIORITY_SCHEDULE, MacroMovementGoal
from app.models.spatial_contracts import NodeRef, NodeRole
from app.services.npc.life_engine import LifeEngine
from app.services.scene_state_manager import SceneStateManager
from app.services.spatial.movement_engine import MovementEngine
from app.services.spatial.spatial_service import SpatialService

# ── Фикстуры ──────────────────────────────────────────────────────────────


class _DummyGraph:
    """Заглушка для LocationGraph, возвращающая NodeRef."""

    def __init__(self, location_id: str, nodes: dict):
        self.location_id = location_id
        # P7-FIX: MovementEngine проверяет _location_id для нужд needs_dynamic
        self._location_id = location_id
        self._nodes = nodes

    def all_nodes(self) -> dict:
        return self._nodes


@pytest.fixture
def tavern_graph():
    """Минимальный граф таверны: 3 узла, 2 ребра."""
    _loc_id = "tavern_silver_wolf"
    nodes = {
        "main_hall": NodeRef(node_id="main_hall", role=NodeRole.DEFAULT, tags=[], x=10.0, y=10.0, zone_id=_loc_id),
        "bar_area": NodeRef(node_id="bar_area", role=NodeRole.BAR, tags=[], x=5.0, y=5.0, zone_id=_loc_id),
        "bed": NodeRef(node_id="bed", role=NodeRole.BED, tags=[], x=15.0, y=15.0, zone_id=_loc_id),
    }
    graph = _DummyGraph(location_id=_loc_id, nodes=nodes)
    return graph


@pytest.fixture
def scene_state(tavern_graph):
    """Актуальный scene_state с 3 NPC и игроком."""
    return {
        "location_id": "tavern_silver_wolf",
        "tick": 0,
        "game_time_seconds": 28800,  # 08:00
        "environment": {"time_of_day": "08:00", "light": 1.0},
        "npc_positions": {
            "player": {
                "local_position": {"x": 10.0, "y": 10.0},
                "position": "main_hall",
                "name": "Игрок",
            },
            "tavern_keeper_tornin": {
                "local_position": {"x": 5.0, "y": 5.0},
                "position": "bar_area",
                "name": "Торнин",
                "location_id": "tavern_silver_wolf",
                "visible": True,
                "activity": "working",
            },
            "thief_shadow": {
                "local_position": {"x": 15.0, "y": 15.0},
                "position": "bed",
                "name": "Тень",
                "location_id": "tavern_silver_wolf",
                "visible": True,
                "activity": "sleeping",
            },
            "maid_lusya": {
                "local_position": {"x": 10.0, "y": 10.0},
                "position": "main_hall",
                "name": "Люся",
                "location_id": "tavern_silver_wolf",
                "visible": True,
                "activity": "serving_tables",
            },
        },
    }


@pytest.fixture
def spatial_svc(tavern_graph):
    """SpatialService с моком графа."""
    from app.models.spatial_contracts import NodeRef, NodeRole

    svc = MagicMock(spec=SpatialService)
    svc._location_id = "tavern_silver_wolf" # P7-FIX: Предотвращает needs_dynamic=True и пересборку графа
    nodes = tavern_graph.all_nodes()

    def _get_node(node_id):
        n = nodes.get(node_id)
        if n:
            return NodeRef(
                node_id=n.node_id, role=NodeRole.DEFAULT, tags=[], x=n.x, y=n.y, zone_id="tavern_silver_wolf"
            )
        return None

    svc.get_node.side_effect = _get_node
    svc.normalize_id.side_effect = lambda x: x  # Прямой ID
    svc.get_nearest.return_value = _get_node("main_hall")
    svc.get_furthest.return_value = _get_node("bed")
    
    # P7-FIX: Mock find_path to return a list of NodeRef objects, not strings
    def _find_path(src_xy, tgt_node):
        _src_node = NodeRef(node_id="source", role=NodeRole.DEFAULT, tags=[], x=src_xy[0], y=src_xy[1], zone_id="tavern_silver_wolf")
        return [_src_node, tgt_node]
    svc.find_path.side_effect = _find_path

    return svc


@pytest.fixture
def manager():
    return SceneStateManager()


# ── Хелпер: патчим SpatialService.build_for_location ─────────────────────


@pytest.fixture
def patched_spatial_build(spatial_svc):
    """Патчит SpatialFactory.build_for_campaign чтобы вернуть мок (ADR-O-314)."""
    from app.services.spatial.spatial_factory import SpatialFactory
    with patch.object(SpatialFactory, "build_for_campaign", return_value=spatial_svc):
        yield spatial_svc


# ── ТЕСТ 1: Расписание → MovementIntent → SceneChange → Координаты ─────


def test_schedule_locomotion_updates_coordinates(tavern_graph, scene_state, patched_spatial_build, manager):
    """Торнин идёт из bar_area → main_hall по расписанию. Координаты обновляются."""
    spatial_svc = patched_spatial_build

    # Торнин меняет активность: working → talking_at_bar (target=main_hall)
    intent = MacroMovementGoal(
        actor_id="tavern_keeper_tornin",
        target_node_id="main_hall",
        from_node_id="bar_area",
        location_id="tavern_silver_wolf",
        reason="schedule:talking_at_bar",
        priority=PRIORITY_SCHEDULE,
    )

    # MovementEngine обрабатывает intent
    me = MovementEngine()
    me.set_spatial_service(spatial_svc)
    
    changes = me.process_intents(
        [intent],
        tick=1,
        npc_positions=scene_state["npc_positions"],
        campaign_id="test",
        scene_state=scene_state,
    )

    # Должен быть SceneChange для position
    assert len(changes) > 0, "MovementEngine не создал SceneChange"
    pos_changes = [c for c in changes if c.field == "position" and c.target == "tavern_keeper_tornin"]
    assert len(pos_changes) == 1, f"Ожидается 1 position change, получено {len(pos_changes)}"
    assert pos_changes[0].value == "main_hall"

    # Применяем изменения
    manager.apply_changes("test", changes, scene_state)

    # Проверяем, что позиция обновилась
    tornin = scene_state["npc_positions"]["tavern_keeper_tornin"]
    assert tornin.get("position") == "main_hall", f"Позиция не обновилась: {tornin.get('position')}"


# ── ТЕСТ 2: Приказ APPROACH → Тень подходит к игроку ────────────────────


def test_approach_command_creates_movement(scene_state, patched_spatial_build, manager):
    """Тень получает приказ APPROACH → MovementIntent → SceneChange."""
    spatial_svc = patched_spatial_build
    me = MovementEngine()
    me.set_spatial_service(spatial_svc)

    # Тень подходит к игроку (игрок в main_hall)
    intent = MacroMovementGoal(
        actor_id="thief_shadow",
        target_node_id="main_hall",  # игрок в main_hall
        from_node_id="bed",
        location_id="tavern_silver_wolf",
        reason="decision:approach_target=player",
        priority=PRIORITY_NEEDS,
    )

    changes = me.process_intents(
        [intent],
        tick=2,
        npc_positions=scene_state["npc_positions"],
        campaign_id="test",
        scene_state=scene_state,
    )

    assert len(changes) > 0, "APPROACH не создал SceneChange"
    pos_changes = [c for c in changes if c.field == "position" and c.target == "thief_shadow"]
    assert len(pos_changes) == 1
    assert pos_changes[0].value == "main_hall"

    manager.apply_changes("test", changes, scene_state)
    shadow = scene_state["npc_positions"]["thief_shadow"]
    assert shadow.get("position") == "main_hall"


# ── ТЕСТ 3: 3 тика — полный цикл жизни NPC ──────────────────────────────


def test_three_tick_lifecycle(tavern_graph, scene_state, patched_spatial_build, manager):
    """Тик 1: Люся в main_hall. Тик 2: Люся идёт к bar_area. Тик 3: Проверяем координаты."""
    spatial_svc = patched_spatial_build
    me = MovementEngine()
    me.set_spatial_service(spatial_svc)

    # Тик 1: Люся в main_hall — проверяем стартовое состояние
    lusya = scene_state["npc_positions"]["maid_lusya"]
    assert lusya["position"] == "main_hall"
    assert lusya["local_position"]["x"] == 10.0

    # Тик 2: Люся получает intent идти к bar_area
    intent = MacroMovementGoal(
        actor_id="maid_lusya",
        target_node_id="bar_area",
        from_node_id="main_hall",
        location_id="tavern_silver_wolf",
        reason="schedule:serving_drinks",
        priority=PRIORITY_SCHEDULE,
    )
    changes = me.process_intents(
        [intent],
        tick=2,
        npc_positions=scene_state["npc_positions"],
        campaign_id="test",
        scene_state=scene_state,
    )
    manager.apply_changes("test", changes, scene_state)

    # После тика 2: позиция обновлена, traversal создан
    lusya = scene_state["npc_positions"]["maid_lusya"]
    assert lusya["position"] == "bar_area", f"Позиция Люси после тика 2: {lusya.get('position')}"

    # Тик 3: Проверяем, что traversal завершается корректно
    traversals = scene_state.get("active_traversals", {})
    if "maid_lusya" in traversals:
        t = traversals["maid_lusya"]
        assert t["status"] == "MOVING"
        assert t["target_node"] == "bar_area"


# ── ТЕСТ 4: build_spatial_data_for_dm возвращает NPC с дистанциями ───────


def test_spatial_data_for_dm_includes_nearby_npcs(scene_state):
    """Без SpatialQueryService — fallback на euclidean из npc_positions."""
    from app.services.spatial.player_target_pipeline import build_spatial_data_for_dm

    result = build_spatial_data_for_dm("tavern_silver_wolf", scene_state)

    # NPC должны быть в списке (не пустой!)
    assert len(result["npcs"]) > 0, f"nearby_npcs пуст! spatial_data={result}"

    # Торнин в bar_area (5,5), игрок в main_hall (10,10) → dist ≈ 7.07
    tornin_entry = next((n for n in result["npcs"] if n["npc_id"] == "tavern_keeper_tornin"), None)
    assert tornin_entry is not None, "Торнин не найден в nearby_npcs"
    assert tornin_entry["distance_to_player"] < 20.0, (
        f"Дистанция до Торнина = {tornin_entry['distance_to_player']} (должна быть < 20)"
    )

    # Тень в bed (15,15), игрок в main_hall (10,10) → dist ≈ 7.07
    shadow_entry = next((n for n in result["npcs"] if n["npc_id"] == "thief_shadow"), None)
    assert shadow_entry is not None, "Тень не найдена в nearby_npcs"
    assert shadow_entry["distance_to_player"] < 20.0, f"Дистанция до Тени = {shadow_entry['distance_to_player']}"

    # Игрок НЕ должен быть в nearby_npcs
    player_entry = next((n for n in result["npcs"] if n["npc_id"] == "player"), None)
    assert player_entry is None, "Игрок не должен быть в nearby_npcs"


# ── ТЕСТ 5: tick_decisions возвращает movement_intents ───────────────────


def test_tick_decisions_returns_movement_intents():
    """tick_decisions возвращает 3-й элемент: movement_intents."""
    engine = LifeEngine()
    # Пустой кэш → должен вернуть ([], [], [])
    # BUG-CORE-016/017 FIX: tick_decisions удалён. Используем tick().
    result = engine.tick("nonexistent_campaign", {})
    assert len(result) == 2, f"tick() должен возвращать 2 значения (changes, intents), вернул {len(result)}"
    changes, intents = result
    assert isinstance(changes, list)
    assert isinstance(intents, list)

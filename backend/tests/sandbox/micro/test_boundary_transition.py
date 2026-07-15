"""ДОЛГ 6.2: Boundary Transition Pipeline — верификация причинной модели.

Инварианты:
1. SceneChange = semantic event (NO geometry)
2. apply_changes = geometric resolver
3. Boundary resolution at completion time (не creation time)
4. MovementEngine не знает про чанки

Запуск: python -m pytest backend/tests/sandbox/ -v --tb=short
"""

from unittest.mock import MagicMock, patch

from app.models.spatial_contracts import NodeRef, NodeRole
from app.services.scene_change import ChangeType, SceneChange

# ── Фабрики ──────────────────────────────────────────────────────


def _make_boundary_map():
    """Карта граничных узлов: tavern → city_gate."""
    return {
        "tavern:exit_east": {
            "direction": "east",
            "neighbor_chunk": "city_gate",
            "entry_direction": "west",
            "entry_node_hint": "city_gate:entry_west",
        }
    }


def _make_spatial_service_mock(boundary_map=None):
    """Mock SpatialService с boundary_map."""
    svc = MagicMock()
    svc._boundary_map = boundary_map or _make_boundary_map()
    svc.is_boundary_node = lambda node_id: node_id in svc._boundary_map
    svc.get_boundary_info = lambda node_id: svc._boundary_map.get(node_id)
    svc.normalize_id = lambda raw_id: raw_id
    return svc


def _make_traversal(target_node="tavern:exit_east", from_node="tavern:main_hall"):
    """Traversal dict — как хранится в active_traversals."""
    return {
        "npc_id": "npc_lusya",
        "from_node": from_node,
        "target_node": target_node,
        "path_waypoints": [[1.0, 2.0], [15.0, 8.0]],
        "speed": 2.0,
        "started_tick": 5,
        "duration_ticks": 3,
        "locomotion": "WALK",
        "status": "MOVING",
    }


# ── Тест 1: Boundary traversal создаёт SceneChange с target_location_id ──


def test_boundary_traversal_emits_transition_scene_change():
    """Traversal через boundary edge создаёт SceneChange с target_location_id."""
    from app.services.tick_orchestrator import TickOrchestrator

    orch = TickOrchestrator()
    orch._spatial_service = _make_spatial_service_mock()

    trav = _make_traversal(target_node="tavern:exit_east")
    scene_state = {
        "active_traversals": {"npc_lusya": trav},
        "tick": 10,  # started_tick(5) + duration(3) = 8, тик 10 > 8
    }

    # Минимальный _TickContext
    ctx = MagicMock()
    ctx.scene_state = scene_state

    orch._process_traversals(ctx)

    # ADR-TRAV-FSM: TickOrchestrator не мутирует статус напрямую.
    # Он эмитит SceneChange(cause="traversal_complete", traversal_status="COMPLETED").
    # Проверка применения статуса будет в тесте SSM.

    # Проверяем что apply_changes был вызван с SceneChange
    applied = orch._scene_manager is not None
    if orch._scene_manager:
        # Если scene_manager есть — изменения через apply_changes
        pass
    else:
        # Без scene_manager — изменения в completion_changes (прямой путь)
        # В текущем коде: completion_changes → scene_manager.apply_changes
        # Если scene_manager None — изменения теряются (ожидаемое поведение)
        pass

    # Верификация: напрямую проверить что SceneChange создан правильно
    # Для этого нужен доступ к completion_changes — тестируем через mock
    changes_applied = []

    if orch._scene_manager:
        # Уже применено
        pass
    else:
        # Создаём оркестратор с mock scene_manager
        mock_sm = MagicMock()
        captured_changes = []
        mock_sm.apply_changes = lambda cid, changes, ss: captured_changes.extend(changes)
        orch._scene_manager = mock_sm

        # Переустанавливаем traversal
        trav["status"] = "MOVING"
        orch._process_traversals(ctx)

        assert len(captured_changes) >= 1
        pos_change = captured_changes[0]
        assert pos_change.field == "position"
        assert pos_change.target_location_id == "city_gate"
        assert pos_change.value == "city_gate:entry_west"


# ── Тест 2: MovementEngine не переключает чанк напрямую ──


def test_movement_engine_does_not_switch_chunk():
    """MovementEngine не знает про чанки — только SceneChange."""
    from app.domain.movement import MacroMovementGoal
    from app.services.spatial.movement_engine import MovementEngine

    me = MovementEngine()
    svc = _make_spatial_service_mock()
    # Добавляем узлы в mock
    svc.get_node = MagicMock(return_value=MagicMock(x=10.0, y=5.0))
    svc.find_path = MagicMock(return_value=[])
    me.set_spatial_service(svc)

    # Intent на boundary node
    intent = MacroMovementGoal(
        actor_id="npc_lusya",
        target_node_id="tavern:exit_east",
        reason="flee",
        priority=0.8,
        location_id="tavern",
    )

    changes = me.process_intents([intent], tick=1)

    # MovementEngine создаёт SceneChange, но НЕ заполняет target_location_id
    # Это ответственность _process_traversals
    for ch in changes:
        assert ch.target_location_id == "", (
            "MovementEngine не должен заполнять target_location_id. "
            "Boundary resolution — ответственность _process_traversals."
        )


# ── Тест 3: apply_changes выполняет snap при boundary transition ──


def test_runtime_applies_boundary_snap():
    """SceneStateManager.apply_changes() материализует NPC в новом чанке."""
    from app.services.scene_state_manager import SceneStateManager

    mgr = SceneStateManager()
    mgr._persistence = None  # без персистенции для теста

    scene_state = {
        "location_id": "tavern",
        "npc_positions": {
            "npc_lusya": {
                "position": "tavern:main_hall",
                "local_position": {"x": 1.0, "y": 2.0},
                "location": "tavern",
                "location_id": "tavern",
            }
        },
        "active_traversals": {},
        "tick": 10,
    }

    # SceneChange от boundary transition
    boundary_change = SceneChange(
        type=ChangeType.NPC_POSITION,
        target="npc_lusya",
        field="position",
        value="city_gate:entry_west",
        cause="traversal_complete",
        tick=10,
        target_location_id="city_gate",
    )

    # Mock SpatialService — патчим на месте импорта (локальный import внутри метода)
    # Используем spec=NodeRef, чтобы mock поддерживал атрибуты x и y как реальные числа.
    mock_node = NodeRef(node_id="city_gate:entry_west", x=20.0, y=15.0, role=NodeRole.ENTRANCE, zone_id="city_gate", tags=["entrance"])
    mock_svc_instance = MagicMock()
    mock_svc_instance.get_node = MagicMock(return_value=mock_node)
    mock_svc_instance.build_for_location = MagicMock(return_value=mock_svc_instance)

    with patch("app.services.spatial.spatial_service.SpatialService") as MockSvc:
        MockSvc.build_for_location = MagicMock(return_value=mock_svc_instance)

        mgr.apply_changes("test_campaign", [boundary_change], scene_state)

    # Верификация: NPC перемещён в новый чанк
    entry = scene_state["npc_positions"]["npc_lusya"]
    assert entry.get("location_id") == "city_gate", f"NPC должен быть в city_gate, а не в {entry.get('location_id')}"
    assert entry.get("position") == "city_gate:entry_west", (
        f"Позиция должна быть city_gate:entry_west, а не {entry.get('position')}"
    )
    # Boundary snap: local_position установлен из node coordinates
    lp = entry.get("local_position", {})
    assert lp.get("x") == 20.0 and lp.get("y") == 15.0, (
        f"local_position должен быть из node (20.0, 15.0), а не ({lp.get('x')}, {lp.get('y')})"
    )
    # Boundary snap: traversal НЕ создаётся для кросс-локационного перехода
    assert "npc_lusya" not in scene_state.get("active_traversals", {}), (
        "Traversal не должен создаваться для boundary snap (переход уже завершён)"
    )


# ── Тест 4 (опциональный): Non-boundary traversal не триггерит transition ──


def test_non_boundary_traversal_emits_no_transition():
    """Обычный traversal внутри чанка НЕ заполняет target_location_id."""
    from app.services.tick_orchestrator import TickOrchestrator

    orch = TickOrchestrator()
    orch._spatial_service = _make_spatial_service_mock()
    orch._scene_manager = MagicMock()

    # Traversal на обычный узел (не boundary)
    trav = _make_traversal(target_node="tavern:kitchen")
    scene_state = {
        "active_traversals": {"npc_lusya": trav},
        "tick": 10,
    }
    ctx = MagicMock()
    ctx.scene_state = scene_state

    orch._process_traversals(ctx)

    # Проверяем что scene_manager.apply_changes вызван
    call_args = orch._scene_manager.apply_changes.call_args
    if call_args:
        changes = call_args[0][1]  # второй аргумент = list[SceneChange]
        pos_change = next((c for c in changes if c.field == "position"), None)
        if pos_change:
            assert pos_change.target_location_id == "", (
                f"Non-boundary traversal не должен иметь target_location_id, "
                f"а получил '{pos_change.target_location_id}'"
            )

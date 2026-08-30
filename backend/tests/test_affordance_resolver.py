"""
path: backend/tests/test_affordance_resolver.py
Назначение: W2 (ADR-O-372) — контрактные тесты AffordanceResolver:
    замыкание реестров (паттерн INV-INTENT-EVENT-COMPLETENESS), таблица
    v1 (ТЗ §19.2 + В10-правка), body-гейты (В9), порог смежности,
    HOLDER/OCCUPANT-гейты, purity/детерминизм, W3-ревалидация, краевые.
    Объекты — через фабрики (§12.3/§13.4): build_world_object + доменный
    dataclass_replace; тела — через build_body_state_view из РЕАЛЬНЫХ
    словарей BODY_STATE_HEALTHY / BODY_STATE_DISABLED_DATA (§12.4).
Зависимости: pytest, app.domain, app.services.world, app.models
Основные сущности: (тесты)
"""
import dataclasses

import pytest
from app.domain.body_state_view import build_body_state_view
from app.domain.semantic_action import WorldActionType
from app.domain.world_object import build_world_object, dataclass_replace
from app.models.npc_state import BODY_STATE_DISABLED_DATA, BODY_STATE_HEALTHY
from app.services.world.affordance_resolver import (
    _AFFORDANCE_TABLE,
    PRECONDITION_REGISTRY,
    AffordanceResolver,
    compute_affordances,
    effective_state,
)

# ── Фикстуры (реальные данные, §12.4) ────────────────────────────────

_NPC = "npc_test"
_NPC_OTHER = "npc_other"
_HERE = (5.0, 3.0)
_NEAR = (5.5, 3.0)  # дистанция 0.5 ≤ 1.5
_FAR = (9.0, 3.0)   # дистанция 4.0 > 1.5


def _healthy(npc_id: str = _NPC):
    return build_body_state_view(dict(BODY_STATE_HEALTHY), npc_id)


def _door(state: str = "CLOSED"):
    return build_world_object("door_1", "door", "tavern", _NEAR, state)


def _chair():
    return build_world_object("chair_1", "chair", "tavern", _NEAR)


def _container(state: str = "CLOSED"):
    return build_world_object("chest_1", "container", "tavern", _NEAR, state)


def _types(actions) -> set:
    return {a.action_type for a in actions}


# ── 1. Замыкание реестров (структурные) ──────────────────────────────


def test_precondition_registry_closure():
    """Каждый предикат таблицы зарегистрирован; реестр = ровно 7 имён v1."""
    for row in _AFFORDANCE_TABLE.values():
        for action in row:
            for p in action.preconditions:
                assert p.predicate in PRECONDITION_REGISTRY, p.predicate
    assert len(PRECONDITION_REGISTRY) == 7


def test_base_trio_and_state_is_on_every_action():
    """В9 + ревалидация W3: базовая тройка и STATE_IS на каждом действии."""
    for row in _AFFORDANCE_TABLE.values():
        for action in row:
            names = [p.predicate for p in action.preconditions]
            assert "IS_ALIVE" in names
            assert "IS_CONSCIOUS" in names
            assert "IS_CAPABLE" in names
            assert "STATE_IS" in names


def test_world_object_has_no_stored_affordances():
    """ADR-O-371: производная не хранится на объекте."""
    assert not any(
        f.name == "affordances" for f in dataclasses.fields(_chair())
    )


def test_semantic_action_field_set_closed():
    """W0-инвариант: поле-сет SemanticAction закрыт (ноль presentation)."""
    expected = {
        "action_type",
        "target_object_id",
        "target_location_id",
        "target_attachment_slot",
        "preconditions",
    }
    for row in _AFFORDANCE_TABLE.values():
        for action in row:
            assert {f.name for f in dataclasses.fields(action)} == expected


def test_reserved_actions_never_issued():
    """INSERT/REMOVE_ITEM — в enum, но таблицей v1 не выдаются (W3)."""
    for row in _AFFORDANCE_TABLE.values():
        issued = _types(row)
        assert WorldActionType.INSERT_ITEM not in issued
        assert WorldActionType.REMOVE_ITEM not in issued


# ── 2. Таблица v1 (ТЗ §19.2 + В10-правка) ────────────────────────────


def test_door_closed_full_set():
    actions = AffordanceResolver.resolve(_door("CLOSED"), _healthy(), _HERE)
    assert _types(actions) == {
        WorldActionType.OPEN,
        WorldActionType.KNOCK,
        WorldActionType.LOCK,
        WorldActionType.UNLOCK,
        WorldActionType.BREAK,
    }


def test_door_open_pair_rule():
    """В10-правка: FSM door допускает оба перехода → пара OPEN+CLOSE."""
    actions = AffordanceResolver.resolve(_door("OPEN"), _healthy(), _HERE)
    assert _types(actions) == {
        WorldActionType.OPEN,
        WorldActionType.CLOSE,
        WorldActionType.PASS_THROUGH,
        WorldActionType.LOCK,
    }


def test_container_open_pair_rule_and_reserved():
    """В10-правка: пара OPEN+CLOSE; INSERT/REMOVE зарезервированы (W3)."""
    actions = AffordanceResolver.resolve(_container("OPEN"), _healthy(), _HERE)
    assert _types(actions) == {WorldActionType.OPEN, WorldActionType.CLOSE}


def test_door_locked_and_broken():
    assert _types(
        AffordanceResolver.resolve(_door("LOCKED"), _healthy(), _HERE)
    ) == {WorldActionType.UNLOCK, WorldActionType.BREAK, WorldActionType.KNOCK}
    assert _types(
        AffordanceResolver.resolve(_door("BROKEN"), _healthy(), _HERE)
    ) == {WorldActionType.REPAIR, WorldActionType.PASS_THROUGH}


def test_chair_available():
    actions = AffordanceResolver.resolve(_chair(), _healthy(), _HERE)
    assert _types(actions) == {
        WorldActionType.SIT,
        WorldActionType.TAKE,
        WorldActionType.MOVE,
        WorldActionType.KICK,
    }


def test_chair_occupied_stand_up_scoped_to_occupant():
    chair = dataclass_replace(_chair(), occupancy=_NPC)
    mine = AffordanceResolver.resolve(chair, _healthy(_NPC), _HERE)
    other = AffordanceResolver.resolve(chair, _healthy(_NPC_OTHER), _HERE)
    assert WorldActionType.STAND_UP in _types(mine)
    assert WorldActionType.STAND_UP not in _types(other)
    assert WorldActionType.KICK in _types(other)


def test_chair_held_scoped_to_holder():
    chair = dataclass_replace(_chair(), holder=_NPC)
    mine = AffordanceResolver.resolve(chair, _healthy(_NPC), _FAR)
    other = AffordanceResolver.resolve(chair, _healthy(_NPC_OTHER), _HERE)
    assert _types(mine) == {
        WorldActionType.PLACE,
        WorldActionType.DROP,
        WorldActionType.THROW,
    }
    # HOLDER_IS ложен; смежность в HELD честно False → пусто даже вплотную
    assert other == ()


# ── 3. Body-гейты (В9) и sentinel ───────────────────────────────────


def test_unconscious_npc_gets_nothing():
    body = build_body_state_view(
        {**BODY_STATE_HEALTHY, "consciousness": 0.05}, _NPC
    )
    assert AffordanceResolver.resolve(_door(), body, _HERE) == ()
    assert AffordanceResolver.resolve(_chair(), body, _HERE) == ()


def test_dead_npc_gets_nothing():
    body = build_body_state_view(
        {**BODY_STATE_HEALTHY, "life_status": "DEAD"}, _NPC
    )
    assert AffordanceResolver.resolve(_door(), body, _HERE) == ()


def test_incapacitated_npc_gets_nothing():
    body = build_body_state_view({**BODY_STATE_HEALTHY, "pain": 80.0}, _NPC)
    assert AffordanceResolver.resolve(_container(), body, _HERE) == ()


def test_disabled_sentinel_gets_nothing():
    """Реальный NPIC-sentinel: оси False через сами функции ADR-123."""
    body = build_body_state_view(dict(BODY_STATE_DISABLED_DATA), _NPC)
    assert not body.is_conscious
    assert not body.is_capable
    assert AffordanceResolver.resolve(_door(), body, _HERE) == ()


# ── 4. Смежность (В6) и краевые ──────────────────────────────────────


def test_adjacency_threshold_boundary():
    door = build_world_object("door_2", "door", "tavern", (6.5, 3.0), "CLOSED")
    # дистанция ровно 1.5 → включительно
    assert WorldActionType.OPEN in _types(
        AffordanceResolver.resolve(door, _healthy(), _HERE)
    )
    door_far = build_world_object(
        "door_3", "door", "tavern", (6.51, 3.0), "CLOSED"
    )
    assert AffordanceResolver.resolve(door_far, _healthy(), _HERE) == ()


def test_unknown_archetype_and_state_yield_empty():
    lever = build_world_object("lever_1", "lever", "tavern", _NEAR, "CLOSED")
    assert AffordanceResolver.resolve(lever, _healthy(), _HERE) == ()
    ajar = build_world_object("door_9", "door", "tavern", _NEAR, "AJAR")
    assert AffordanceResolver.resolve(ajar, _healthy(), _HERE) == ()


# ── 5. Purity / детерминизм / W3-ревалидация ────────────────────────


def test_resolve_deterministic_and_pure():
    door = _door()
    body = _healthy()
    a1 = AffordanceResolver.resolve(door, body, _HERE)
    assert a1 == compute_affordances(door, body, _HERE)
    assert a1 == AffordanceResolver.resolve(door, body, _HERE)


def test_preconditions_enable_w3_revalidation():
    """STATE_IS в кортеже ловит устаревшее действие (механизм W3)."""
    door = _door("CLOSED")
    (open_action,) = [
        a
        for a in AffordanceResolver.resolve(door, _healthy(), _HERE)
        if a.action_type is WorldActionType.OPEN
    ]
    assert open_action.target_object_id == "door_1"
    # Мир изменился (W3-writer открыл дверь): устаревший OPEN обязан провалиться
    opened = dataclass_replace(door, state="OPEN")
    for p in open_action.preconditions:
        if p.predicate == "STATE_IS":
            verdict = PRECONDITION_REGISTRY[p.predicate](
                opened, _healthy(), _HERE, p.args
            )
            assert verdict is False


def test_effective_state_chair_derivation():
    assert effective_state(_chair()) == "AVAILABLE"
    assert effective_state(dataclass_replace(_chair(), occupancy=_NPC)) == "OCCUPIED"
    assert effective_state(dataclass_replace(_chair(), holder=_NPC)) == "HELD"
    broken = build_world_object("c2", "chair", "tavern", _NEAR, "BROKEN")
    assert effective_state(broken) == "BROKEN"


def test_open_close_pair_rule_formal():
    """В10-правка (формально): паре в состоянии OPEN обладают только
    архетипы, чей FSM (ТЗ §22.1) допускает оба перехода (door, container)."""
    assert WorldActionType.OPEN in _types(_AFFORDANCE_TABLE[("door", "OPEN")])
    assert WorldActionType.CLOSE in _types(_AFFORDANCE_TABLE[("door", "OPEN")])
    assert WorldActionType.OPEN in _types(
        _AFFORDANCE_TABLE[("container", "OPEN")]
    )
    assert WorldActionType.CLOSE in _types(
        _AFFORDANCE_TABLE[("container", "OPEN")]
    )
    # chair-FSM не допускает OPEN/CLOSE переходов → правило не применимо
    for (arch, _st), row in _AFFORDANCE_TABLE.items():
        if arch == "chair":
            assert WorldActionType.OPEN not in _types(row)
            assert WorldActionType.CLOSE not in _types(row)


def test_body_view_factory_rejects_empty_body():
    with pytest.raises(ValueError):
        build_body_state_view({}, _NPC)
    with pytest.raises(ValueError):
        build_body_state_view(None, _NPC)


def test_world_action_type_members_distinct():
    """Регрессия S231-инцидента: stranded-декоратор @dataclass(frozen=True)
    на enum (однострочный якорь патча перед декорированным классом) генерил
    zero-field dataclass __eq__ (всегда True) и __hash__ (константа) —
    множества членов схлопывались: set-equality ложно PASS, not-in ложно
    FAIL. Гвард: реестр — 19 РАЗЛИЧНЫХ членов."""
    members = list(WorldActionType)
    assert len(members) == 19
    assert len(set(members)) == 19
    assert WorldActionType.OPEN != WorldActionType.KICK
    assert WorldActionType.INSERT_ITEM != WorldActionType.OPEN
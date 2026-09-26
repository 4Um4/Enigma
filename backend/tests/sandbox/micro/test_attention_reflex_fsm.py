# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_attention_reflex_fsm.py
Назначение: P2-гейт — FSM внимания: обнаружение→ориентация (реальный SceneChange),
    выравненный вход (ORIENTED без SceneChange), периферия, стационарность,
    transition-gating, LOST-заморозка и GC, симметрия (NPC↔NPC, player как
    субъект и наблюдатель), вектор в окне (субстрат P3-MATH). Стены не
    тестируются (LOS-блок — SUPERBOX P2 на реальной карте).
Зависимости: app.domain.tick.create_tick_state, app.services.npc.attention_reflex.
Основные сущности: pytest-тесты compute_attention_pass.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_attention_reflex_fsm.py -v; cd ..
"""
import math

import pytest

from app.domain.tick import create_tick_state
from app.services.npc import attention_reflex as ar


@pytest.fixture(autouse=True)
def _cognition_v0_on(monkeypatch):
    # Флаг читается при импорте (прецедент commitment_arbiter.py:32-34:
    # «тесты monkeypatch-ят атрибут модуля напрямую»). Патчим attention_reflex,
    # т.к. binding произведён импортом в модуль.
    monkeypatch.setattr(ar, "COGNITION_V0", True)


def _pos(x: float, y: float, heading: float = 0.0) -> dict:
    return {"local_position": {"x": x, "y": y}, "body_heading": heading}


def _raw(npc_id: str) -> dict:
    # is_conscious({}) == True (vital_state:161) — сознание по умолчанию.
    return {"npc_id": npc_id, "body_state": {}}


def _state(positions, raws, traversals=None, prev=None, tick=100):
    return create_tick_state(
        tick_id=tick,
        campaign_id="t",
        scene_state={
            "npc_positions": positions,
            "active_traversals": traversals or {},
        },
        all_npcs_raw=raws,
        effective_drives_map={},
        interventions=[],
        attention_states_map=prev or {},
    )


def test_entry_orients_with_real_scenechange() -> None:
    # Орм смотрит на восток, Люся в FOV, но НЕ в центре взгляда:
    # азимут atan2(3,4) ≈ 0.6435 ≥ порога → нужен физический поворот.
    st = _state(
        {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(4, 3)},
        [_raw("orm"), _raw("maid_lusya")],
    )
    delta, changes = ar.compute_attention_pass(st)
    assert delta["orm"]["maid_lusya"]["phase"] == "oriented"
    assert len(changes) == 1
    ch = changes[0]
    assert ch.target == "orm" and ch.field == "body_heading"
    assert ch.value == pytest.approx(math.atan2(3, 4), abs=1e-6)
    assert str(ch.cause).startswith("attention_orient:")


def test_aligned_entry_orients_without_scenechange() -> None:
    # Субъект в центре взгляда: внимание ориентировано, тело не поворачиваем.
    st = _state(
        {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(5, 0)},
        [_raw("orm"), _raw("maid_lusya")],
    )
    delta, changes = ar.compute_attention_pass(st)
    assert delta["orm"]["maid_lusya"]["phase"] == "oriented"
    assert changes == []
    win = delta["orm"]["maid_lusya"]["observation_window"]
    assert len(win) == 1
    assert win[0][4] == pytest.approx(5.0) and win[0][5] == pytest.approx(0.0)


def test_behind_and_far_not_detected() -> None:
    # Сценарий C с ОБЕИХ сторон: Орм не видит Люсю за спиной (6м > периферии),
    # Люся (смотрит на запад) не видит Орма за своей спиной.
    st = _state(
        {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(-6, 0, math.pi)},
        [_raw("orm"), _raw("maid_lusya")],
    )
    delta, changes = ar.compute_attention_pass(st)
    assert delta == {} and changes == []


def test_behind_but_close_peripheral_detect() -> None:
    # Внезапное появление вплотную за спиной — периферия.
    st = _state(
        {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(-2.0, 0)},
        [_raw("orm"), _raw("maid_lusya")],
    )
    delta, changes = ar.compute_attention_pass(st)
    assert delta["orm"]["maid_lusya"]["phase"] == "oriented"
    assert changes[0].value == pytest.approx(math.pi, abs=1e-6)


def test_transition_gating_no_repeat() -> None:
    p1 = {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(4, 3)}
    raws = [_raw("orm"), _raw("maid_lusya")]
    delta1, ch1 = ar.compute_attention_pass(_state(p1, raws, tick=100))
    assert len(ch1) == 1
    prev = {"orm": delta1["orm"]}
    # Тик 2: heading Орма = применённый orient (так делает SSM), Люся ближе
    # ПО ТОМУ ЖЕ лучу → выравнен → повторного поворота нет.
    _h = math.atan2(3, 4)
    p2 = {"orm": _pos(0, 0, _h), "maid_lusya": _pos(3.2, 2.4)}
    delta2, ch2 = ar.compute_attention_pass(_state(p2, raws, prev=prev, tick=101))
    assert ch2 == []
    assert delta2["orm"]["maid_lusya"]["phase"] == "oriented"
    assert len(delta2["orm"]["maid_lusya"]["observation_window"]) == 2


def test_lost_freezes_and_gc_removes() -> None:
    raws = [_raw("orm"), _raw("maid_lusya")]
    delta1, _ = ar.compute_attention_pass(
        _state({"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(5, 0)}, raws, tick=100)
    )
    prev = {"orm": delta1["orm"]}
    delta2, ch2 = ar.compute_attention_pass(
        _state(
            {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(50, 0)},
            raws,
            prev=prev,
            tick=101,
        )
    )
    assert ch2 == []
    assert delta2["orm"]["maid_lusya"]["phase"] == "lost"
    assert len(delta2["orm"]["maid_lusya"]["observation_window"]) == 1  # заморожено, не стёрто
    delta3, _ = ar.compute_attention_pass(
        _state(
            {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(50, 0)},
            raws,
            prev={"orm": delta2["orm"]},
            tick=101 + 31,
        )
    )
    assert delta3["orm"]["maid_lusya"] is None


def test_moving_observer_detects_but_does_not_orient() -> None:
    st = _state(
        {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(5, 0)},
        [_raw("orm"), _raw("maid_lusya")],
        traversals={"orm": {"status": "MOVING"}},
    )
    delta, changes = ar.compute_attention_pass(st)
    assert delta["orm"]["maid_lusya"]["phase"] == "detected"
    assert changes == []  # heading принадлежит движению


def test_two_subjects_single_orient_nearest_wins() -> None:
    st = _state(
        {
            "orm": _pos(0, 0, 0.5),          # нужен поворот к обоим
            "near": _pos(3, 0.2, math.pi),   # ближайший
            "far": _pos(8, 0.4, math.pi),
        },
        [_raw("orm"), _raw("far"), _raw("near")],
    )
    delta, changes = ar.compute_attention_pass(st)
    orm_changes = [c for c in changes if c.target == "orm"]
    assert len(orm_changes) == 1  # одно тело — один поворот за тик
    assert orm_changes[0].value == pytest.approx(math.atan2(0.2, 3), abs=1e-6)
    assert delta["orm"]["near"]["phase"] == "oriented"
    assert delta["orm"]["far"]["phase"] == "detected"


def test_player_is_ordinary_subject_and_npc_orients() -> None:
    st = _state(
        {"orm": _pos(0, 0, 0.0), "player": _pos(4, 3, 0.0)},
        [_raw("orm"), _raw("player")],
    )
    delta, changes = ar.compute_attention_pass(st)
    assert delta["orm"]["player"]["phase"] == "oriented"
    assert len(changes) == 1 and changes[0].target == "orm"
    assert changes[0].value == pytest.approx(math.atan2(3, 4), abs=1e-6)


def test_mutual_npc_npc_both_orient() -> None:
    # Лицом друг к другу, каждый свёрнут на 0.4 рад — обоим нужен поворот.
    st = _state(
        {"orm": _pos(0, 0, 0.4), "maid_lusya": _pos(6, 0, math.pi - 0.4)},
        [_raw("orm"), _raw("maid_lusya")],
    )
    delta, changes = ar.compute_attention_pass(st)
    targets = {c.target for c in changes}
    assert targets == {"orm", "maid_lusya"}
    assert len(changes) == 2


def test_player_observer_never_orients() -> None:
    # Ядро не вертит аватаром (ControlSource), внимание аватара симметрично.
    st = _state(
        {"player": _pos(0, 0, 0.0), "maid_lusya": _pos(5, 0)},
        [_raw("player"), _raw("maid_lusya")],
    )
    delta, changes = ar.compute_attention_pass(st)
    assert delta["player"]["maid_lusya"]["phase"] == "detected"
    assert all(c.target != "player" for c in changes)
# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_mutual_attention.py
Назначение: Сценарий Г (проверка на существующем коде, санкция Мастера):
    Люся наблюдает ПОВОРОТ Орма к себе → получает свидетельство взаимного
    внимания. Оба стационарны — вклад траектории исключён, различие
    treatment/control только в наблюдаемом subject_heading.
    Вскрывает дефект: turn-канал отбрасывается ранней stationary-веткой
    evidence_delta (RED до фикса = доказательство дефекта).
Зависимости: app.domain.tick, app.services.npc.attention_reflex.
Основные сущности: pytest-тесты.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_mutual_attention.py -v; cd ..
"""
import pytest

from app.domain.tick import create_tick_state
from app.services.npc import attention_reflex as ar


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(ar, "COGNITION_V0", True)


def _pos(x, y, heading):
    return {"local_position": {"x": x, "y": y}, "body_heading": heading}


def _raw(npc_id):
    return {"npc_id": npc_id, "body_state": {}}


def _evidence(result, observer, subject):
    snaps = [
        s
        for s in result.cognition_snapshots
        if s["observer_id"] == observer and s["subject_id"] == subject
    ]
    return snaps[-1]["evidence"] if snaps else 0.0


def _two_ticks(orm_heading_tick101):
    """Тик 100: Орм (0,0) смотрит на восток, Люся (0,−2.5) смотрит на него.
    Орм детектирует её периферией → ORIENT-эмиссия (heading → −π/2).
    Тик 101: мир применяется (treatment: −π/2; control: 0.0)."""
    raws = [_raw("orm"), _raw("maid_lusya")]
    p100 = {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(0, -2.5, 1.5708)}
    r1 = ar.run_attention_pass(
        create_tick_state(
            tick_id=100,
            campaign_id="t",
            scene_state={"npc_positions": p100, "active_traversals": {}},
            all_npcs_raw=raws,
            effective_drives_map={},
            interventions=[],
        )
    )
    p101 = {
        "orm": _pos(0, 0, orm_heading_tick101),
        "maid_lusya": _pos(0, -2.5, 1.5708),
    }
    return ar.run_attention_pass(
        create_tick_state(
            tick_id=101,
            campaign_id="t",
            scene_state={"npc_positions": p101, "active_traversals": {}},
            all_npcs_raw=raws,
            effective_drives_map={},
            interventions=[],
            attention_states_map={"orm": r1.attention_delta["orm"],
                                  "maid_lusya": r1.attention_delta["maid_lusya"]},
        )
    )


def test_turn_toward_accumulates_evidence_stationary_pair() -> None:
    # Treatment: Орм повернулся к Люсе (heading применён) → её E растёт.
    treat = _two_ticks(-1.5708)
    e_treat = _evidence(treat, "maid_lusya", "orm")
    # Control: Орм НЕ повернулся (heading остался) → E не растёт.
    ctrl = _two_ticks(0.0)
    e_ctrl = _evidence(ctrl, "maid_lusya", "orm")
    assert e_treat > e_ctrl, (
        f"turn-канал мёртв для стационарных пар: treat={e_treat}, ctrl={e_ctrl}"
    )
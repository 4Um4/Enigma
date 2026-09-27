# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_cognition_snapshot.py
Назначение: P3c-3-гейт — CognitionSnapshot: явное направление пары (Мастер 3.1),
    различимость слоёв наблюдаемое/выведенное/накопленное/интерпретация (3.2),
    surprise_used=None честно (3.3), probably_approaching_me из E, mode=None
    без S, to_dict-форма, producer=DATA-only.
Зависимости: app.domain.tick, app.services.npc.attention_reflex.
Основные сущности: pytest-тесты run_attention_pass.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_cognition_snapshot.py -v; cd ..
"""
import pytest

from app.domain.tick import create_tick_state
from app.services.npc import attention_reflex as ar


@pytest.fixture(autouse=True)
def _cognition_v0_on(monkeypatch):
    monkeypatch.setattr(ar, "COGNITION_V0", True)


def _pos(x, y, heading=0.0):
    return {"local_position": {"x": x, "y": y}, "body_heading": heading}


def _state(positions, raws, tick=100):
    return create_tick_state(
        tick_id=tick,
        campaign_id="t",
        scene_state={"npc_positions": positions, "active_traversals": {}},
        all_npcs_raw=raws,
        effective_drives_map={},
        interventions=[],
    )


def test_snapshot_pair_direction_and_layers() -> None:
    # NPC увидел подходящего игрока (не в центре взгляда) — снимок обязан
    # нести ЯВНОЕ направление пары и различимые слои (Мастер 3.1/3.2).
    st = _state(
        {"orm": _pos(0, 0, 0.0), "player": _pos(4, 3)},
        [{"npc_id": "orm", "body_state": {}}, {"npc_id": "player", "body_state": {}}],
    )
    res = ar.run_attention_pass(st)
    snaps = res.cognition_snapshots
    assert snaps, "снимок должен родиться при детекции"
    pair = [s for s in snaps if s["observer_id"] == "orm" and s["subject_id"] == "player"]
    assert pair, "направление пары явное: orm → player"
    s = pair[0]
    # Слои различимы:
    assert s["observed"]["phase"] == "oriented"
    assert s["observed"]["first_seen_tick"] == 100
    assert "speed" in s["inferred"] and "predicted_min_distance" in s["inferred"]
    assert isinstance(s["evidence"], float)
    # 3.3: surprise_used=None (не 0!) — «не можем оценить», S-ось до аудита.
    assert s["surprise_used"] is None
    # mode=None без S; probably_approaching_me вычислим без S.
    assert s["interpretation"]["mode"] is None
    assert s["interpretation"]["probably_approaching_me"] is False  # E≈0 на входе


def test_probably_approaching_gate_is_evidence_only() -> None:
    # Прямой подход в один тик не даёт порога (окно 1 точка — вывода нет);
    # гейт честно False. Гейт живёт на E, не на дистанции (дистанция мала бы).
    st = _state(
        {"orm": _pos(0, 0, 0.0), "player": _pos(1.0, 0.1)},
        [{"npc_id": "orm", "body_state": {}}, {"npc_id": "player", "body_state": {}}],
    )
    snaps = ar.run_attention_pass(st).cognition_snapshots
    p = [s for s in snaps if s["observer_id"] == "orm" and s["subject_id"] == "player"][0]
    assert p["observed"]["last_distance"] < 1.5  # близко — но…
    assert p["interpretation"]["probably_approaching_me"] is False  # …E ещё 0


def test_no_self_snapshot() -> None:
    # Инвариант: наблюдатель не снимает себя (домен-гвард + отсутствие пары).
    st = _state(
        {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(5, 0)},
        [{"npc_id": "orm", "body_state": {}}, {"npc_id": "maid_lusya", "body_state": {}}],
    )
    snaps = ar.run_attention_pass(st).cognition_snapshots
    assert all(s["observer_id"] != s["subject_id"] for s in snaps)


def test_snapshot_carries_prediction_error_on_history() -> None:
    # S-v2 проводка: на ВТОРОМ наблюдении (история ≥ 2) снимок несёт
    # численную prediction error; на входе (1 точка) — честный None
    # (§ENIGMA-003). Статус величины — «не Surprise» до санкции Мастера;
    # потребление в mode — отдельно.
    raws = [
        {"npc_id": "orm", "body_state": {}},
        {"npc_id": "maid_lusya", "body_state": {}},
    ]

    def _pass(tick_id: int, lusya_x: float, prev_map):
        return ar.run_attention_pass(
            create_tick_state(
                tick_id=tick_id,
                campaign_id="t",
                scene_state={
                    "npc_positions": {
                        "orm": _pos(0, 0, 0.0),
                        "maid_lusya": _pos(lusya_x, 0),
                    },
                    "active_traversals": {},
                },
                all_npcs_raw=raws,
                effective_drives_map={},
                interventions=[],
                attention_states_map=prev_map,
            )
        )

    # Минимальное окно вывода = 3 наблюдения: v̂ требует ≥2 ПРЕДЫДУЩИХ
    # точек (прогноз — только по истории, вердикт Мастера); текущая — факт.
    # Тики 1-2 честно несут None (§ENIGMA-003: вывода нет, не «S=0»).
    r1 = _pass(100, 5.0, {})  # entry: окно=1
    r2 = _pass(101, 4.0, {"orm": r1.attention_delta["orm"]})  # окно=2, история=1
    r3 = _pass(102, 3.0, {"orm": r2.attention_delta["orm"]})  # окно=3 → v̂

    p = [
        s
        for s in r3.cognition_snapshots
        if s["observer_id"] == "orm" and s["subject_id"] == "maid_lusya"
    ][0]
    assert p["surprise_used"] is not None  # история ≥2 → v̂ → ошибка выведена
    assert 0.0 <= p["surprise_used"] <= 1.0
    # Прямолинейное движение → прогноз точен → ошибка ≈ 0 (контрольный №1).
    assert p["surprise_used"] < 0.2


def test_snapshot_dict_json_safe() -> None:
    # Replay-сериализуемость: все значения — primitives (json.dumps молча не должен).
    import json

    st = _state(
        {"orm": _pos(0, 0, 0.0), "maid_lusya": _pos(4, 3)},
        [{"npc_id": "orm", "body_state": {}}, {"npc_id": "maid_lusya", "body_state": {}}],
    )
    snaps = ar.run_attention_pass(st).cognition_snapshots
    text = json.dumps(snaps, ensure_ascii=False)
    assert "orm" in text and "oriented" in text
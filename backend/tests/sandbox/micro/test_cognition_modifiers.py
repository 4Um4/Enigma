# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_cognition_modifiers.py
Назначение: P3d-гейт — producer транспорта: OFF={}, порог/гистерезис-рампа,
    disposition-различия (одинаковый вход — разные реакции), максимум по
    парам (толпа не суммируется), санкционная граница ±0.5, детерминизм,
    apply_modifiers 9-й канал (pure, аддитивный).
Зависимости: app.services.npc.attention_reflex, app.services.npc.attention_config,
    app.services.npc.decision_hub, app.domain.attention_dispositions.
Основные сущности: pytest-тесты.

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_cognition_modifiers.py -v; cd ..
"""
import pytest
from app.services.npc import attention_reflex as ar
from app.services.npc.decision_hub import DecisionHub


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(ar, "COGNITION_V0", True)


def _snap(evidence: float, approaching: bool = True) -> dict:
    return {
        "observer_id": "orm",
        "subject_id": "maid_lusya",
        "evidence": evidence,
        "interpretation": {"probably_approaching_me": approaching, "mode": None},
    }


def test_off_returns_empty() -> None:
    monkeypatch_flag = getattr(ar, "COGNITION_V0")
    try:
        ar.COGNITION_V0 = False
        assert ar.produce_cognition_modifiers([_snap(0.95)]) == {}
    finally:
        ar.COGNITION_V0 = monkeypatch_flag


def test_below_threshold_empty() -> None:
    assert ar.produce_cognition_modifiers([_snap(0.4)]) == {}


def test_hysteresis_half_ramp() -> None:
    mods = ar.produce_cognition_modifiers([_snap(0.5)])
    # Зона удержания [0.45, 0.6) → ramp=0.5 → base=0.25; вес нейтраль.
    assert mods["observe"] == pytest.approx(0.25 * 0.5167, abs=1e-3)
    assert ar.produce_cognition_modifiers([_snap(0.44)]) == {}


def test_neutral_character_full_ramp() -> None:
    # Neutral-драйвы (1/3) дают observe-вес 0.25+0.65/3+0.15/3 ≈ 0.5167.
    mods = ar.produce_cognition_modifiers([_snap(0.95)])
    assert mods["observe"] == pytest.approx(0.5 * 0.5167, abs=1e-3)
    assert mods["idle"] == pytest.approx(0.5 * (0.5 - 0.8 / 3), abs=1e-3)


def test_character_diverges_same_input() -> None:
    # Верховный критерий: ОДИНАКОВОЕ восприятие (те же снимки) →
    # РАЗНЫЕ интерпретации по пирамиде характера (не по профессии).
    # Нулевой вес → ключа нет (фильтр producer'а) — «интенция отсутствует».
    fearful = {"fear": 0.8, "desire": 0.1, "control": 0.1}
    sociable = {"fear": 0.1, "desire": 0.8, "control": 0.1}
    busy = {"fear": 0.1, "desire": 0.1, "control": 0.8}
    m_fear = ar.produce_cognition_modifiers([_snap(0.95)], fearful)
    m_soc = ar.produce_cognition_modifiers([_snap(0.95)], sociable)
    m_busy = ar.produce_cognition_modifiers([_snap(0.95)], busy)
    # Настороженный: смотрит внимательнее всех, НЕ подходит (нет ключа).
    assert m_fear["observe"] > m_soc["observe"]
    assert "approach" not in m_fear
    # Общительный: сам идёт навстречу.
    assert m_soc["approach"] > 0.0
    # Поглощённый делом: ожидание недоступно (0.5−0.8·0.8<0) — сценарий В.
    assert "idle" not in m_busy
    assert "idle" in m_soc


def test_weights_bounded_for_1000_characters() -> None:
    # Grid-инвариант масштабирования: ЛЮБОЙ характер из непрерывного
    # пространства даёт веса ≤ 1 → санкция ±0.5 недостижима по построению
    # (ни одной строки таблицы, ни одного исключения на 1000+ NPC).
    from app.domain.attention_dispositions import get_attention_disposition

    step = 0.1
    n = 11
    for i in range(n):
        for j in range(n):
            for k in range(n):
                d = {"fear": i * step, "desire": j * step, "control": k * step}
                for w in get_attention_disposition(d).values():
                    assert 0.0 <= w <= 1.0


def test_max_over_pairs_not_sum() -> None:
    mods = ar.produce_cognition_modifiers([_snap(0.95), _snap(0.7)])
    # Салиентнейшая пара (0.95, полный рамп) определяет модификаторы.
    assert mods["observe"] == pytest.approx(
        0.5 * (0.25 + 0.65 / 3 + 0.15 / 3), abs=1e-3
    )


def test_sanction_bound_unreachable_by_construction() -> None:
    # Формульные веса ∈ [0,1] → base·w ≤ 0.5: санкционная граница ±0.5
    # недостижима по построению (grid-инвариант — синоним масштабирования
    # на 1000+ характеров без исключений).
    from app.domain.attention_dispositions import get_attention_disposition

    for i in range(11):
        for j in range(11):
            for k in range(11):
                d = {"fear": i * 0.1, "desire": j * 0.1, "control": k * 0.1}
                for w in get_attention_disposition(d).values():
                    assert 0.0 <= w <= 1.0


def test_deterministic() -> None:
    s = [_snap(0.9)]
    d = {"fear": 0.4, "desire": 0.4, "control": 0.2}
    assert ar.produce_cognition_modifiers(s, d) == ar.produce_cognition_modifiers(
        list(s), dict(d)
    )


def test_apply_modifiers_cognition_channel() -> None:
    scores = {"observe": 0.2, "idle": 0.5}
    out = DecisionHub.apply_modifiers(scores, cognition_modifiers={"observe": 0.25})
    assert out["observe"] == pytest.approx(0.45)
    assert scores["observe"] == 0.2  # вход не мутирован (ADR-O-355)
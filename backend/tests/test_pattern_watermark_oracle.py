"""
path: /project/backend/tests/test_pattern_watermark_oracle.py
Назначение: Equivalence oracle ADR-O-400 — побитовая идентичность
detect(H1+H2) vs update(state(H1), H2)+to_evidence() на edge-кейсах и
PBT-разбиениях. Гейт ДО врезки в integration.py:410: расхождение = NO-GO.
Сравнения ТОЛЬКО побитовые (==), approx запрещён (Taboo ADR-O-400).
Зависимости: pattern_detector (эталон), pattern_state (кандидат)
Основные сущности: test_oracle_fixed_edges, test_oracle_pbt_splits, test_oracle_roundtrip
Запуск: cd backend; python -m pytest tests/test_pattern_watermark_oracle.py -v --tb=short; cd ..
"""

import math
from hypothesis import given, strategies as st

from app.domain.identity_events import TraitDriftEvent
from app.services.npc.pattern_detector import PatternDetector
from app.services.npc.pattern_state import WatermarkState


def _ev(source: str, effect: float, weight: float = 1.0, tick: int = 0) -> TraitDriftEvent:
    # Минимальный валидный TraitDriftEvent: детектор читает только
    # source_id / effect_value / observation_weight (ADR-O-305A: event_type игнорируется)
    return TraitDriftEvent(
        tick_id=tick, target_id="npc_x", source_id=source,
        effect_value=effect, observation_weight=weight, event_type="test",
    )


def _assert_evidence_equal(baseline: list, candidate: list) -> None:
    assert len(baseline) == len(candidate), (
        f"количество evidence разошлось: {len(baseline)} vs {len(candidate)}"
    )
    for b, c in zip(baseline, candidate):
        assert b.source_id == c.source_id, f"source_id: {b.source_id} vs {c.source_id}"
        # Побитовые сравнения (==), не approx — Taboo ADR-O-400
        assert b.cumulative_effect == c.cumulative_effect, (
            f"cumulative_effect: {b.cumulative_effect!r} vs {c.cumulative_effect!r}"
        )
        assert b.behavior_variance == c.behavior_variance, (
            f"behavior_variance: {b.behavior_variance!r} vs {c.behavior_variance!r} "
            f"(source={b.source_id})"
        )


def _run_oracle(events: list, split: int) -> None:
    """Baseline: detect(H1+H2). Candidate: update(state(H1), H2) -> to_evidence()."""
    baseline = PatternDetector().detect(list(events))

    state = WatermarkState()
    state.update(events[:split])       # H1
    state.update(events[split:])       # H2
    candidate = state.to_evidence()

    _assert_evidence_equal(baseline, candidate)


# ─── Фиксированные edge-кейсы ───────────────────────────────────────

def test_oracle_empty_and_below_threshold():
    # 0 событий; 1-2 события (< MIN_EVENTS=3) — пустые списки в обоих путях
    _run_oracle([], 0)
    _run_oracle([_ev("a", 0.5), _ev("a", -0.5)], 1)


def test_oracle_exactly_three_events():
    # Ровно MIN_EVENTS: гейт проходит в обоих путях
    _run_oracle([_ev("a", 0.1), _ev("a", 0.2), _ev("a", 0.3)], 2)


def test_oracle_zero_and_negative_zero():
    # Знак нуля: math.copysign(1, -0.0) == -1.0 — класс скрытой развилки.
    # Если candidate теряет знак -0.0 через Fraction — оракул падает ЗДЕСЬ.
    _run_oracle([_ev("a", 0.0), _ev("a", -0.0), _ev("a", 0.0), _ev("a", 1.0)], 2)
    _run_oracle([_ev("a", -0.0), _ev("a", -0.0), _ev("a", -0.0)], 1)


def test_oracle_multi_source_order():
    # Порядок evidence_list = порядок первого появления source (order contract)
    events = [
        _ev("b", 0.3), _ev("a", 0.1), _ev("b", -0.2),
        _ev("c", 0.5), _ev("a", 0.4), _ev("c", -0.1),
        _ev("a", 0.6), _ev("b", 0.7), _ev("c", 0.8),
    ]
    _run_oracle(events, 4)
    _run_oracle(events, 1)


def test_oracle_weighted_cumulative():
    # cumulative = Σ(effect × weight) — последовательный float; weights ≠ 1
    events = [
        _ev("w", 0.1, 0.5), _ev("w", -0.3, 0.9), _ev("w", 0.2, 1.7), _ev("w", 0.4, 0.3),
    ]
    _run_oracle(events, 2)


def test_oracle_invalid_source_raises_both_paths():
    # ADR-O-305 guard: invalid source → ValueError в ОБОИХ путях (семантика исключения тоже эквивалентна)
    bad = [_ev("unknown", 0.1), _ev("unknown", 0.2), _ev("unknown", 0.3)]
    try:
        PatternDetector().detect(list(bad))
        raised_baseline = False
    except ValueError:
        raised_baseline = True
    try:
        state = WatermarkState()
        state.update(bad)
        raised_candidate = False
    except ValueError:
        raised_candidate = True
    assert raised_baseline and raised_candidate, "guard ADR-O-305 должен срабатывать в обоих путях"


# ─── PBT: случайные потоки и разбиения H1/H2 ─────────────────────────

# Домен effect_value по контракту ADR-O-305A: [-1.0, 1.0] (identity_events:37);
# вне-доменные float'ы роняют и БАЗОВЫЙ путь (statistics float-конверсия) — не валидные данные
_floats = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False, width=64)
_weights = st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False)
_event = st.tuples(st.sampled_from(["s1", "s2", "s3", "s4"]), _floats, _weights)

@given(
    data=st.lists(_event, min_size=0, max_size=60),
    seed=st.integers(min_value=0, max_value=1 << 30),
)
def test_oracle_pbt_splits(data, seed):
    events = [_ev(s, e, w, tick=i) for i, (s, e, w) in enumerate(data)]
    split = seed % (len(events) + 1)  # любое разбиение H1/H2, включая пустые части
    _run_oracle(events, split)


# ─── Watermark (ветка 2): монотонность + tail-read + round-trip ─────

def test_watermark_tail_equals_full():
    # Tail-read (t_from=last+1) + ingest_tail == полное чтение + update.
    # События с МОНТОННЫМИ tick (контракт ветки 2: писатели коммитят с текущим тиком).
    events = [
        _ev("a", 0.1, tick=1), _ev("a", 0.2, tick=2), _ev("a", 0.3, tick=3),
        _ev("b", -0.4, tick=4), _ev("a", 0.5, tick=5),
    ]
    baseline = PatternDetector().detect(list(events))

    state = WatermarkState()
    # Визит 1 (тик 2): хвост = события tick <= 2
    state.ingest_tail([e for e in events if e.tick_id <= 2])
    # Визит 2 (тик 5): хвост = t_from = last_seen_tick + 1 (ровно как врезка integration:410)
    state.ingest_tail([
        e for e in events if e.tick_id > state.last_seen_tick
    ])
    _assert_evidence_equal(baseline, state.to_evidence())


def test_watermark_monotonicity_raises():
    # Событие со stale tick → RuntimeError (не молчаливая потеря)
    import pytest as _pytest

    state = WatermarkState()
    state.ingest_tail([_ev("a", 0.1, tick=5), _ev("a", 0.2, tick=6)])
    with _pytest.raises(RuntimeError):
        state.ingest_tail([_ev("a", 0.3, tick=4)])


def test_watermark_roundtrip_with_tick():
    events = [_ev("a", 0.1, tick=3), _ev("a", 0.2, tick=7), _ev("b", 0.4, tick=9)]
    state = WatermarkState()
    state.ingest_tail(events)
    restored = WatermarkState.from_dict(state.to_dict())
    assert restored.last_seen_tick == state.last_seen_tick == 9
    _assert_evidence_equal(state.to_evidence(), restored.to_evidence())


# ─── Persistence round-trip (§12/ADR-O-400 контракт 3) ──────────────

def test_oracle_roundtrip():
    events = [
        _ev("a", 0.1), _ev("b", -0.2), _ev("a", 0.3, 0.7), _ev("b", 0.4), _ev("a", -0.5),
    ]
    state = WatermarkState()
    state.update(events)

    restored = WatermarkState.from_dict(state.to_dict())
    _assert_evidence_equal(state.to_evidence(), restored.to_evidence())
    # Побитовая идентичность Fraction-полей после round-trip
    for sid in ("a", "b"):
        _assert_evidence_equal(
            [e for e in state.to_evidence() if e.source_id == sid],
            [e for e in restored.to_evidence() if e.source_id == sid],
        )
"""
Назначение: Песочницы (контрактные тесты) для PatternDetector (L1.5).
Зависимости: pytest, app.domain.identity_events, app.services.npc.pattern_detector
Основные сущности: TraitDriftEvent, EvidenceOfPersistence, PatternDetector

Запуск: python -m pytest backend/tests/sandbox/identity/test_pattern_detector.py -v --tb=short

Контракт: ADR-O-305A (Evidence Semantics).
Тесты проверяют математическую корректность и архитектурную чистоту
статистического слоя до написания реализации.
"""

from unittest.mock import MagicMock

import pytest

# Импортируем DTO (даже если они еще не реализованы, тесты ожидает их контракта)
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.identity_events import EvidenceOfPersistence, TraitDriftEvent
from app.services.npc.pattern_detector import MIN_EVENTS_FOR_PERSISTENCE, PatternDetector


def _make_event(
    tick: int, source: str, effect: float, weight: float = 1.0, event_type: str = "test"
) -> TraitDriftEvent:
    """Фабрика для создания чистых L1 событий."""
    return TraitDriftEvent(
        tick_id=tick,
        target_id="npc_1",
        source_id=source,
        effect_value=effect,
        event_type=event_type,
        observation_weight=weight,
    )


# --- Level 1: Mathematical Correctness ---


def test_1_noise_filtering():
    """Test 1: Событий меньше MIN_EVENTS_FOR_PERSISTENCE. Evidence не генерируется."""
    events = [_make_event(tick=i, source="player", effect=-0.1) for i in range(MIN_EVENTS_FOR_PERSISTENCE - 1)]

    detector = PatternDetector()
    evidence_list = detector.detect(events)

    assert evidence_list == [], "Шум должен быть отфильтрован"


def test_2_persistence_detection():
    """Test 2: Количество событий >= MIN_EVENTS. Evidence генерируется."""
    events = [_make_event(tick=i, source="player", effect=-0.2) for i in range(MIN_EVENTS_FOR_PERSISTENCE)]

    detector = PatternDetector()
    evidence_list = detector.detect(events)

    assert len(evidence_list) == 1
    assert evidence_list[0].source_id == "player"
    assert evidence_list[0].cumulative_effect < 0.0


def test_3_behavior_variance_relative():
    """Test 3: Осцилляция (знак меняется) дает строго большую variance, чем стабильный поток."""
    # Стабильный поток (все негативные)
    stable_events = [_make_event(tick=i, source="player", effect=-0.5) for i in range(10)]

    # Осциллирующий поток (плюс-минус)
    mixed_events = []
    for i in range(10):
        effect = -0.5 if i % 2 == 0 else 0.5
        mixed_events.append(_make_event(tick=i, source="player", effect=effect))

    detector = PatternDetector()
    stable_ev = detector.detect(stable_events)[0]
    mixed_ev = detector.detect(mixed_events)[0]

    assert mixed_ev.behavior_variance > stable_ev.behavior_variance, "Осцилляция должна давать более высокую variance"


# --- Level 2: Architectural Purity ---


def test_4_l1_append_only_independence():
    """Test 4: PatternDetector не имеет права писать в L1Chronicle."""
    mock_chronicle = MagicMock()
    mock_chronicle.append = MagicMock()

    events = [_make_event(tick=i, source="player", effect=-0.1) for i in range(10)]

    detector = PatternDetector()
    # detect не должен вызывать append
    detector.detect(
        events, chronicle=mock_chronicle
    ) if "chronicle" in detector.detect.__code__.co_varnames else detector.detect(events)

    mock_chronicle.append.assert_not_called(), "Нарушение ADR-O-208: PatternDetector пишет в L1!"


def test_5_source_isolation():
    """Test 5: События без source_id или с source_id='unknown' вызывают ошибку/игнорируются (запрет скалярного страха)."""
    invalid_events = [_make_event(tick=i, source="unknown", effect=-0.5) for i in range(10)]

    detector = PatternDetector()

    with pytest.raises((ValueError, TypeError)):
        detector.detect(invalid_events)


def test_6_psychological_purity():
    """Test 6: В DTO EvidenceOfPersistence нет психологических полей (trait, emotion)."""
    # Проверяем структуру dataclass
    fields = set(EvidenceOfPersistence.__dataclass_fields__.keys())

    assert "trait" not in fields, "Нарушение ADR-O-306: PatternDetector содержит trait!"
    assert "emotion" not in fields, "Нарушение ADR-O-306: PatternDetector содержит emotion!"

    # Проверяем, что обязательные статистические поля на месте
    assert "cumulative_effect" in fields
    assert "behavior_variance" in fields


# --- Level 3: ADR-O-305A Gates (Future Drift Protection) ---


def test_A_event_type_invariance():
    """Test A: event_type является provenance only и не влияет на математику."""
    tick = 1
    base_params = {"source": "player", "effect": -0.5, "weight": 1.0}

    ev_damage = _make_event(tick, event_type="physical_damage", **base_params)
    ev_aid = _make_event(tick, event_type="social_aid", **base_params)
    ev_random = _make_event(tick, event_type="random_blabla", **base_params)

    detector = PatternDetector()

    # Сравниваем агрегированные результаты для групп из одинаковых событий, но разных event_type
    res1 = detector.detect([ev_damage] * MIN_EVENTS_FOR_PERSISTENCE)[0]
    res2 = detector.detect([ev_aid] * MIN_EVENTS_FOR_PERSISTENCE)[0]
    res3 = detector.detect([ev_random] * MIN_EVENTS_FOR_PERSISTENCE)[0]

    assert res1.cumulative_effect == res2.cumulative_effect == res3.cumulative_effect
    assert res1.behavior_variance == res2.behavior_variance == res3.behavior_variance


def test_B_observation_weight_semantics():
    """Test B: observation_weight модулирует cumulative_effect (вес 1.0 тяжелее веса 0.1)."""
    # Группа А: Прямой удар (weight = 1.0)
    events_A = [
        _make_event(tick=i, source="player", effect=-1.0, weight=1.0) for i in range(MIN_EVENTS_FOR_PERSISTENCE)
    ]

    # Группа B: Слабое наблюдение (weight = 0.1)
    events_B = [
        _make_event(tick=i, source="player", effect=-1.0, weight=0.1) for i in range(MIN_EVENTS_FOR_PERSISTENCE)
    ]

    detector = PatternDetector()
    res_A = detector.detect(events_A)[0]
    res_B = detector.detect(events_B)[0]

    # -1.0 * 1.0 < -1.0 * 0.1 (т.е. ущерб с весом 1.0 математически "глубже")
    assert res_A.cumulative_effect < res_B.cumulative_effect, "Observation weight не модулирует cumulative_effect!"

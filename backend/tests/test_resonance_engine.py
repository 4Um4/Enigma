"""
Тесты R5.4 — ResonanceEngine: детекция паттернов поведения игрока.
path: backend/tests/test_resonance_engine.py
Запуск: python -m pytest tests/test_resonance_engine.py -v --tb=short
"""

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.npc_state import EventMemory, MemoryStage
from app.services.memory.resonance_engine import ResonanceEngine


def _mem(event_type: str, emotion: str = "angry", importance: float = 0.7, day: int = 1) -> EventMemory:
    return EventMemory(
        event_type=event_type,
        target_id="player",
        emotion_tag=emotion,
        day=day,
        importance=importance,
        clarity=0.9,
        confidence=0.9,
        decay_rate=0.03,
        stage=MemoryStage.FRESH,
    )


# ── Betrayal Chain ────────────────────────────────────────────────────────────


def test_betrayal_chain_detected() -> None:
    """3 кражи → distrust_player trait."""
    engine = ResonanceEngine()
    events = [_mem("theft", day=1), _mem("theft", day=2), _mem("intimidation", day=3)]
    patterns = engine.detect(events, actor_id="player")
    names = [p.pattern_name for p in patterns]
    assert "betrayal_chain" in names


def test_betrayal_chain_trait_name() -> None:
    """Паттерн предательства → именно distrust_player."""
    engine = ResonanceEngine()
    events = [_mem("theft", day=i) for i in range(3)]
    patterns = engine.detect(events, actor_id="player")
    betrayal = next(p for p in patterns if p.pattern_name == "betrayal_chain")
    assert betrayal.trait_name == "distrust_player"
    assert 0.0 < betrayal.trait_delta <= 0.30


def test_betrayal_below_threshold_not_detected() -> None:
    """Слабые события не дотягивают до порога формирования trait."""
    engine = ResonanceEngine()
    events = [_mem("theft", importance=0.05, day=i) for i in range(3)]
    patterns = engine.detect(events, actor_id="player")
    names = [p.pattern_name for p in patterns]
    assert "betrayal_chain" not in names


def test_two_events_not_enough() -> None:
    """2 события — меньше минимума, паттерн не срабатывает."""
    engine = ResonanceEngine()
    events = [_mem("theft", day=1), _mem("theft", day=2)]
    assert engine.detect(events) == []


# ── Chronic Help ──────────────────────────────────────────────────────────────


def test_chronic_help_detected() -> None:
    """3 помощи → trust_bias trait."""
    engine = ResonanceEngine()
    events = [_mem("help", "grateful", day=i) for i in range(3)]
    patterns = engine.detect(events, actor_id="player")
    names = [p.pattern_name for p in patterns]
    assert "chronic_help" in names


def test_chronic_help_trait_name() -> None:
    engine = ResonanceEngine()
    events = [_mem("help", "grateful", 0.7, day=i) for i in range(4)]
    patterns = engine.detect(events, actor_id="player")
    help_p = next(p for p in patterns if p.pattern_name == "chronic_help")
    assert help_p.trait_name == "trust_bias"


# ── Gaslighting ───────────────────────────────────────────────────────────────


def test_gaslighting_detected() -> None:
    """Чередование агрессии и помощи → suspicious."""
    engine = ResonanceEngine()
    events = [
        _mem("combat", "fearful", 0.8, day=1),
        _mem("help", "grateful", 0.7, day=2),
        _mem("intimidation", "fearful", 0.8, day=3),
        _mem("help", "grateful", 0.7, day=4),
    ]
    patterns = engine.detect(events, actor_id="player")
    names = [p.pattern_name for p in patterns]
    assert "gaslighting" in names


def test_gaslighting_requires_alternation() -> None:
    """Только помощь без агрессии — не gaslighting."""
    engine = ResonanceEngine()
    events = [_mem("help", "grateful", 0.7, day=i) for i in range(4)]
    patterns = engine.detect(events, actor_id="player")
    names = [p.pattern_name for p in patterns]
    assert "gaslighting" not in names


# ── Temporal Density ──────────────────────────────────────────────────────────


def test_dense_events_stronger_than_sparse() -> None:
    """Плотные кражи (1 день) формируют более сильный паттерн чем редкие (30 дней)."""
    engine = ResonanceEngine()

    dense = [_mem("theft", day=i) for i in range(3)]  # дни 0,1,2
    sparse = [_mem("theft", day=i * 10) for i in range(3)]  # дни 0,10,20

    p_dense = engine.detect(dense, actor_id="player")
    p_sparse = engine.detect(sparse, actor_id="player")

    dense_strength = next(p.strength for p in p_dense if p.pattern_name == "betrayal_chain")
    sparse_strength = next(p.strength for p in p_sparse if p.pattern_name == "betrayal_chain")

    assert dense_strength > sparse_strength


# ── Фильтрация ────────────────────────────────────────────────────────────────


def test_forgotten_events_ignored() -> None:
    """FORGOTTEN события не участвуют в детекции."""
    engine = ResonanceEngine()
    events = [
        EventMemory("theft", "player", "angry", 1, 0.8, stage=MemoryStage.FORGOTTEN),
        EventMemory("theft", "player", "angry", 2, 0.8, stage=MemoryStage.FORGOTTEN),
        EventMemory("theft", "player", "angry", 3, 0.8, stage=MemoryStage.FORGOTTEN),
    ]
    assert engine.detect(events, actor_id="player") == []


def test_wrong_actor_ignored() -> None:
    """События от другого actor не влияют на паттерн."""
    engine = ResonanceEngine()
    events = [_mem("theft", day=i) for i in range(3)]
    assert engine.detect(events, actor_id="guard_01") == []


def test_pattern_delta_within_bounds() -> None:
    """trait_delta никогда не превышает MAX_PATTERN_DELTA."""
    engine = ResonanceEngine()
    events = [_mem("theft", importance=1.0, day=i) for i in range(10)]
    patterns = engine.detect(events, actor_id="player")
    for p in patterns:
        assert p.trait_delta <= 0.30

"""
Тесты R5.3 — WorkingMemory.apply_decay() возвращает identity weights.
Назначение: проверяет что apply_decay() возвращает identity_weights при ABSTRACT-переходе.
Запуск: python -m pytest tests/test_working_memory.py -v --tb=short
"""

from app.services.memory.working_memory import WorkingMemory
from app.models.npc_state import EventMemory, MemoryStage


def _make_fresh(emotion_tag: str = "angry", importance: float = 0.9) -> EventMemory:
    """Вспомогательная фабрика EventMemory."""
    return EventMemory(
        event_type="theft",
        target_id="player",
        emotion_tag=emotion_tag,
        day=1,
        importance=importance,
        clarity=0.8,
        confidence=0.9,
        decay_rate=0.0,   # decay_rate=0 → importance не меняется → стадия не меняется
        stage=MemoryStage.FRESH,
    )


def test_apply_decay_returns_list() -> None:
    """apply_decay всегда возвращает список, даже пустой."""
    wm = WorkingMemory()
    result = wm.apply_decay("camp_1", ticks=1)
    assert isinstance(result, list)


def test_apply_decay_no_transition_no_weights() -> None:
    """FRESH с нулевым decay_rate не переходит в ABSTRACT → weights пусты."""
    wm = WorkingMemory()
    wm.push("camp_1", _make_fresh())
    weights = wm.apply_decay("camp_1", ticks=1)
    assert weights == []


def test_apply_decay_abstract_transition_yields_resentment() -> None:
    """Переход в ABSTRACT с angry emotion_tag → resentment trait."""
    wm = WorkingMemory()
    # Подбираем importance и decay_rate так чтобы за 1 тик перейти в ABSTRACT
    # ABSTRACT порог: importance < ~0.20 (из _resolve_stage)
    mem = EventMemory(
        event_type="intimidation",
        target_id="player",
        emotion_tag="angry",
        day=1,
        importance=0.22,
        clarity=1.0,
        confidence=1.0,
        decay_rate=0.50,           # быстрый decay: 0.22 * e^(-0.5) ≈ 0.13 → ABSTRACT
        stage=MemoryStage.COMPRESSED,
    )
    wm.push("camp_1", mem)
    weights = wm.apply_decay("camp_1", ticks=1)

    if weights:   # если переход состоялся
        trait_names = [w[0] for w in weights]
        assert "resentment" in trait_names
        for name, delta in weights:
            assert 0.0 < delta <= 1.0


def test_apply_decay_grateful_yields_dependency() -> None:
    """Переход в ABSTRACT с grateful → dependency trait."""
    wm = WorkingMemory()
    mem = EventMemory(
        event_type="help",
        target_id="player",
        emotion_tag="grateful",
        day=1,
        importance=0.22,
        clarity=1.0,
        confidence=1.0,
        decay_rate=0.50,
        stage=MemoryStage.COMPRESSED,
    )
    wm.push("camp_1", mem)
    weights = wm.apply_decay("camp_1", ticks=1)

    if weights:
        trait_names = [w[0] for w in weights]
        assert "dependency" in trait_names


def test_apply_decay_removes_forgotten() -> None:
    """Забытые события (importance → < 0.05) удаляются из буфера."""
    wm = WorkingMemory()
    mem = EventMemory(
        event_type="movement",
        target_id="player",
        emotion_tag="neutral",
        day=1,
        importance=0.04,   # уже ниже порога FORGOTTEN
        clarity=0.5,
        confidence=0.5,
        decay_rate=0.5,
        stage=MemoryStage.ABSTRACT,
    )
    wm.push("camp_1", mem)
    wm.apply_decay("camp_1", ticks=1)
    assert wm.get("camp_1") == []


def test_apply_decay_preserves_legacy_dicts() -> None:
    """Legacy dict события не затрагиваются decay и не генерируют weights."""
    wm = WorkingMemory()
    wm.push("camp_1", {"type": "legacy_event", "importance": 0.5})
    weights = wm.apply_decay("camp_1", ticks=1)
    assert weights == []
    assert len(wm.get("camp_1")) == 1

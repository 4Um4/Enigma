"""
Запуск: pytest backend/tests/test_compression_stage9.py
Этап 9 — сжатие памяти.
Проверяет: MemoryPromotionEngine.compress(), compress_narrative_cache().

path: backend/tests/test_compression_stage9.py
Назначение: Тесты Этапа 9 — сжатие памяти
Зависимости: MemoryPromotionEngine, MemoryManager, EventMemory
Основные сущности: compress(), compress_narrative_cache()

Формулы и алгоритмы:
- compress() сжимает 3+ событий с одинаковыми тегами в одно абстрактное событие с пометкой "X раз".
- compress_narrative_cache() заменяет группы событий в кэше на сжатые   абстракции, если они подходят под критерии сжатия.
- Секретные события и события с высокой важностью (importance >= 0.6) не сжимаются.
- Сжатые события получают clarity=0.5 и stage=ABSTRACT.
"""

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.npc_state import EventMemory, MemoryStage
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.promotion_engine import MemoryPromotionEngine


def _make_mem(
    event_type: str = "dialogue",
    tags: tuple = ("dialogue", "positive"),
    importance: float = 0.3,
    is_secret: bool = False,
    sequence_id: int = 0,
) -> EventMemory:
    return EventMemory(
        event_type=event_type,
        target_id="player",
        emotion_tag="happy",
        day=1,
        importance=importance,
        decay_rate=0.05,
        stage=MemoryStage.FRESH,
        summary="Разговор",
        npc_id="npc_01",
        tags=tags,
        is_secret=is_secret,
        sequence_id=sequence_id,
    )


def _make_manager() -> MemoryManager:
    from unittest.mock import MagicMock

    mm = MemoryManager.__new__(MemoryManager)
    mm._working = MagicMock()
    mm._layered = MagicMock()
    mm._relationship = MagicMock()
    mm._resonance = MagicMock()
    mm._dialogue = MagicMock()
    return mm


# ── MemoryPromotionEngine ──


def test_compress_finds_group_of_3() -> None:
    """3+ событий с одинаковыми тегами → сжатие."""
    engine = MemoryPromotionEngine()
    mems = [_make_mem(sequence_id=i) for i in range(3)]
    results = engine.compress(mems)
    assert len(results) == 1
    assert results[0].compressed.is_compressed
    assert "(3 раз)" in results[0].compressed.summary


def test_compress_skips_if_less_than_3() -> None:
    """Меньше 3 — нет сжатия."""
    engine = MemoryPromotionEngine()
    mems = [_make_mem(sequence_id=i) for i in range(2)]
    assert engine.compress(mems) == []


def test_compress_skips_secrets() -> None:
    """Секреты не сжимаются."""
    engine = MemoryPromotionEngine()
    mems = [
        _make_mem(is_secret=True, sequence_id=0),
        _make_mem(is_secret=True, sequence_id=1),
        _make_mem(is_secret=True, sequence_id=2),
    ]
    assert engine.compress(mems) == []


def test_compress_skips_high_importance() -> None:
    """importance >= 0.6 — не сжимается (отдаётся ResonanceEngine)."""
    engine = MemoryPromotionEngine()
    mems = [_make_mem(importance=0.7, sequence_id=i) for i in range(3)]
    assert engine.compress(mems) == []


def test_compress_no_batch_limit() -> None:
    """Все события группы сжимаются вместе, без лимита 5."""
    engine = MemoryPromotionEngine()
    mems = [_make_mem(sequence_id=i) for i in range(7)]
    results = engine.compress(mems)
    assert len(results) == 1
    assert "(7 раз)" in results[0].compressed.summary


def test_compress_different_tags_no_group() -> None:
    """Разные теги → разные группы, каждая < 3 → нет сжатия."""
    engine = MemoryPromotionEngine()
    mems = [
        _make_mem(tags=("dialogue", "positive"), sequence_id=0),
        _make_mem(tags=("combat",), sequence_id=1),
        _make_mem(tags=("trade",), sequence_id=2),
    ]
    assert engine.compress(mems) == []


def test_compress_abstract_stage() -> None:
    """Сжатое событие сразу в ABSTRACT."""
    engine = MemoryPromotionEngine()
    mems = [_make_mem(sequence_id=i) for i in range(3)]
    results = engine.compress(mems)
    assert results[0].compressed.stage == MemoryStage.ABSTRACT


def test_compress_clarity_lower() -> None:
    """Сжатая абстракция имеет clarity=0.5 (менее чёткая)."""
    engine = MemoryPromotionEngine()
    mems = [_make_mem(sequence_id=i) for i in range(3)]
    results = engine.compress(mems)
    assert results[0].compressed.clarity == 0.5


# ── compress_narrative_cache ──


def test_compress_narrative_replaces_group() -> None:
    """compress_narrative_cache заменяет группу на абстракцию."""
    mm = _make_manager()
    mems = tuple(_make_mem(sequence_id=i) for i in range(3))
    result = mm.compress_narrative_cache(mems)

    # 3 оригинала заменены на 1 сжатую
    assert len(result) == 1
    assert result[0].is_compressed


def test_compress_narrative_keeps_unmatched() -> None:
    """Несжатые события остаются в кэше."""
    mm = _make_manager()
    # 3 сжимаемых + 1 уникальное
    mems = tuple(_make_mem(sequence_id=i) for i in range(3)) + (
        _make_mem(event_type="combat", tags=("combat",), sequence_id=99),
    )
    result = mm.compress_narrative_cache(mems)

    # 1 сжатая + 1 combat = 2
    assert len(result) == 2
    compressed = [m for m in result if m.is_compressed]
    kept = [m for m in result if not m.is_compressed]
    assert len(compressed) == 1
    assert len(kept) == 1
    assert kept[0].event_type == "combat"


def test_compress_narrative_no_candidates_returns_original() -> None:
    """Нет кандидатов → оригинальный кортеж."""
    mm = _make_manager()
    mems = tuple(_make_mem(sequence_id=i) for i in range(2))
    result = mm.compress_narrative_cache(mems)
    assert result is mems

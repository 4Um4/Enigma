# backend/tests/test_event_memory.py
"""
R5.1 — тесты EventMemory: clarity, confidence, decay lifecycle.
"""

import math

import pytest
from app.models.npc_state import EventMemory, MemoryStage, NPCPersonality, _resolve_stage
from app.services.memory.working_memory import WorkingMemory

# ─────────────────────────────────────────────────────────────────────────────
# EventMemory dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestEventMemory:
    def test_default_stage_is_fresh(self) -> None:
        """Новое событие — стадия FRESH."""
        mem = EventMemory(
            event_type="theft",
            target_id="player",
            emotion_tag="angry",
            day=1,
            importance=0.9,
        )
        assert mem.stage == MemoryStage.FRESH

    def test_values_clamped_on_create(self) -> None:
        """Невалидные значения зажимаются при создании."""
        mem = EventMemory(
            event_type="combat",
            target_id="player",
            emotion_tag="fearful",
            day=1,
            importance=1.5,  # > 1.0
            clarity=-0.1,  # < 0.0
            confidence=99.0,  # > 1.0
        )
        assert mem.importance == 1.0
        assert mem.clarity == 0.0
        assert mem.confidence == 1.0

    def test_decay_reduces_importance(self) -> None:
        """После decay важность снижается."""
        mem = EventMemory(
            event_type="theft",
            target_id="player",
            emotion_tag="angry",
            day=1,
            importance=0.9,
            decay_rate=0.1,
        )
        decayed = mem.decayed(game_days=1)
        assert decayed.importance < mem.importance

    def test_decay_follows_exponential(self) -> None:
        """Decay экспоненциальный: importance *= exp(-rate * ticks)."""
        mem = EventMemory(
            event_type="help",
            target_id="player",
            emotion_tag="grateful",
            day=1,
            importance=0.8,
            decay_rate=0.05,
        )
        decayed = mem.decayed(game_days=2)
        expected = round(0.8 * math.exp(-0.05 * 2), 4)
        assert decayed.importance == pytest.approx(expected, abs=1e-3)

    def test_clarity_preserved_after_decay(self) -> None:
        """clarity фиксируется в момент восприятия — decay не меняет."""
        mem = EventMemory(
            event_type="combat",
            target_id="player",
            emotion_tag="fearful",
            day=1,
            importance=0.9,
            clarity=0.7,
            decay_rate=0.1,
        )
        decayed = mem.decayed(game_days=5)
        assert decayed.clarity == pytest.approx(0.7)

    def test_confidence_decreases_after_decay(self) -> None:
        """confidence снижается медленнее importance (drift деталей)."""
        mem = EventMemory(
            event_type="combat",
            target_id="player",
            emotion_tag="fearful",
            day=1,
            importance=0.9,
            confidence=1.0,
            decay_rate=0.1,
        )
        decayed = mem.decayed(game_days=5)
        assert decayed.confidence < 1.0
        assert decayed.confidence > decayed.importance  # медленнее затухает

    def test_forgotten_after_heavy_decay(self) -> None:
        """После достаточного decay событие переходит в FORGOTTEN."""
        mem = EventMemory(
            event_type="idle",
            target_id="player",
            emotion_tag="neutral",
            day=1,
            importance=0.15,
            decay_rate=0.3,
        )
        decayed = mem.decayed(game_days=10)
        assert decayed.is_forgotten

    def test_critical_memory_survives(self) -> None:
        """Критическая память (decay_rate≈0) не забывается."""
        mem = EventMemory(
            event_type="saved_life",
            target_id="player",
            emotion_tag="grateful",
            day=1,
            importance=1.0,
            decay_rate=0.001,  # почти не затухает
        )
        decayed = mem.decayed(game_days=100)
        assert not decayed.is_forgotten
        assert decayed.importance > 0.9


class TestMemoryStageResolution:
    def test_stage_boundaries(self) -> None:
        """Стадии соответствуют порогам importance."""
        assert _resolve_stage(0.90) == MemoryStage.FRESH
        assert _resolve_stage(0.60) == MemoryStage.DETAILED
        assert _resolve_stage(0.35) == MemoryStage.COMPRESSED
        assert _resolve_stage(0.15) == MemoryStage.ABSTRACT
        assert _resolve_stage(0.05) == MemoryStage.FORGOTTEN


class TestWorkingMemoryDecay:
    def test_decay_removes_forgotten_events(self) -> None:
        """После decay забытые события удаляются из буфера."""
        wm = WorkingMemory(maxlen=10)
        # Слабое событие — быстро забудется
        weak = EventMemory(
            event_type="idle",
            target_id="player",
            emotion_tag="neutral",
            day=1,
            importance=0.12,
            decay_rate=0.5,
        )
        # Сильное — останется
        strong = EventMemory(
            event_type="combat",
            target_id="player",
            emotion_tag="fearful",
            day=1,
            importance=0.95,
            decay_rate=0.05,
        )
        wm.push("test", weak)
        wm.push("test", strong)
        wm.apply_decay("test", game_days=5)

        remaining = wm.get("test")
        assert len(remaining) == 1
        assert remaining[0].event_type == "combat"

    def test_decay_preserves_legacy_dicts(self) -> None:
        """Legacy dict-события не затрагиваются decay."""
        wm = WorkingMemory()
        wm.push("test", {"type": "legacy_event", "actor": "player"})
        wm.apply_decay("test", game_days=10)
        result = wm.get("test")
        assert len(result) == 1
        assert result[0]["type"] == "legacy_event"

    def test_maxlen_is_20_by_default(self) -> None:
        """Дефолтный maxlen = 20 по спецификации."""
        wm = WorkingMemory()
        assert wm._maxlen == 20


class TestToIdentityWeight:
    def test_abstract_angry_gives_resentment(self) -> None:
        """ABSTRACT + angry → resentment delta."""
        mem = EventMemory(
            event_type="betrayal",
            target_id="player",
            emotion_tag="angry",
            day=5,
            importance=0.15,  # уже ABSTRACT
            decay_rate=0.0,  # не затухает дальше
            stage=MemoryStage.ABSTRACT,
        )
        result = mem.to_identity_weight()
        assert result is not None
        trait, delta = result
        assert trait == "resentment"
        assert delta > 0.0

    def test_abstract_grateful_gives_dependency(self) -> None:
        """ABSTRACT + grateful → dependency delta."""
        mem = EventMemory(
            event_type="help",
            target_id="player",
            emotion_tag="grateful",
            day=3,
            importance=0.15,
            stage=MemoryStage.ABSTRACT,
        )
        result = mem.to_identity_weight()
        assert result is not None
        assert result[0] == "dependency"

    def test_non_abstract_returns_none(self) -> None:
        """Только ABSTRACT конвертируется в identity weight."""
        mem = EventMemory(
            event_type="theft",
            target_id="player",
            emotion_tag="angry",
            day=1,
            importance=0.9,
        )
        assert mem.stage == MemoryStage.FRESH
        assert mem.to_identity_weight() is None

    def test_neutral_emotion_returns_none(self) -> None:
        """Нейтральная эмоция не формирует identity weight."""
        mem = EventMemory(
            event_type="idle",
            target_id="player",
            emotion_tag="neutral",
            day=1,
            importance=0.15,
            stage=MemoryStage.ABSTRACT,
        )
        assert mem.to_identity_weight() is None


@pytest.fixture
def base_personality():
    """Минимальная личность NPC для тестов вербализации."""
    from app.models.npc_state import NPCTier

    return NPCPersonality(
        npc_id="test_npc",
        tier=NPCTier.MAJOR,
        drives_base={
            "control": 0.4,
            "significance": 0.3,
            "fear": 0.2,
            "desire": 0.1,
        },
        willpower=50.0,
        breakpoint=80.0,
        loyalty_base=50.0,
        voice_profile="",
        backstory="",
    )

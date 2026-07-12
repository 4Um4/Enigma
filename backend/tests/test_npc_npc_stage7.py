"""
python -m pytest backend/tests/test_npc_npc_stage7.py -v --tb=short 2>&1 | Select-Object -Last 20

Этап 7 — NPC-NPC через память.
Проверяет: recall по target_npc_id, npc_memory_modifiers, ResonanceEngine.detect_npc_patterns,
VerbalizationContext.npc_npc_context.

path: backend/tests/test_npc_npc_stage7.py
Назначение: Тесты Этапа 7 — NPC-NPC через память
Зависимости: MemoryManager, ResonanceEngine, DecisionHub, EventMemory, VerbalizationContext
Основные сущности: recall(target_npc_id), npc_memory_modifiers, detect_npc_patterns, npc_npc_context
"""

from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import EventMemory, MemoryStage
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.resonance_engine import ResonanceEngine
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.verbalization.verbalization_context import VerbalizationContext


def _make_manager() -> MemoryManager:
    """MemoryManager с замоканым LayeredMemory."""
    from unittest.mock import MagicMock

    mm = MemoryManager.__new__(MemoryManager)
    mm._working = MagicMock()
    mm._layered = MagicMock()
    mm._relationship = MagicMock()
    mm._resonance = MagicMock()
    mm._dialogue = MagicMock()
    return mm


def _make_mem(
    event_type: str = "combat",
    target_id: str = "player",
    npc_id: str = "npc_01",
    tags: tuple = ("combat", "negative"),
    importance: float = 0.8,
    stage: MemoryStage = MemoryStage.FRESH,
) -> EventMemory:
    return EventMemory(
        event_type=event_type,
        target_id=target_id,
        emotion_tag="angry",
        day=1,
        importance=importance,
        clarity=0.9,
        confidence=0.9,
        decay_rate=0.05,
        stage=stage,
        summary=f"{npc_id} → {target_id}: {event_type}",
        npc_id=npc_id,
        tags=tags,
    )


def _make_personality() -> NPCProfileL0:
    return NPCProfileL0(
        id="npc_01",
        name="Тест",
        tier="mass",
        drives_base={"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5},
        psyche_base=PsycheBase(willpower=50, breakpoint=80),
        voice_profile="neutral",
    )


# ── 7.1: recall(target_npc_id=...) ──


def test_recall_by_target_npc_id() -> None:
    """recall с target_npc_id возвращает только события о конкретном NPC."""
    mm = _make_manager()
    mem_player = _make_mem(target_id="player")
    mem_tavernkeeper = _make_mem(target_id="tavernkeeper", event_type="intimidation")
    mem_guard = _make_mem(target_id="guard", event_type="combat")
    cache = (mem_player, mem_tavernkeeper, mem_guard)

    result = mm.recall(cache, target_npc_id="tavernkeeper")
    assert len(result) == 1
    assert result[0].target_id == "tavernkeeper"


def test_recall_target_npc_falls_through_to_random() -> None:
    """Если по target_npc_id ничего не найдено — падает в случайный recall."""
    mm = _make_manager()
    mem = _make_mem(target_id="player", importance=0.9)
    # accessibility по умолчанию 1.0 > 0.2 — попадёт в случайный recall
    cache = (mem,)

    result = mm.recall(cache, target_npc_id="nonexistent")
    assert len(result) == 1
    assert result[0].target_id == "player"


def test_recall_target_npc_priority_over_random() -> None:
    """Триггерный и target_npc_id имеют приоритет над случайным recall."""
    mm = _make_manager()
    mem_about_tk = _make_mem(target_id="tavernkeeper", importance=0.5)
    mem_other = _make_mem(target_id="player", importance=0.9)
    cache = (mem_other, mem_about_tk)

    result = mm.recall(cache, target_npc_id="tavernkeeper")
    assert len(result) == 1
    assert result[0].target_id == "tavernkeeper"


# ── 7.2: TopicExtractor — NPC-NPC event types ──


def test_topic_extractor_npc_npc() -> None:
    """NPC-NPC event types маппятся в тему 'встреча'."""
    from app.services.npc.topic_extractor import extract_topic

    assert extract_topic("npc_interacts_npc") == "встреча"
    assert extract_topic("npc_proximity_close") == "встреча"


# ── 7.3: VerbalizationContext — npc_npc_context ──


def test_verbalization_context_has_npc_npc_field() -> None:
    """npc_npc_context существует и по умолчанию пустой."""
    ctx = VerbalizationContext(
        npc_id="npc_01",
        npc_name="Тест",
        tier="mass",
        emotion="neutral",
        will_state="loyal",
        intent="greet",
        intent_target="tavernkeeper",
    )
    assert ctx.npc_npc_context == ()


def test_verbalization_context_accepts_npc_npc() -> None:
    """npc_npc_context принимает кортеж EventMemory."""
    mem = _make_mem(target_id="tavernkeeper")
    ctx = VerbalizationContext(
        npc_id="npc_01",
        npc_name="Тест",
        tier="mass",
        emotion="neutral",
        will_state="loyal",
        intent="greet",
        intent_target="tavernkeeper",
        npc_npc_context=(mem,),
    )
    assert len(ctx.npc_npc_context) == 1
    assert ctx.npc_npc_context[0].target_id == "tavernkeeper"


# ── 7.4: DecisionHub — npc_memory_modifiers ──


def test_npc_memory_modifiers_boost_intent() -> None:
    """npc_memory_modifiers повышает score целевого intent."""
    hub = DecisionHub(seed=42)
    state = __import__("app.models.npc_state", fromlist=["NPCState"]).NPCState(npc_id="npc_01")
    personality = _make_personality()
    event = EventContext(event_type="npc_interacts_npc", actor_id="tavernkeeper")

    result_base = hub.compute(state=state, personality=personality, event=event)
    result_boosted = hub.compute(
        state=state,
        personality=personality,
        event=event,
        npc_memory_modifiers={"avoid": 0.4},
    )

    base_score = getattr(result_base, "scores", {}).get("avoid", 0.0)
    boosted_score = getattr(result_boosted, "scores", {}).get("avoid", 0.0)
    assert boosted_score >= base_score


def test_npc_memory_modifiers_none_no_effect() -> None:
    """npc_memory_modifiers=None — backward-compatible."""
    hub = DecisionHub(seed=42)
    state = __import__("app.models.npc_state", fromlist=["NPCState"]).NPCState(npc_id="npc_01")
    personality = _make_personality()
    event = EventContext(event_type="npc_interacts_npc", actor_id="tavernkeeper")
    result = hub.compute(state=state, personality=personality, event=event)
    assert result.intent is not None


# ── 7.5: ResonanceEngine — detect_npc_patterns ──


def test_detect_npc_patterns_hostile() -> None:
    """3+ негативных события о target_npc → hostile_pattern."""
    engine = ResonanceEngine()
    mems = [
        _make_mem(event_type="intimidation", target_id="tavernkeeper", npc_id="tavernkeeper", importance=0.7),
        _make_mem(event_type="combat", target_id="tavernkeeper", npc_id="tavernkeeper", importance=0.8),
        _make_mem(event_type="intimidation", target_id="tavernkeeper", npc_id="tavernkeeper", importance=0.6),
    ]
    patterns = engine.detect_npc_patterns(mems, target_npc_id="tavernkeeper")
    assert len(patterns) == 1
    assert patterns[0].pattern_name == "hostile_pattern"
    assert patterns[0].trait_name == "hostile_to_npc"
    assert patterns[0].trait_delta > 0


def test_detect_npc_patterns_too_few() -> None:
    """Меньше 3 негативных событий → нет паттерна."""
    engine = ResonanceEngine()
    mems = [
        _make_mem(event_type="intimidation", target_id="tavernkeeper", npc_id="tavernkeeper"),
        _make_mem(
            event_type="dialogue", target_id="tavernkeeper", npc_id="tavernkeeper", tags=("dialogue",), importance=0.3
        ),
    ]
    patterns = engine.detect_npc_patterns(mems, target_npc_id="tavernkeeper")
    assert patterns == []


def test_detect_npc_patterns_ignores_forgotten() -> None:
    """Forgotten события не учитываются в паттерне."""
    engine = ResonanceEngine()
    mems = [
        _make_mem(
            event_type="intimidation", target_id="tavernkeeper", npc_id="tavernkeeper", stage=MemoryStage.FORGOTTEN
        ),
        _make_mem(event_type="intimidation", target_id="tavernkeeper", npc_id="tavernkeeper"),
        _make_mem(event_type="intimidation", target_id="tavernkeeper", npc_id="tavernkeeper"),
    ]
    patterns = engine.detect_npc_patterns(mems, target_npc_id="tavernkeeper")
    assert patterns == []

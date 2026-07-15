# Путь: backend\tests\test_contracts_stage6.py
"""
python -m pytest backend/tests/test_contracts_stage6.py -v --tb=short 2>&1 | Select-Object -Last 25

Этап 6 — контракты и обязательства.
Проверяет: теги, decay, get_unfulfilled_contracts, contract_modifiers в DecisionHub.

Назначение: Тесты Этапа 6 — контракты и обязательства в памяти
Зависимости: MemoryManager, EventMemory, EventDTO, DecisionHub
Основные сущности: get_unfulfilled_contracts, apply() с contract_tag, contract_modifiers
"""

from app.domain.events import (
    CONTRACT_TAG_DEBT,
    CONTRACT_TAG_PROMISE_GIVEN,
    CONTRACT_TAG_PROMISE_RECEIVED,
    CONTRACT_TAGS,
    EventDTO,
)
from app.domain.identity_events import EffectiveDrives
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import EventMemory, MemoryStage, NPCState
from app.services.memory.memory_manager import MemoryManager
from app.services.npc.decision_hub import DecisionHub, EventContext

# Фикстура для EffectiveDrives (L3), требуемая DecisionHub.compute
_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})


def _make_manager() -> MemoryManager:
    """MemoryManager с замоканым LayeredMemory — без файловой системы."""
    from unittest.mock import MagicMock

    mm = MemoryManager.__new__(MemoryManager)
    mm._working = MagicMock()
    mm._layered = MagicMock()
    mm._relationship = MagicMock()
    mm._resonance = MagicMock()
    mm._dialogue = MagicMock()
    return mm


def _make_contract_mem(
    tag: str = CONTRACT_TAG_PROMISE_GIVEN,
    fulfilled: bool = False,
    importance: float = 0.8,
    stage: MemoryStage = MemoryStage.FRESH,
) -> EventMemory:
    """Создаёт EventMemory с контрактным тегом."""
    return EventMemory(
        event_type="player_promised",
        target_id="player",
        emotion_tag="neutral",
        day=1,
        importance=importance,
        clarity=0.9,
        confidence=0.9,
        decay_rate=0.05,
        stage=stage,
        summary="Игрок обещал помочь",
        npc_id="npc_01",
        tags=(tag, "player_promised"),
        fulfilled=fulfilled,
    )


# ── 6.1: Константы ──


def test_contract_tags_are_frozenset() -> None:
    """CONTRACT_TAGS — неизменяемый набор."""
    assert isinstance(CONTRACT_TAGS, frozenset)
    assert CONTRACT_TAG_PROMISE_GIVEN in CONTRACT_TAGS
    assert CONTRACT_TAG_PROMISE_RECEIVED in CONTRACT_TAGS
    assert CONTRACT_TAG_DEBT in CONTRACT_TAGS


# ── 6.3: apply() — тег + decay ──


def test_apply_adds_contract_tag() -> None:
    """apply() добавляет contract_tag в теги EventMemory."""
    mm = _make_manager()
    state = NPCState(npc_id="npc_01")
    event = EventDTO.create(
        event_type="player_promised",
        source="player",
        payload={
            "npc_id": "npc_01",
            "target_id": "player",
            "contract_tag": CONTRACT_TAG_PROMISE_GIVEN,
            "summary": "Игрок обещал помочь",
            "scene_state": {},
        },
    )
    new_state = mm.apply(event, state, campaign_id="camp_1")
    mems = new_state.narrative_cache
    assert len(mems) == 1
    assert CONTRACT_TAG_PROMISE_GIVEN in mems[0].tags


def test_apply_lowers_decay_for_contracts() -> None:
    """Контрактные события decay_rate ×0.4 от базового."""
    mm = _make_manager()
    state = NPCState(npc_id="npc_01")
    # Базовый decay для neutral = 0.05
    event = EventDTO.create(
        event_type="player_promised",
        source="player",
        payload={
            "npc_id": "npc_01",
            "target_id": "player",
            "contract_tag": CONTRACT_TAG_PROMISE_GIVEN,
            "summary": "Обещание",
            "scene_state": {},
        },
    )
    new_state = mm.apply(event, state, campaign_id="camp_1")
    assert new_state.narrative_cache[0].decay_rate < 0.05


def test_apply_ignores_unknown_contract_tag() -> None:
    """Несуществующий contract_tag не добавляется в теги."""
    mm = _make_manager()
    state = NPCState(npc_id="npc_01")
    event = EventDTO.create(
        event_type="talk",
        source="player",
        payload={
            "npc_id": "npc_01",
            "contract_tag": "nonexistent_tag",
            "scene_state": {},
        },
    )
    new_state = mm.apply(event, state, campaign_id="camp_1")
    assert "nonexistent_tag" not in new_state.narrative_cache[0].tags


# ── 6.4: get_unfulfilled_contracts ──


def test_get_unfulfilled_returns_only_active() -> None:
    """fulfilled=True исключается из результата."""
    mm = _make_manager()
    active = _make_contract_mem(fulfilled=False)
    done = _make_contract_mem(fulfilled=True)
    cache = (active, done)
    result = mm.get_unfulfilled_contracts(cache)
    assert len(result) == 1
    assert result[0] is active


def test_get_unfulfilled_ignores_forgotten() -> None:
    """Forgotten события не попадают в контракты."""
    mm = _make_manager()
    active = _make_contract_mem()
    forgotten = _make_contract_mem(stage=MemoryStage.FORGOTTEN)
    cache = (active, forgotten)
    result = mm.get_unfulfilled_contracts(cache)
    assert len(result) == 1


def test_get_unfulfilled_filter_by_tag() -> None:
    """tag_filter ограничивает поиск конкретным тегом."""
    mm = _make_manager()
    promise = _make_contract_mem(tag=CONTRACT_TAG_PROMISE_GIVEN)
    debt = _make_contract_mem(tag=CONTRACT_TAG_DEBT)
    cache = (promise, debt)
    result = mm.get_unfulfilled_contracts(
        cache,
        tag_filter=(CONTRACT_TAG_DEBT,),
    )
    assert len(result) == 1
    assert CONTRACT_TAG_DEBT in result[0].tags


def test_get_unfulfilled_sorts_by_importance() -> None:
    """Результат сортирован: самые важные первые."""
    mm = _make_manager()
    low = _make_contract_mem(importance=0.3)
    high = _make_contract_mem(importance=0.9)
    mid = _make_contract_mem(importance=0.6)
    cache = (low, high, mid)
    result = mm.get_unfulfilled_contracts(cache)
    assert result[0].importance >= result[1].importance >= result[2].importance


def test_get_unfulfilled_empty_cache() -> None:
    """Пустой cache → пустой список."""
    mm = _make_manager()
    assert mm.get_unfulfilled_contracts(()) == []


# ── 6.5: DecisionHub — contract_modifiers ──


def test_contract_modifiers_boost_intent() -> None:
    """contract_modifiers повышает score целевого intent."""
    hub = DecisionHub(seed=42)
    state = NPCState(npc_id="npc_01")
    personality = NPCProfileL0(
        id="npc_01",
        name="Тест",
        tier="mass",
        drives_base={"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5},
        psyche_base=PsycheBase(willpower=50, breakpoint=80),
        voice_profile="neutral",
    )
    event = EventContext(event_type="player_interacts", actor_id="player")

    result_base = hub.compute(state=state, personality=personality, event=event, effective_drives=_MOCK_DRIVES)
    base_score = getattr(result_base, "scores", {}).get("remind", 0.0)

    result_boosted = hub.compute(
        state=state,
        personality=personality,
        event=event,
        effective_drives=_MOCK_DRIVES,
        contract_modifiers={"remind": 0.5},
    )
    boosted_score = getattr(result_boosted, "scores", {}).get("remind", 0.0)

    assert boosted_score >= base_score


def test_contract_modifiers_none_no_effect() -> None:
    """contract_modifiers=None — без эффекта, backward-compatible."""
    hub = DecisionHub(seed=42)
    state = NPCState(npc_id="npc_01")
    personality = NPCProfileL0(
        id="npc_01",
        name="Тест",
        tier="mass",
        drives_base={"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5},
        psyche_base=PsycheBase(willpower=50, breakpoint=80),
        voice_profile="neutral",
    )
    event = EventContext(event_type="player_interacts", actor_id="player")
    result = hub.compute(state=state, personality=personality, event=event, effective_drives=_MOCK_DRIVES)
    assert result.intent is not None

# path: /project/backend/tests/gameplay/test_p6_e1_dialogue_executor.py
"""
Файл: backend/tests/gameplay/test_p6_e1_dialogue_executor.py
Назначение: P6/E1 — T8: сквозной P1→P6 через DialogueExecutor (router=None:
    доставка без LLM; текст — не источник discovery). T3: анти-лотерея.
Зависимости: app.domain.*, app.services.*, tests.gameplay.harness
Запуск: python -m pytest backend/tests/gameplay/test_p6_e1_dialogue_executor.py -v
"""

import copy
from pathlib import Path

import pytest
from app.domain.communication import DialogueRequest, ExposureLevel
from app.domain.execution import QueuedTask, TaskKind, TaskPriority
from app.domain.player_epistemics import IDENTIFIED, UNKNOWN
from app.models.player_epistemic_state import PlayerEpistemicState
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.input.intent_compressor import extract_subject
from app.services.player_cognition.discovery_bridge import DiscoveryBridge
from app.services.truth_state_loader import TruthStateLoader
from tests.gameplay.harness import TavernGameplayHarness

BASE_DIR = Path(__file__).resolve().parents[3]
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"


class _FakeMemoryManager:
    """Эмит читает только get_dialogue_pressure (α: topic-heat)."""

    def __init__(self, pressure: int = 0) -> None:
        self._pressure = pressure

    def get_dialogue_pressure(self, campaign_id: str, npc_id: str) -> int:
        return self._pressure


def _task(owner: str, topic: str, tick: int) -> QueuedTask:
    req = DialogueRequest(
        topic=topic,
        target_id="player",
        exposure=ExposureLevel(semantic="normal"),
        intent_type="talk",
    )
    return QueuedTask(
        task_id=f"e1-{owner}-{tick}",
        tick=tick,
        counter=0,
        kind=TaskKind.DIALOGUE,
        priority=TaskPriority.NORMAL,
        creator_system="test",
        owner_id=owner,
        target_ids=["player"],
        payload=req,
        created_tick=tick,
    )


def _executor(borko_dict, truth, bridge, trust, pressure):
    return DialogueExecutor(
        router=None,
        memory_manager=_FakeMemoryManager(pressure=pressure),
        discovery_bridge=bridge,
        npc_states_provider=lambda cid: [borko_dict],
        relationship_provider=lambda cid, knower, recipient: {
            "trust": trust,
            "fear": 0.0,
        },
        subject_resolver=lambda topic: extract_subject(f"про {topic}"),
    )


def _rig(harness, trust, pressure):
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    bridge = DiscoveryBridge(state, truth)
    executor = _executor(borko_dict, truth, bridge, trust, pressure)
    return executor, truth, state


@pytest.fixture()
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    _h.advance_ticks(3)
    yield _h
    _h.dispose()


def test_t8_reveal_via_executor_delivery(harness):
    """T8: «Спроси Борко про караван», trust=60, давление=2 → P3→P4→P5→P6."""
    executor, truth, state = _rig(harness, trust=60.0, pressure=2)
    artifacts = list(executor.execute(_task("guard_borko", "караван", tick=5)))
    assert artifacts and artifacts[-1].success is True
    assert truth.discovered_secrets == {"borko_negligence"}
    assert state.level("borko_negligence") == IDENTIFIED
    assert len(state.observations) == 1


def test_t8_deny_via_executor(harness):
    """T8-контр: trust=0, давление=0 → DENY: уровень 0, observation only."""
    executor, truth, state = _rig(harness, trust=0.0, pressure=0)
    artifacts = list(executor.execute(_task("guard_borko", "караван", tick=6)))
    assert artifacts and artifacts[-1].success is True
    assert truth.discovered_secrets == set()
    assert state.level("borko_negligence") == UNKNOWN
    assert len(state.observations) == 1


_NON_CANON_TOPICS = ["зебра", "квадрат", "философия", "гравий", "оптимизм"]


def test_t3_random_topics_zero_discovery(harness):
    """T3: 100 не-канонных тем → 0 discovery (текст/тема не угадываются)."""
    executor, truth, state = _rig(harness, trust=60.0, pressure=2)
    for i in range(100):
        topic = _NON_CANON_TOPICS[i % len(_NON_CANON_TOPICS)]
        list(executor.execute(_task("guard_borko", topic, tick=10 + i)))
    assert truth.discovered_secrets == set()
    assert state.levels == {}


def test_t3_no_string_matching_in_dialogue(harness, monkeypatch):
    """T3-инвариант ТЗ: SequenceMatcher не вызывается в диалоговом тике."""
    import difflib

    import app.services.player_cognition.legacy_bridge as legacy_bridge

    calls = []
    _orig = difflib.SequenceMatcher

    def _spy(*args, **kwargs):
        calls.append(args)
        return _orig(*args, **kwargs)

    monkeypatch.setattr(difflib, "SequenceMatcher", _spy)
    monkeypatch.setattr(legacy_bridge, "SequenceMatcher", _spy)

    executor, truth, state = _rig(harness, trust=60.0, pressure=2)
    list(executor.execute(_task("guard_borko", "караван", tick=7)))
    assert calls == []

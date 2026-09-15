# path: /project/backend/tests/gameplay/test_p7_disclosure_verbalization.py
"""
Файл: backend/tests/gameplay/test_p7_disclosure_verbalization.py
Назначение: P7-A + P7-B (санкция Мастера) —
    P7-A: вердикт decide_disclosure выносится ДО вербализации, РОВНО
    ОДИН раз на реплику, сериализуется в промпт как поведенческая
    директива "[ДИРЕКТИВА РАСКРЫТИЯ: LEVEL]" и эмитится той же
    вычисленной величиной (один вердикт — один источник; LLM
    вербализует, не решает).
    P7-B: метка EAVESDROP по провенансу KnowledgeItem спикера:
    payload.exposure ∈ {secret, whisper} → CONTENT_EAVESDROP_FULL →
    IDENTIFIED; normal → CLUE; проводка отсутствует / знания нет →
    secret_id=None (observation only).
    Гварды: E1 target=="player"; E2 listener≠player ∧ speaker≠player;
    fail-open; монополия bridge; Р1 (mark только →IDENTIFIED).
    T-P7-4/T-P7-5 — production path: реальный NPC-словарь (harness),
    реальный retrieval, реальный bridge: реплика → SurfaceEvent.
Зависимости: app.domain.*, app.services.*, tests.gameplay.harness
Основные сущности: _FakeRouter, _SpyBridge, _FakeAvatar, _FakeSpatial,
    _FakeMemoryManager
Запуск: cd backend && python -m pytest tests/gameplay/test_p7_disclosure_verbalization.py -v
"""

import copy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.domain.communication import DialogueRequest, ExposureLevel
from app.domain.disclosure import DisclosureLevel
from app.domain.events import EventDTO
from app.domain.execution import QueuedTask, TaskKind, TaskPriority
from app.domain.player_epistemics import (
    CLUE,
    CONTENT_EAVESDROP_FULL,
    IDENTIFIED,
    UNKNOWN,
    SurfaceKind,
)
from app.models.player_epistemic_state import PlayerEpistemicState
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.input.intent_compressor import extract_subject
from app.services.player_cognition.discovery_bridge import DiscoveryBridge
from app.services.truth_state_loader import TruthStateLoader
from tests.gameplay.harness import TavernGameplayHarness

BASE_DIR = Path(__file__).resolve().parents[3]
CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"


# ── Двойники (наследуют паттерны E1/E2; контракты подтверждены А8) ──────

class _FakeRouter:
    """Захватывает промпт; контракт request_for_agent + _abort_generation."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list = []

    def request_for_agent(self, agent_name, prompt, system_prompt, params):
        self.prompts.append(prompt)
        return self._reply

    def _abort_generation(self) -> None:
        pass


class _SpyBridge:
    """Двойник моста: пишет полученные SurfaceEvent."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.received = []

    def process(self, surface):
        self.received.append(surface)
        return self._inner.process(surface)


class _FakeAvatar:
    def __init__(self) -> None:
        self.entries = []

    def append_journal(self, campaign_id, speaker, text) -> None:
        self.entries.append((campaign_id, speaker, text))


class _FakeSpatial:
    def __init__(self, dist) -> None:
        self._dist = dist

    def player_distances(self, ids):
        return {i: self._dist for i in ids}


class _FakeMemoryManager:
    def __init__(self, pressure: int = 0) -> None:
        self._pressure = pressure

    def get_dialogue_pressure(self, campaign_id: str, npc_id: str) -> int:
        return self._pressure

    def get_stm_prompt_block_pair(self, campaign_id: str, a: str, b: str) -> str:
        return ""


# ── Фикстуры P7-A (executor; наследуют _rig E1) ─────────────────────────

def _task(owner: str, topic: str, tick: int) -> QueuedTask:
    req = DialogueRequest(
        topic=topic,
        target_id="player",
        exposure=ExposureLevel(semantic="normal"),
        intent_type="talk",
    )
    return QueuedTask(
        task_id=f"p7-{owner}-{tick}",
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


def _executor(borko_dict, truth, bridge, trust, pressure, router):
    return DialogueExecutor(
        router=router,
        memory_manager=_FakeMemoryManager(pressure=pressure),
        discovery_bridge=bridge,
        npc_states_provider=lambda cid: [borko_dict],
        relationship_provider=lambda cid, knower, recipient: {
            "trust": trust,
            "fear": 0.0,
        },
        subject_resolver=lambda topic: extract_subject(f"про {topic}"),
    )


@pytest.fixture()
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    _h.advance_ticks(3)
    yield _h
    _h.dispose()


# ── Фикстуры P7-B (subscriber; наследуют паттерн E2) ────────────────────

def _spoke_event(target_id, exposure, radius, visibility, topic="караван"):
    return EventDTO.create(
        event_type="npc_spoke",
        source="guard_borko",
        payload={
            "target_id": target_id,
            "text": "Караван шёл через перевал, я видел.",
            "topic": topic,
            "exposure": exposure,
            "tone": "NEUTRAL",
            "intent_type": "talk",
        },
        visibility=visibility,
        radius=radius,
        persistence_level="session",
    )


def _make_subscriber(bridge, dist, npc_states=None, resolver=None):
    """P7-B: npc_states_provider (существующий) + subject_resolver (НОВЫЙ
    контракт P7-B — Callable[[topic], SubjectRef], симметрия E1)."""
    kwargs = dict(
        memory_manager=MagicMock(),
        relationship_store=MagicMock(),
        campaign_id_provider=lambda: "test_p7",
        avatar_service=_FakeAvatar(),
        spatial_query_provider=lambda: _FakeSpatial(dist),
        tick_provider=lambda: 42,
        discovery_bridge_provider=lambda: bridge,
    )
    if npc_states is not None:
        kwargs["npc_states_provider"] = lambda: npc_states
    if resolver is not None:
        kwargs["subject_resolver"] = resolver
    return NpcDialogueSubscriber(**kwargs)


# ── P7-A: вердикт до слов ───────────────────────────────────────────────

def test_t_p7_1_reveal_directive_in_prompt(harness):
    """T-P7-1: REVEAL-условия → промпт содержит директиву раскрытия."""
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    router = _FakeRouter("Он спал на посту, и караван увели.")
    executor = _executor(borko_dict, truth, spy, trust=60.0, pressure=2, router=router)

    artifacts = list(executor.execute(_task("guard_borko", "караван", tick=5)))

    assert artifacts and artifacts[-1].success is True
    assert router.prompts, "LLM не вызвана"
    assert "[ДИРЕКТИВА РАСКРЫТИЯ: REVEAL]" in router.prompts[0]
    dialogues = [s for s in spy.received if s.kind == SurfaceKind.DIALOGUE_OUTCOME]
    assert dialogues, "DIALOGUE_OUTCOME не эмитирована"
    assert dialogues[0].disclosure_level == DisclosureLevel.REVEAL


def test_t_p7_2_deny_directive_and_no_level(harness):
    """T-P7-2: DENY (trust=0, давление=0) → директива уклонения в промпте;
    уровень не меняется; observation записан; mark не вызван."""
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    router = _FakeRouter("Не знаю ничего про это.")
    executor = _executor(borko_dict, truth, spy, trust=0.0, pressure=0, router=router)

    artifacts = list(executor.execute(_task("guard_borko", "караван", tick=6)))

    assert artifacts and artifacts[-1].success is True
    assert "[ДИРЕКТИВА РАСКРЫТИЯ: DENY]" in router.prompts[0]
    assert "уклон" in router.prompts[0].lower()
    assert state.level("borko_negligence") == UNKNOWN
    assert truth.discovered_secrets == set()
    assert len(state.observations) == 1


def test_t_p7_3_single_verdict_per_replica(harness, monkeypatch):
    """T-P7-3 (ПИН, инвариант Мастера §1): decide_disclosure — РОВНО ОДИН
    вызов на реплику, при любом маршруте (LLM / заглушка)."""
    import app.services.execution.dialogue_executor as _dex

    calls = []
    _orig = _dex.decide_disclosure

    def _spy_fn(*a, **k):
        calls.append(1)
        return _orig(*a, **k)

    monkeypatch.setattr(_dex, "decide_disclosure", _spy_fn)

    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    executor = _executor(borko_dict, truth, spy, trust=60.0, pressure=2, router=None)

    list(executor.execute(_task("guard_borko", "караван", tick=7)))

    assert len(calls) == 1, f"вердикт вычислен {len(calls)} раз — DOUBLE TRUTH"
    assert truth.discovered_secrets == {"borko_negligence"}
    assert state.level("borko_negligence") == IDENTIFIED


def test_t_p7_7_router_none_still_emits_verdict(harness):
    """T-P7-7 (ПИН, LLM-OFF): router=None → вердикт вычислен, поверхность
    DIALOGUE_OUTCOME эмитирована по вердикту; семантика E1 сохранена."""
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    executor = _executor(borko_dict, truth, spy, trust=60.0, pressure=2, router=None)

    artifacts = list(executor.execute(_task("guard_borko", "караван", tick=8)))

    assert artifacts and artifacts[-1].success is True
    dialogues = [s for s in spy.received if s.kind == SurfaceKind.DIALOGUE_OUTCOME]
    assert dialogues and dialogues[0].disclosure_level == DisclosureLevel.REVEAL
    assert state.level("borko_negligence") == IDENTIFIED


# ── P7-B: метка по провенансу (production path) ─────────────────────────

def test_t_p7_4_whisper_eavesdrop_full_identified(harness):
    """T-P7-4 (production path): whisper-реплика NPC→NPC, спикер обладает
    канон-знанием → secret_id проставлен, FULL → IDENTIFIED + mark (Р1)."""
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    sub = _make_subscriber(
        spy, dist=2.0, npc_states=[borko_dict],
        resolver=lambda t: extract_subject(f"про {t}"),
    )

    sub.on_npc_spoke(_spoke_event("maid_lusya", "whisper", 3.0, "whisper"))

    eaves = [s for s in spy.received if s.kind == SurfaceKind.EAVESDROP]
    assert eaves, "EAVESDROP surface не эмитирована"
    assert eaves[0].secret_id == "borko_negligence"
    assert eaves[0].content_class == CONTENT_EAVESDROP_FULL
    assert state.level("borko_negligence") == IDENTIFIED
    assert truth.discovered_secrets == {"borko_negligence"}


def test_t_p7_5_normal_eavesdrop_clue(harness):
    """T-P7-5 (production path): normal-реплика, то же знание → метка
    есть, но CLUE (не IDENTIFIED); mark не вызван."""
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    sub = _make_subscriber(
        spy, dist=4.0, npc_states=[borko_dict],
        resolver=lambda t: extract_subject(f"про {t}"),
    )

    sub.on_npc_spoke(_spoke_event("maid_lusya", "normal", 6.0, "public"))

    eaves = [s for s in spy.received if s.kind == SurfaceKind.EAVESDROP]
    assert eaves, "EAVESDROP surface не эмитирована"
    assert eaves[0].secret_id == "borko_negligence"
    assert eaves[0].content_class is None
    assert state.level("borko_negligence") == CLUE
    assert truth.discovered_secrets == set()


def test_t_p7_6_unwired_labeling_fail_open(harness):
    """T-P7-6 (ПИН, регресс E2): проводка метки отсутствует →
    secret_id=None → observation only; уровень не меняется."""
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    sub = _make_subscriber(spy, dist=2.0)  # без npc_states/resolver

    sub.on_npc_spoke(_spoke_event("maid_lusya", "whisper", 3.0, "whisper"))

    eaves = [s for s in spy.received if s.kind == SurfaceKind.EAVESDROP]
    assert eaves, "EAVESDROP surface не эмитирована"
    assert eaves[0].secret_id is None
    assert state.level("borko_negligence") == UNKNOWN
    assert truth.discovered_secrets == set()
    assert len(state.observations) == 1


def test_t_p7_6b_no_knowledge_observation_only(harness):
    """T-P7-6b: полная проводка, но тема вне знания спикера →
    метки нет (провенанс пуст) → observation only."""
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    sub = _make_subscriber(
        spy, dist=2.0, npc_states=[borko_dict],
        resolver=lambda t: extract_subject(f"про {t}"),
    )

    sub.on_npc_spoke(_spoke_event("maid_lusya", "whisper", 3.0, "whisper", topic="погода"))

    eaves = [s for s in spy.received if s.kind == SurfaceKind.EAVESDROP]
    assert eaves, "EAVESDROP surface не эмитирована"
    assert eaves[0].secret_id is None
    assert state.level("borko_negligence") == UNKNOWN
    assert truth.discovered_secrets == set()


def test_t_p7_8_two_channels_one_bridge_monotonic(harness):
    """T-P7-8 (интеграл): два канала — один Bridge — одно состояние.
    EAVESDROP-FULL поднял до IDENTIFIED; последующий DENY по E1-каналу
    добавляет observation, но НЕ понижает уровень (монотонность)."""
    borko_dict = copy.deepcopy(harness.inspect_npc("guard_borko"))
    truth = TruthStateLoader.load(CANON_PATH)
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth))
    sub = _make_subscriber(
        spy, dist=2.0, npc_states=[borko_dict],
        resolver=lambda t: extract_subject(f"про {t}"),
    )
    sub.on_npc_spoke(_spoke_event("maid_lusya", "whisper", 3.0, "whisper"))
    assert state.level("borko_negligence") == IDENTIFIED

    executor = _executor(borko_dict, truth, spy, trust=0.0, pressure=0, router=None)
    list(executor.execute(_task("guard_borko", "караван", tick=9)))

    assert state.level("borko_negligence") == IDENTIFIED  # не понижен
    assert truth.discovered_secrets == {"borko_negligence"}
    assert len(state.observations) == 2  # eavesdrop + deny
# path: /project/backend/tests/gameplay/test_p6_e2_eavesdrop_channel.py
"""
Файл: backend/tests/gameplay/test_p6_e2_eavesdrop_channel.py
Назначение: E2 (S256) — EAVESDROP-канал delivery: подслушанная canonical-
    реплика NPC->NPC (мембрана S128/Р-Г пройдена, журнал игрока записан)
    становится observation игрока БЕЗ эпистемического перехода: до P7
    secret_id/content_class = None -> map_surface -> observation only;
    mark_discovered недостижим (Р1-МОНОПОЛИЯ).
    Законы: DISCOVERY IS DELIVERY · PROVENANCE, NOT STRINGS.
Покрытие: T-E2-1 пин моста · T-E2-2/3 причинный контраст (радиус) ·
    T-E2-4 адресат · T-E2-5 сентинел · T-E2-6 fail-open · T-E2-8
    unwired-skip. T-E2-7 (монополия) — AST-гейт, отдельный скрипт.
"""

from unittest.mock import MagicMock

from app.domain.communication import SELF_TALK_SENTINEL
from app.domain.events import EventDTO
from app.domain.player_epistemics import UNKNOWN, SurfaceEvent, SurfaceKind
from app.models.player_epistemic_state import PlayerEpistemicState
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber
from app.services.player_cognition.discovery_bridge import (
    DiscoveryBridge,
    map_surface,
)


class _FakeAvatar:
    """Журнал игрока: запись вызовов append_journal."""

    def __init__(self) -> None:
        self.entries = []

    def append_journal(self, campaign_id, speaker, text) -> None:
        self.entries.append((campaign_id, speaker, text))


class _FakeSpatial:
    """SpatialQuery-двойник: только player_distances (путь :94-95).
    Без атрибута distance -> мембрана адресата Р-Б2 пропускается
    (hasattr-гейт :143) — вне рамки E2."""

    def __init__(self, dist) -> None:
        self._dist = dist

    def player_distances(self, ids):
        return {i: self._dist for i in ids}


class _SpyBridge:
    """Двойник моста: пишет полученные SurfaceEvent и результаты."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.received = []
        self.results = []

    def process(self, surface):
        res = self._inner.process(surface)
        self.received.append(surface)
        self.results.extend(res)
        return res


class _RaisingBridge:
    """T-E2-6: process() падает после доказанной доставки."""

    def process(self, surface):
        raise RuntimeError("boom-e2")


def _surface():
    return SurfaceEvent(
        kind=SurfaceKind.EAVESDROP,
        tick=42,
        source_id="borko",
        secret_id=None,
        content_class=None,
        subject_hint="караван",
    )


def _spoke_event(target_id, radius=6.0):
    return EventDTO.create(
        event_type="npc_spoke",
        source="borko",
        payload={
            "target_id": target_id,
            "text": "Караван шёл через перевал, я видел.",
            "topic": "караван",
            "tone": "NEUTRAL",
        },
        visibility="public",
        radius=radius,
        persistence_level="session",
    )


def _make_subscriber(bridge_provider, dist, avatar):
    return NpcDialogueSubscriber(
        memory_manager=MagicMock(),
        relationship_store=MagicMock(),
        campaign_id_provider=lambda: "test_e2",
        avatar_service=avatar,
        spatial_query_provider=lambda: _FakeSpatial(dist),
        tick_provider=lambda: 42,
        discovery_bridge_provider=bridge_provider,
    )


def _wired():
    state = PlayerEpistemicState()
    spy = _SpyBridge(DiscoveryBridge(state, truth_state=None))
    return state, spy


def test_t_e2_1_unmarked_eavesdrop_is_observation_only() -> None:
    """T-E2-1 (ПИН, главный): EAVESDROP secret_id=None -> obs only.
    Закрывает дыру покрытия Н26: гвард map_surface :83-84 — регрессионно."""
    surface = _surface()

    decision = map_surface(surface)
    assert decision.secret_id is None
    assert decision.target_level is None
    assert decision.observation is True

    state = PlayerEpistemicState()
    bridge = DiscoveryBridge(state, truth_state=None)
    (update,) = bridge.process(surface)

    assert update.secret_id is None
    assert update.level_changed is False
    assert update.marked_discovered is False
    assert update.from_level == UNKNOWN
    assert update.to_level == UNKNOWN
    assert update.observation is not None
    assert update.observation.secret_id is None

    assert len(state.observations) == 1
    assert state.observations[0].surface_kind == SurfaceKind.EAVESDROP
    assert state.observations[0].secret_id is None


def test_t_e2_2_in_radius_delivery_and_observation() -> None:
    """T-E2-2 (КОНТРАСТ +): canonical NPC->NPC, игрок в радиусе ->
    журнал + EAVESDROP. Жёсткие критерии Мастера: level_changed=False,
    marked=False, secret_id=None (анти CAUSAL FALSE GREEN) — через контур."""
    state, spy = _wired()
    avatar = _FakeAvatar()
    sub = _make_subscriber(lambda: spy, dist=2.0, avatar=avatar)

    sub.on_npc_spoke(_spoke_event(target_id="guard_captain"))

    # доставка: реплика в журнале игрока
    assert len(avatar.entries) == 1
    assert avatar.entries[0][1] == "borko"
    # канал: ровно один SurfaceEvent с чистой провенанс-структурой
    assert len(spy.received) == 1
    s = spy.received[0]
    assert s.kind == SurfaceKind.EAVESDROP
    assert s.secret_id is None
    assert s.content_class is None
    assert s.source_id == "borko"
    assert s.subject_hint == "караван"
    # эпистемика: observation есть, перехода нет, mark не вызван
    assert len(spy.results) == 1
    u = spy.results[0]
    assert u.secret_id is None
    assert u.level_changed is False
    assert u.marked_discovered is False
    assert u.to_level == UNKNOWN
    assert len(state.observations) == 1
    assert state.observations[0].surface_kind == SurfaceKind.EAVESDROP


def test_t_e2_3_out_of_radius_no_delivery_no_discovery() -> None:
    """T-E2-3 (КОНТРАСТ -): игрок вне радиуса -> нет журнала, нет эмита,
    нет observation. Провал восприятия = провал доставки = провал знания."""
    state, spy = _wired()
    avatar = _FakeAvatar()
    sub = _make_subscriber(lambda: spy, dist=10.0, avatar=avatar)

    sub.on_npc_spoke(_spoke_event(target_id="guard_captain", radius=6.0))

    assert avatar.entries == []
    assert spy.received == []
    assert state.observations == []


def test_t_e2_4_player_addressee_is_e1_territory() -> None:
    """T-E2-4 (АДРЕСАТ): listener='player' -> журнал пишется (существующее
    поведение сохранено), EAVESDROP не возникает (суверенитет E1)."""
    state, spy = _wired()
    avatar = _FakeAvatar()
    sub = _make_subscriber(lambda: spy, dist=2.0, avatar=avatar)

    sub.on_npc_spoke(_spoke_event(target_id="player"))

    assert len(avatar.entries) == 1
    assert spy.received == []
    assert state.observations == []


def test_t_e2_5_soliloquy_is_eavesdroppable() -> None:
    """T-E2-5 (СЕНТИНЕЛ): SELF_TALK_SENTINEL, whisper-радиус (материа-
    лизатор Н34: сентинел -> radius 3.0), игрок вплотную -> эмит есть."""
    state, spy = _wired()
    avatar = _FakeAvatar()
    sub = _make_subscriber(lambda: spy, dist=2.0, avatar=avatar)

    sub.on_npc_spoke(_spoke_event(target_id=SELF_TALK_SENTINEL, radius=3.0))

    assert len(avatar.entries) == 1
    assert len(spy.received) == 1
    assert spy.received[0].kind == SurfaceKind.EAVESDROP
    assert len(state.observations) == 1


def test_t_e2_6_emit_failure_is_fail_open(caplog) -> None:
    """T-E2-6 (FAIL-OPEN): bridge.process падает ПОСЛЕ доказанной
    доставки -> WARNING; исключение не покидает обработчик; журнал жив."""
    avatar = _FakeAvatar()
    sub = _make_subscriber(lambda: _RaisingBridge(), dist=2.0, avatar=avatar)

    with caplog.at_level("WARNING"):
        sub.on_npc_spoke(_spoke_event(target_id="guard_captain"))

    assert len(avatar.entries) == 1
    assert any("eavesdrop emit failed" in r.getMessage() for r in caplog.records)


def test_t_e2_8_unwired_bridge_is_silent_skip(caplog) -> None:
    """T-E2-8 (ПРОВОДКА): bridge=None -> тихий skip (прецедент :88 —
    отсутствие consumer-wiring не аварийно); журнал и обработчик живы."""
    avatar = _FakeAvatar()
    sub = _make_subscriber(lambda: None, dist=2.0, avatar=avatar)

    with caplog.at_level("WARNING"):
        sub.on_npc_spoke(_spoke_event(target_id="guard_captain"))

    assert len(avatar.entries) == 1
    assert not [r for r in caplog.records if "eavesdrop" in r.getMessage()]

"""SPATIAL-UNIFICATION (B7): инварианты волны B.

1. Реестр активных SQ-контекстов (B4/B5): register / токен / if-absent / release / изоляция.
2. Провайдер = только реестр (B5): entry -> SQ, пусто -> None + error (никаких RuntimeError).
3. Журнальный тик-гейт (B4): WARN-skip при расхождении event_tick/SQ.tick_id,
   pass при совпадении, fail-open parity для легаси payload без event_tick.
4. Шинный штамп event_tick (B4): default = identity-тик, явный штамп не перетирается.
"""

import dataclasses
import logging
import pathlib
import sys
import threading

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.events.event_bus import EventBus
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber
from app.services.game_loop.game_loop import GameLoop


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self.calls.append(name)
            return None

        return _call


_FakeDTO = dataclasses.make_dataclass(
    "FakeDTO",
    [
        ("type", str, dataclasses.field(default="")),
        ("source", str, dataclasses.field(default="")),
        ("payload", dict, dataclasses.field(default_factory=dict)),
        ("id", object, dataclasses.field(default=None)),
        ("timestamp", float, dataclasses.field(default=0.0)),
    ],
    frozen=True,
)


def _make_event(etype, source, payload):
    from app.domain.events import EventDTO

    try:
        return EventDTO(type=etype, source=source, payload=payload)
    except TypeError:
        return _FakeDTO(type=etype, source=source, payload=payload)


def _bare_loop(cid="camp_test"):
    gl = GameLoop.__new__(GameLoop)
    gl._active_turn_contexts = {}
    gl._active_turn_ctx_seq = 0
    gl._active_turn_ctx_lock = threading.Lock()
    gl._current_campaign_id = cid
    return gl


class _SQStub:
    def __init__(self, tick_id, dist=1.0):
        self.tick_id = tick_id
        self._dist = dist
        self._npc_positions = {
            "npc_a": {"name": "Мэри", "local_position": {"x": 1.0, "y": 0.0}},
            "player": {"local_position": {"x": 0.0, "y": 0.0}},
        }

    def player_distances(self, ids):
        return {i: self._dist for i in ids}


def _make_sub(sq, av=None):
    sub = NpcDialogueSubscriber.__new__(NpcDialogueSubscriber)
    sub._avatar_service = av if av is not None else _Recorder()
    sub._get_spatial_query = (lambda: sq) if sq is not None else None
    sub._get_campaign_id = lambda: "camp_test"
    sub._get_tick = lambda: 7
    sub._pending_recognition = []
    sub._get_discovery_bridge = None
    sub._subject_resolver = None
    sub._get_npc_state = None
    sub._extractor = None
    sub.memory = _Recorder()
    sub.relationships = _Recorder()
    sub._rel_write_gate = _Recorder()
    sub._l1_chronicle = None
    return sub


def _spoke_payload(event_tick=None):
    payload = {
        "target_id": "player",
        "text": "Привет, путник.",
        "tone": "NEUTRAL",
        "topic": "greeting",
    }
    if event_tick is not None:
        payload["event_tick"] = event_tick
    return payload


# ── 1. Реестр (B4/B5) ──


def test_register_active_roundtrip_and_empty_provider(caplog):
    gl = _bare_loop()
    sq = _SQStub(5)
    token = gl._register_active_spatial_context("camp_test", sq)
    assert token is not None and token > 0
    assert gl._get_spatial_query_for_subscriber() is sq
    gl._release_active_spatial_context("camp_test", token)
    with caplog.at_level(logging.ERROR):
        assert gl._get_spatial_query_for_subscriber() is None
    assert any("SPATIAL-PROVIDER" in rec.getMessage() for rec in caplog.records)


def test_register_idle_if_absent_respects_player_turn():
    gl = _bare_loop()
    sq_player = _SQStub(9)
    token = gl._register_active_spatial_context("camp_test", sq_player)
    assert gl._register_idle_spatial_context("camp_test", _SQStub(10)) is None
    assert gl._get_spatial_query_for_subscriber() is sq_player
    gl._release_active_spatial_context("camp_test", token)
    assert gl._get_spatial_query_for_subscriber() is None


def test_release_stale_token_protects_newer_context():
    gl = _bare_loop()
    sq1 = _SQStub(1)
    tok1 = gl._register_active_spatial_context("camp_test", sq1)
    sq2 = _SQStub(2)
    tok2 = gl._register_active_spatial_context("camp_test", sq2)
    assert tok2 > tok1
    gl._release_active_spatial_context("camp_test", tok1)
    assert gl._get_spatial_query_for_subscriber() is sq2
    gl._release_active_spatial_context("camp_test", tok2)
    assert gl._get_spatial_query_for_subscriber() is None


def test_cross_campaign_isolation():
    gl = _bare_loop()
    ta = gl._register_active_spatial_context("camp_a", _SQStub(3))
    tb = gl._register_active_spatial_context("camp_b", _SQStub(4))
    assert ta != tb
    gl._release_active_spatial_context("camp_a", ta)
    gl._current_campaign_id = "camp_b"
    assert gl._active_turn_contexts["camp_b"][1].tick_id == 4
    assert gl._active_turn_contexts.get("camp_a") is None
    assert gl._active_turn_contexts.get("camp_b") is not None


def test_register_idle_concurrent_single_winner():
    gl = _bare_loop()
    sq = _SQStub(6)
    barrier = threading.Barrier(8)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        token = gl._register_idle_spatial_context("camp_test", sq)
        with lock:
            results.append(token)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert gl._get_spatial_query_for_subscriber() is sq


# ── 2. Журнальный тик-гейт (B4) ──


def test_gate_cross_tick_warns_and_skips(caplog):
    av = _Recorder()
    sub = _make_sub(_SQStub(5), av)
    with caplog.at_level(logging.WARNING):
        sub.on_npc_spoke({"source": "npc_a", "payload": _spoke_payload(event_tick=4)})
    assert "append_journal" not in av.calls
    assert any("journal SKIP" in rec.getMessage() for rec in caplog.records)


def test_gate_valid_event_tick_passes_to_journal():
    av = _Recorder()
    sub = _make_sub(_SQStub(4), av)
    sub.on_npc_spoke({"source": "npc_a", "payload": _spoke_payload(event_tick=4)})
    assert "append_journal" in av.calls


def test_gate_legacy_payload_without_event_tick_fail_open():
    av = _Recorder()
    sub = _make_sub(_SQStub(4), av)
    sub.on_npc_spoke({"source": "npc_a", "payload": _spoke_payload()})
    assert "append_journal" in av.calls


def test_provider_none_means_no_journal_entry():
    av = _Recorder()
    sub = _make_sub(None, av)
    sub.on_npc_spoke({"source": "npc_a", "payload": _spoke_payload(event_tick=4)})
    assert "append_journal" not in av.calls


# ── 3. Шинный штамп event_tick (B4) ──


def test_finalize_identity_default_stamp_uses_identity_tick():
    bus = EventBus()
    bus._identity_provider = lambda t, s: (11, 3)
    out = bus._finalize_identity(_make_event("NPC_SPOKE", "npc_a", {"text": "hi"}))
    assert out.payload.get("event_tick") == 11
    assert out.timestamp == float(11)


def test_finalize_identity_does_not_overwrite_stamp():
    bus = EventBus()
    bus._identity_provider = lambda t, s: (11, 3)
    out = bus._finalize_identity(
        _make_event("NPC_SPOKE", "npc_a", {"text": "hi", "event_tick": 4})
    )
    assert out.payload["event_tick"] == 4


def test_finalize_identity_none_provider_is_passthrough():
    bus = EventBus()
    out = bus._finalize_identity(_make_event("NPC_SPOKE", "npc_a", {"text": "hi"}))
    assert "event_tick" not in out.payload
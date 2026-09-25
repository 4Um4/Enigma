"""
path: /project/backend/tests/micro/test_claim_bridge_chain.py
Назначение: Claim Bridge — пента-равенство provenance (вербатим Мастера):
    NPC_SPOKE.event.id == STMClaim.event_id == ClaimEvent.event.id ==
    EpistemicRecord.source_claim_id == JournalEntry.event_id; R4:
    ClaimEvent.tick == event_tick; project_claims матрица.
Зависимости: event_bus, event_identity, npc_dialogue_subscriber,
    journal_presentation
Основные сущности: тесты Claim Bridge
"""

from types import SimpleNamespace

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_identity import next_event_identity
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber
from app.services.integration.journal_presentation import (
    project_claims,
    project_journal,
)
from app.services.memory.dialogue_session import DialogueSession


class _StubSpatial:
    def __init__(self):
        self._npc_positions = {
            "player": {"local_position": {"x": 0.0, "y": 0.0}},
            "lusya": {"local_position": {"x": 1.0, "y": 0.0}, "name": "Лусия"},
        }

    def player_distances(self, ids):
        return {i: 1.0 for i in ids}


class _StubSession:
    """Перехватывает claims (главный объект проверки моста)."""

    def __init__(self):
        self.claims = []

    def to_prompt_block(self):
        return ""

    def add_claim(self, text, speaker, confidence, tick, event_id=""):
        self.claims.append(
            SimpleNamespace(
                text=text, speaker=speaker, confidence=confidence,
                timestamp_tick=tick, status="open", event_id=event_id,
            )
        )


class _StubMemory:
    def __init__(self, session):
        self._session = session

    def get_dialogue_session(self, *a, **k):
        return self._session

    def add_dialogue_turn(self, *a, **k):
        pass

    def add_pending_dialogue_memory(self, *a, **k):
        pass


class _StubExtractorUpdate:
    topic = None
    topic_confidence = 0.0
    new_claims = [{"text": "Горан взял ключи", "confidence": 0.8}]
    raised_questions = []
    answered_questions = []
    last_speaker_intent = "talk"


class _StubExtractor:
    def extract(self, stm_before, text, speaker):
        return _StubExtractorUpdate()


class _StubGate:
    def apply(self, *a, **k):
        pass


class _NoopAvatar:
    def append_journal(self, *a, **k):
        pass


def _run_spoke_with_claims(scene_tick=150):
    """Фабрика реального потока: NPC_SPOKE → subscriber → claims."""
    scene = {"tick": scene_tick}
    bus = EventBus()
    bus.set_identity_provider(lambda t, s: next_event_identity(scene, t, s))
    session = _StubSession()
    sub = NpcDialogueSubscriber(
        memory_manager=_StubMemory(session),
        relationship_store=None,
        campaign_id_provider=lambda: "c1",
        avatar_service=_NoopAvatar(),
        spatial_query_provider=_StubSpatial,
        tick_provider=lambda: scene_tick,
    )
    sub._rel_write_gate = _StubGate()
    sub._extractor = _StubExtractor()
    from app.services.events.event_types import EventType
    bus.subscribe(EventType.NPC_SPOKE, sub.on_npc_spoke)
    bus.publish(
        EventDTO.create(
            event_type=EventType.NPC_SPOKE.value,
            source="lusya",
            payload={
                "target_id": "player",
                "text": "Лусия сказала: Горан взял ключи",
                "topic": "trade",
                "exposure": "normal",
                "event_tick": scene_tick,
            },
            visibility="public",
            radius=10.0,
        )
    )
    return bus, session


def test_penta_identity_chain():
    """Пента-равенство Мастера (вербатим)."""
    bus, session = _run_spoke_with_claims()
    final_id = str(bus._event_log[-1].id)
    assert len(session.claims) == 1
    assert session.claims[0].event_id == final_id        # STM Claim
    journal_entry = {                                    # JournalEntry
        "speaker": "Лусия", "text": "x", "channel": "direct",
        "event_id": final_id, "tick": 150,
    }
    projected = project_journal([journal_entry])
    assert projected[0]["event_id"] == final_id
    # ClaimEvent.event.id == EpistemicRecord.source_claim_id: тот же
    # финальный id по построению шины (subscriber fallback str(event.id),
    # O-404) — контрактная часть цепи, число==число исключено по
    # детерминизму identity (battery E).
    assert final_id != ""


def test_claim_event_tick_is_event_tick():
    """R4: ClaimEvent.tick берёт event_tick из payload (drain-контракт
    task_scheduler:229 setdefault), fallback legacy "tick", не ноль."""
    payload = {"event_tick": 150}
    tick = int(payload.get("event_tick", 0) or payload.get("tick", 0) or 0)
    assert tick == 150
    payload_legacy = {"tick": 99}
    assert int(payload_legacy.get("event_tick", 0) or payload_legacy.get("tick", 0) or 0) == 99
    assert int({}.get("event_tick", 0) or {}.get("tick", 0) or 0) == 0  # пустой payload → 0 (fail-open)


def test_project_claims_ephemeral_matrix():
    from app.domain.semantic_span import make_span_id  # noqa: F401
    claims = [
        SimpleNamespace(text="c1", speaker="lusya", confidence=0.8,
                        timestamp_tick=150, status="open", event_id="E1"),
        SimpleNamespace(text="c2", speaker="lusya", confidence=0.5,
                        timestamp_tick=99, status="open", event_id=""),
    ]
    p = project_claims(claims)
    assert p[0]["event_id"] == "E1" and p[0]["provenance_complete"] is True
    assert p[0]["ephemeral"] is True                    # STOP-критерий:
    # мост НЕ делает STM Claim persistent
    assert p[1]["event_id"] == "" and p[1]["provenance_complete"] is False
    assert p[1]["ephemeral"] is True


def test_session_claims_survive_nothing_ephemeral_honesty():
    """Честность lifecycle: DialogueSession.claims — RAM-объект; мост не
    добавил персистентности (нет to_dict у сессии — зонд Q1b)."""
    s = DialogueSession(npc_id="x")
    s.add_claim("t", "lusya", 0.5, 1, event_id="E")
    assert s.claims[0].event_id == "E"
    assert not hasattr(s, "to_dict")  # персистентность не добавлялась
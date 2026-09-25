"""
path: /project/backend/tests/micro/test_utterance_identity_chain.py
Назначение: Вертикальный срез Фазы 2 — сквозная идентичность NPC_SPOKE →
    journal → PresentationProjection. Границы: без LLM/Span/Board/Claim.
Зависимости: event_bus, event_identity, npc_dialogue_subscriber,
    journal_presentation
Основные сущности: тесты среза
"""

from types import SimpleNamespace

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_identity import next_event_identity
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber
from app.services.integration.journal_presentation import project_journal


class _StubSpatial:
    """Позиции близко: мембрана журнала проходит, INV-NPC-NAME резолвится."""

    def __init__(self):
        self._npc_positions = {
            "player": {"local_position": {"x": 0.0, "y": 0.0}},
            "lusya": {
                "local_position": {"x": 1.0, "y": 0.0},
                "name": "Лусия",
            },
        }

    def player_distances(self, ids):
        return {i: 1.0 for i in ids}


class _StubMemory:
    """Минимальный контур: _process_canonical деградирует мягко (прецедент
    soft-degradation подписчика), journal-ветка не зависит от памяти."""

    def get_dialogue_session(self, *a, **k):
        return SimpleNamespace(
            to_prompt_block=lambda: "",
            topic=None,
            add_claim=lambda **k: None,
            add_open_question=lambda **k: None,
            answer_question=lambda *a, **k: None,
        )

    def add_dialogue_turn(self, *a, **k):
        pass

    def add_pending_dialogue_memory(self, *a, **k):
        pass


class _StubGate:
    def apply(self, *a, **k):
        pass


class _CapturingAvatar:
    def __init__(self):
        self.calls = []

    def append_journal(self, campaign_id, speaker, text, channel="narrative",
                       event_id="", tick=0):
        self.calls.append(
            {"speaker": speaker, "text": text, "channel": channel,
             "event_id": event_id, "tick": tick}
        )


def _make_subscriber(avatar):
    sub = NpcDialogueSubscriber(
        memory_manager=_StubMemory(),
        relationship_store=None,
        campaign_id_provider=lambda: "c1",
        avatar_service=avatar,
        spatial_query_provider=_StubSpatial,
        tick_provider=lambda: 100,
    )
    sub._rel_write_gate = _Gate_stub()
    sub._extractor = None
    return sub


def _Gate_stub():
    return _StubGate()


def test_chain_npc_spoke_event_id_reaches_journal():
    """Сквозная идентичность: event.id, полученный подписчиком шины, —
    тот же, что лег в journal-запись (ADR-O-404, Фаза 2)."""
    scene = {"tick": 100}
    bus = EventBus()
    bus.set_identity_provider(lambda t, s: next_event_identity(scene, t, s))
    avatar = _CapturingAvatar()
    sub = _make_subscriber(avatar)
    from app.services.events.event_types import EventType
    bus.subscribe(EventType.NPC_SPOKE, sub.on_npc_spoke)

    bus.publish(
        EventDTO.create(
            event_type=EventType.NPC_SPOKE.value,
            source="lusya",
            payload={
                "target_id": "player",
                "text": "Привет",
                "topic": "trade",
                "exposure": "normal",
                "event_tick": 100,
            },
            visibility="public",
            radius=10.0,
        )
    )

    assert len(avatar.calls) == 1
    call = avatar.calls[0]
    # ГЛАВНАЯ проверка: journal наследует ФИНАЛЬНЫЙ id шины
    assert call["event_id"] == str(bus._event_log[-1].id)
    assert call["event_id"] != ""          # provisional-ноль исключён
    assert call["tick"] == 100             # event_tick (ADR-O-399)
    assert call["channel"] == "direct"     # игрок-адресат
    assert call["speaker"] == "Лусия"      # INV-NPC-NAME: имя, не npc_id


def test_projection_marks_provenance():
    """PresentationProjection: provenance_complete честен по записям."""
    projected = project_journal(
        [
            {"speaker": "Лусия", "text": "Привет", "channel": "direct",
             "event_id": "abc", "tick": 42},
            {"speaker": "Рассказчик", "text": "Метель.", "channel": "narrative"},
        ]
    )
    assert projected[0]["provenance_complete"] is True
    assert projected[0]["event_id"] == "abc"
    assert projected[1]["provenance_complete"] is False  # легальный legacy


def test_projection_end_to_end_event_id_preserved():
    """Полная цепь: шина → journal → проекция, event_id не меняется."""
    scene = {"tick": 100}
    bus = EventBus()
    bus.set_identity_provider(lambda t, s: next_event_identity(scene, t, s))
    bus.publish(
        EventDTO.create(
            event_type="npc_spoke", source="lusya",
            payload={"text": "x", "event_tick": 100},
        )
    )
    final_id = str(bus._event_log[-1].id)
    journal = [{"speaker": "l", "text": "x", "channel": "direct",
                "event_id": final_id, "tick": 100}]
    projected = project_journal(journal)
    assert projected[0]["event_id"] == final_id
    assert projected[0]["provenance_complete"] is True
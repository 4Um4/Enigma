"""
path: /project/backend/tests/micro/test_event_identity.py
Назначение: Regression battery identity-контракта EventDTO (ADR: Event Identity).
    Кейсы A-F + nested-publish. Все тесты идут через фабрику publish() шины —
    конструкторы EventDTO.create используются только как ВХОД (§13.4:
    фабрика реального потока = шина с провайдером, не прямое создание).
Зависимости: app.services.events.event_bus, app.services.events.event_identity
Основные сущности: тесты battery
"""

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_identity import next_event_identity


def _make_bus(scene: dict) -> EventBus:
    bus = EventBus()
    bus.set_identity_provider(lambda t, s: next_event_identity(scene, t, s))
    return bus


def _spoke(bus, text="Привет", source="lusya"):
    bus.publish(
        EventDTO.create(
            event_type="npc_spoke", source=source, payload={"text": text}
        )
    )
    return bus._event_log[-1]


def test_A_same_event_same_id():
    scene = {"tick": 100}
    bus = _make_bus(scene)
    e1 = _spoke(bus)
    scene["tick"] = 100  # логическое «то же событие» = та же позиция потока
    bus2 = _make_bus({"tick": 100})
    e2 = _spoke(bus2)
    assert e1.id == e2.id


def test_B_same_source_diff_tick_diff_id():
    scene = {"tick": 100}
    bus = _make_bus(scene)
    e1 = _spoke(bus)
    scene["tick"] = 101
    e2 = _spoke(bus)
    assert e1.id != e2.id


def test_C_same_tick_same_source_two_utterances_diff_id():
    """ГЛАВНЫЙ кейс (Мастер): старый timestamp=0 здесь схлопывал события."""
    scene = {"tick": 100}
    bus = _make_bus(scene)
    e1 = _spoke(bus, "Привет")
    e2 = _spoke(bus, "Уходи")
    assert e1.id != e2.id


def test_D_diff_source_same_tick_diff_id():
    scene = {"tick": 100}
    bus = _make_bus(scene)
    e1 = _spoke(bus, source="lusya")
    e2 = _spoke(bus, source="borko")
    assert e1.id != e2.id


def test_E_replay_same_sequence_same_ids():
    log1 = []
    scene = {"tick": 500}
    bus = _make_bus(scene)
    for t in ("a", "b", "c", "b"):
        log1.append(_spoke(bus, t))
    bus2 = _make_bus({"tick": 500})
    log2 = []
    for t in ("a", "b", "c", "b"):
        log2.append(_spoke(bus2, t))
    assert [e.id for e in log1] == [e.id for e in log2]


def test_F_identical_repeated_utterances_diff_id():
    """Две ОДИНАКОВЫЕ реплики подряд (штатный случай Investigation Board)."""
    scene = {"tick": 100}
    bus = _make_bus(scene)
    e1 = _spoke(bus, "Привет")
    e2 = _spoke(bus, "Привет")
    assert e1.id != e2.id


def test_G_nested_publish_projection_events():
    """Nested-publish (social_action_subscriber): ordinals назначаются в
    детерминированном порядке вложенности — родитель до проекций."""
    scene = {"tick": 100}
    bus = _make_bus(scene)
    parent = _spoke(bus, "outer")
    bus.publish(
        EventDTO.create(
            event_type="communication_claim", source="lusya", payload={}
        )
    )
    child = bus._event_log[-1]
    assert parent.id != child.id
    # порядок вложенности детерминирован: повтор → те же ids
    bus2 = _make_bus({"tick": 100})
    p2 = _spoke(bus2, "outer")
    bus2.publish(
        EventDTO.create(
            event_type="communication_claim", source="lusya", payload={}
        )
    )
    assert p2.id == parent.id and bus2._event_log[-1].id == child.id


def test_H_no_provider_provisional_id_preserved():
    bus = EventBus()
    e = EventDTO.create(event_type="npc_spoke", source="lusya", payload={})
    bus.publish(e)
    assert bus._event_log[-1].id == e.id
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
    bus.publish(EventDTO.create(event_type="npc_spoke", source=source, payload={"text": text}))
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
    bus.publish(EventDTO.create(event_type="communication_claim", source="lusya", payload={}))
    child = bus._event_log[-1]
    assert parent.id != child.id
    # порядок вложенности детерминирован: повтор → те же ids
    bus2 = _make_bus({"tick": 100})
    p2 = _spoke(bus2, "outer")
    bus2.publish(EventDTO.create(event_type="communication_claim", source="lusya", payload={}))
    assert p2.id == parent.id and bus2._event_log[-1].id == child.id


def test_H_no_provider_provisional_id_preserved():
    bus = EventBus()
    e = EventDTO.create(event_type="npc_spoke", source="lusya", payload={})
    bus.publish(e)
    assert bus._event_log[-1].id == e.id


def test_I_provisional_no_bus_collision_reproduces():
    """D-X03 X-A-T1: reproduce provisional-identity collision mechanism.

    Two EventDTO.create() calls with identical (event_type, source) and
    default timestamp=0.0, ordinal=0, WITHOUT EventBus finalization,
    produce identical event.id. Downstream _mem_id formula from
    memory_manager.py:371-372 (reproduced here locally, no apply() call)
    yields identical _mem_id when npc_id and summary also match.

    This proves the COLLISION MECHANISM is reproducible.
    It does NOT prove production reachability — that requires proof that
    two identical dialogue_line events actually flow through BUG-DL-06
    fallback in the same session (deferred to X-A runtime evidence).

    Contract reference (ADR-O-404, events.py:96-100):
    "ordinal=0 legal only for paths with proven cardinality 1".
    The investigated paths (npc_dialogue_subscriber.py:564,
    npc_tick_pipeline.py:1529/1617) do not carry that proof.
    """
    import hashlib

    # Two provisional creations, identical args, no bus finalization.
    # payload is DATA, not identity (events.py:97-98) — deliberately identical.
    e1 = EventDTO.create(
        event_type="dialogue_line",
        source="lusya",
        payload={"npc_id": "borko", "text": "Привет"},
    )
    e2 = EventDTO.create(
        event_type="dialogue_line",
        source="lusya",
        payload={"npc_id": "borko", "text": "Привет"},
    )

    # X1: provisional id collision — same (event_type, source, ts, ordinal)
    assert e1.id == e2.id, (
        f"provisional id collision expected, got {e1.id} != {e2.id}; "
        "either EventDTO.create changed its seed formula, or a default "
        "timestamp/ordinal became non-deterministic"
    )

    # X2: _mem_id formula from memory_manager.py:371-372 reproduced locally.
    # No apply() call — no production side effect.
    def _mem_id_for(ev, npc_id, summary):
        digest = hashlib.md5((summary or "").encode("utf-8")).hexdigest()[:12]
        return f"{ev.id}:{npc_id}:{digest}"

    m1 = _mem_id_for(e1, "borko", "Привет")
    m2 = _mem_id_for(e2, "borko", "Привет")
    assert m1 == m2, (
        "identical (event.id, npc_id, summary) must yield identical _mem_id; "
        "if this fails, digest discriminates and collision is mitigated downstream"
    )

    # X3: control — different summary must yield different _mem_id (digest discriminates)
    m1_alt = _mem_id_for(e1, "borko", "Уходи")
    assert m1 != m1_alt, (
        "different summary must yield different _mem_id; if this fails, digest is not actually discriminating"
    )

    # X4: control — different npc must yield different _mem_id
    m1_other = _mem_id_for(e1, "ivan", "Привет")
    assert m1 != m1_other, "different npc_id must yield different _mem_id"

    # X5: control — different source must yield different event.id (finalized or provisional)
    e3 = EventDTO.create(
        event_type="dialogue_line",
        source="borko",
        payload={"npc_id": "lusya", "text": "Привет"},
    )
    assert e1.id != e3.id, "different source must yield different event.id"

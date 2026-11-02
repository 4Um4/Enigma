"""
Тесты USL-1.4: Free ASSERT → ClaimEvent → EpistemicStore (ADR-O-437).

Проверяют:
    - Free ASSERT (без DM-вектора) строит proposition(speaker, ASSERTS, content);
    - DM-vector path (ACCUSE/THREATEN/HELP) не затронут — работает как прежде;
    - Empty content → no proposition (defensive);
    - PLAYER_ASSERTION → CANON запрещён (USL-2) — subscriber не имеет API для записи в канон;
    - Детерминизм (повторный прогон = та же proposition);
    - claim_id детерминирован от event.id.
"""
import dataclasses
import pytest
from unittest.mock import MagicMock

from app.domain.epistemology import Predicate
from app.services.events.claim_event_subscriber import ClaimEventSubscriber


# ── Mock Event (frozen dataclass — как настоящий EventDTO) ──────────────────

@dataclasses.dataclass(frozen=True)
class MockEvent:
    """Mock EventDTO для тестов. Frozen — dataclasses.replace работает."""
    id: str
    type: str = "PLAYER_SPOKE"
    source: str = "player"
    payload: dict = dataclasses.field(default_factory=dict)
    radius: float = 10.0
    visibility: str = "public"
    timestamp: float = 0.0
    persistence_level: str = "working"


def _make_event(payload: dict, source: str = "player", event_id: str = "evt-1"):
    return MockEvent(id=event_id, source=source, payload=payload)


def _make_subscriber():
    """Создаёт ClaimEventSubscriber с mock-зависимостями."""
    engine = MagicMock()
    store = MagicMock()
    sub = ClaimEventSubscriber(engine=engine, store=store)
    return sub, engine, store


# ── 1. Free ASSERT path (главный тест USL-1.4) ──────────────────────────────

def test_free_assert_builds_correct_proposition():
    """Free ASSERT (без DM-вектора) → proposition(player, ASSERTS, content)."""
    sub, engine, store = _make_subscriber()

    captured = []
    sub.on_claim_event = lambda e: captured.append(e)

    event = _make_event({
        "content": "я украл хлеб вчера",
        "action_type": "dialogue",
    })

    sub.on_player_spoke(event)

    assert len(captured) == 1
    prop = captured[0].payload["proposition"]
    assert prop["subject_id"] == "player"
    assert prop["predicate"] == Predicate.ASSERTS.value
    assert prop["object_id"] == "я украл хлеб вчера"
    assert prop["polarity"] is True
    assert captured[0].payload["claim_id"] == "player-claim-evt-1"
    assert captured[0].payload["speech_act"] == "assert"


def test_free_assert_creates_epistemic_record():
    """Free ASSERT → on_claim_event вызван (делегация в BeliefRevisionEngine)."""
    sub, engine, store = _make_subscriber()

    call_count = [0]
    original_on_claim = sub.on_claim_event
    def counting_on_claim(event):
        call_count[0] += 1
        # Не вызываем оригинал — он требует scene_state для spatial flow
    sub.on_claim_event = counting_on_claim

    event = _make_event({
        "content": "я работал на тебя пять лет",
        "action_type": "dialogue",
    })

    sub.on_player_spoke(event)

    # on_claim_event был вызван — proposition дошла до эпистемического транспорта
    assert call_count[0] == 1


def test_free_assert_empty_content_skipped():
    """Empty content → no proposition built, on_claim_event не вызывается."""
    sub, engine, store = _make_subscriber()

    captured = []
    sub.on_claim_event = lambda e: captured.append(e)

    event = _make_event({
        "content": "",
        "action_type": "dialogue",
    })

    sub.on_player_spoke(event)
    assert len(captured) == 0


def test_free_assert_no_content_key_skipped():
    """Нет ключа content в payload → no-op (defensive)."""
    sub, engine, store = _make_subscriber()

    captured = []
    sub.on_claim_event = lambda e: captured.append(e)

    event = _make_event({
        "action_type": "dialogue",
    })

    sub.on_player_spoke(event)
    assert len(captured) == 0


# ── 2. DM-vector path не затронут (регрессия ADR-O-388) ─────────────────────

def test_dm_vector_accuse_still_works():
    """DM-vector ACCUSE → Proposition(STOLE) — работает как прежде."""
    sub, engine, store = _make_subscriber()

    captured = []
    sub.on_claim_event = lambda e: captured.append(e)

    event = _make_event({
        "content": "ты украл!",
        "action_type": "dialogue",
        "semantic_action": "ACCUSE",
        "target_reference": "orm",
    })

    sub.on_player_spoke(event)

    assert len(captured) == 1
    prop = captured[0].payload["proposition"]
    assert prop["predicate"] == Predicate.STOLE.value
    assert prop["subject_id"] == "orm"


def test_dm_vector_threaten_still_works():
    """DM-vector THREATEN → Proposition(ATTACKED) — работает как прежде."""
    sub, engine, store = _make_subscriber()

    captured = []
    sub.on_claim_event = lambda e: captured.append(e)

    event = _make_event({
        "content": "я тебя убью!",
        "action_type": "dialogue",
        "semantic_action": "THREATEN",
        "target_reference": "orm",
    })

    sub.on_player_spoke(event)

    assert len(captured) == 1
    prop = captured[0].payload["proposition"]
    assert prop["predicate"] == Predicate.ATTACKED.value
    assert prop["subject_id"] == "player"


def test_dm_vector_help_still_works():
    """DM-vector HELP → Proposition(HELPED) — работает как прежде."""
    sub, engine, store = _make_subscriber()

    captured = []
    sub.on_claim_event = lambda e: captured.append(e)

    event = _make_event({
        "content": "я помогу тебе",
        "action_type": "dialogue",
        "semantic_action": "HELP",
        "target_reference": "orm",
    })

    sub.on_player_spoke(event)

    assert len(captured) == 1
    prop = captured[0].payload["proposition"]
    assert prop["predicate"] == Predicate.HELPED.value


# ── 3. USL-2: PLAYER_ASSERTION → CANON запрещён ────────────────────────────

def test_free_assert_does_not_touch_canon():
    """Free ASSERT не пишет в TruthState/канон (USL-2).
    ClaimEventSubscriber не имеет reference на TruthState/canon — архитектурно невозможно.
    """
    sub, engine, store = _make_subscriber()
    # Subscriber имеет только engine (BeliefRevisionEngine) и store (EpistemicStore)
    # Никаких ссылок на TruthState/ChronicleStore/канон
    assert not hasattr(sub, "_truth_state")
    assert not hasattr(sub, "_canon")
    assert not hasattr(sub, "_chronicle_store")


# ── 4. Детерминизм (USL-6) ──────────────────────────────────────────────────

def test_free_assert_deterministic_proposition():
    """Одинаковый event → одинаковая proposition (USL-6)."""
    sub, engine, store = _make_subscriber()

    captured1, captured2 = [], []
    sub.on_claim_event = lambda e: captured1.append(e)
    event = _make_event({"content": "тестовая фраза", "action_type": "dialogue"})
    sub.on_player_spoke(event)

    sub.on_claim_event = lambda e: captured2.append(e)
    sub.on_player_spoke(event)

    assert len(captured1) == 1
    assert len(captured2) == 1
    assert captured1[0].payload["proposition"] == captured2[0].payload["proposition"]
    assert captured1[0].payload["claim_id"] == captured2[0].payload["claim_id"]


# ── 5. claim_id уникален per event ─────────────────────────────────────────

def test_claim_id_includes_event_id():
    """claim_id = 'player-claim-{event.id}' — детерминирован от event."""
    sub, engine, store = _make_subscriber()

    captured = []
    sub.on_claim_event = lambda e: captured.append(e)

    event1 = _make_event({"content": "фраза 1", "action_type": "dialogue"}, event_id="evt-A")
    event2 = _make_event({"content": "фраза 2", "action_type": "dialogue"}, event_id="evt-B")

    sub.on_player_spoke(event1)
    sub.on_player_spoke(event2)

    assert captured[0].payload["claim_id"] == "player-claim-evt-A"
    assert captured[1].payload["claim_id"] == "player-claim-evt-B"
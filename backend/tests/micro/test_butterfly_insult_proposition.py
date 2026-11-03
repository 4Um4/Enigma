# backend/tests/micro/test_butterfly_insult_proposition.py
"""
path: /project/backend/tests/micro/test_butterfly_insult_proposition.py
Назначение: COGNITIVE-CONTINUITY-01 Этап 2 — PLAYER_INSULTS → Proposition(INSULTED).
Тестирует: ветку оскорбления в on_player_spoke, мембрану слуха, сериализацию,
same-source boost, guard на отсутствие target_id.
Зависимости: app.domain.epistemology, app.services.events.claim_event_subscriber
Основные сущности: MockEvent, MockReliabilityProvider
"""

from dataclasses import dataclass
from typing import Any

from app.domain.epistemology import Predicate
from app.services.events.claim_event_subscriber import ClaimEventSubscriber
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore


@dataclass(frozen=True)
class MockEvent:
    """Минимальный mock EventDTO для тестов (frozen — dataclasses.replace работает)."""
    id: str
    type: str
    source: str
    payload: dict
    radius: float = 10.0


class MockReliabilityProvider:
    """Фиксированная reliability=0.5 для детерминированных тестов."""
    def get_reliability(self, observer: str, source: str, context: Any = None) -> float:
        return 0.5


def _make_subscriber() -> tuple[ClaimEventSubscriber, EpistemicStore]:
    store = EpistemicStore()
    engine = BeliefRevisionEngine(MockReliabilityProvider())
    return ClaimEventSubscriber(engine, store), store


def test_player_insults_creates_insulted_belief():
    """CC-01 базовый: PLAYER_INSULTS → EpistemicRecord с Predicate.INSULTED."""
    sub, store = _make_subscriber()
    event = MockEvent(
        id="test-insult-1",
        type="player_insults",
        source="player",
        payload={"target_id": "tavern_keeper_tornin", "content": "свинья", "event_tick": 1},
        radius=10.0,
    )
    sub.on_player_spoke(event)

    # Без spatial_query мембрана fallback на target_id как listener
    record = store.get("tavern_keeper_tornin")
    assert record is not None, "BELIEF не создана"
    assert record.proposition.predicate == Predicate.INSULTED
    assert record.proposition.subject_id == "player"
    assert record.proposition.object_id == "tavern_keeper_tornin"
    assert record.source_type == "testimony"
    assert record.original_source_id == "player"


def test_player_insults_no_target_no_belief():
    """Guard: оскорбление без target_id → нет записи."""
    sub, store = _make_subscriber()
    event = MockEvent(
        id="test-insult-no-target",
        type="player_insults",
        source="player",
        payload={"content": "свинья", "event_tick": 1},
        radius=10.0,
    )
    sub.on_player_spoke(event)
    # Ни одна запись не должна быть создана
    all_records = store.to_dict()
    assert len(all_records) == 0, f"Запись создана без target_id: {all_records}"


def test_insulted_belief_round_trip():
    """Сериализация: to_dict → from_dict сохраняет INSULTED + provenance."""
    sub, store = _make_subscriber()
    event = MockEvent(
        id="test-insult-rt",
        type="player_insults",
        source="player",
        payload={"target_id": "maid_lusya", "content": "жлоб", "event_tick": 5},
        radius=10.0,
    )
    sub.on_player_spoke(event)

    data = store.to_dict()
    store2 = EpistemicStore.from_dict(data)
    record = store2.get("maid_lusya")
    assert record is not None
    assert record.proposition.predicate == Predicate.INSULTED
    assert record.source_type == "testimony"
    assert record.original_source_id == "player"


def test_repeated_insult_same_source_boost():
    """Повторное оскорбление → та же запись, confidence растёт (same-source boost)."""
    sub, store = _make_subscriber()
    for i in range(2):
        event = MockEvent(
            id=f"test-insult-rep-{i}",
            type="player_insults",
            source="player",
            payload={"target_id": "guard_borko", "content": "жлоб", "event_tick": i},
            radius=10.0,
        )
        sub.on_player_spoke(event)

    record = store.get("guard_borko")
    assert record is not None
    assert record.proposition.predicate == Predicate.INSULTED
    # Первая: 0.5*1.0=0.5. Вторая (same source): 0.5 + 0.5*0.2 = 0.6
    assert record.confidence > 0.5, f"Confidence не вырос: {record.confidence}"
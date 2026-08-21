"""
Файл: backend/tests/sandbox/micro/test_observer_causality.py
Назначение: Тест S202 — Observer Causality. Проверка, что наблюдатели в радиусе получают убеждения об атаке.
Зависимости: app.services.events.event_bus, app.domain.events, app.services.events.claim_event_subscriber
Основные сущности: test_observer_in_radius_gets_belief, test_observer_out_of_radius_no_belief

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_observer_causality.py; cd ..
"""

import pytest
from typing import Optional
from app.services.events.event_bus import EventBus
from app.domain.events import EventDTO
from app.services.events.claim_event_subscriber import ClaimEventSubscriber
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.events.event_types import EventType

class MockSpatialQuery:
    def __init__(self, positions, distances):
        self._npc_positions = positions
        self._distances = distances

    def distance(self, a, b):
        return self._distances.get((a, b), 99.0)

class MockReliabilityProvider:
    """Мок-провайдер надёжности источника для BeliefRevisionEngine."""
    def get_reliability(self, observer: str, source: str, context: Optional[dict] = None) -> float:
        return 0.5  # Нейтральная надёжность

@pytest.fixture
def setup():
    bus = EventBus()
    store = EpistemicStore()
    reliability_provider = MockReliabilityProvider()
    engine = BeliefRevisionEngine(reliability_provider)
    
    # NPC: player, lusya (target), borko (observer)
    positions = {"player": {}, "maid_lusya": {}, "guard_borko": {}}
    
    # Scenario 1: Borko is near Lusya (distance 5.0)
    distances_near = {("maid_lusya", "guard_borko"): 5.0, ("player", "guard_borko"): 15.0}
    sq_near = MockSpatialQuery(positions, distances_near)
    
    # Scenario 2: Borko is far from Lusya (distance 15.0)
    distances_far = {("maid_lusya", "guard_borko"): 15.0, ("player", "guard_borko"): 25.0}
    sq_far = MockSpatialQuery(positions, distances_far)
    
    return bus, store, engine, sq_near, sq_far

def test_observer_in_radius_gets_belief(setup):
    bus, store, engine, sq_near, _ = setup
    sub = ClaimEventSubscriber(engine, store, lambda: sq_near)
    bus.subscribe(EventType.COMMUNICATION_CLAIM, sub.on_claim_event)
    
    # Player attacks Lusya
    payload = {
        "target_id": "maid_lusya",
        "proposition": {"subject_id": "player", "predicate": "attacked", "object_id": "maid_lusya", "polarity": True},
        "speech_act": "assert",
        "tick": 1
    }
    event = EventDTO.create(event_type="communication_claim", source="player", payload=payload)
    bus.publish(event)
    
    # Borko should have the belief
    beliefs = store.get_all_for_agent("guard_borko")
    assert len(beliefs) > 0
    assert any(b.proposition.predicate.value == "attacked" for b in beliefs)

def test_observer_out_of_radius_no_belief(setup):
    bus, store, engine, _, sq_far = setup
    sub = ClaimEventSubscriber(engine, store, lambda: sq_far)
    bus.subscribe(EventType.COMMUNICATION_CLAIM, sub.on_claim_event)
    
    # Player attacks Lusya
    payload = {
        "target_id": "maid_lusya",
        "proposition": {"subject_id": "player", "predicate": "attacked", "object_id": "maid_lusya", "polarity": True},
        "speech_act": "assert",
        "tick": 1
    }
    event = EventDTO.create(event_type="communication_claim", source="player", payload=payload)
    bus.publish(event)
    
    # Borko should NOT have the belief
    beliefs = store.get_all_for_agent("guard_borko")
    assert len(beliefs) == 0
"""
A21.1: Rumor Chain Decay Test.
Критерий: 10 пересказов одного слуха не должны превращаться в 10 независимых подтверждений.
Уверенность должна затухать по цепочке, так как каждый рассказчик передаёт свою уверенность.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, ClaimEvent, SpeechAct
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.trust_based_reliability_provider import TrustBasedReliabilityProvider


class MockRelationshipStore:
    def __init__(self, trust_map: dict):
        self._trust = trust_map

    def get_pair(self, campaign_id: str, observer: str, source: str):
        trust = self._trust.get((observer, source), 50.0)
        rel = MagicMock()
        rel.trust = trust
        return rel


def test_rumor_chain_decay_10_hops():
    """
    Цепочка: A -> C1 -> C2 -> ... -> C10.
    Все доверяют друг другу умеренно (trust=50 -> reliability ~0.6).
   初始 уверенность A = 1.0 (он сам видел).
    Каждый следующий NPC должен получать всё меньшую уверенность,
    так как speaker_confidence падает по цепочке.
    """
    trust_map = {}
    npcs = ["A"] + [f"C{i}" for i in range(1, 11)]
    for i in range(len(npcs) - 1):
        trust_map[(npcs[i+1], npcs[i])] = 50.0  # умеренное доверие

    store = MockRelationshipStore(trust_map)
    provider = TrustBasedReliabilityProvider(relationship_store=store, campaign_id="test")
    engine = BeliefRevisionEngine(reliability_provider=provider)

    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")

    # A сам видел (direct_observation)
    claim_a = ClaimEvent(
        event_id="e0", claim_id="claim_1", speaker_id="A", listener_id="C1",
        proposition=prop, speech_act=SpeechAct.ASSERT, tick=1
    )
    record = engine.revise(
        listener_id="C1", claim=claim_a, existing_record=None,
        reliability_context={"source_type": "direct_observation", "original_source_id": "A"}
    )

    confidences = [record.confidence]

    # Цепочка пересказов
    for i in range(1, 10):
        speaker = npcs[i]
        listener = npcs[i+1]
        claim = ClaimEvent(
            event_id=f"e{i}", claim_id="claim_1", speaker_id=speaker, listener_id=listener,
            proposition=prop, speech_act=SpeechAct.ASSERT, tick=i+1
        )
        record = engine.revise(
            listener_id=listener, claim=claim, existing_record=None,
            reliability_context={
                "source_type": "testimony",
                "original_source_id": "A",
                "speaker_confidence": record.confidence
            }
        )
        confidences.append(record.confidence)

    # Проверяем затухание
    print(f"Confidences along chain: {[round(c, 3) for c in confidences]}")

    # Уверенность должна монотонно убывать (или хотя бы не расти до 1.0)
    assert confidences[-1] < confidences[0], f"Цепочка должна затухать: начало={confidences[0]}, конец={confidences[-1]}"
    assert confidences[-1] < 0.5, f"После 10 пересказов уверенность должна быть низкой, получено: {confidences[-1]}"

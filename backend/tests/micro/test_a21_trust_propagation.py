"""
A21.1: Trust Propagation Chain Test.
Доказывает разрыв: уверенность D должна зависеть от уверенности C и доверия D к первоисточнику A,
а не только от доверия D к рассказчику C.
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
        # trust_map: {(observer, source): trust_value}
        self._trust = trust_map

    def get_pair(self, campaign_id: str, observer: str, source: str):
        trust = self._trust.get((observer, source), 0.0)
        rel = MagicMock()
        rel.trust = trust
        return rel


def test_trust_propagation_chain_dampening():
    """
    Сценарий: A (вор) рассказывает C (служанке) о краже. C рассказывает D (стражу).
    D очень доверяет C (0.9), но не доверяет A (0.1).
    C сам почти не верит A (низкая уверенность).
    ОЖИДАНИЕ: Уверенность D должна быть низкой, так как слух прошёл через ненадёжного A и сомневающегося C.
    ТЕКУЩЕЕ ПОВЕДЕНИЕ (РАЗРЫВ): Уверенность D будет высокой, так как учитывается только trust(D, C).
    """
    # Настройка доверия
    trust_map = {
        ("C", "A"): 20.0,   # C немного доверяет A (нормализовано ~0.5)
        ("D", "C"): 90.0,   # D очень доверяет C (нормализовано ~0.95)
        ("D", "A"): -50.0,  # D не доверяет A (враг, инверсия)
    }
    store = MockRelationshipStore(trust_map)
    provider = TrustBasedReliabilityProvider(relationship_store=store, campaign_id="test")
    engine = BeliefRevisionEngine(reliability_provider=provider)

    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")

    # Шаг 1: A рассказывает C
    claim_a_to_c = ClaimEvent(
        event_id="e1", claim_id="claim_1", speaker_id="A", listener_id="C",
        proposition=prop, speech_act=SpeechAct.ASSERT, tick=1
    )
    record_c = engine.revise(
        listener_id="C", claim=claim_a_to_c, existing_record=None,
        reliability_context={"source_type": "testimony", "original_source_id": "A"}
    )
    
    # C должен иметь умеренную/низкую уверенность, так как trust(C, A) невелик
    assert record_c.confidence < 0.6, f"C должен сомневаться в слухе от A, получено: {record_c.confidence}"

    # Шаг 2: C рассказывает D
    claim_c_to_d = ClaimEvent(
        event_id="e2", claim_id="claim_1", speaker_id="C", listener_id="D",
        proposition=prop, speech_act=SpeechAct.ASSERT, tick=2
    )
    
    # В реальном ClaimEventSubscriber сюда передаётся original_source_id="A"
    # и должна передаваться уверенность C (record_c.confidence)
    record_d = engine.revise(
        listener_id="D", claim=claim_c_to_d, existing_record=None,
        reliability_context={
            "source_type": "testimony", 
            "original_source_id": "A",
            "speaker_confidence": record_c.confidence  # <-- Этого сейчас нет в production, но мы ожидаем
        }
    )

    # КРИТИЧЕСКОЕ ОЖИДАНИЕ A21:
    # D не должен слепо верить C, если сам C сомневается, а первоисточник A — враг D.
    # Уверенность D должна быть существенно ниже, чем просто trust(D, C).
    # Ожидаем, что она будет dampened (подавлена) уверенностью C и отношением к A.
    assert record_d.confidence < 0.5, (
        f"РАЗРЫВ A21: D получил высокую уверенность {record_d.confidence}, "
        f"несмотря на то, что C сомневался ({record_c.confidence}), а A — враг D. "
        f"Система должна учитывать уверенность рассказчика и доверие к первоисточнику."
    )
"""
A19.5 Step 1: Idempotency Tests.
Доказывает, что повторная доставка одного и того же claim_id не создаёт ложного роста confidence
и не обновляет last_updated_tick.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, ClaimEvent, SpeechAct
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine


def _make_engine_with_reliability(value: float = 0.5) -> BeliefRevisionEngine:
    """Создаёт BeliefRevisionEngine с моком reliability_provider."""
    mock_provider = MagicMock()
    mock_provider.get_reliability = MagicMock(return_value=value)
    return BeliefRevisionEngine(reliability_provider=mock_provider)


def test_first_claim_creates_belief():
    """Первый claim создаёт убеждение с корректным seen_claim_ids."""
    store = EpistemicStore()
    engine = _make_engine_with_reliability(0.5)
    
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    claim1 = ClaimEvent("evt1", "claim_1", "B", "C", prop, SpeechAct.ASSERT, 1)
    
    rec1 = engine.revise("C", claim1, None)
    store.upsert(rec1)
    
    result = store.get("C", prop)
    assert result is not None, "Убеждение должно быть создано"
    assert result.confidence > 0.0, "Confidence должна быть положительной"
    assert "claim_1" in result.seen_claim_ids, "claim_1 должен быть в seen_claim_ids"
    assert result.last_updated_tick == 1


def test_repeat_claim_no_changes():
    """Повторная доставка claim_1 не меняет ни confidence, ни last_updated_tick."""
    store = EpistemicStore()
    engine = _make_engine_with_reliability(0.5)
    
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    
    # Первая доставка
    claim1 = ClaimEvent("evt1", "claim_1", "B", "C", prop, SpeechAct.ASSERT, 1)
    rec1 = engine.revise("C", claim1, None)
    store.upsert(rec1)
    conf1 = store.get("C", prop).confidence
    tick1 = store.get("C", prop).last_updated_tick
    
    # Повторная доставка (на другом тике)
    claim1_repeat = ClaimEvent("evt2", "claim_1", "B", "C", prop, SpeechAct.ASSERT, 5)
    rec2 = engine.revise("C", claim1_repeat, store.get("C", prop))
    store.upsert(rec2)
    
    result = store.get("C", prop)
    assert result.confidence == conf1, f"Confidence не должна измениться: {result.confidence} != {conf1}"
    assert result.last_updated_tick == tick1, f"last_updated_tick не должен обновиться: {result.last_updated_tick} != {tick1}"


def test_sequence_claim1_claim2_claim1():
    """Последовательность claim_1 → claim_2 → claim_1: только claim_2 повышает confidence."""
    store = EpistemicStore()
    engine = _make_engine_with_reliability(0.5)
    
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    
    # claim_1
    claim1 = ClaimEvent("evt1", "claim_1", "B", "C", prop, SpeechAct.ASSERT, 1)
    rec1 = engine.revise("C", claim1, None)
    store.upsert(rec1)
    conf1 = store.get("C", prop).confidence
    
    # claim_2 (другой источник)
    claim2 = ClaimEvent("evt2", "claim_2", "D", "C", prop, SpeechAct.ASSERT, 2)
    rec2 = engine.revise("C", claim2, store.get("C", prop))
    store.upsert(rec2)
    conf2 = store.get("C", prop).confidence
    assert conf2 >= conf1, "Новый claim должен повышать или сохранять уверенность (насыщение)"
    
    # Повтор claim_1
    claim1_repeat = ClaimEvent("evt3", "claim_1", "B", "C", prop, SpeechAct.ASSERT, 3)
    rec3 = engine.revise("C", claim1_repeat, store.get("C", prop))
    store.upsert(rec3)
    
    result = store.get("C", prop)
    assert result.confidence == conf2, f"Повтор claim_1 не должен повышать уверенность: {result.confidence} != {conf2}"
    assert "claim_1" in result.seen_claim_ids
    assert "claim_2" in result.seen_claim_ids


def test_persistence_roundtrip():
    """Идемпотентность переживает сериализацию/десериализацию."""
    store = EpistemicStore()
    engine = _make_engine_with_reliability(0.5)
    
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    
    # Создаём убеждение с seen_claim_ids
    claim1 = ClaimEvent("evt1", "claim_1", "B", "C", prop, SpeechAct.ASSERT, 1)
    rec1 = engine.revise("C", claim1, None)
    store.upsert(rec1)
    conf_before = store.get("C", prop).confidence
    
    # Сериализуем и десериализуем (эмуляция перезапуска)
    serialized = store.to_dict()
    restored_store = EpistemicStore.from_dict(serialized)
    
    # Проверяем, что seen_claim_ids сохранился
    restored_rec = restored_store.get("C", prop)
    assert restored_rec is not None
    assert "claim_1" in restored_rec.seen_claim_ids, "seen_claim_ids должен сохраниться после перезапуска"
    
    # Повторная доставка claim_1 после перезапуска не должна изменить ничего
    claim1_repeat = ClaimEvent("evt2", "claim_1", "B", "C", prop, SpeechAct.ASSERT, 2)
    rec2 = engine.revise("C", claim1_repeat, restored_rec)
    restored_store.upsert(rec2)
    
    final_conf = restored_store.get("C", prop).confidence
    assert final_conf == conf_before, "Идемпотентность должна переживать перезапуск"


def test_backward_compatibility_old_save():
    """Старые сохранения без seen_claim_ids загружаются с защитой последнего claim."""
    old_data = [
        {
            "agent_id": "C",
            "proposition": {
                "subject_id": "X",
                "predicate": "stole",
                "object_id": "Y",
                "polarity": True
            },
            "confidence": 0.5,
            "source_id": "B",
            "source_claim_id": "old_claim",
            "first_observed_tick": 1,
            "last_updated_tick": 1,
            "source_type": "testimony",
            "original_source_id": "A"
            # Заметим: НЕТ поля "seen_claim_ids"
        }
    ]
    
    store = EpistemicStore.from_dict(old_data)
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    rec = store.get("C", prop)
    assert rec is not None
    assert rec.seen_claim_ids == ("old_claim",), "Старые сохранения должны восстанавливать source_claim_id в seen_claim_ids"


def test_backward_compatibility_empty_source_claim():
    """Старые сохранения без source_claim_id загружаются с пустым seen_claim_ids."""
    old_data = [
        {
            "agent_id": "C",
            "proposition": {
                "subject_id": "X",
                "predicate": "stole",
                "object_id": "Y",
                "polarity": True
            },
            "confidence": 0.5,
            "source_id": "B",
            "source_claim_id": "",
            "first_observed_tick": 1,
            "last_updated_tick": 1
        }
    ]
    
    store = EpistemicStore.from_dict(old_data)
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    rec = store.get("C", prop)
    assert rec is not None
    assert rec.seen_claim_ids == (), "Пустой source_claim_id не должен добавляться в seen_claim_ids"
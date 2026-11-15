"""
A19.5 Step 2: EpistemicContext Enrichment Tests.
Доказывает, что DecisionHub получает содержательные убеждения через recent_beliefs.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, EpistemicRecord, BeliefSummary, EpistemicContext
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver


def test_belief_summary_structure():
    """BeliefSummary содержит все необходимые поля."""
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    belief = BeliefSummary(
        proposition=prop,
        confidence=0.8,
        source_id="B",
        subject_id="X",
        object_id="Y"
    )
    assert belief.subject_id == "X"
    assert belief.object_id == "Y"
    assert belief.confidence == 0.8
    assert belief.source_id == "B"


def test_epistemic_context_has_recent_beliefs():
    """EpistemicContext содержит поле recent_beliefs."""
    ctx = EpistemicContext(agent_id="C")
    assert hasattr(ctx, 'recent_beliefs')
    assert ctx.recent_beliefs == ()


def test_resolver_populates_recent_beliefs():
    """EpistemicContextResolver заполняет recent_beliefs топ-3 убеждениями."""
    store = EpistemicStore()
    
    # Создаём 5 убеждений с разным confidence
    props = [
        Proposition(subject_id="X1", predicate=Predicate.STOLE, object_id="Y1"),
        Proposition(subject_id="X2", predicate=Predicate.ATTACKED, object_id="Y2"),
        Proposition(subject_id="X3", predicate=Predicate.HELPED, object_id="Y3"),
        Proposition(subject_id="X4", predicate=Predicate.INSULTED, object_id="Y4"),
        Proposition(subject_id="X5", predicate=Predicate.STOLE, object_id="Y5"),
    ]
    
    for i, prop in enumerate(props):
        rec = EpistemicRecord(
            agent_id="C",
            proposition=prop,
            confidence=0.2 * (i + 1),  # 0.2, 0.4, 0.6, 0.8, 1.0
            source_id=f"source_{i}",
            source_claim_id=f"claim_{i}",
            first_observed_tick=i,
            last_updated_tick=i,
            source_type="testimony",
            original_source_id=f"orig_{i}"
        )
        store.upsert(rec)
    
    resolver = EpistemicContextResolver(store=store)
    ctx = resolver.resolve("C")
    
    # Проверяем, что recent_beliefs содержит топ-3 по confidence
    assert len(ctx.recent_beliefs) == 3, f"Ожидалось 3 убеждения, получено {len(ctx.recent_beliefs)}"
    
    # Проверяем, что они отсортированы по confidence (desc)
    confidences = [b.confidence for b in ctx.recent_beliefs]
    assert confidences == sorted(confidences, reverse=True), "recent_beliefs должны быть отсортированы по confidence (desc)"
    
    # Проверяем, что топ-3 — это записи с confidence 1.0, 0.8, 0.6
    assert round(confidences[0], 2) == 1.0
    assert round(confidences[1], 2) == 0.8
    assert round(confidences[2], 2) == 0.6
    
    # Проверяем, что subject_id и object_id корректны
    assert ctx.recent_beliefs[0].subject_id == "X5"
    assert ctx.recent_beliefs[0].object_id == "Y5"


def test_resolver_empty_store():
    """EpistemicContextResolver корректно обрабатывает пустой store."""
    store = EpistemicStore()
    resolver = EpistemicContextResolver(store=store)
    ctx = resolver.resolve("C")
    
    assert len(ctx.recent_beliefs) == 0


def test_resolver_single_belief():
    """EpistemicContextResolver корректно обрабатывает одно убеждение."""
    store = EpistemicStore()
    prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
    rec = EpistemicRecord(
        agent_id="C",
        proposition=prop,
        confidence=0.7,
        source_id="B",
        source_claim_id="claim_1",
        first_observed_tick=1,
        last_updated_tick=1
    )
    store.upsert(rec)
    
    resolver = EpistemicContextResolver(store=store)
    ctx = resolver.resolve("C")
    
    assert len(ctx.recent_beliefs) == 1
    assert ctx.recent_beliefs[0].confidence == 0.7
    assert ctx.recent_beliefs[0].subject_id == "X"
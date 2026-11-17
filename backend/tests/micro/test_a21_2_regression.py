"""
A21.2 Regression Tests:证明 разрывы перед исправлением.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, EpistemicRecord
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.decision_hub import DecisionHub
from app.models.npc_state import NPCState


def test_rumor_proposition_for_theft():
    """C знает о краже A против B. Должен получить report_proposition и буст к spread_rumor."""
    store = EpistemicStore()
    prop = Proposition(subject_id="A", predicate=Predicate.STOLE, object_id="B")
    rec = EpistemicRecord(
        agent_id="C", proposition=prop, confidence=0.8, source_id="witness",
        source_claim_id="c1", first_observed_tick=1, last_updated_tick=1,
        source_type="testimony", original_source_id="witness"
    )
    store.upsert(rec)
    
    resolver = EpistemicContextResolver(store=store)
    ctx = resolver.resolve("C")
    
    # ОЖИДАНИЕ: report_proposition должен содержать кражу
    assert ctx.report_proposition is not None, "Разрыв: C не получил proposition для слуха о краже"
    assert ctx.report_proposition.predicate == Predicate.STOLE
    
    mods = resolver.to_modifiers(ctx, archetype="maid")
    assert mods.get("spread_rumor", 0.0) > 0.0, "Разрыв: C не получил мотивацию пересказать кражу"


def test_spread_rumor_target_ranking():
    """У C есть два доверенных слушателя в радиусе. Должен выбрать одного, а не None."""
    hub = DecisionHub(seed=42)
    state = MagicMock(spec=NPCState)
    state.npc_id = "C"
    state.relationship_cache = {}
    
    # Мокаем spatial_query: оба в радиусе
    spatial = MagicMock()
    spatial.distance.return_value = 1.0
    
    # Мокаем _get_rel_value: D1 trust=0.9, D2 trust=0.5
    def mock_rel(st, cid, key):
        if key == "trust":
            return {"D1": 0.9, "D2": 0.5}.get(cid, 0.0)
        return 0.0
    hub._get_rel_value = mock_rel
    
    target = hub._resolve_target(
        intent="spread_rumor",
        event=MagicMock(),
        state=state,
        spatial_query=spatial,
        all_npc_ids=["C", "D1", "D2"],
        epistemic_context=None
    )
    
    # ОЖИДАНИЕ: должен выбрать D1 (больше trust), а не None
    assert target is not None, "Разрыв: при 2 кандидатах target=None"
    assert target == "D1", f"Должен выбрать D1 с большим trust, получено: {target}"
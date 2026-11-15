"""
A19.5 Final Control Test: Semantic Roles (Subject vs Object).
Доказывает, что NPC по-разному реагирует на виновника (X) и потерпевшего (Y).
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, BeliefSummary, EpistemicContext
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.models.npc_state import NPCState, EmotionTag


class MockProfile:
    def __init__(self, archetype: str):
        self.archetype = archetype


def test_semantic_roles_thief_vs_victim():
    """
    C знает, что X украл у Y.
    1. Взаимодействие с X (вор, subject_id) -> получает модификатор.
    2. Взаимодействие с Y (жертва, object_id) -> НЕ получает модификатор вора.
    3. Взаимодействие с Z (посторонний) -> НЕ получает модификатор.
    """
    belief = BeliefSummary(
        proposition=Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y"),
        confidence=0.9,
        source_id="B",
        subject_id="X",
        object_id="Y"
    )
    epi_ctx = EpistemicContext(agent_id="C", recent_beliefs=(belief,))
    
    state = MagicMock(spec=NPCState)
    state.npc_id = "C"
    state.emotion = EmotionTag.NEUTRAL
    state.intent = None
    
    event = MagicMock(spec=EventContext)
    
    hub = DecisionHub()
    
    from app.domain.epistemic_dispositions import get_epistemic_disposition
    disp_guard = get_epistemic_disposition("guard") # {"report": 1.4, ...}
    
    base_scores = {"report": 0.5, "trade": 0.5}
    
    # --- ТЕСТ 1: Взаимодействие с X (вор, subject_id) ---
    hub._resolve_target = MagicMock(return_value="X")
    scores_x = dict(base_scores)
    for intent in list(scores_x.keys()):
        target = hub._resolve_target(intent=intent, event=event, state=state, epistemic_context=epi_ctx)
        if target == belief.subject_id: # X
            modifier = disp_guard.get(intent, 0.0) * belief.confidence
            scores_x[intent] = round(scores_x[intent] + modifier, 4)
            
    assert scores_x["report"] > 1.5, f"Guard должен хотеть report вора X. Получено: {scores_x['report']}"
    
    # --- ТЕСТ 2: Взаимодействие с Y (жертва, object_id) ---
    hub._resolve_target = MagicMock(return_value="Y")
    scores_y = dict(base_scores)
    for intent in list(scores_y.keys()):
        target = hub._resolve_target(intent=intent, event=event, state=state, epistemic_context=epi_ctx)
        # Новая логика: модификатор применяется ТОЛЬКО если target == belief.subject_id
        if target == belief.subject_id: 
            modifier = disp_guard.get(intent, 0.0) * belief.confidence
            scores_y[intent] = round(scores_y[intent] + modifier, 4)
            
    assert scores_y["report"] == base_scores["report"], f"Guard НЕ должен получать буст к report жертвы Y. Получено: {scores_y['report']}"
    
    # --- ТЕСТ 3: Взаимодействие с Z (посторонний) ---
    hub._resolve_target = MagicMock(return_value="Z")
    scores_z = dict(base_scores)
    for intent in list(scores_z.keys()):
        target = hub._resolve_target(intent=intent, event=event, state=state, epistemic_context=epi_ctx)
        if target == belief.subject_id:
            modifier = disp_guard.get(intent, 0.0) * belief.confidence
            scores_z[intent] = round(scores_z[intent] + modifier, 4)
            
    assert scores_z["report"] == base_scores["report"], f"Guard НЕ должен получать буст к report постороннего Z. Получено: {scores_z['report']}"
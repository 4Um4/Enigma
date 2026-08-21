"""S199.2: Семантическая классификация интентов для обхода ADR-O-342.
 
Классифицирует интенты по трём осям:
- requires_dialogue_context: нужен ли контекст диалога (STM)
- requires_llm_materialization: нужна ли LLM для генерации текста
- produces_claim: порождает ли интент EpistemicClaim
"""
from typing import Dict, Any

INTENT_PROFILES: Dict[str, Dict[str, Any]] = {
    "talk": {"requires_dialogue_context": True, "requires_llm": True, "produces_claim": False},
    "warn": {"requires_dialogue_context": False, "requires_llm": False, "produces_claim": True},
    "intimidate": {"requires_dialogue_context": False, "requires_llm": False, "produces_claim": True},
    "threaten": {"requires_dialogue_context": False, "requires_llm": False, "produces_claim": True},
    "report": {"requires_dialogue_context": False, "requires_llm": False, "produces_claim": True},
    "spread_rumor": {"requires_dialogue_context": False, "requires_llm": False, "produces_claim": True},
}

def requires_dialogue_context(intent_type: str) -> bool:
    return INTENT_PROFILES.get(intent_type, {}).get("requires_dialogue_context", True)

def requires_llm_materialization(intent_type: str) -> bool:
    return INTENT_PROFILES.get(intent_type, {}).get("requires_llm", True)
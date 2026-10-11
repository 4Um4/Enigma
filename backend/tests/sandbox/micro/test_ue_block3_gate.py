# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_block3_gate.py
Назначение: S-UE Блок 3 — матрица readiness (чистая функция, 5 значений) +
    fail-closed гейт: ATTACK@PARTIAL деградирует до PLAYER_SPOKE (замок evt_map,
    без шины). UE-RED-1 (снятие xfail) — отдельным прогоном safety_red.
Зависимости: app.services.game_loop.phase_1_input, app.domain.intent_profile
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_block3_gate.py -q; cd ..
"""
from types import SimpleNamespace

from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import compute_intent_readiness


def _field(action: ActionType, raw: str, **kw) -> IntentSemanticField:
    return IntentSemanticField(action=action, raw_text=raw, **kw)


# ── Матрица compute_intent_readiness ──
def test_matrix_attack_plain_resolved():
    # Совместимость боя: «Ударь его» — RESOLVED (регрессии нет)
    assert compute_intent_readiness(_field(ActionType.ATTACK, "Ударь его."), "guard_gate", []) == "RESOLVED"


def test_matrix_attack_unresolved_negation_partial():
    # NEG-04: «Не бей его» — negated=None (нет per-act) + частица → PARTIAL
    assert compute_intent_readiness(_field(ActionType.ATTACK, "Не бей его."), "", []) == "PARTIAL"


def test_matrix_reference_ambiguous():
    assert compute_intent_readiness(_field(ActionType.OBSERVE, "Проследи за стражником."), "", ["a", "b"]) == "REFERENCE_AMBIGUOUS"


def test_matrix_semantic_ambiguous():
    f = _field(ActionType.DIALOGUE, "Сделай так, как мы обсуждали.")
    object.__setattr__(f, "ambiguity", __import__("app.domain.intent_profile", fromlist=["SemanticAmbiguity"]).SemanticAmbiguity.AMBIGUOUS)
    assert compute_intent_readiness(f, "", []) == "SEMANTIC_AMBIGUOUS"


def test_matrix_uncertain_failed():
    f = _field(ActionType.UNCERTAIN, "хм", comprehension_facts={"llm_status": "UNAVAILABLE"})
    assert compute_intent_readiness(f, "", []) == "FAILED"


def test_matrix_negated_known_unblocks():
    # Блок 4-мост: per-act negated=False + 'не' в raw → RESOLVED (LLM разрешила)
    acts = [{"type": "ORDER", "params": {}, "negated": False}]
    assert compute_intent_readiness(_field(ActionType.ATTACK, "Не бей его.", semantic_acts=acts), "guard_gate", []) == "RESOLVED"
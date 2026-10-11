# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_block1_contract.py
Назначение: S-UE Блок 1 — контракт IntentReadiness (5 значений, SEMANTIC_AMBIGUOUS
    ≠ PARTIAL) + comprehension_facts (additive, frozen) + совместимость старых
    конструкторов (замороженные схемы не сломаны).
Зависимости: app.domain.intent_profile
Основные сущности: IntentReadiness, IntentSemanticField
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_block1_contract.py -q; cd ..
"""
import pytest
from app.domain.intent_profile import IntentReadiness, IntentSemanticField, ActionType


def test_readiness_enum_five_values():
    values = {e.value for e in IntentReadiness}
    assert values == {"RESOLVED", "REFERENCE_AMBIGUOUS", "SEMANTIC_AMBIGUOUS", "PARTIAL", "FAILED"}


def test_field_accepts_comprehension_facts_and_frozen():
    f = IntentSemanticField(
        action=ActionType.DIALOGUE, raw_text="x",
        comprehension_facts={"has_acts": False, "llm_status": "OK"},
    )
    assert f.comprehension_facts["llm_status"] == "OK"
    with pytest.raises(Exception):
        f.comprehension_facts = {"has_acts": True}  # frozen-модель: мутация запрещена


def test_field_without_new_members_valid():
    # Совместимость: старый конструктор (все новые поля — дефолт None)
    f = IntentSemanticField(action=ActionType.DIALOGUE, raw_text="привет")
    assert f.comprehension_facts is None
    assert f.semantic_acts == []


def test_per_act_keys_pass_through_field():
    # Ключи per-act контракта проходят в поле (Dict-контракт; валидация — Блок 4)
    acts = [{"type": "ORDER", "params": {}, "negated": True,
             "modality": None, "quoted": False, "quoted_speaker_hint": None}]
    f = IntentSemanticField(action=ActionType.DIALOGUE, raw_text="не говори", semantic_acts=acts)
    assert f.semantic_acts[0]["negated"] is True
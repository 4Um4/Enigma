# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_fix3_order_gate.py
Назначение: S-UE мини-fix №3 (вердикт Мастера) — контракт гейта:
    (1) ORDER + частица-не + negated=None → не-RESOLVED (находка закрыта);
    (2) позитивный ORDER без частицы → RESOLVED (обычные приказы не блокируются);
    (3) ATTACK с неразобранной негацией → запрещено (прежняя защита);
    (4) старые акты без новых полей — совместимость (в т.ч. ORDER без
    частицы = RESOLVED; ORDER+частица+negated=False = RESOLVED-мост);
    (5) world-changing без target → PARTIAL (не задет).
Зависимости: app.services.game_loop.phase_1_input
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_fix3_order_gate.py -q; cd ..
"""
from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import compute_intent_readiness


def _f(action, raw, acts=None):
    return IntentSemanticField(action=action, raw_text=raw, semantic_acts=acts or [])


def test_fix3_order_negation_unresolved_blocks():
    # НАХОДКА №3: диалоговый приказ с частицей, негация не разобрана — не RESOLVED
    f = _f(ActionType.DIALOGUE, "Не говори ему, что я согласен.", [{"type": "ORDER", "params": {}}])
    assert compute_intent_readiness(f, "tavern_keeper", []) != "RESOLVED"


def test_fix3_positive_order_resolved():
    # Позитивный приказ без частицы — не блокируется (пункт 3 контракта)
    f = _f(ActionType.DIALOGUE, "Скажи ему, что я согласен.", [{"type": "ORDER", "params": {}}])
    assert compute_intent_readiness(f, "tavern_keeper", []) == "RESOLVED"


def test_fix3_attack_negation_still_blocks():
    f = _f(ActionType.ATTACK, "Не бей его.")
    assert compute_intent_readiness(f, "guard_gate", []) == "PARTIAL"


def test_fix3_legacy_acts_compat():
    # Старый акт без новых полей: без частицы — RESOLVED (совместимость)
    f = _f(ActionType.DIALOGUE, "Прикажи кузнецу работать.", [{"type": "ORDER", "params": {"topic": "работать"}}])
    assert compute_intent_readiness(f, "blacksmith", []) == "RESOLVED"


def test_fix3_negated_false_bridge_unblocks():
    # Мост: LLM разобрала негацию (negated=False на не-реплике) → RESOLVED
    f = _f(ActionType.DIALOGUE, "Не говори ему, а просто кивни.",
           [{"type": "ORDER", "params": {}, "negated": False}])
    assert compute_intent_readiness(f, "tavern_keeper", []) == "RESOLVED"


def test_fix3_world_changing_no_target_untouched():
    f = _f(ActionType.STEAL, "Возьми кошелёк.")
    assert compute_intent_readiness(f, "", []) == "PARTIAL"
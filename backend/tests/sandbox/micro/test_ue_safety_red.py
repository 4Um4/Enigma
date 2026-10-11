# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_safety_red.py
Назначение: S-UE Блок 1 — фиксаторы двух производственных дефектов (baseline
    NEG-04 / REF-01). xfail(strict=True): красные ДО Блоков 2–3; зелёный
    (XPASS) = сигнал «защита заработала — снять xfail». Критерий приёмки
    Блока 3 Мастера: ОБА зелёные без xfail.
Зависимости: app.domain.intent_profile, app.services.game_loop.phase_1_input
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_safety_red.py -q; cd ..
"""
import pytest

from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import resolve_player_intent

_SCENE = {
    "npc_positions": {
        "guard_gate": {"name": "стражник у ворот", "x": 10.0, "y": 10.0},
        "guard_market": {"name": "стражник на рынке", "x": 40.0, "y": 10.0},
    },
    "location_id": "tavern",
}


@pytest.mark.xfail(strict=True, reason="UE-RED-1 (baseline NEG-04): ATTACK без "
                   "разрешённого отрицания обязан быть не-RESOLVED; readiness "
                   "появляется в Блоке 3 — тогда снять xfail")
def test_red_attack_unresolved_negation_not_resolved():
    # «Не бей его» сегодня: ATTACK, негация потеряна fast-path'ом (0.001s),
    # negated-информации нет вовсе → исполнение обязано быть закрыто.
    sf = IntentSemanticField(action=ActionType.ATTACK, raw_text="Не бей его.")
    res = resolve_player_intent(
        raw_action="Не бей его.", action_type="player_attacks", target="",
        player_dict=None, scene_context=_SCENE, semantic_field=sf,
    )
    assert res.original_intent.parameters.intent_readiness != "RESOLVED"


@pytest.mark.xfail(strict=True, reason="UE-RED-2 (baseline REF-01): два "
                   "стражника — автопик первого без основания запрещён; "
                   "reference_candidates появляются в Блоке 2 — тогда снять xfail")
def test_red_two_guards_no_silent_pick():
    # «Проследи за стражником» при двух стражниках: резолвер обязан вернуть
    # кандидатов, а не молча выбрать guard_market.
    sf = IntentSemanticField(action=ActionType.OBSERVE, raw_text="Проследи за стражником.", target="стражник")
    res = resolve_player_intent(
        raw_action="Проследи за стражником.", action_type="player_interacts",
        target="стражник", player_dict=None, scene_context=_SCENE, semantic_field=sf,
    )
    params = res.original_intent.parameters
    assert getattr(params, "reference_candidates", None) is not None
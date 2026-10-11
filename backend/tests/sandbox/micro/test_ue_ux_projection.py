# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_ux_projection.py
Назначение: UX-UE-01 Этап 1, ① (DP-1, GO Тай) — спецификация расширения
    G1-проекции понимания (build_intent_projection) полями readiness /
    reason / candidates. Контракт: additive, None ≠ «резолвили в пустоту»
    (§ENIGMA-003), candidates ≠ выбранная цель, совместимость потребителей.
    Паттерн safety_red: xfail(strict=True) — спецификация красная ДО
    реализации Этапа 2; XPASS = реализация заработала, снять xfail.
    Существующее поведение — зелёные замки без xfail.
Зависимости: app.services.game_loop.phase_1_input, app.domain.intent_profile
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_ux_projection.py -q; cd ..
"""
import pytest

from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import (
    build_intent_projection,
    resolve_player_intent,
)

# Канон S346 (test_ue_safety_red._SCENE): два стражника — REF-01 обязан
# давать кандидатов, а не угадывание. Фразы — ue0-корпус (NEG-04/REF-01/CON-01).
_SCENE = {
    "npc_positions": {
        "guard_gate": {"name": "стражник у ворот", "x": 10.0, "y": 10.0},
        "guard_market": {"name": "стражник на рынке", "x": 40.0, "y": 10.0},
    },
    "location_id": "tavern",
}


def _resolve(raw: str, sf: IntentSemanticField, action_type: str):
    """Фабрика (§13.4): живой IntentResolution через resolve_player_intent."""
    return resolve_player_intent(
        raw_action=raw, action_type=action_type, target="",
        player_dict=None, scene_context=_SCENE, semantic_field=sf,
    )


@pytest.mark.xfail(strict=True, reason="UX-UE-01 ①: поля проекции не реализованы (Этап 2)")
def test_projection_readiness_partial():
    res = _resolve("Не бей его.", IntentSemanticField(action=ActionType.ATTACK, raw_text="Не бей его."), "player_attacks")
    proj = build_intent_projection(res)
    assert proj is not None
    assert proj.get("readiness") == "PARTIAL"


@pytest.mark.xfail(strict=True, reason="UX-UE-01 ①: поля проекции не реализованы (Этап 2)")
def test_projection_readiness_and_candidates_reference_ambiguous():
    res = _resolve(
        "Проследи за стражником.",
        IntentSemanticField(action=ActionType.OBSERVE, raw_text="Проследи за стражником.", target="стражник"),
        "player_interacts",
    )
    proj = build_intent_projection(res)
    assert proj.get("readiness") == "REFERENCE_AMBIGUOUS"
    # Кандидаты ≠ выбранная цель: перечень, не выбор
    assert sorted(proj.get("candidates") or []) == sorted(["guard_gate", "guard_market"])


@pytest.mark.xfail(strict=True, reason="UX-UE-01 ①: поля проекции не реализованы (Этап 2)")
def test_projection_resolved_readiness_without_candidates():
    res = _resolve("Привет.", IntentSemanticField(action=ActionType.DIALOGUE, raw_text="Привет."), "player_interacts")
    proj = build_intent_projection(res)
    assert proj.get("readiness") == "RESOLVED"
    assert "candidates" not in proj  # None ≠ пустой список: ключа нет


@pytest.mark.xfail(strict=True, reason="UX-UE-01 ①: поля проекции не реализованы (Этап 2)")
def test_projection_failed_reason_llm_status():
    sf = IntentSemanticField(action=ActionType.UNCERTAIN, raw_text="хм",
                             comprehension_facts={"llm_status": "UNAVAILABLE"})
    res = _resolve("хм", sf, "player_interacts")
    proj = build_intent_projection(res)
    assert proj.get("readiness") == "FAILED"
    assert proj.get("reason") == "UNAVAILABLE"  # машинная причина для текста UX


def test_projection_absence_lock():
    # Замок существующего поведения: нет резолва → None (§ENIGMA-003)
    assert build_intent_projection(None) is None


def test_projection_existing_fields_lock():
    # Замок совместимости: существующие поля не деградируют
    res = _resolve("Привет.", IntentSemanticField(action=ActionType.DIALOGUE, raw_text="Привет."), "player_interacts")
    proj = build_intent_projection(res)
    assert "action" in proj and "target" in proj
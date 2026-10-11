# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_block2_resolver.py
Назначение: S-UE Блок 2 — запрет молчаливого автопика цели. Эмпирика
    baseline: автопик совершала LLM (id одного стражника при двух в сцене),
    R14 «валидировал». Защита — текстовая сверка raw_text с именами сцены.
Зависимости: app.services.game_loop.phase_1_input, app.domain.intent_profile
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_block2_resolver.py -q; cd ..
"""
from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import resolve_target_with_candidates

_SCENE_TWO_GUARDS = {
    "npc_positions": {
        "guard_gate": {"name": "стражник у ворот", "x": 10.0, "y": 10.0},
        "guard_market": {"name": "стражник на рынке", "x": 40.0, "y": 10.0},
        "tavern_keeper": {"name": "трактирщик", "x": 5.0, "y": 5.0},
    },
    "location_id": "tavern",
}


def _field(target: str, raw: str) -> IntentSemanticField:
    return IntentSemanticField(action=ActionType.OBSERVE, raw_text=raw, target=target)


def test_two_guards_no_silent_pick():
    # baseline REF-01: LLM вернула guard_market; родовой «стражник» в реплике
    # покрывает ОБОИХ — выбор отброшен, кандидаты перечислены
    tid, cands = resolve_target_with_candidates(
        _field("guard_market", "Проследи за стражником."), _SCENE_TWO_GUARDS
    )
    assert tid == ""
    assert sorted(cands) == ["guard_gate", "guard_market"]


def test_full_name_disambiguates_and_corrects_llm():
    # Полное имя в реплике: единственный full-match побеждает, даже если
    # LLM назвала другого стражника (Python владеет идентификацией)
    tid, cands = resolve_target_with_candidates(
        _field("guard_market", "Проследи за стражником у ворот."), _SCENE_TWO_GUARDS
    )
    assert tid == "guard_gate" and cands == []


def test_unique_generic_term_picks():
    # Родовой термин, покрывающий ровно ОДНОГО NPC — легитимный выбор
    tid, cands = resolve_target_with_candidates(
        _field("tavern_keeper", "Спроси трактирщика про драку."), _SCENE_TWO_GUARDS
    )
    assert tid == "tavern_keeper" and cands == []


def test_anaphora_falls_back_to_legacy():
    # 0 упоминаний имён: анафора — прежние пути (R14 exact-id);
    # задокументированное ограничение Блока 2 (анафора — Блок 5)
    tid, cands = resolve_target_with_candidates(
        _field("guard_gate", "Не бей его."), _SCENE_TWO_GUARDS
    )
    assert tid == "guard_gate" and cands == []


def test_no_match_returns_empty():
    tid, cands = resolve_target_with_candidates(
        _field("", "Поговори с драконом."), _SCENE_TWO_GUARDS
    )
    assert tid == "" and cands == []
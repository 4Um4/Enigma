# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_block52_escalation.py
Назначение: S-UE Блок 5.2 — эскалация не-частицы: юнит-критерии _fast_incomplete
    (NEG-01/02-формы → True; CON/QUE/ATTACK-формы → False) + интеграционный
    smoke с фальсификатором LLM (NEG-01 → ровно 1 вызов; CON-01 → 0).
Зависимости: app.services.input.intent_compressor
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_block52_escalation.py -q; cd ..
"""
import asyncio
from unittest.mock import MagicMock

from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.input.intent_compressor import IntentCompressor


def _fast(action: ActionType, raw: str, speech_act=None) -> IntentSemanticField:
    return IntentSemanticField(action=action, raw_text=raw, speech_act=speech_act)


def _comp() -> IntentCompressor:
    return IntentCompressor(MagicMock())


def test_neg01_form_escalates():
    assert _comp()._fast_incomplete(_fast(ActionType.DIALOGUE, "Не говори ему, что я согласен."), None) is True


def test_neg02_form_escalates():
    assert _comp()._fast_incomplete(_fast(ActionType.DIALOGUE, "Не говори ему, что я не согласен."), None) is True


def test_neg04_attack_not_affected():
    # ATTACK-ветка ниже по коду (зона/пропозиция) — DIALOGUE-правило её не касается
    assert _comp()._fast_incomplete(_fast(ActionType.ATTACK, "Не бей его."), None) is True  # зона UNDEFINED


def test_con01_no_negation_no_escalation():
    assert _comp()._fast_incomplete(_fast(ActionType.DIALOGUE, "Привет."), None) is False


def test_que01_question_path_untouched():
    # вопрос эскалируется СТАРЫМ критерием (speech_act=question), не-частица не нужна
    assert _comp()._fast_incomplete(_fast(ActionType.DIALOGUE, "Кто ты?", speech_act="question"), None) is True


def test_integration_neg01_reaches_llm():
    # Фальсификатор: LLM зовётся РОВНО один раз для NEG-01 (slow-only путь)
    calls = []

    class _FakeLLM:
        async def compress_intent(self, raw_text, scene_context, dialogue_session=None):
            calls.append(raw_text)
            return {
                "action": "DIALOGUE", "speech_act": "order",
                "semantic_acts": [{"type": "ORDER", "params": {}, "negated": True, "quoted": False}],
            }

    comp = IntentCompressor(_FakeLLM())
    f = asyncio.run(comp.compress("Не говори ему, что я согласен.", {}))
    assert calls == ["Не говори ему, что я согласен."]
    assert f.semantic_acts and f.semantic_acts[0].get("negated") is True


def test_integration_positive_twin_stays_fast():
    # Контрольная пара эскалации: тот же глагол, что fast закрывает у NEG-01
    # (baseline 0.001s), БЕЗ не-частицы — правило не эскалирует позитивную
    # форму. «Привет.» не годится как контроль: fast-словарь его не закрывает
    # (SLOW_ONLY by design, задокументировано замерами UE4/UE5/UE52).
    calls = []

    class _FakeLLM:
        async def compress_intent(self, raw_text, scene_context, dialogue_session=None):
            calls.append(raw_text)
            return None

    comp = IntentCompressor(_FakeLLM())
    asyncio.run(comp.compress("Говори ему, что я согласен.", {}))
    assert calls == []
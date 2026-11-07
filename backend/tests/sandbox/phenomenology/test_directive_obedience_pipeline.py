"""
E2E валидация каузальной цепи: Текст -> LLM -> Intent -> Directive -> Obedience
Доказывает, что LegitimacyGate открывается при high fear/trust,
и LLM корректно извлекает MOVE intent из текстовой команды.

ЗАПУСК (Устав §19 — тест НЕ владеет llama-server; Host broker SDK — ensure_llm(label="directive_obedience")):

# ЗАПУСК LLM — не требуется (ensure_llm вызывается автоматически при обращении к LLM)
# Для ручного запуска: python -c "from app.services.llm.runtime.client import ensure_llm; ensure_llm(label='directive_obedience')"

# ПРОВЕРКА
python -c "from app.core.config import settings; print(settings.llama_cpp_server_url)"

# ТЕСТ
python -m pytest backend/tests/sandbox/phenomenology/test_directive_obedience_pipeline.py -v -s

# Остановка LLM — отдельная административная операция (не обязательный шаг теста).
"""

# TODO: Расширить тесты для OBSERVE, ATTACK и других директив.
# Можно добавить проверку логов/событий EventBus при подчинении/неподчинении.
# E2E тест с реальным LLM даёт больше уверенности в интеграции компонентов.

import json
import types
import urllib.error
import urllib.request

import pytest
from app.core.config import settings
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.state_delta import DeltaDomain

from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber

LLM_URL = settings.llama_cpp_server_url


@pytest.fixture(scope="module", autouse=True)
def check_llm_alive():
    """Проверяет, что LLM сервер запущен перед тестами."""
    # Этап 4.1.13: migrated to Host broker SDK. ensure_llm handles start.
    from app.services.llm.runtime.client import ensure_llm
    try:
        ensure_llm(label="directive_obedience")
    except Exception as _e:
        pytest.skip(f"LLM недоступна ({_e}). Каузальный тест пропущен.")


def test_llm_extracts_move_intent():
    """Шаг 1: LLM должен извлечь MOVE intent из текста 'Борко, иди сюда!'"""
    payload = json.dumps(
        {
            "messages": [
                {
                    "role": "system",
                    "content": "Извлеки action (MOVE/OBSERVE/ATTACK) и target из текста. Формат: ACTION: <action>, TARGET: <target>",
                },
                {"role": "user", "content": "Борко, иди сюда!"},
            ],
            "temperature": 0.1,
            "max_tokens": 50,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{LLM_URL}/v1/chat/completions", data=payload, headers={"Content-Type": "application/json"}
    )

    r = urllib.request.urlopen(req, timeout=30)
    data = json.loads(r.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"].upper()

    print(f"\n🧠 LLM Response: {content}")
    assert "MOVE" in content, f"LLM не распознал MOVE intent в команде. Ответ: {content}"


def test_legitimacy_gate_allows_high_fear():
    """Шаг 2: Стражник Борко (fear=0.8) должен подчиниться приказу подойти."""
    npc_borko = {
        "id": "guard_borko",
        "name": "Борко",
        "social_stats": {"fear_of_player": 0.8, "trust": 10.0},
        "body_state": {"disabled": False, "shock_impulse": 0.0},
    }

    event = types.SimpleNamespace(
        source="player",
        payload={
            "semantic_action": "MOVE",
            "target_reference": "борко",
            "target_id": "guard_borko",
            "social_pressure": 0.8,
        },
    )

    sub = DirectiveInterpretationSubscriber()
    deltas = sub.handle(event, [npc_borko])

    identity_delta = next((d for d in deltas if d.domain == DeltaDomain.IDENTITY), None)
    assert identity_delta is not None, "Директива заблокирована! Identity дельта не создана."

    payload = identity_delta.payload
    assert payload.recent_directive_data is not None, "recent_directive_data отсутствует!"
    assert payload.recent_directive_data.get("interrupts_routine") is True, "interrupts_routine не поднят!"
    assert payload.compliance_bias_delta > 0, "compliance_bias_delta должен быть > 0 при подчинении"


def test_legitimacy_gate_blocks_low_fear_thief():
    """Шаг 3: Тень (fear=0.1, trust=0.1) должен ОТКЛОНИТЬ приказ и разозлиться."""
    npc_shadow = {
        "id": "thief_shadow",
        "name": "Тень",
        "social_stats": {"fear_of_player": 0.1, "trust": 0.1},
        "body_state": {"disabled": False, "shock_impulse": 0.0},
    }

    event = types.SimpleNamespace(
        source="player",
        payload={
            "semantic_action": "MOVE",
            "target_reference": "тень",
            "target_id": "thief_shadow",
            "social_pressure": 0.8,
        },
    )

    sub = DirectiveInterpretationSubscriber()
    deltas = sub.handle(event, [npc_shadow])

    identity_delta = next((d for d in deltas if d.domain == DeltaDomain.IDENTITY), None)
    assert identity_delta is not None

    payload = identity_delta.payload
    assert payload.recent_directive_data.get("is_obedience") is False, "Тень не должен подчиняться!"
    assert payload.compliance_bias_delta < 0.2, "Смещение к подчинению должно быть слабым"

"""
E2E валидация каузальной цепи: Текст -> LLM -> Intent -> Directive -> Obedience
Доказывает, что LegitimacyGate открывается при high fear/trust,
и LLM корректно извлекает MOVE intent из текстовой команды.
"""

r"""
ИНСТРУКЦИЯ ЗАПУСКА (PowerShell):
# 0. Убиваем зомби-процессы от прошлых запусков (освобождаем VRAM)
Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

# 1. Запускаем мозг
 $exe = "C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe"
 $model = "C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"
 $llmProc = Start-Process -FilePath $exe -ArgumentList "-m `"$model`" -ngl 99 -c 8192 -t 8 --port 8080 --host 127.0.0.1" -PassThru -WindowStyle Hidden

Write-Host "🧠 LLM сервер запускается (грузим 8GB в VRAM)..."

# 2. Ждем пульс (до 60 секунд для тяжелой модели)
 $ready = $false
for ($i=0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            $ready = $true
            Write-Host "✅ LLM сервер жив. Начинаю E2E тест LegitimacyGate."
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    Write-Host "❌ LLM сервер не поднялся за 60 секунд. Проверь VRAM."
    Stop-Process -Id $llmProc.Id -Force -ErrorAction SilentlyContinue
    Read-Host "Нажми Enter"
    exit 1
}

# 3. Запускаем E2E тест каузальной цепи Директива → Подчинение
python -m pytest backend/tests/sandbox/phenomenology/test_directive_obedience_pipeline.py -v -s

# 4. Убиваем мозг после теста
Write-Host "🧹 Останавливаю LLM сервер (освобождаю VRAM)..."
Stop-Process -Id $llmProc.Id -Force -ErrorAction SilentlyContinue

Read-Host "Готово. Нажми Enter"
"""

# TODO: Расширить тесты для OBSERVE, ATTACK и других директив.
# Можно добавить проверку логов/событий EventBus при подчинении/неподчинении.
# E2E тест с реальным LLM даёт больше уверенности в интеграции компонентов.

import json
import types
import urllib.error
import urllib.request

import pytest
from app.models.state_delta import DeltaDomain

# Примечание: PowerShell-скрипт запускается отдельно (run_directive_test.ps1)
from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber

LLM_URL = "http://127.0.0.1:8080"


@pytest.fixture(scope="module", autouse=True)
def check_llm_alive():
    """Проверяет, что LLM сервер запущен перед тестами."""
    try:
        r = urllib.request.urlopen(f"{LLM_URL}/health", timeout=2)
        if r.status != 200:
            pytest.skip("LLM сервер запущен, но health != 200")
    except urllib.error.URLError:
        pytest.skip("LLM сервер не запущен на localhost:8080. Запусти run_directive_test.ps1")


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

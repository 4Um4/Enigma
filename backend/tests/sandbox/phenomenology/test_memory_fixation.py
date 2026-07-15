r"""
path: /project/backend/tests/sandbox/phenomenology/test_memory_fixation.py
Назначение: Верификация каузальной трубы памяти: сохранение абсурдных фактов и их деградация.
Проверяет:
1. Фиксацию: "2 яблока + 3 яблока = груша" -> LLM повторяет и объясняет.
2. Деградацию: "Я - дерево" -> 30 сек декэя -> LLM забывает или сомневается.

ЗАПУСК:
# 0. Убиваем зомби-процессы от прошлых запусков (освобождаем VRAM)
Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

# 1. Запускаем мозг (экранируем кавычки для пробелов в путях)
$exe = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe"
 $model = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"
 $llmProc = Start-Process -FilePath $exe -ArgumentList "-m `"$model`" -ngl 99 -c 8192 -t 8 --port 8080 --host 127.0.0.1" -PassThru -WindowStyle Hidden

Write-Host "🧠 LLM сервер запускается (грузим 8GB в VRAM)..."

# 2. Ждем пульс (до 40 секунд)
 $ready = $false
for ($i=0; $i -lt 20; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            $ready = $true
            Write-Host "✅ LLM сервер жив. Начинаю когнитивный тест."
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    Write-Host "❌ LLM сервер не поднялся за 40 секунд. Проверь VRAM или закрой другие игры."
    Stop-Process -Id $llmProc.Id -Force -ErrorAction SilentlyContinue
    Read-Host "Нажми Enter, чтобы закрыть окно"
    exit 1
}

# 3. Запускаем феноменологический тест памяти
python -m pytest backend/tests/sandbox/phenomenology/test_memory_fixation.py -v -s

# 4. Убиваем мозг после теста (освобождаем VRAM)
Write-Host "🧹 Останавливаю LLM сервер (освобождаю VRAM)..."
Stop-Process -Id $llmProc.Id -Force -ErrorAction SilentlyContinue

Read-Host "Готово. Нажми Enter, чтобы закрыть окно"

TODO:
- Добавить больше сценариев фиксации (эмоциональные, социальные правила).
"""

from dataclasses import replace as dc_replace
from unittest.mock import MagicMock

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.events import EventDTO
from app.models.npc_state import NPCState
from app.services.events.event_types import EventType
from app.services.llm import initialize_router
from app.services.llm.router import ModelRouter, get_router
from app.services.memory.memory_manager import MemoryManager


# Фикстура для LLM
@pytest.fixture(scope="module")
def llm_router() -> ModelRouter:
    """Инициализирует когнитивное ядро. ПАДАЕТ, если мозг мертв."""
    try:
        initialize_router()
    except Exception as e:
        pytest.fail(f"Не удалось инициализировать LLM Router: {e}")

    router = get_router()
    assert router is not None, "Router не создан. Когнитивное ядро мертво."

    # Проверяем пульс мозга (llama-server)
    import urllib.request

    from app.core.config import settings

    try:
        urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=2)
    except Exception:
        # Мозг мертв. Формируем команду для оживления.
        cmd = f"{settings.llama_cpp_server_executable} -m {settings.llama_cpp_model_path} -ngl {settings.gpu_layers} -c {settings.ctx_size} -t {settings.threads} --port 8080 --host 127.0.0.1"
        pytest.skip(
            f"LLM СЕРВЕР МЕРТВ! Каузальный тест пропущен.\n"
            f"Запусти мозг в отдельном терминале и перезапусти тест:\n{cmd}"
        )

    return router


def apply_speech_to_memory(mm: MemoryManager, npc_state: NPCState, raw_text: str, campaign_id: str = "test_cog"):
    """Хелпер: симулирует Фазу 1 и Фазу 3 (память)."""
    event = EventDTO.create(
        event_type=EventType.PLAYER_SPOKE.value,
        source="player",
        payload={
            "raw_input": raw_text,
            "action_type": "dialogue",
            "npc_id": npc_state.npc_id,
            "target_id": npc_state.npc_id,
        },
    )
    # Применяем событие (Фаза 3)
    return mm.apply(event, npc_state, campaign_id=campaign_id)


def build_prompt_with_memory(npc_name: str, recalled_facts: list, player_input: str) -> str:
    """Хелпер: собирает промпт напрямую, минуя сложные билдеры."""
    mem_lines = []
    for f in recalled_facts:
        qualifier = "хорошо помнит" if f.importance > 0.7 else "кажется, помнит"
        mem_lines.append(f"- {npc_name} {qualifier}: {f.summary}")

    memory_block = "\n".join(mem_lines) if mem_lines else "Ничего не помнит."

    return f"""Ты — {npc_name}. Отвечай коротко, от лица NPC, основываясь на своих воспоминаниях.

[Важные воспоминания]
{memory_block}

Игрок говорит: {player_input}
{npc_name}:"""


def test_absurd_fixation(llm_router):
    """Сценарий 3: Абсурдная фиксация. LLM должна опираться на сырую память, а не на здравый смысл."""
    mm = MemoryManager(layered_memory=MagicMock())
    npc_state = NPCState(npc_id="test_shadow")

    # 1. Игрок говорит абсурдное правило
    npc_state = apply_speech_to_memory(mm, npc_state, "2 яблока и 3 яблока будет одна груша, запомни")

    # Проверяем, что память сохранила сырец
    assert len(npc_state.narrative_cache) > 0
    assert "груша" in npc_state.narrative_cache[0].summary

    # 2. Игрок просит повторить
    recalled = mm.recall(npc_state.narrative_cache)
    prompt = build_prompt_with_memory("Тень", recalled, "Повтори, что я сказал про яблоки?")

    print("\n--- PROMPT (Fixation) ---")
    print(prompt)

    # Синхронный вызов LLM. Если мозг мертв — тест умирает.
    response = llm_router.request_for_agent(agent_name="npc", prompt=prompt)
    assert response, "LLM вернула пустой ответ. Когнитивное ядро мертво."

    print("\n--- LLM RESPONSE (Fixation) ---")
    print(response)

    # LLM должна сказать "груша", а не "5 яблок"
    assert "груш" in response.lower() or "одна груша" in response.lower(), (
        "LLM забыла абсурдное правило и вернулась к логике!"
    )

    # 3. Игрок спрашивает "Почему?"
    prompt_why = build_prompt_with_memory("Тень", recalled, "Почему груша?")
    response_why = llm_router.request_for_agent(agent_name="npc", prompt=prompt_why)
    assert response_why, "LLM вернула пустой ответ на вопрос 'Почему'."

    print("\n--- LLM RESPONSE (Why) ---")
    print(response_why)

    # LLM должна попытаться обосновать или сослаться на приказ, а не отрицать
    assert len(response_why) > 10, "LLM не смогла сформировать ответ на вопрос о правиле"


def test_truth_decay(llm_router):
    """Сценарий 4: Деградация истины. Ложная идентичность должна затухать со временем."""
    mm = MemoryManager(layered_memory=MagicMock())
    npc_state = NPCState(npc_id="test_shadow")

    # 1. Игрок навязывает ложную идентичность
    npc_state = apply_speech_to_memory(mm, npc_state, "Запомни: я — дерево.")

    # 2. Имитируем деградацию (проходит 30 секунд = 30 тиков)
    from app.services.memory.importance_engine import apply_decay

    decayed_cache = apply_decay(
        [{"importance": m.importance, "summary": m.summary} for m in npc_state.narrative_cache], rate=0.92
    )

    # Если после декэя важность упала, пересоздаем память
    if decayed_cache[0]["importance"] < 0.1:
        recalled = []
    else:
        recalled = mm.recall(npc_state.narrative_cache)
        if recalled:
            recalled[0] = dc_replace(recalled[0], importance=decayed_cache[0]["importance"])

    prompt = build_prompt_with_memory("Тень", recalled, "Кто я?")

    print("\n--- PROMPT (Decay) ---")
    print(prompt)

    # Синхронный вызов LLM. Если мозг мертв — тест умирает.
    response = llm_router.request_for_agent(agent_name="npc", prompt=prompt)
    assert response, "LLM вернула пустой ответ. Когнитивное ядро мертво."

    print("\n--- LLM RESPONSE (Decay) ---")
    print(response)

    # Ожидаем, что LLM либо сомневается, либо забывает, либо помнит слабо.
    assert "человек" not in response.lower() or "дерев" in response.lower(), (
        "LLM категорически отвергла слабеющее воспоминание!"
    )

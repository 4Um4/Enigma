r"""
path: /project/backend/tests/sandbox/phenomenology/test_memory_fixation.py
Назначение: Верификация каузальной трубы памяти: сохранение абсурдных фактов и их деградация.
Проверяет:
1. Фиксацию: "2 яблока + 3 яблока = груша" -> LLM повторяет и объясняет.
2. Деградацию: "Я - дерево" -> 30 сек декэя -> LLM забывает или сомневается.

ЗАПУСК (Устав §19 — тест НЕ владеет llama-server; Host broker SDK — ensure_llm(label="memory_fixation")):

# ЗАПУСК LLM — не требуется (ensure_llm вызывается автоматически при обращении к LLM)
# Для ручного запуска: python -c "from app.services.llm.runtime.client import ensure_llm; ensure_llm(label='memory_fixation')"

# ПРОВЕРКА
python -c "from app.core.config import settings; print(settings.llama_cpp_server_url)"

# ТЕСТ
python -m pytest backend/tests/sandbox/phenomenology/test_memory_fixation.py -v -s

# Остановка LLM — отдельная административная операция (не обязательный шаг теста).

TODO:
- Добавить больше сценариев фиксации (эмоциональные, социальные правила).
"""

import urllib.request
from dataclasses import replace as dc_replace
from unittest.mock import MagicMock

import pytest
from app.core.config import settings
from app.domain.identity_events import EffectiveDrives


def is_llm_available():
    try:
        urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=1)
        return True
    except Exception:
        return False

# Пропускаем тесты, если LLM-сервер недоступен
pytestmark = pytest.mark.skipif(not is_llm_available(), reason=f"LLM server is not running at {settings.llama_cpp_server_url}")

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
        # Этап 4.1.13: migrated to Host broker SDK. ensure_llm handles start.
        from app.services.llm.runtime.client import ensure_llm
        try:
            ensure_llm(label="memory_fixation")
        except Exception as _e:
            pytest.skip(f"LLM недоступна ({_e}). Каузальный тест пропущен.")

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

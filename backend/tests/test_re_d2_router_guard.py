"""
path: /project/backend/tests/test_re_d2_router_guard.py
Назначение: Регрессия RE-D2 — request_for_agent() с потока event loop обязан
    падать громко (RuntimeError) немедленно, а не устраивать 60-секундный
    дедлок всего бэкенда (run_coroutine_threadsafe на собственную петлю +
    future.result). До фикса тест ВОСПРОИЗВОДИТ инцидент (60с, TimeoutError).
Зависимости: pytest, asyncio, time; app.services.llm.router.get_router
Основные сущности: test_request_for_agent_from_loop_thread_raises_fast,
    test_router_source_has_no_self_deadlock_bridge
"""

import asyncio
import time
from pathlib import Path

import app.services.llm.router as router_mod
import pytest
from app.services.llm.router import get_router


def test_request_for_agent_from_loop_thread_raises_fast():
    """RE-D2: вызов с потока петли = мгновенный RuntimeError, не дедлок.

    asyncio.run поднимает петлю НА main-потоке pytest: worker-ветка
    (thread != main, router.py:541) не срабатывает — попадаем ровно в
    охраняемую ветку. Guard срабатывает ДО любого обращения к пулу
    моделей/провайдеру, поэтому LLM не нужна.
    """
    router = get_router()

    async def _call_on_loop_thread():
        with pytest.raises(RuntimeError, match="RE-D2"):
            router.request_for_agent(agent_name="dialogue_extractor", prompt="probe")

    _t0 = time.monotonic()
    asyncio.run(_call_on_loop_thread())
    _elapsed = time.monotonic() - _t0
    assert _elapsed < 5.0, (
        f"guard не сработал: вызов занял {_elapsed:.1f}с — "
        "дедлок RE-D2 жив (ветка run_coroutine_threadsafe в router.py)"
    )


def test_router_source_has_no_self_deadlock_bridge():
    """Надгробие: submit-to-self мост в router.py запрещён навсегда.

    Любая будущая легальная потребность в run_coroutine_threadsafe внутри
    роутера — это ровно класс RE-D2 и требует мини-ADR.
    """
    _src = Path(router_mod.__file__).read_text(encoding="utf-8")
    assert "run_coroutine_threadsafe" not in _src, (
        "RE-D2: в router.py возвращён threadsafe-мост — "
        "см. вердикт RE-D2 (self-deadlock) и DEBT-RE-D2A"
    )
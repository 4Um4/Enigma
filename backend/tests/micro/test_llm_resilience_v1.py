"""path: /project/backend/tests/micro/test_llm_resilience_v1.py
Назначение: COV-2 приёмочные тесты LLM-доставки. T1 (D67): playback-miss = RuntimeError; кэшированный пустой ответ = легальная пустая строка без исключения.
Зависимости: pytest, app.services.llm.router, monkeypatch настроек.
Основные сущности: _StubStore, test_playback_miss_is_loud, test_playback_valid_empty_response."""

# backend/tests/micro/test_llm_resilience_v1.py
# COV-2 / D67: контракт replay-playback — miss громкий, пустая запись честная.

import pytest


class _StubStore:
    """Минимальный replay-store: словарь (session, agent, hash) -> запись."""

    def __init__(self, entries=None):
        self._entries = entries or {}

    def get_llm_call(self, session_id, agent_name, prompt_hash):
        return self._entries.get((session_id, agent_name, prompt_hash))

    def record_llm_call(self, **kwargs):
        pass


def _make_router(entries=None):
    from app.services.llm.router import ModelRouter

    router = ModelRouter()
    router.set_replay_context(_StubStore(entries), "sess-t1")
    return router


def test_playback_miss_is_loud_not_empty(monkeypatch):
    """D67: отсутствие записи в кэше playback = RuntimeError, не тихая ``."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "replay_playback", True)
    router = _make_router(entries={})  # пустой стор = miss
    with pytest.raises(RuntimeError, match="cache miss in playback"):
        router.request_for_agent("dm", "probe: отсутствующая запись")


def test_playback_valid_empty_response_is_returned(monkeypatch):
    """D67-контр-кейс: кэшированный пустой ответ — легальный результат."""
    from app.core.config import settings
    from app.services.replay.llm_cache import compute_prompt_hash

    monkeypatch.setattr(settings, "replay_playback", True)
    _hash = compute_prompt_hash("probe: валидная пустая запись", None, None)
    router = _make_router(
        entries={("sess-t1", "dm", _hash): {"response": ""}}
    )
    result = router.request_for_agent("dm", "probe: валидная пустая запись")
    assert result == ""
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


# ── T3: D65 — стрим в едином replay-контракте ─────────────────────────────

def test_stream_record_via_notify_end(monkeypatch):
    """D65: полный стрим-ответ пишется в кэш через notify_stream_end."""
    from app.core.config import settings
    from app.services.llm.router import ModelRouter

    monkeypatch.setattr(settings, "replay_record", True)
    calls = []

    class _RecStore:
        def get_llm_call(self, s, a, h):
            return None

        def record_llm_call(self, **kw):
            calls.append(kw)

    r = ModelRouter()
    r.set_replay_context(_RecStore(), "sess-t3")
    ctx = r.notify_stream_start(
        "dm_narrative", "narrative", prompt="PROMPT", system_prompt="SYS", params=None
    )
    r.notify_stream_end(ctx, 42, full_text="ПОЛНЫЙ ОТВЕТ")
    assert len(calls) == 1
    assert calls[0]["prompt"] == "PROMPT"
    assert calls[0]["response"] == "ПОЛНЫЙ ОТВЕТ"
    assert calls[0]["session_id"] == "sess-t3"
    assert calls[0]["agent_name"] == "dm_narrative"


def test_stream_notify_end_without_full_text_no_record(monkeypatch):
    """D65 back-compat: без full_text запись не происходит."""
    from app.core.config import settings
    from app.services.llm.router import ModelRouter

    monkeypatch.setattr(settings, "replay_record", True)
    calls = []

    class _RecStore:
        def get_llm_call(self, s, a, h):
            return None

        def record_llm_call(self, **kw):
            calls.append(kw)

    r = ModelRouter()
    r.set_replay_context(_RecStore(), "sess-t3")
    ctx = r.notify_stream_start("dm_narrative", "narrative")
    r.notify_stream_end(ctx, 42)
    assert calls == []


def test_stream_playback_hit_returns_cached_no_model(monkeypatch):
    """D65: playback-hit возвращает кэш; провайдер не участвует by construction."""
    from app.core.config import settings
    from app.services.replay.llm_cache import compute_prompt_hash
    from app.services.llm.router import ModelRouter

    monkeypatch.setattr(settings, "replay_playback", True)
    _h = compute_prompt_hash("PROMPT", "SYS", None)
    r = ModelRouter()
    r.set_replay_context(
        _StubStore(entries={("sess-t3", "dm_narrative", _h): {"response": "ОТВЕТ"}}),
        "sess-t3",
    )
    assert r.playback_stream_lookup("dm_narrative", "PROMPT", "SYS", None) == "ОТВЕТ"


def test_stream_playback_miss_is_loud(monkeypatch):
    """D65+D67: playback-miss стрима — RuntimeError, не пустота."""
    from app.core.config import settings
    from app.services.llm.router import ModelRouter

    monkeypatch.setattr(settings, "replay_playback", True)
    r = ModelRouter()
    r.set_replay_context(_StubStore(entries={}), "sess-t3")
    with pytest.raises(RuntimeError, match="stream cache miss"):
        r.playback_stream_lookup("dm_narrative", "NOPE", None, None)


def test_stream_live_when_not_playback(monkeypatch):
    """D65: вне playback — None, живой стрим продолжается."""
    from app.core.config import settings
    from app.services.llm.router import ModelRouter

    monkeypatch.setattr(settings, "replay_playback", False)
    r = ModelRouter()
    assert r.playback_stream_lookup("dm_narrative", "PROMPT", "SYS", None) is None
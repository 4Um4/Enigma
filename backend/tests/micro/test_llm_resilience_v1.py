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

# ── T-queue: D62 — приоритетная очередь worker-ветки (LLM_RESILIENCE_V1) ──

import threading as _th
import time as _t

import app.services.llm.router as _router_mod
from app.services.llm.router import (
    LlmQueueDeadlineError,
    LlmQueueOverflowError,
    ModelRouter,
)


def _q_reset(router):
    """Singleton ModelRouter: состояние очереди сбрасывается между тестами."""
    with router._worker_lock:
        router._slot_busy = False
        router._slot_epoch = 0
        router._waiters = []
        router._waiter_seq = 0
        router._request_in_progress = False


def _q_router():
    r = ModelRouter()
    _q_reset(r)
    return r


class _CallLog:
    """Стаб _request_via_pool: invocation 1 — блокирующийся, далее мгновенные."""

    def __init__(self, router, block_first=0.0, gate=None,
                 first_result="FIRST", later_result="LATER"):
        self.calls = 0
        self.block_first = block_first
        self.gate = gate
        self.first_result = first_result
        self.later_result = later_result
        router._request_via_pool = self.fake  # type: ignore[method-assign]

    def fake(self, capability, preferred_keys=None, prompt="",
             params=None, system_prompt=None):
        self.calls += 1
        if self.calls == 1:
            if self.gate is not None:
                self.gate.wait(timeout=10.0)
            elif self.block_first > 0:
                _t.sleep(self.block_first)
            return self.first_result
        return self.later_result


class _AbortCounter:
    """Счётчик abort_generation (сервер-отмена — no-op в тестах)."""

    def __init__(self, router):
        self.n = 0
        router._abort_generation = self.fake  # type: ignore[method-assign]

    def fake(self):
        self.n += 1


def _run_worker(router, prompt="probe", priority=None, results=None, errors=None):
    def _target():
        try:
            kw = {"priority": priority} if priority is not None else {}
            out = router.request_for_agent("npc", prompt, None, "sys", **kw)
            if results is not None:
                results.append(out)
        except Exception as e:  # тест-сборщик исключений воркеров
            if errors is not None:
                errors.append(e)

    t = _th.Thread(target=_target, daemon=True)
    t.start()
    return t


def _wait_until(pred, timeout=3.0):
    _end = _t.time() + timeout
    while _t.time() < _end:
        if pred():
            return True
        _t.sleep(0.02)
    return pred()


def test_queue_second_canonical_waits_first_not_aborted(monkeypatch):
    """Ядро D62: второй canonical ждёт и обслужен; первый не прерван."""
    monkeypatch.setenv("LLM_RESILIENCE_V1", "1")
    r = _q_router()
    _CallLog(r, block_first=0.4)
    ab = _AbortCounter(r)
    res1, res2, err1, err2 = [], [], [], []
    t1 = _run_worker(r, prompt="first", results=res1, errors=err1)
    assert _wait_until(lambda: r._slot_busy)
    t2 = _run_worker(r, prompt="second", results=res2, errors=err2)
    t1.join(timeout=5); t2.join(timeout=5)
    assert res1 == ["FIRST"] and not err1
    assert res2 == ["LATER"] and not err2
    assert ab.n == 0  # выполняющийся не прерывается прибытием


def test_queue_ambient_yields_to_canonical(monkeypatch):
    """Приоритет: canonical, прибывший ПОЗЖЕ ambient, обслуживается раньше."""
    monkeypatch.setenv("LLM_RESILIENCE_V1", "1")
    r = _q_router()
    order = []
    state = {"n": 0}

    def fake(capability, preferred_keys=None, prompt="",
             params=None, system_prompt=None):
        state["n"] += 1
        if state["n"] == 1:
            _t.sleep(0.4)
        order.append(prompt)
        return "ok"

    r._request_via_pool = fake  # type: ignore[method-assign]
    _AbortCounter(r)
    t0 = _run_worker(r, prompt="holder")
    assert _wait_until(lambda: r._slot_busy)
    ta = _run_worker(r, prompt="ambient-1", priority="ambient")
    assert _wait_until(lambda: len(r._waiters) >= 1)
    tc = _run_worker(r, prompt="canonical-1", priority="canonical")
    assert _wait_until(lambda: len(r._waiters) >= 2)
    for t in (t0, ta, tc):
        t.join(timeout=5)
    assert order == ["holder", "canonical-1", "ambient-1"]


def test_queue_ambient_overflow_drop(monkeypatch):
    """cap=8: девятый ожидающий ambient — контролируемый DROP с причиной."""
    monkeypatch.setenv("LLM_RESILIENCE_V1", "1")
    r = _q_router()
    _CallLog(r, block_first=0.6)
    _AbortCounter(r)
    holder = _run_worker(r, prompt="holder")
    assert _wait_until(lambda: r._slot_busy)
    waiters = [_run_worker(r, prompt=f"amb-{i}", priority="ambient")
               for i in range(8)]
    assert _wait_until(lambda: len(r._waiters) >= 8)
    errs = []
    ninth = _run_worker(r, prompt="amb-9", priority="ambient", errors=errs)
    ninth.join(timeout=5)
    assert len(errs) == 1 and isinstance(errs[0], LlmQueueOverflowError)
    for t in [holder] + waiters:
        t.join(timeout=5)


def test_queue_ambient_deadline_during_wait(monkeypatch):
    """Условие Мастера: дедлайн ambient срабатывает ВО ВРЕМЯ ожидания —
    задача отброшена ДО освобождения занятого слота, не при пробуждении."""
    monkeypatch.setenv("LLM_RESILIENCE_V1", "1")
    monkeypatch.setattr(_router_mod, "_AMBIENT_QUEUE_DEADLINE_SEC", 0.2)
    monkeypatch.setattr(_router_mod, "_WORKER_WALL_TIME_CEILING_SEC", 30.0)
    r = _q_router()
    _CallLog(r, block_first=1.0)
    _AbortCounter(r)
    holder = _run_worker(r, prompt="holder")
    assert _wait_until(lambda: r._slot_busy)
    errs = []
    amb = _run_worker(r, prompt="amb", priority="ambient", errors=errs)
    amb.join(timeout=5)
    assert len(errs) == 1 and isinstance(errs[0], LlmQueueDeadlineError)
    assert r._slot_busy  # слот ещё занят — отказ произошёл в ожидании
    holder.join(timeout=5)
    assert not r._slot_busy


def test_queue_canonical_timeout_loud_never_empty(monkeypatch):
    """canonical-бюджет: истёк — громкий отказ; пустой успех исключён."""
    monkeypatch.setenv("LLM_RESILIENCE_V1", "1")
    monkeypatch.setattr(_router_mod, "_CANONICAL_QUEUE_TIMEOUT_SEC", 0.2)
    monkeypatch.setattr(_router_mod, "_WORKER_WALL_TIME_CEILING_SEC", 30.0)
    r = _q_router()
    _CallLog(r, block_first=1.0)
    _AbortCounter(r)
    holder = _run_worker(r, prompt="holder")
    assert _wait_until(lambda: r._slot_busy)
    errs = []
    c = _run_worker(r, prompt="canon", errors=errs)
    c.join(timeout=5)
    assert len(errs) == 1 and isinstance(errs[0], LlmQueueDeadlineError)
    assert "canonical" in str(errs[0])
    holder.join(timeout=5)


def test_queue_walltime_forfeit_and_late_result_guard(monkeypatch):
    """Интеграционный (условие Мастера): зависший вызов — abort попытан,
    слот форфейтен, следующий canonical обслужен, поздний результат первого
    конвертирован в исключение, слот после всего чист."""
    monkeypatch.setenv("LLM_RESILIENCE_V1", "1")
    monkeypatch.setattr(_router_mod, "_WORKER_WALL_TIME_CEILING_SEC", 0.3)
    monkeypatch.setattr(_router_mod, "_ABORT_GRACE_SEC", 0.2)
    r = _q_router()
    gate = _th.Event()
    _CallLog(r, gate=gate, first_result="LATE", later_result="SECOND")
    ab = _AbortCounter(r)  # «сервер не отменил» — слой 2 обязан работать один
    err1, res2 = [], []
    t1 = _run_worker(r, prompt="stuck", errors=err1)
    assert _wait_until(lambda: r._slot_busy)
    t2 = _run_worker(r, prompt="second", results=res2)
    t2.join(timeout=5)
    assert res2 == ["SECOND"]          # следующий canonical обслужен
    assert ab.n >= 1                   # слой 1: реальная отмена попытана
    gate.set()                         # «сервер наконец ответил» первому
    t1.join(timeout=5)
    assert len(err1) == 1 and "R4A_WALLTIME" in str(err1[0])  # не «LATE»
    res3 = []
    t3 = _run_worker(r, prompt="third", results=res3)
    t3.join(timeout=5)
    assert res3 == ["SECOND"]          # слот чист: прямой захват


def test_queue_flag_off_old_abort_mechanics(monkeypatch):
    """OFF: прежняя механика — второй вызов abort-ит зависший первый."""
    monkeypatch.delenv("LLM_RESILIENCE_V1", raising=False)
    r = _q_router()
    gate = _th.Event()
    _CallLog(r, gate=gate, first_result="A", later_result="B")
    ab = _AbortCounter(r)
    res1, res2 = [], []
    t1 = _run_worker(r, prompt="first", results=res1)
    assert _wait_until(lambda: r._request_in_progress)
    t2 = _run_worker(r, prompt="second", results=res2)
    _t.sleep(0.15)   # t2 внутри abort-ветки (sleep 1.0 старого пути)
    gate.set()       # первый освобождается
    t1.join(timeout=5); t2.join(timeout=5)
    assert ab.n >= 1
    assert res1 == ["A"] and res2 == ["B"]
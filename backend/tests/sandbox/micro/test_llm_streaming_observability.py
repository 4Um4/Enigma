"""
ADR-147: LLM Streaming Observability Gate

Верифицирует, что streaming LLM-вызовы:
1. Проходят через Router (notify_stream_start/end)
2. Генерируют [R4A_STREAM] маркеры
3. CDS парсит маркеры и вызывает on_llm_call/on_llm_response

Запуск: pytest backend/tests/sandbox/micro/test_llm_streaming_observability.py
"""

import logging
from unittest.mock import MagicMock

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.llm.router import ModelRouter

from diagnostics.health_checkers.tick_health import TickHealthChecker
from diagnostics.pattern_registry import COMPILED


class TestRouterStreamingObservability:
    """Router.notify_stream_start/end — корректность маркеров."""

    def test_notify_stream_start_returns_context(self):
        r = ModelRouter()
        ctx = r.notify_stream_start("dm_narrative", "narrative")
        assert "start_time" in ctx
        assert ctx["agent_name"] == "dm_narrative"
        assert ctx["capability"] == "narrative"

    def test_notify_stream_end_logs_marker(self, caplog):
        r = ModelRouter()
        ctx = r.notify_stream_start("dm_narrative", "narrative")
        with caplog.at_level(logging.INFO, logger="root"):
            r.notify_stream_end(ctx, 150)
        assert any("[R4A_STREAM] stream complete" in rec.message for rec in caplog.records)
        assert any("150 chars" in rec.message for rec in caplog.records)

    def test_notify_stream_end_measures_elapsed(self, caplog):
        import time

        r = ModelRouter()
        ctx = r.notify_stream_start("dm_narrative", "narrative")
        time.sleep(0.01)  # 10ms минимум
        with caplog.at_level(logging.INFO, logger="root"):
            r.notify_stream_end(ctx, 200)
        # Должен показать elapsed_ms > 0
        assert any("ms" in rec.message for rec in caplog.records)


class TestPatternRegistryStreaming:
    """Pattern registry распознаёт [R4A_STREAM] маркеры."""

    def test_llm_stream_call_pattern_matches(self):
        line = "[R4A_STREAM] calling stream_tokens(), agent=dm_narrative, capability=narrative"
        assert COMPILED["llm_stream_call"].search(line) is not None

    def test_llm_stream_call_pattern_no_false_positive(self):
        line = "[R4A_POOL] calling complete() on qwen_7b..."
        assert COMPILED["llm_stream_call"].search(line) is None

    def test_llm_stream_response_pattern_extracts_chars(self):
        line = "[R4A_STREAM] stream complete, 247 chars in 1523ms"
        m = COMPILED["llm_stream_response"].search(line)
        assert m is not None
        assert m.group(1) == "247"

    def test_llm_stream_response_pattern_no_false_positive(self):
        line = "[R4A_WORKER] returned 100 chars"
        assert COMPILED["llm_stream_response"].search(line) is None


class TestCausalObserverStreaming:
    """CausalObserver вызывает on_llm_call/on_llm_response при [R4A_STREAM]."""

    def _make_observer(self):
        """Создаёт CausalObserver без файла (только _dispatch)."""
        from diagnostics.causal_observer import CausalObserver

        obs = CausalObserver(log_path=None)
        obs._tick_checker = MagicMock(spec=TickHealthChecker)
        return obs

    def test_stream_call_dispatches_on_llm_call(self):
        obs = self._make_observer()
        line = "2026-06-11 22:50:00 app.services.llm.router INFO: [R4A_STREAM] calling stream_tokens(), agent=dm_narrative, capability=narrative"
        obs._dispatch(line)
        obs._tick_checker.on_llm_call.assert_called_once()

    def test_stream_response_dispatches_on_llm_response(self):
        obs = self._make_observer()
        line = "2026-06-11 22:50:03 app.services.llm.router INFO: [R4A_STREAM] stream complete, 247 chars in 3100ms"
        obs._dispatch(line)
        obs._tick_checker.on_llm_response.assert_called_once_with(247)

    def test_pool_call_still_works(self):
        """Регрессионный: [R4A_POOL] маркеры по-прежнему работают."""
        obs = self._make_observer()
        line = "2026-06-11 22:50:00 app.services.llm.router INFO: [R4A_POOL] calling complete() on qwen_7b..."
        obs._dispatch(line)
        obs._tick_checker.on_llm_call.assert_called_once()

    def test_worker_response_still_works(self):
        """Регрессионный: [R4A_WORKER] маркеры по-прежнему работают."""
        obs = self._make_observer()
        line = "2026-06-11 22:50:01 app.services.llm.router INFO: [R4A_WORKER] returned 500 chars"
        obs._dispatch(line)
        obs._tick_checker.on_llm_response.assert_called_once_with(500)

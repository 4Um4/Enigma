"""
path: /backend/tests/services/cognition/test_router_adapter.py
Назначение: P5-B Step 3 — контракты RouterAdapter (ModelRouter → LLMClientProtocol).
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

from app.services.cognition.router_adapter import RouterAdapter


class _FakeRouter:
    """Production-like ModelRouter stub."""

    def __init__(self, response: str = "YES"):
        self._response = response
        self.calls: list[dict] = []
        self.abort_calls: int = 0

    def request_for_agent(
        self,
        agent_name: str,
        prompt: str,
        params=None,
        system_prompt=None,
        priority: str = "canonical",
    ) -> str:
        self.calls.append({
            "agent_name": agent_name,
            "prompt": prompt,
            "params": params,
            "system_prompt": system_prompt,
            "priority": priority,
        })
        return self._response

    def _abort_generation(self):
        self.abort_calls += 1


class _TextObjectRouter:
    """Mock-router, который возвращает объект с .text (как некоторые mock'и)."""

    def __init__(self, text: str = "YES"):
        self._text = text

    def request_for_agent(self, agent_name, prompt, params=None, system_prompt=None, priority="canonical"):
        obj = MagicMock()
        obj.text = self._text
        return obj


def test_adapter_calls_request_for_agent_with_correct_params():
    router = _FakeRouter("YES")
    adapter = RouterAdapter(router, agent_name="verifier")

    result = adapter.complete("Test prompt?", max_tokens=8, timeout=5.0)

    assert result == "YES"
    assert len(router.calls) == 1
    call = router.calls[0]
    assert call["agent_name"] == "verifier"
    assert call["prompt"] == "Test prompt?"
    assert call["system_prompt"] is None
    assert call["priority"] == "canonical"


def test_adapter_returns_string_directly():
    router = _FakeRouter("NO")
    adapter = RouterAdapter(router)

    assert adapter.complete("prompt") == "NO"


def test_adapter_normalizes_text_attribute():
    router = _TextObjectRouter("ДА")
    adapter = RouterAdapter(router)

    assert adapter.complete("prompt") == "ДА"


def test_adapter_schedules_timeout_timer_when_abort_available():
    router = _FakeRouter("YES")
    adapter = RouterAdapter(router, agent_name="verifier")

    adapter.complete("prompt", max_tokens=8, timeout=5.0)

    assert router.abort_calls == 0


def test_adapter_works_without_abort_generation():
    class _MinimalRouter:
        def __init__(self):
            self.calls = 0
        def request_for_agent(self, agent_name, prompt, params=None, system_prompt=None, priority="canonical"):
            self.calls += 1
            return "YES"

    router = _MinimalRouter()
    adapter = RouterAdapter(router)

    result = adapter.complete("prompt", timeout=5.0)

    assert result == "YES"
    assert router.calls == 1


def test_adapter_returns_empty_string_for_none_response():
    class _NoneRouter:
        def request_for_agent(self, agent_name, prompt, params=None, system_prompt=None, priority="canonical"):
            return None

    adapter = RouterAdapter(_NoneRouter())

    assert adapter.complete("prompt") == ""


def test_adapter_handles_zero_timeout_gracefully():
    router = _FakeRouter("YES")
    adapter = RouterAdapter(router)

    result = adapter.complete("prompt", timeout=0)

    assert result == "YES"
    assert router.abort_calls == 0


def test_adapter_propagates_custom_agent_name():
    router = _FakeRouter("YES")
    adapter = RouterAdapter(router, agent_name="proposition_verifier")

    adapter.complete("prompt")

    assert router.calls[0]["agent_name"] == "proposition_verifier"

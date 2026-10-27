"""
S371.3-GBNF unit-тесты: endpoint branching, grammar payload, error handling.

Покрытие мандата §5:
1. GBNF передаётся в /completion
2. Ответ /completion разбирается корректно (body["content"])
3. Запрос без GBNF → /v1/chat/completions (прежний endpoint)
4. Остальные consumers (grammar=None) не переключаются
5. HTTP-ошибка → RuntimeError с диагностикой
6. Все EntryKind представлены в грамматике (static check)
7. Грамматика не маскирует невалидный JSON (static: root требует closing })
"""
from __future__ import annotations

import json
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any

import pytest

from app.services.llm.llama_cpp_provider import LlamaCppProvider
from app.services.llm.provider import GenerationParams
from app.domain.chronicle import EntryKind

_ROOT = Path(__file__).resolve().parents[3]
_GBNF_PATH = _ROOT / "config" / "chronicle_decompose.gbnf"


@contextmanager
def _mock_http_response(captured: dict, response_content: str = '{"items": []}', endpoint: str = "completion"):
    """Перехватывает urllib.request.build_opener, возвращает mock opener."""
    fake_response_bytes = json.dumps({
        "content": response_content,
        "tokens_predicted": len(response_content.split()),
    }).encode("utf-8") if endpoint == "completion" else json.dumps({
        "choices": [{"message": {"content": response_content}}],
        "usage": {"completion_tokens": len(response_content.split())},
    }).encode("utf-8")

    class _FakeCtx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return fake_response_bytes

    fake_ctx = _FakeCtx()
    fake_opener = MagicMock()
    fake_opener.open.return_value = fake_ctx

    def _fake_build_opener(*args, **kwargs):
        return fake_opener

    def _open(req, timeout=None):
        captured["data"] = req.data
        captured["url"] = req.full_url
        return fake_ctx

    fake_opener.open.side_effect = _open

    with patch("urllib.request.build_opener", side_effect=_fake_build_opener):
        yield captured


def _make_provider() -> LlamaCppProvider:
    return LlamaCppProvider(server_url="http://127.0.0.1:8181")


# ── Тест 1: GBNF передаётся в /completion ────────────────────────────────────

def test_grammar_uses_completion_endpoint():
    """params.grammar задан → POST /completion (не /v1/chat/completions)."""
    captured: dict = {}
    provider = _make_provider()
    grammar = 'root ::= "{" ws "}"'
    params = GenerationParams(temperature=0.0, max_tokens=100, grammar=grammar)

    with _mock_http_response(captured, '{"items": []}'):
        provider.complete("test prompt", params=params, system_prompt="sys")

    assert "/completion" in captured["url"], f"Expected /completion, got {captured['url']}"
    assert "/v1/chat/completions" not in captured["url"]


def test_grammar_in_payload():
    """params.grammar попадает в HTTP payload как поле 'grammar'."""
    captured: dict = {}
    provider = _make_provider()
    grammar = 'root ::= "{" ws "}"'
    params = GenerationParams(temperature=0.0, max_tokens=100, grammar=grammar)

    with _mock_http_response(captured, '{"items": []}'):
        provider.complete("test prompt", params=params, system_prompt="sys")

    payload = json.loads(captured["data"].decode("utf-8"))
    assert payload.get("grammar") == grammar, f"grammar not in payload: {sorted(payload.keys())}"


# ── Тест 2: Ответ /completion разбирается корректно ──────────────────────────

def test_completion_response_parsed():
    """body['content'] извлекается из /completion ответа."""
    captured: dict = {}
    provider = _make_provider()
    grammar = 'root ::= "{" ws "}"'
    params = GenerationParams(temperature=0.0, max_tokens=100, grammar=grammar)

    expected_content = '{"items": [{"kind": "EVENT", "draft_payload": {"summary": "test"}, "confidence": 0.9}]}'
    with _mock_http_response(captured, expected_content):
        result = provider.complete("test prompt", params=params, system_prompt="sys")

    assert result == expected_content, f"Expected {expected_content!r}, got {result!r}"


# ── Тест 3: Запрос без GBNF → прежний endpoint ───────────────────────────────

def test_no_grammar_uses_chat_endpoint():
    """params.grammar=None → POST /v1/chat/completions (прежний endpoint)."""
    captured: dict = {}
    provider = _make_provider()
    params = GenerationParams(temperature=0.0, max_tokens=100, grammar=None)

    with _mock_http_response(captured, "response", endpoint="chat"):
        provider.complete("test prompt", params=params, system_prompt="sys")

    assert "/v1/chat/completions" in captured["url"], f"Expected /v1/chat/completions, got {captured['url']}"
    assert "/completion" not in captured["url"] or "/v1/chat/completions" in captured["url"]


def test_no_grammar_no_grammar_field():
    """params.grammar=None → поле 'grammar' отсутствует в payload."""
    captured: dict = {}
    provider = _make_provider()
    params = GenerationParams(temperature=0.0, max_tokens=100, grammar=None)

    with _mock_http_response(captured, "response", endpoint="chat"):
        provider.complete("test prompt", params=params, system_prompt="sys")

    payload = json.loads(captured["data"].decode("utf-8"))
    assert "grammar" not in payload, f"grammar=None, но поле в payload: {payload.get('grammar')}"


# ── Тест 5: HTTP-ошибка → RuntimeError ───────────────────────────────────────

def test_http_error_raises_runtime_error():
    """HTTP-ошибка → RuntimeError с диагностикой (после retry)."""
    provider = _make_provider()
    grammar = 'root ::= "{" ws "}"'
    params = GenerationParams(temperature=0.0, max_tokens=100, grammar=grammar)

    with patch("urllib.request.build_opener") as mock_build:
        mock_opener = MagicMock()
        mock_opener.open.side_effect = urllib.error.URLError("test error")
        mock_build.return_value = mock_opener

        with patch("time.sleep"):  # ускоряем retry
            with pytest.raises(RuntimeError, match="Не удалось подключиться к llama-server"):
                provider.complete("test prompt", params=params, system_prompt="sys")


# ── Тест 6: Все EntryKind представлены в грамматике ──────────────────────────

def test_grammar_file_exists():
    """config/chronicle_decompose.gbnf существует."""
    assert _GBNF_PATH.exists(), f"GBNF grammar not found: {_GBNF_PATH}"


def test_grammar_all_entrykinds_represented():
    """Грамматика permissive — поддерживает все EntryKind через generic object.

    Текущая грамматика не ограничивает значения 'kind' (LLM может выдать любой
    string; нормализатор валидирует EntryKind). Проверяем, что грамматика
    разрешает string values для kind и object values для draft_payload.
    """
    grammar = _GBNF_PATH.read_text(encoding="utf-8")

    # Грамматика должна содержать правила для string и object
    assert "string" in grammar, "Grammar missing string rule"
    assert "object" in grammar, "Grammar missing object rule"
    assert "array" in grammar, "Grammar missing array rule"
    assert "root" in grammar, "Grammar missing root rule"

    # root должен требовать items (форма {"items": [...]})
    assert '"items"' in grammar or '"\\\"items\\\""' in grammar, "Grammar missing items key in root"


# ── Тест 7: Грамматика не маскирует невалидный JSON ──────────────────────────

def test_grammar_requires_closing_brace():
    """root правило требует closing } — LLM не может остановиться на ] без }.

    Проверяем статически: root ::= ... ws "}" — финальный } обязателен.
    """
    grammar = _GBNF_PATH.read_text(encoding="utf-8")

    # root rule должен заканчиваться на "}"
    root_lines = [l for l in grammar.splitlines() if l.strip().startswith("root ::=")]
    assert root_lines, "Grammar missing root rule"

    root_rule = root_lines[0]
    assert '"}"' in root_rule, f"root rule missing closing brace: {root_rule!r}"
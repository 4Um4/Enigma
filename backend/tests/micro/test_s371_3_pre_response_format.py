"""
S371.3-pre: response_format доезжает до HTTP payload в _complete_via_server.

Mirror H-14 FIX из openai_compatible_provider:90-91.
Тесты НЕ требуют живого llama-server — перехватывают urllib.request.build_opener,
читают req.data (payload), проверяют json.loads(payload)["response_format"].

Принципы:
- только server-mode /v1/chat/completions (payload 166-178)
- streaming/CLI (payload 367/479) не тестируем — ограничение Мастера «не расширять на CLI»
- мок HTTP через monkeypatch urllib.request.build_opener
"""
from __future__ import annotations

import json
import urllib.request
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.llama_cpp_provider import LlamaCppProvider
from app.services.llm.provider import GenerationParams


@contextmanager
def _mock_http_response(payload_captured: dict):
    """Перехватывает urllib.request.build_opener, возвращает mock opener.

    Сохраняет req.data в payload_captured для последующей проверки.
    Возвращает JSON-ответ в формате llama-server /v1/chat/completions.
    """
    fake_response_bytes = json.dumps({
        "choices": [
            {"message": {"content": '{"items": []}'}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
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

    # Перехватываем opener + сохраняем req из open()
    def _make_open_capture():
        def _open(req, timeout=None):
            payload_captured["data"] = req.data
            payload_captured["url"] = req.full_url
            return fake_ctx
        return _open

    fake_opener.open.side_effect = _make_open_capture()

    with patch("urllib.request.build_opener", side_effect=_fake_build_opener):
        yield payload_captured


def _make_provider() -> LlamaCppProvider:
    """Создаёт LlamaCppProvider в server-mode (server_url непустой → _use_server=True)."""
    return LlamaCppProvider(server_url="http://127.0.0.1:8181")


def test_response_format_in_payload():
    """response_format={"type":"json_object"} попадает в HTTP payload."""
    captured: dict = {}
    provider = _make_provider()
    params = GenerationParams(
        temperature=0.0,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )

    with _mock_http_response(captured):
        provider._complete_via_server("test prompt", "test system", params)

    assert "data" in captured, "req.data не перехвачен"
    payload = json.loads(captured["data"].decode("utf-8"))
    assert payload.get("response_format") == {"type": "json_object"}, (
        f"response_format не дошёл до payload; payload keys = {sorted(payload.keys())}"
    )


def test_response_format_none_omitted():
    """response_format=None → ключа нет в payload (поведение прежнее, регрессия)."""
    captured: dict = {}
    provider = _make_provider()
    params = GenerationParams(
        temperature=0.0,
        max_tokens=2048,
        response_format=None,
    )

    with _mock_http_response(captured):
        provider._complete_via_server("test prompt", "test system", params)

    payload = json.loads(captured["data"].decode("utf-8"))
    assert "response_format" not in payload, (
        f"response_format=None, но ключ в payload: {payload.get('response_format')}"
    )


def test_other_fields_unchanged():
    """Все остальные поля payload сохраняются (snapshot contract)."""
    captured: dict = {}
    provider = _make_provider()
    params_with = GenerationParams(
        temperature=0.0,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    params_without = GenerationParams(
        temperature=0.0,
        max_tokens=2048,
        response_format=None,
    )

    with _mock_http_response(captured):
        provider._complete_via_server("test prompt", "test system", params_with)
    payload_with = json.loads(captured["data"].decode("utf-8"))

    captured2: dict = {}
    with _mock_http_response(captured2):
        provider._complete_via_server("test prompt", "test system", params_without)
    payload_without = json.loads(captured2["data"].decode("utf-8"))

    # Все ключи без response_format должны совпадать
    keys_with = set(payload_with.keys()) - {"response_format"}
    keys_without = set(payload_without.keys())
    assert keys_with == keys_without, (
        f"Изменился набор ключей: with={sorted(keys_with)} without={sorted(keys_without)}"
    )

    # Значения всех общих ключей совпадают (seed детерминирован по prompt)
    for key in keys_with:
        assert payload_with[key] == payload_without[key], (
            f"Поле {key} изменилось: with={payload_with[key]} without={payload_without[key]}"
        )
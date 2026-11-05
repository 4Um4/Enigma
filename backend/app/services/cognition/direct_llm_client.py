"""
path: /backend/app/services/cognition/direct_llm_client.py
Назначение: P5-B L4 test — прямой HTTP client к llama-server (localhost:8181).

Обходит router capability mapping для verifier'а. Production wiring
остаётся через RouterAdapter; этот client — для L4 live tests, где
нужен прямой доступ к Hermes-3 без router abstraction.

Контракт: LLMClientProtocol.complete(prompt, *, max_tokens, timeout) -> str.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class DirectLLMClient:
    """Прямой HTTP client к llama-server. LLMClientProtocol implementation."""

    def __init__(
        self,
        server_url: str = "http://localhost:8181",
        model: str = "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf",
        temperature: float = 0.0,
    ):
        self._server_url = server_url.rstrip("/")
        self._model = model
        self._temperature = temperature

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 3,
        timeout: float = 30.0,
    ) -> str:
        """LLMClientProtocol.complete() — POST /v1/chat/completions."""
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": self._temperature,
            "stop": ["\n"],
        }
        body_bytes = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            f"{self._server_url}/v1/chat/completions",
            data=body_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
                content = response_data["choices"][0]["message"]["content"]
                logger.debug(
                    "DirectLLMClient.complete: prompt_head=%r → %r",
                    prompt[:80], content,
                )
                return content
        except urllib.error.URLError as exc:
            logger.warning("DirectLLMClient: URLError — %s", exc)
            raise
        except Exception as exc:
            logger.warning("DirectLLMClient: error — %s", exc)
            raise

"""
path: /backend/app/services/cognition/router_adapter.py
Назначение: P5-B Step 3 — adapter из production ModelRouter в LLMClientProtocol.

Production router (app.services.llm.router.ModelRouter) использует метод
request_for_agent(agent_name, prompt, params, system_prompt, priority) -> str.
PropositionVerifier требует LLMClientProtocol.complete(prompt, *, max_tokens, timeout).

Adapter переводит один интерфейс в другой, сохраняя:
  - timeout через существующий cancellation boundary (ModelRouter._abort_generation,
    ENIGMA-ARCH-022) — тот же механизм, что использует DialogueExecutor.
  - max_tokens через GenerationParams (если поддерживается).
  - agent_name="verifier" — отдельная семантическая категория для метрик router'а.

Зависимости: app.services.llm.router (ModelRouter, GenerationParams)
Основные сущности: RouterAdapter
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class RouterAdapter:
    """Adapter: ModelRouter → LLMClientProtocol.complete().

    Используется PropositionVerifier'ом для LLM-вызова верификации
    candidate proposition ↔ LLM-текста.
    """

    def __init__(
        self,
        router: Any,
        agent_name: str = "verifier",
    ):
        self._router = router
        self._agent_name = agent_name

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 8,
        timeout: float | None = 5.0,
    ) -> str:
        """LLMClientProtocol.complete() implementation via ModelRouter."""
        params: Any = None
        try:
            from app.services.llm.router import GenerationParams
            try:
                params = GenerationParams(max_tokens=max_tokens)
            except TypeError:
                try:
                    params = GenerationParams(max_tokens)
                except Exception:  # noqa: BLE001
                    params = None
        except ImportError:
            params = None

        _abort = getattr(self._router, "_abort_generation", None)
        _timer: threading.Timer | None = None
        if _abort is not None and timeout is not None and timeout > 0:
            _timer = threading.Timer(timeout, _abort)
            _timer.daemon = True
            _timer.start()

        try:
            raw = self._router.request_for_agent(
                agent_name=self._agent_name,
                prompt=prompt,
                params=params,
                system_prompt=None,
                priority="canonical",
            )
        finally:
            if _timer is not None:
                _timer.cancel()

        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        text_attr = getattr(raw, "text", None)
        if isinstance(text_attr, str):
            return text_attr
        return str(raw)

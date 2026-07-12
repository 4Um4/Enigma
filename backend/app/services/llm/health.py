from __future__ import annotations
# backend/app/services/llm/health.py
"""
Инфраструктурный слой: Проверка доступности LLM бэкенда.
Отвечает только за ping сервера (жив/мертв), не за генерацию.
"""


import time
from typing import Dict

import httpx

from app.core.config import settings

# Простой in-memory кэш для избежания спама запросами при рефреше UI
_cache: Dict = {}
_cache_time: float = 0.0
_CACHE_TTL_SEC: float = 5.0


def check_llm_health(use_cache: bool = True) -> Dict:
    """
    Проверяет доступность llama.cpp/vLLM сервера.
    Возвращает словарь со статусом, именем модели и URL.
    """
    global _cache, _cache_time

    if use_cache and (time.time() - _cache_time < _CACHE_TTL_SEC) and _cache:
        return _cache

    url = settings.llama_cpp_server_url

    try:
        with httpx.Client(timeout=settings.llama_cpp_timeout_sec) as client:
            response = client.get(f"{url}/v1/models")

            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                model_name = models[0].get("id", "unknown") if models else "unknown"

                _cache = {"status": "online", "model": model_name, "url": url}
            else:
                _cache = {
                    "status": "error",
                    "code": response.status_code,
                    "details": f"HTTP {response.status_code}",
                }
    except httpx.ConnectError:
        _cache = {"status": "offline", "details": "Connection refused"}
    except Exception as e:
        # Защита от краша при любых других сетевых ошибках
        _cache = {"status": "error", "details": str(e)}

    _cache_time = time.time()
    return _cache

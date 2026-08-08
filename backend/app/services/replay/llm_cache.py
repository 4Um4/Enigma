# backend/app/services/replay/llm_cache.py
"""
Подсистема 2: Логика кэширования LLM-ответов для Replay (Этап 2.3).
Инкапсулирует хеширование промпта, чтобы избежать дублирования (DRY).
"""
import hashlib
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def compute_prompt_hash(prompt: str) -> str:
    """Вычисляет стабильный SHA-256 хеш промпта для дедупликации."""
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()

class LLMCache:
    """Read-through кэш, делегирующий чтение в ReplayStore."""
    def __init__(self, store: Any):
        self.store = store

    def get(self, agent_name: str, prompt: str) -> Optional[Dict[str, Any]]:
        _hash = compute_prompt_hash(prompt)
        return self.store.get_llm_call(agent_name, _hash)

    def record(self, session_id: str, tick_id: int, agent_name: str, prompt: str, response: str, model_name: str, latency_ms: int = 0) -> None:
        """Делегирует запись в ReplayStore."""
        self.store.record_llm_call(
            session_id=session_id,
            tick_id=tick_id,
            agent_name=agent_name,
            prompt=prompt,
            response=response,
            model_name=model_name,
            latency_ms=latency_ms
        )
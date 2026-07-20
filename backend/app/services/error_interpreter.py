"""
Error Interpreter Service (F1-T01)

Intercepts LLM/agent errors, analyzes context from JSONL logs,
provides human-readable diagnostics + fix recommendations.

Supported errors:
- timeout (asyncio.TimeoutError)
- OOM (VRAM exceed + MemoryError)
- SyntaxError/ModuleNotFoundError (model load/parse)
- context_overflow (token limit)
- model_fail (provider error)
"""

import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# JSONL log path (shared with structured logging)
LOG_DIR = Path(settings.data_dir) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"enigma_{datetime.now().strftime('%Y%m%d')}.jsonl"


class ErrorInterpreter:
    """Singleton error analyzer."""

    _instance: Optional["ErrorInterpreter"] = None

    def __new__(cls) -> "ErrorInterpreter":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_logs()
        return cls._instance

    def _init_logs(self):
        self._log_entries: list[dict] = []
        self._tail_lines = 50  # Analyze last N entries

    def handle(
        self,
        exc: Exception,
        context: Dict[str, any] = None,
        agent: str = "unknown",
        model: str = "unknown",
    ) -> Tuple[str, str]:
        """
        Analyze exception → return (human_msg, fix_recommendation)

        Args:
            exc: Caught exception
            context: {'session_id', 'vram_before', ...}
            agent/model: For precise diagnostics

        Returns:
            (user_message, dev_fix)
        """
        error_code = self._classify_error(exc)
        timestamp = datetime.now().isoformat()

        # Log structured event
        tb_str = traceback.format_exc()
        log_entry = {
            "timestamp": timestamp,
            "level": "ERROR",
            "agent": agent,
            "model": model,
            "error_code": error_code,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": tb_str,
            "context": context or {},
            "recommendation": self._get_fix_recommendation(error_code, context),
        }
        self._jsonl_log(log_entry)

        human_msg = self._human_message(error_code, agent, model)
        fix = self._get_fix_recommendation(error_code, context)

        # Dev alert
        logger.error(f"[ERROR_INTERPRETER] {agent}/{model}: {human_msg} | Fix: {fix}")

        return human_msg, fix

    def _classify_error(self, exc: Exception) -> str:
        exc_type = type(exc).__name__.lower()
        exc_msg = str(exc).lower()

        if "timeout" in exc_type or "timeout" in exc_msg:
            code = "timeout"
        elif "memory" in exc_type or "oom" in exc_msg or "out of memory" in exc_msg:
            code = "oom"
        elif "syntaxerror" in exc_type:
            code = "syntax"
        elif "modulenotfounderror" in exc_type or "no module named" in exc_msg:
            code = "modulenotfound"
        elif "context" in exc_msg or "token limit" in exc_msg:
            code = "context_overflow"
        else:
            code = "model_fail"

        return code

    def _human_message(self, error_code: str, agent: str, model: str) -> str:
        messages = {
            "timeout": f"⏰ {agent.upper()} ({model}) timed out. Проверьте llama-server.",
            "oom": f"💥 {agent.upper()} ({model}) OOM - не хватило VRAM. Разгрузите модели.",
            "syntax": f"🔧 {agent.upper()} ({model}) SyntaxError в модели/промпте.",
            "modulenotfound": f"📦 {agent.upper()} ({model}) модуль не найден.",
            "context_overflow": f"📜 {agent.upper()} ({model}) превышен лимит контекста.",
            "model_fail": f"❌ {agent.upper()} ({model}) провалился (см. логи).",
        }
        return messages.get(error_code, f"❌ {agent.upper()} ({model}) ошибка.")

    def _get_fix_recommendation(self, error_code: str, context: Dict) -> str:
        fixes = {
            "timeout": [
                "1. Проверьте llama-server: http://127.0.0.1:8181/health",
                "2. Увеличьте model_load_timeout_sec в config.py",
                "3. Перезапустите backend/start_enigma.bat",
            ],
            "oom": [
                "1. nvidia-smi → Проверьте VRAM (<6GB свободно)",
                "2. ModelPool.unload_all() или перезапуск сервера",
                "3. Уменьшите gpu_layers в llama-server (--gpu-layers 25)",
            ],
            "syntax": [
                "1. Проверьте model path в config.py → available_models",
                "2. .gguf файл повреждён? Перекачайте",
                "3. Конфликт chat template в промпте",
            ],
            "modulenotfound": [
                "1. pip install -r backend/requirements.txt",
                "2. Проверьте PYTHONPATH (backend/app)",
                "3. Перезапустите VSCode terminal",
            ],
            "context_overflow": [
                "1. Уменьшите context_size в model config (4096→2048)",
                "2. Очистите session_memory: rm data/session_memory_*.jsonl",
                "3. Включите memory compression в orchestrator",
            ],
            "model_fail": [
                "1. Проверьте /api/health → LLM status",
                "2. data/logs/*.jsonl → tail -20",
                "3. ModelPool debug=True в main.py startup",
            ],
        }
        return "\n".join(fixes.get(error_code, ["1. Проверьте логи data/logs/*.jsonl"]))

    def _jsonl_log(self, entry: Dict):
        """Append to daily JSONL log."""
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            self._log_entries.append(entry)
            self._log_entries = self._log_entries[-self._tail_lines :]
        except Exception:
            logger.error("Failed to write JSONL log")

    def get_recent_logs(self, lines: int = 20) -> list[Dict]:
        """Return tail of logs for /debug/logs-tail."""
        return self._log_entries[-lines:]

    def analyze_recent_errors(self) -> Dict[str, int]:
        """Count recent error_codes for dashboard."""
        errors = {}
        for entry in self._log_entries[-50:]:
            code = entry.get("error_code")
            if code:
                errors[code] = errors.get(code, 0) + 1
        return errors

    def simulate_startup_error(self):
        try:
            raise Exception("Simulated startup error")
        except Exception as e:
            entry = {"error_code": "startup_error", "error_message": str(e)}
            self._jsonl_log(entry)
            raise


# Global convenience
_interpreter_instance: ErrorInterpreter | None = None


def get_error_interpreter() -> ErrorInterpreter:
    global _interpreter_instance
    if _interpreter_instance is None:
        _interpreter_instance = ErrorInterpreter()
    return _interpreter_instance

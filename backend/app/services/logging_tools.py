"""
Назначение: Простейший логгер в JSONL. Append-only, без ротации.
создан для аудита действий в системе, включая возможность захвата полных промптов LLM (Large Language Model) при включенной соответствующей настройке.
Файл лога: enigma_audit.jsonl (для аудита) и llm_full_prompts.jsonl (для захвата полных промптов LLM, если включено).
"""

import json
import os
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.log_gate import file_logs_enabled

LOG_DIR = Path(settings.data_dir) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
# M-11 FIX: Единый append-only файл лога (provenance chain, без daily rotation)
LOG_FILE = LOG_DIR / "enigma_audit.jsonl"


def jsonl_log(entry: dict[str, Any]) -> None:
    """Простейший логгер в JSONL. Append-only, без ротации."""
    # LOG-GATE: при ENIGMA_DISABLE_FILE_LOGS=1 (тесты из git-хуков) файл молчит.
    if not file_logs_enabled():
        return
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# B4-R6: Full prompt capture — separate file, env-gated
_FULL_PROMPT_FILE = LOG_DIR / "llm_full_prompts.jsonl"


def log_full_prompt(entry: dict[str, Any]) -> None:
    """B4-R6: Full prompt capture. Disabled by default.

    Set ENIGMA_LOG_FULL_PROMPTS=1 to enable.
    Saves to separate file (llm_full_prompts.jsonl) to avoid bloating enigma_audit.jsonl.
    Full system_prompt + user_prompt saved (NOT truncated).
    """
    if not file_logs_enabled():
        return
    if os.environ.get("ENIGMA_LOG_FULL_PROMPTS", "").strip().lower() not in ("1", "true", "yes"):
        return
    with open(_FULL_PROMPT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

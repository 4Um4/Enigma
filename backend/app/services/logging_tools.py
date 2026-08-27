import json
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.log_gate import file_logs_enabled

LOG_DIR = Path(settings.data_dir) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
# M-11 FIX: Единый append-only файл лога (provenance chain, без daily rotation)
LOG_FILE = LOG_DIR / "enigma_audit.jsonl"


def jsonl_log(entry: dict):
    """Простейший логгер в JSONL. Append-only, без ротации."""
    # LOG-GATE: при ENIGMA_DISABLE_FILE_LOGS=1 (тесты из git-хуков) файл молчит.
    if not file_logs_enabled():
        return
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

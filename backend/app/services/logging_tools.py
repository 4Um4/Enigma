import json
from datetime import datetime
from pathlib import Path
from app.core.config import settings

LOG_DIR = Path(settings.data_dir) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"enigma_{datetime.now().strftime('%Y%m%d')}.jsonl"

def jsonl_log(entry: dict):
    """Простейший логгер в JSONL"""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
file_path = ROOT / "backend/app/services/spatial/movement_engine.py"

if not file_path.exists():
    print(f"[ERROR] File not found: {file_path}")
    exit(1)

content = file_path.read_text(encoding="utf-8")
content = content.replace('print(f"[BORKO_', 'logger.debug(f"[BORKO_')
file_path.write_text(content, encoding="utf-8")
print("[FIXED] movement_engine.py prints replaced with logger.debug")
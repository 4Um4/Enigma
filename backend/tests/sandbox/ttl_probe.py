"""S259/IRON-RIVER F1b: фактическая форма TTL-фильтра — что реально стоит
на месте _UI_TTL_SEC (комментарий 'moved to module level (021)' лжёт)."""
import sys
from pathlib import Path

sys.path.insert(0, ".")
src = Path("app/services/game_loop/task_scheduler.py").read_text(encoding="utf-8")
lines = src.splitlines()
for idx, line in enumerate(lines):
    if "_UI_TTL" in line or "TTL" in line.upper() and "=" in line and not line.strip().startswith("#"):
        print(f"{idx+1}: {line}")
# контекст функции get_recent_dialogues
for idx, line in enumerate(lines):
    if "def get_recent_dialogues" in line:
        for j in range(idx, min(idx + 18, len(lines))):
            print(f"{j+1}: {lines[j]}")
        break
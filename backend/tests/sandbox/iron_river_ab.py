"""
path: /project/backend/tests/sandbox/iron_river_ab.py
Назначение: IRON RIVER D-1/F1 — мини A/B канон-дифф (два подпроцесса,
    один ambient-паттерн, 150 тиков, канонический хеш сцены; real_ts
    исключён). Замена отсутствующему iron_river_run.py (Linux-сессия).
Зависимости: subprocess, hashlib, json, tempfile
Основные сущности: _RUNNER (код подпроцесса), main
Запуск: cd backend; python tests/sandbox/iron_river_ab.py
"""
import hashlib
import json
import subprocess
import sys

_RUNNER = r"""
import sys, tempfile, types, os, hashlib, json, shutil
from pathlib import Path
sys.path.insert(0, ".")
from app.core.config import settings

# IRON RIVER D-3 (F4): ПОЛНОЕ temp-окружение. P0-4 закрыт для A/B:
# life_engine.sessions_dir = data_dir/"sessions" (:245, хардкод от data_dir,
# НЕ settings.saves_dir) → world_tick.json жил в общем data/ и RUN2 наследовал
# sim_tick RUN1 (+150). Изоляция: копия data/ в temp (конфиги NPC/карты нужны
# живьём) + settings.data_dir на копию → sessions лягут в temp. Production
# не тронут (build_game_loop(data_dir=...) — существующий вход).
# IRON RIVER D-3: копия data/ БЕЗ тяжёлых артефактов прогона (replay.db
# растёт месяцами — его копирование переполнило диск, WinError 112) +
# автоочистка temp по завершении прогона (гейт гоняется десятками раз).
import atexit

_data_src = Path(settings.data_dir)
_data_tmp = Path(tempfile.mkdtemp(prefix="ab_f4_data_"))
_ignore = shutil.ignore_patterns("replay.db", "*.jsonl", "logs", "campaign_memory_*")
shutil.copytree(_data_src, _data_tmp, dirs_exist_ok=True, ignore=_ignore)
atexit.register(lambda: shutil.rmtree(_data_tmp, ignore_errors=True))
# чистим унаследованный счётчик и артефакты прошлых прогонов в копии
_wt = _data_tmp / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.saves_dir = tempfile.mkdtemp(prefix="ab_f1_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
from app.services.game_loop_builder import build_game_loop
w = types.SimpleNamespace(game_loop=build_game_loop(_data_tmp))
for _ in range(150):
    w.game_loop.idle_tick("Open_road")
scene = w.game_loop.scene_manager.get_scene_state("Open_road", "tavern") or {}
def canon(o):
    if isinstance(o, dict):
        return {k: ("<RT>" if k == "real_ts" else canon(v)) for k, v in sorted(o.items())}
    if isinstance(o, list):
        return [canon(x) for x in o]
    return o
print("HASH " + hashlib.sha256(json.dumps(canon(scene), sort_keys=True, default=str).encode()).hexdigest())
"""

def main() -> int:
    hashes = []
    for i in range(2):
        r = subprocess.run(
            [sys.executable, "-c", _RUNNER],
            capture_output=True, text=True, cwd=".",
        )
        line = next((l for l in r.stdout.splitlines() if l.startswith("HASH ")), "")
        if not line:
            print(f"RUN{i+1}: ERR")
            print("STDERR tail:", r.stderr.strip().splitlines()[-3:])
            hashes.append(None)
        else:
            hashes.append(line[5:])
            print(f"RUN{i+1}: {line[5:]}")
    if hashes[0] and hashes[0] == hashes[1]:
        print("VERDICT: MATCH")
        return 0
    print("VERDICT: MISMATCH")
    return 1

if __name__ == "__main__":
    sys.exit(main())
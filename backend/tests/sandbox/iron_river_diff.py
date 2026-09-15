"""
path: /project/backend/tests/sandbox/iron_river_diff.py
Назначение: IRON RIVER — диф канонов: два RUN'а, при MISMATCH печатает
    ПУТИ расхождений (до 30) — источник недетерминизма по полям, не хеш-слепота.
Зависимости: subprocess, json, tempfile
Запуск: cd backend; python tests/sandbox/iron_river_diff.py
"""
import json
import subprocess
import sys

_RUNNER = r"""
import sys, tempfile, types, os, json, shutil, atexit, hashlib
from pathlib import Path
sys.path.insert(0, ".")
from app.core.config import settings
_data_src = Path(settings.data_dir)
_data_tmp = Path(tempfile.mkdtemp(prefix="ab_diff_data_"))
shutil.copytree(_data_src, _data_tmp, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
atexit.register(lambda: shutil.rmtree(_data_tmp, ignore_errors=True))
_wt = _data_tmp / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.saves_dir = tempfile.mkdtemp(prefix="ab_diff_saves_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
from app.services.game_loop_builder import build_game_loop
w = types.SimpleNamespace(game_loop=build_game_loop(_data_tmp))
for _ in range(150):
    w.game_loop.idle_tick("Open_road")
scene = w.game_loop.scene_manager.get_scene_state("Open_road", "tavern") or {}
# Phase B: добавляем npc-стейт Люсьи (activity_state/desires живут в
# engine-стейте, не в сцене — прежний дифф их не видел)
_l = next((n for n in w.game_loop._get_life_engine().get_npc_states("Open_road")
           if n.get("npc_id") == "maid_lusya"), None)
scene = dict(scene)
scene["_lusya"] = {
    "desires": _l.get("desires") if _l else None,
    "activity_state": _l.get("activity_state") if _l else None,
    "position": _l.get("position") if _l else None,
}
def canon(o):
    if isinstance(o, dict):
        return {k: ("<RT>" if k == "real_ts" else canon(v)) for k, v in sorted(o.items())}
    if isinstance(o, list):
        return [canon(x) for x in o]
    return o
print("SCENE " + json.dumps(canon(scene), sort_keys=True, default=str))
"""

def _flat(o, prefix=""):
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(_flat(v, f"{prefix}.{k}"))
    elif isinstance(o, list):
        out[prefix] = json.dumps(o, sort_keys=True, default=str)[:200]
    else:
        out[prefix] = str(o)
    return out

def main() -> int:
    scenes = []
    for i in range(2):
        r = subprocess.run([sys.executable, "-c", _RUNNER],
                           capture_output=True, text=True, cwd=".")
        line = next((l for l in r.stdout.splitlines() if l.startswith("SCENE ")), None)
        if not line:
            print(f"RUN{i+1}: ERR"); print(r.stderr[-300:]); return 2
        scenes.append(json.loads(line[6:]))
    a, b = _flat(scenes[0]), _flat(scenes[1])
    diffs = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    print(f"DIFFS: {len(diffs)}")
    for k in diffs[:30]:
        print(f"  {k}\n    A={a.get(k, '<нет>')[:100]}\n    B={b.get(k, '<нет>')[:100]}")
    if not diffs:
        print("VERDICT: MATCH")
    return 0 if not diffs else 1

if __name__ == "__main__":
    sys.exit(main())
"""
path: /project/backend/tests/sandbox/iron_river_lusya.py
Назначение: IRON RIVER Phase B / Фронт 1 — пограничная расходимость
    maid_lusya (eat-онсет, тик 148/149): per-tick трасса urgency d:food +
    activity_state + pending_tasks в двух RUN'ах. Разводит гипотезы:
    async-интерливинг (urgency идентичен, onset расходится) vs входной
    сдвиг (urgency расходится раньше границы).
Запуск: cd backend; python tests/sandbox/iron_river_lusya.py
"""
import json
import subprocess
import sys

_RUNNER = r"""
import sys, tempfile, types, os, json, shutil, atexit
from pathlib import Path
sys.path.insert(0, ".")
from app.core.config import settings
_data_src = Path(settings.data_dir)
_data_tmp = Path(tempfile.mkdtemp(prefix="lusya_data_"))
shutil.copytree(_data_src, _data_tmp, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
atexit.register(lambda: shutil.rmtree(_data_tmp, ignore_errors=True))
_wt = _data_tmp / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.saves_dir = tempfile.mkdtemp(prefix="lusya_saves_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
from app.services.game_loop_builder import build_game_loop
w = types.SimpleNamespace(game_loop=build_game_loop(_data_tmp))
# Phase B: router-stub — см. iron_river_ab (wall-clock LLM-ретраи = P2-5)
_sched = getattr(w.game_loop, "_task_scheduler", None)
_exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
if _exec is not None and hasattr(_exec, "_router"):
    _exec._router = None
LUSYA = "maid_lusya"
out = []
for t in range(1, 151):
    w.game_loop.idle_tick("Open_road")
    if t < 130:
        continue  # трассируем только зону границы
    _st = w.game_loop._get_life_engine().get_npc_states("Open_road")
    _l = next((n for n in _st if n.get("npc_id") == LUSYA), {}) or {}
    _urg = next((d.get("urgency") for d in (_l.get("desires") or [])
                 if d.get("subject_class") == "food"), None)
    _act = (_l.get("activity_state") or {}).get("activity_type")
    _pt = (w.game_loop.scene_manager.get_scene_state("Open_road", "tavern")
           or {}).get("pending_tasks") or []
    _my_tasks = sum(1 for x in _pt if x.get("owner_id") == LUSYA)
    out.append(f"{t}|urg={_urg}|act={_act}|pt={_my_tasks}")
print("LUSYA " + json.dumps(out))
"""

def main() -> int:
    seqs = []
    for i in range(2):
        r = subprocess.run([sys.executable, "-c", _RUNNER],
                           capture_output=True, text=True, cwd=".")
        line = next((l for l in r.stdout.splitlines() if l.startswith("LUSYA ")), None)
        if not line:
            print(f"RUN{i+1}: ERR"); print(r.stderr[-300:]); return 2
        seqs.append(json.loads(line[6:]))
    a, b = seqs
    print(f"LEN a={len(a)} b={len(b)}")
    first_div = None
    for idx in range(max(len(a), len(b))):
        va = a[idx] if idx < len(a) else "<нет>"
        vb = b[idx] if idx < len(b) else "<нет>"
        if va != vb:
            if first_div is None:
                first_div = idx
            print(f"  DIV@{idx}:\n    A={va}\n    B={vb}")
    if first_div is None:
        print("VERDICT: TRACE-MATCH (расходимость не воспроизвелась — повторить серию)")
    else:
        print(f"VERDICT: FIRST-DIVERGENCE @ index {first_div} (тик 130+{first_div})")
        # контекст: 3 строки до границы
        for j in range(max(0, first_div - 3), first_div):
            print(f"  CTX A={a[j]}")
            print(f"  CTX B={b[j]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
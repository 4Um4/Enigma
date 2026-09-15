"""
path: /project/backend/tests/sandbox/iron_river_eatlog.py
Назначение: Фронт 1 — eat-терминал-диагноз: ОДИН прогон (не A/B), полный
    вывод наружу: [ACTIVITY]-лог конвертера + per-tick трасса maid_lusya/
    tavern_keeper_tornin (activity_state/urgency/терминалы). Развилки:
    (а) Люсья: зависание STEP vs гейт; (б) Торнин: какой гейт режет TAKE.
Запуск: cd backend; python tests/sandbox/iron_river_eatlog.py
"""
import subprocess
import sys

_RUNNER = r"""
import sys, tempfile, types, os, json, shutil, atexit, logging
from pathlib import Path
sys.path.insert(0, ".")
from app.core.config import settings
_data_src = Path(settings.data_dir)
_data_tmp = Path(tempfile.mkdtemp(prefix="eatlog_data_"))
shutil.copytree(_data_src, _data_tmp, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
atexit.register(lambda: shutil.rmtree(_data_tmp, ignore_errors=True))
_wt = _data_tmp / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.saves_dir = tempfile.mkdtemp(prefix="eatlog_saves_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
from app.services.game_loop_builder import build_game_loop
w = types.SimpleNamespace(game_loop=build_game_loop(_data_tmp))
_sched = getattr(w.game_loop, "_task_scheduler", None)
_exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
if _exec is not None and hasattr(_exec, "_router"):
    _exec._router = None
# Свидетель: конвертер активностей на INFO (терминалы/гейты/onsert)
logging.basicConfig(level=logging.WARNING, stream=sys.stdout)
logging.getLogger("app.services.npc.activity_lifecycle_service").setLevel(logging.INFO)
LUSYA, TORNIN = "maid_lusya", "tavern_keeper_tornin"
out = []
for t in range(1, 151):
    w.game_loop.idle_tick("Open_road")
    _st = w.game_loop._get_life_engine().get_npc_states("Open_road")
    _row = {"t": t}
    for _nid in (LUSYA, TORNIN):
        _n = next((n for n in _st if n.get("npc_id") == _nid), {}) or {}
        _a = _n.get("activity_state") or {}
        _u = next((d.get("urgency") for d in (_n.get("desires") or [])
                   if d.get("subject_class") == "food"), None)
        _row[_nid] = {
            "act": _a.get("activity_type"),
            "step": _a.get("step_index"),
            "trg": str(_a.get("target_ref", ""))[:18],
            "urg": _u,
            "hun": (_n.get("needs") or {}).get("hunger"),
            # Фронт 1-добивка: MOVE-зависание второй порции — позиция и
            # транзит в трассе (окно 84-146: путь? конфликт? прибытие?)
            "pos": str(_n.get("position", ""))[-22:],
            "trv": (_nid in (_sc_trav := (w.game_loop.scene_manager
                        .get_scene_state("Open_road", "tavern") or {})
                        .get("active_traversals") or {})),
        }
    out.append(_row)
print("EATLOG " + json.dumps(out))
"""

def main() -> int:
    r = subprocess.run([sys.executable, "-c", _RUNNER],
                       capture_output=True, text=True, cwd=".")
    # КЛЮЧЕВОЕ ОТЛИЧИЕ ОТ ГЕЙТА: полный вывод RUN'а наружу
    sys.stdout.write(r.stdout)
    if r.stderr.strip():
        print("--- STDERR tail ---")
        print("\n".join(r.stderr.strip().splitlines()[-15:]))
    return 0

if __name__ == "__main__":
    sys.exit(main())
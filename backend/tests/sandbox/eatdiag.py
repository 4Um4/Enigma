"""S266-разведка: где застревает eat-активность Торнина (ACTIVITY-лог)."""
import sys, tempfile, types, os, shutil, logging
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="eatdiag_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp()
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

logging.basicConfig(level=logging.INFO)
logging.getLogger("app.services.npc.activity_lifecycle_service").setLevel(logging.INFO)
for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
           "app.services.llm.llama_cpp_provider", "app.services.memory",
           "app.services.game_loop", "app.services.npc.npc_tick_pipeline",
           "pymorphy3.opencorpora_dict.wrapper"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

from app.services.game_loop_builder import build_game_loop

w = types.SimpleNamespace(game_loop=build_game_loop(Path(_d)))
gl = w.game_loop
_s = getattr(gl, "_task_scheduler", None)
_e = getattr(_s, "_executor", None) or getattr(_s, "executor", None)
if _e is not None and hasattr(_e, "_router"):
    _e._router = None

gl.idle_tick("Open_road")

TORNIN = "tavern_keeper_tornin"
_st = gl._get_life_engine().get_npc_states("Open_road")
_t = next(n for n in _st if n.get("id") == TORNIN)
_t.setdefault("needs", {})["hunger"] = 0.9

for _i in range(50):
    gl.idle_tick("Open_road")
    _st = gl._get_life_engine().get_npc_states("Open_road")
    _t = next(n for n in _st if n.get("id") == TORNIN)
    _a = (_t.get("activity_state") or {})
    _h = float((_t.get("needs") or {}).get("hunger", 0))
    if _i % 5 == 0 or _a:
        print(f"t{_i+1}: hunger={_h:.2f} act={_a.get('activity_type')} "
              f"step={_a.get('step_index')} trg={str(_a.get('target_ref', ''))[:24]}")

print("DONE")
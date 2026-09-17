"""S266: W5-разведка — рождается ли второй TRADE-заказ после thirst."""
import sys, tempfile, types, os, shutil, logging
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="w5_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp()
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
os.environ["WORK_ENABLED"] = "1"

logging.basicConfig(level=logging.INFO)
for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
           "app.services.llm.llama_cpp_provider", "app.services.memory",
           "app.services.game_loop.task_scheduler",
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

GORAN = "merchant_goran"
TORNIN = "tavern_keeper_tornin"

_p = gl._svc.get_or_create_economic_profiles("Open_road")
_p[TORNIN].stock_for_sale["ale"] = 5.0
_st = gl._get_life_engine().get_npc_states("Open_road")
_g = next(n for n in _st if n.get("id") == GORAN)
_t = next(n for n in _st if n.get("id") == TORNIN)
_g["position"] = _t.get("position")
_g.setdefault("needs", {})["thirst"] = 0.9
print("SEEDED: goran pos=", _g.get("position"))

for _i in range(60):
    gl.idle_tick("Open_road")
    _st = gl._get_life_engine().get_npc_states("Open_road")
    _g = next(n for n in _st if n.get("id") == GORAN)
    _ale = [(d.get("subject_class"), d.get("urgency"))
            for d in (_g.get("desires") or [])
            if d.get("subject_class") == "ale"]
    if _i % 5 == 0:
        print(f"t{_i+1}: ale={_ale} pos={str(_g.get('position',''))[:25]}")

print("DONE")
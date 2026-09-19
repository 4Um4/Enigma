"""S264-финал: E7-диагноз (needs vs body_state hunger) + R5-живость."""
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="e7_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp()
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

import logging

for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
           "app.services.llm.llama_cpp_provider", "app.services.memory",
           "app.services.game_loop.task_scheduler", "app.services.game_loop",
           "app.services.npc.npc_tick_pipeline",
           "pymorphy3.opencorpora_dict.wrapper"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)
logging.getLogger("app.services.npc.activity_lifecycle_service").setLevel(logging.INFO)

from app.services.game_loop_builder import build_game_loop

w = types.SimpleNamespace(game_loop=build_game_loop(Path(_d)))
gl = w.game_loop
_sched = getattr(gl, "_task_scheduler", None)
_exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
if _exec is not None and hasattr(_exec, "_router"):
    _exec._router = None

gl.idle_tick("Open_road")  # прогрев (структура жива после первого тика)

TORNIN = "tavern_keeper_tornin"


def _me():
    st = gl._get_life_engine().get_npc_states("Open_road")
    return next(n for n in st if n.get("id") == TORNIN or n.get("npc_id") == TORNIN)


_t = _me()
_t.setdefault("needs", {})["hunger"] = 0.9
print("START: needs.hunger=0.9 injected")

for i in range(45):
    gl.idle_tick("Open_road")
    _t = _me()
    h = (_t.get("needs") or {}).get("hunger")
    bs = (_t.get("body_state") or {}).get("hunger")
    act = (_t.get("activity_state") or {}).get("activity_type")
    if i % 5 == 0 or (h is not None and float(h) < 0.5) or act:
        print(f"t{i+1}: needs={h} body={bs} act={act}")

_t = _me()
print("FINAL: needs=", (_t.get("needs") or {}).get("hunger"),
      " body=", (_t.get("body_state") or {}).get("hunger"))
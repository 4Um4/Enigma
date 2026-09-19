"""S266-финал: dump ctx.scene_state в момент терминала (прямой в файл,
без логгеров): location_id, world_objects, есть ли TARGET."""
import logging
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="ctxp_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp()
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
logging.basicConfig(level=logging.CRITICAL)

import app.services.npc.activity_lifecycle_service as als

LOG = Path("C:/DDD/Codex/VSC_Enigma/Enigma/ctx_diag.txt")

_orig_term = als._terminate

def spy_terminate(ctx, orchestrator, npc, state, *, success, reason):
    if reason == "target_vanished":
        _ss = ctx.scene_state
        with open(LOG, "a") as _f:
            _f.write(
                f"tick={ctx.tick_number} loc={_ss.get('location_id') if isinstance(_ss, dict) else type(_ss).__name__} "
                f"wo={len(_ss.get('world_objects') or {}) if isinstance(_ss, dict) else -1} "
                f"trg_in={state.target_ref in (_ss.get('world_objects') or {}) if isinstance(_ss, dict) else '?'} "
                f"ss_type={type(_ss).__name__}\n"
            )
    return _orig_term(ctx, orchestrator, npc, state, success=success, reason=reason)

als._terminate = spy_terminate

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
for _ in range(25):
    gl.idle_tick("Open_road")
print("DONE — смотри ctx_diag.txt")
"""F4-зонд: фактические пути счётчика тиков vs изоляция харнесса.
RUN-паттерн A/B (temp saves_dir) — куда реально ляжет world_tick.json?"""
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

print("DEFAULT data_dir:", settings.data_dir)
print("DEFAULT saves_dir:", settings.saves_dir)

settings.saves_dir = tempfile.mkdtemp(prefix="f4_probe_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

from app.services.game_loop_builder import build_game_loop

w = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
le = w.game_loop._get_life_engine()
print("life_engine.sessions_dir:", getattr(le, "sessions_dir", "?"))
te = getattr(le, "_temporal", None)
print("temporal._sessions_dir:", getattr(te, "_sessions_dir", "?"))
print("tick_file:", te._tick_file_path("Open_road") if te else "?")
gl_sd = getattr(w.game_loop, "_saves_dir", "?")
print("game_loop._saves_dir:", gl_sd)
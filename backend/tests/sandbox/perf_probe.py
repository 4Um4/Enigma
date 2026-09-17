"""S265: замер цены тика ДО/ПОСЛЕ фиксов (LLM-глушок полный)."""
import sys, tempfile, types, os, shutil, time, logging
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="perf_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
_wt = _d / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp(prefix="perf_saves_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
os.environ["AIDM_REPLAY_MODE"] = "off"
os.environ["ENIGMA_DISABLE_FILE_LOGS"] = "1"

logging.basicConfig(level=logging.CRITICAL)
for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
           "app.services.llm.llama_cpp_provider", "app.services.memory",
           "app.services.game_loop", "app.services.game_loop.task_scheduler",
           "app.services.npc.npc_tick_pipeline", "app.services.npc.state_applicator",
           "app.services.events.social_subscriber",
           "pymorphy3.opencorpora_dict.wrapper"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

from app.services.game_loop_builder import build_game_loop

w = types.SimpleNamespace(game_loop=build_game_loop(Path(_d)))
gl = w.game_loop
_s = getattr(gl, "_task_scheduler", None)
_e = getattr(_s, "_executor", None) or getattr(_s, "executor", None)
if _e is not None and hasattr(_e, "_router"):
    _e._router = None

gl.idle_tick("Open_road")  # прогрев

N = 200
t0 = time.monotonic()
for _ in range(N):
    gl.idle_tick("Open_road")
dt = (time.monotonic() - t0) / N * 1000
print(f"PERF: {dt:.1f} ms/tick ({N} тиков, {N*dt/1000:.1f}s)")

# Наклон
t0 = time.monotonic()
for _ in range(50):
    gl.idle_tick("Open_road")
early = (time.monotonic() - t0) / 50 * 1000
t0 = time.monotonic()
for _ in range(50):
    gl.idle_tick("Open_road")
late = (time.monotonic() - t0) / 50 * 1000
print(f"SLOPE: early={early:.1f} late={late:.1f} (+{late-early:.1f} мс)")

# Проекция 10k
print(f"10K ПРОЕКЦИЯ: ~{dt*10000/1000/60:.1f} мин (плоско) / "
      f"~{(dt + (late-early)*100)*10000/1000/60:.1f} мин (с наклоном)")
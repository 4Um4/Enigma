"""S266: прямой вызов _get_object/WorldObjectStore.get на живой сцене —
исключение? пустой subtree? возвращаемый None? Без логгеров-посредников."""
import sys, tempfile, types, os, shutil, logging, traceback
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="gop_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp()
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
logging.basicConfig(level=logging.CRITICAL)

from app.services.game_loop_builder import build_game_loop
from app.services.npc.activity_lifecycle_service import _get_object
from app.services.world.world_object_store import WorldObjectStore

w = types.SimpleNamespace(game_loop=build_game_loop(Path(_d)))
gl = w.game_loop
gl.idle_tick("Open_road")

TARGET = "wo_4eb400e3f1cfa459"

# 1) SSM-сцена напрямую
sc = gl.scene_manager.get_scene_state("Open_road", "tavern") or {}
print("SSM wo:", len(sc.get("world_objects") or {}))

# 2) WorldObjectStore.get на SSM-сцене
try:
    obj = WorldObjectStore.get(sc, TARGET)
    print("Store.get(SSM):", obj is not None,
          getattr(obj, "state", "?") if obj else "-",
          getattr(obj, "holder", "?") if obj else "-")
except Exception as ex:
    print("Store.get(SSM) EXCEPTION:", type(ex).__name__, ex)
    traceback.print_exc()

# 3) _get_object (конвертерный врапер) на SSM-сцене
try:
    obj2 = _get_object(sc, TARGET)
    print("_get_object(SSM):", obj2 is not None)
except Exception as ex:
    print("_get_object(SSM) EXCEPTION:", type(ex).__name__, ex)

# 4) А теперь — на deepcopy-снимке (как в реальном тике)
import copy
snap = copy.deepcopy(sc)
try:
    obj3 = WorldObjectStore.get(snap, TARGET)
    print("Store.get(deepcopy):", obj3 is not None)
except Exception as ex:
    print("Store.get(deepcopy) EXCEPTION:", type(ex).__name__, ex)

# 5) Ключ объекта: есть ли TARGET в subtree вообще?
sub = sc.get("world_objects") or {}
print("TARGET in SSM subtree:", TARGET in sub)
print("Все food-ids:", [k for k, v in sub.items()
      if isinstance(v, dict) and v.get("archetype") == "food_portion"][:8])
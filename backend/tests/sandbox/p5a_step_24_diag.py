# P5-A Step 2.4 — Диагностика hang в init_scene
# Без class-level patches, только изоляция точки hang
from __future__ import annotations
import sys, time, traceback
from pathlib import Path
from unittest.mock import MagicMock
import tempfile, shutil

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

print("[1] imports...")
sys.stdout.flush()
t0 = time.time()
from app.core.config import settings, BASE_DIR
from app.services.game_loop_builder import build_game_loop
print(f"[1] imports done in {time.time()-t0:.2f}s")
sys.stdout.flush()

print("[2] build_test_loop...")
sys.stdout.flush()
t1 = time.time()
temp_dir = Path(tempfile.mkdtemp(prefix="p24_diag_"))
real_data_dir = Path(settings.data_dir)
settings.saves_dir = str(temp_dir)
settings.environment = "development"
loop = build_game_loop(data_dir=real_data_dir)
print(f"[2] build_test_loop done in {time.time()-t1:.2f}s, temp_dir={temp_dir}")
sys.stdout.flush()

print("[3] scene_manager.get_scene_state('Open_road', 'tavern')...")
sys.stdout.flush()
t2 = time.time()
try:
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    print(f"[3] get_scene_state returned: type={type(scene).__name__} in {time.time()-t2:.2f}s")
    sys.stdout.flush()
except Exception as e:
    print(f"[3] EXCEPTION in {time.time()-t2:.2f}s: {type(e).__name__}: {e}")
    traceback.print_exc()

print("[4] scene_manager.initialize_scene('Open_road', 'tavern', '12:00')...")
sys.stdout.flush()
t3 = time.time()
try:
    scene2 = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
    print(f"[4] initialize_scene returned: type={type(scene2).__name__} in {time.time()-t3:.2f}s")
    sys.stdout.flush()
    if scene2 is not None:
        pos = scene2.get("npc_positions", {}) or {}
        print(f"[4] npc_positions count={len(pos)}, ids={sorted(list(pos.keys()))[:10]}")
        if "maid_lusya" in pos:
            print(f"[4] maid_lusya pos: {pos.get('maid_lusya')}")
        if "player" in pos:
            print(f"[4] player pos: {pos.get('player')}")
except Exception as e:
    print(f"[4] EXCEPTION in {time.time()-t3:.2f}s: {type(e).__name__}: {e}")
    traceback.print_exc()

print("[5] cleanup...")
shutil.rmtree(temp_dir, ignore_errors=True)
print("[DONE]")
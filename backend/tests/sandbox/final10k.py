"""S265-финал: 10 000 тиков — полный отчёт (время/наклон/канон/drift/
живость мира). Прямой production-стек, полная изоляция, LLM-free."""
import sys, tempfile, types, os, shutil, time, logging, hashlib, json
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="final10k_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
_wt = _d / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp(prefix="final10k_saves_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
os.environ["AIDM_REPLAY_MODE"] = "off"
os.environ["ENIGMA_DISABLE_FILE_LOGS"] = "1"

logging.basicConfig(level=logging.CRITICAL)
for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
           "app.services.llm.llama_cpp_provider", "app.services.memory",
           "app.services.game_loop", "app.services.game_loop.task_scheduler",
           "app.services.npc.npc_tick_pipeline",
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

N = 10000
_milestones = {}
_t0 = time.monotonic()
for _i in range(N):
    gl.idle_tick("Open_road")
    if (_i + 1) % 2000 == 0:
        _el = (time.monotonic() - _t0) / (_i + 1) * 1000
        _milestones[_i + 1] = round(_el, 1)
_dt = time.monotonic() - _t0

# ── Канон сцены ──
_scene = gl.scene_manager.get_scene_state("Open_road", "tavern") or {}
_h = hashlib.sha256(
    json.dumps(_scene, sort_keys=True, default=str).encode()
).hexdigest()[:16]

# ── Drift-статистика оркестратора ──
_orch = gl._tick_orch
_drift = getattr(_orch, "drift_stats", None)
if _drift is None:
    _drift = {k: getattr(_orch, k, "?")
              for k in ("total_comparisons", "drift_A", "drift_B",
                        "drift_C", "drift_D", "drift_E")}

# ── Живость мира (итоговые стейты) ──
_st = gl._get_life_engine().get_npc_states("Open_road")
_alive = sum(1 for n in _st if isinstance(n, dict)
             and (n.get("body_state") or {}).get("life_status") != "DEAD")
_pos = {}
for n in _st:
    if isinstance(n, dict):
        _pos[n.get("npc_id") or n.get("id")] = str(n.get("position", ""))[:30]
_final_tick = _scene.get("tick", "?")
_gt = _scene.get("game_time_seconds", 0.0)

print("=" * 60)
print(f"ФИНАЛ 10K: {N} тиков за {(_dt/60):.1f} мин "
      f"({(_dt/N)*1000:.1f} мс/тик среднее)")
print(f"МИЛИСТОУНЫ (мс/тик на отметке): {_milestones}")
print(f"НАКЛОН: старт→финиш = "
      f"{_milestones.get(2000, '?')} → {_milestones.get(10000, '?')}")
print(f"КАНОН: {_h}")
print(f"DRIFT: {_drift}")
print(f"МИР: alive={_alive}/{len(_st)}, tick={_final_tick}, "
      f"game_time={_gt/60:.0f} мин игровых")
print(f"ПОЗИЦИИ: {_pos}")
print("=" * 60)
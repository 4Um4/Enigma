"""
path: /project/backend/tests/sandbox/superbox_social_deterministic.py
Назначение: S262 / SOCIAL — ДЕТЕРМИНИРОВАННАЯ приёмочная труба (LLM-free,
    timing-free): синхронный executor (submit → result немедленно) в
    тестовой зоне; production не тронут. Цель: доказать полную причинную
    цепь СТАБИЛЬНО:
        pressure → intent → target → interaction → relationship → next-tick
    Ответ на 7/0/0: не «цепь мертва», а «исполнение timing-sensitive» —
    этот харнесс устраняет тайминг как переменную.
Зависимости: app.services.game_loop_builder, threading (sync-замена пула)
Запуск: cd backend; python tests/sandbox/superbox_social_deterministic.py
"""
import sys
import tempfile
import types
import os
import shutil
import logging
from pathlib import Path

# S262-урок: файл в backend/tests/sandbox/ → backend = parents[2]
# (parents[3] = корень проекта, где живёт СТАРАЯ копия app/ от 26.07
# без app.errors — молчаливый перехват импортов; страж ниже ловит).
BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))
assert (BACKEND_ROOT / "app" / "errors.py").exists(), (
    f"BACKEND_ROOT неверен: {BACKEND_ROOT} (нет app/errors.py — "
    "чужое дерево?)")

from app.core.config import settings

# ── Изоляция (контракт-D-уроки: data-копия + чистый world_tick) ──────────
_data_src = Path(settings.data_dir)
_data_tmp = Path(tempfile.mkdtemp(prefix="soc_det_data_"))
shutil.copytree(_data_src, _data_tmp, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
_wt = _data_tmp / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.data_dir = str(_data_tmp)
settings.saves_dir = tempfile.mkdtemp(prefix="soc_det_saves_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

logging.basicConfig(level=logging.WARNING)
for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
           "app.services.llm.llama_cpp_provider", "app.services.memory",
           "app.services.npc.npc_tick_pipeline"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)
logging.getLogger("app.services.npc.state_applicator").setLevel(logging.INFO)
logging.getLogger("app.services.events.social_subscriber").setLevel(logging.DEBUG)
logging.getLogger("app.services.game_loop.task_scheduler").setLevel(logging.INFO)

from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
ACTORS = ("merchant_goran", "tavern_keeper_tornin", "maid_lusya",
          "blacksmith_orm", "guard_borko", "thief_shadow")
TICKS = 160

SPY_SPOKE = []       # (source, target_id, intent_type)
SPY_OUTCOME = []


def _spy(event):
    _t = str(getattr(event, "type", ""))
    _pl = getattr(event, "payload", {}) or {}
    if _t == "npc_spoke":
        SPY_SPOKE.append((getattr(event, "source", "?"),
                          _pl.get("target_id"), _pl.get("intent_type")))
    elif _t == "activity_outcome":
        SPY_OUTCOME.append((getattr(event, "source", "?"), _pl.get("success")))


class _SyncPool:
    """Тестовый синхронный executor — контракт ThreadPoolExecutor.submit:
    submit(fn, *args, **kwargs) → fn(*args, **kwargs) немедленно в
    вызывающем потоке. Устраняет тайминг worker'а как переменную.
    Production-пул не тронут."""

    def __init__(self, target=None):
        self._shutdown = False  # target не нужен: fn приходит в submit

    def submit(self, fn, *args, **kwargs):
        if self._shutdown:
            raise RuntimeError("cannot schedule new futures after shutdown")
        fn(*args, **kwargs)
        return types.SimpleNamespace(result=lambda: None)  # API-совместимость

    def shutdown(self, wait=True):
        self._shutdown = True


def _main() -> int:
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    gl = world.game_loop

    # router-stub (LLM-free) + SYNC-пул (timing-free)
    _sched = getattr(gl, "_task_scheduler", None)
    _exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _exec is not None and hasattr(_exec, "_router"):
        _exec._router = None
    if _sched is not None and hasattr(_sched, "_process_tasks_async"):
        _sched._executor_pool = _SyncPool()

    _bus = gl._tick_orch._get_event_bus()
    _bus.subscribe(EventType.NPC_SPOKE, _spy)
    _bus.subscribe(EventType.ACTIVITY_OUTCOME, _spy)

    gl.idle_tick(CAMPAIGN)  # прогрев

    # Срезы отношений ДО (SSOT-ридер: player-словарь; trust-письма идут
    # source='player' → social_sub:talk)
    def _rel_snapshot():
        _rel = getattr(gl, "_rel_store", None) or getattr(
            getattr(gl, "memory_manager", None), "_relationships", None)
        try:
            return dict(_rel.get(CAMPAIGN, "player") or {})
        except Exception as _e:
            print(f"[REL] fault: {_e}")
            return {}

    rel_before = _rel_snapshot()

    for _ in range(TICKS):
        gl.idle_tick(CAMPAIGN)

    # Дренаж: sync-пул исполняет мгновенно — пауза не нужна; но даём
    # Фазе-8 последнего тика доесть события (уже съел — sync).
    rel_after = _rel_snapshot()

    ok = True
    # D1: interaction стабильна и ненулевая
    n_spoke = len(SPY_SPOKE)
    print(f"[D1] interaction: {n_spoke} реплик; пары: {SPY_SPOKE[:6]}")
    d1 = n_spoke >= 3
    print(f"[D1] {'✅' if d1 else '❌'} (>=3 реплик за {TICKS} тиков)")
    ok &= d1

    # D2: таргеты разрешены (resolver-пары, не soliloquy-мусор)
    _pairs = [(s, t) for s, t, _ in SPY_SPOKE if t and t != "soliloquy"]
    print(f"[D2] resolver-пар: {len(_pairs)}/{n_spoke}")
    d2 = len(_pairs) >= max(1, n_spoke // 2)
    print(f"[D2] {'✅' if d2 else '❌'}")
    ok &= d2

    # D3: relationship consequence. Форма стора: {target: {trust: f, fear: f}}
    # — читаем trust-скаляр вложенно; дельта = after−before.
    def _trust_of(snap, k):
        _v = snap.get(k)
        if isinstance(_v, dict):
            return round(float(_v.get("trust", 0.0)), 3)
        if isinstance(_v, (int, float)):
            return round(float(_v), 3)
        return 0.0

    _delta = {}
    for _k in set(rel_before) | set(rel_after):
        _tb, _ta = _trust_of(rel_before, _k), _trust_of(rel_after, _k)
        if _tb != _ta:
            _delta[_k] = round(_ta - _tb, 3)
    print(f"[D3] trust-дельты: {_delta}")
    d3 = bool(_delta)
    print(f"[D3] {'✅' if d3 else '❌'} (relationship consequence жива)")
    ok &= d3

    # D4: next-tick observable (EMA-насыщение спикеров — petля давления)
    _st = gl._get_life_engine().get_npc_states(CAMPAIGN)
    _ema = {n.get("npc_id"): round(float(n.get("social_input_ema", 0.0)), 3)
            for n in _st if isinstance(n, dict)}
    print(f"[D4] EMA-итог: {_ema}")
    _speakers = {s for s, t, _ in SPY_SPOKE}
    d4 = any(_ema.get(s, 0.0) > 0.0 for s in _speakers)
    print(f"[D4] {'✅' if d4 else '❌'} (спикеры {_speakers} насыщаются)")
    ok &= d4

    print("=" * 60)
    print("🎉 SOCIAL ПРИЧИННАЯ ЦЕПЬ ДОКАЗАНА (детерминированная труба): "
          "pressure → intent → target → interaction → relationship → "
          "next-tick" if ok else "❌ НЕ ЗАМКНУТО — см. D1–D4 выше")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
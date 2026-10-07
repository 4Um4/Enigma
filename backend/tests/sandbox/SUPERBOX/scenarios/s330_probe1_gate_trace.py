"""
S330-PROBE-1 (диагностика, НЕ фикс; мандат Мастера: targeted-probe).

Вопросы:
  Q1 COLLAPSE: [GATE_B1_COLLAPSE] по Торнину?        Q4 PLAN_REJECTED?
  Q2 B1.5:     [GATE_B1_5] zомби-MOVING режет?       Q5 NOT_FOUND (граф)?
  Q3 SAME_NODE?                                      Q6/Q7: зомби-traversal vs пустой реестр?
Метод: DEBUG-логи + log-only обёртка MovementEngine.process_intents
(паттерн ObservabilityTap ADR-O-361; поведение не меняется).
Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/s330_probe1_gate_trace.py
"""
import io
import logging
import os
import sys
import tempfile
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.sandbox.fixture_loader import FIXTURE_DIR, has_fixture

if has_fixture():
    settings.data_dir = str(FIXTURE_DIR)
settings.saves_dir = tempfile.mkdtemp(prefix="s330_probe1_")

os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
TORNIN = "tavern_keeper_tornin"
MAX_TICKS = 25
REPORT = BACKEND_ROOT / "reports" / "s330_probe1_gate_trace.txt"
_MARKERS = ("GATE_B1_COLLAPSE", "GATE_B1_5", "reason=SAME_NODE",
            "reason=PLAN_REJECTED", "ARBITER_GATE_2", "GATE_B1_ACCEPT",
            "reason=SUCCESS", "NOT_FOUND", "COLLAPSE: npc")

_buf = io.StringIO()


class _BufHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _buf.write(self.format(record) + "\n")


def _instrument() -> None:
    logging.getLogger().setLevel(logging.CRITICAL)
    for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
               "app.services.llm.llama_cpp_provider",
               "app.services.game_loop.task_scheduler",
               "app.services.execution.dialogue_queue",
               "app.services.memory", "app.services.npc.npc_tick_pipeline"):
        logging.getLogger(_n).setLevel(logging.CRITICAL)
    _h = _BufHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    for _n in ("app.services.spatial", "app.services.phases",
               "app.services.action", "app.services.npc"):
        _lg = logging.getLogger(_n)
        _lg.setLevel(logging.DEBUG)
        _lg.addHandler(_h)
        _lg.propagate = False


def _tap_process_intents() -> None:
    from app.services.spatial import movement_engine as _me
    _orig = _me.MovementEngine.process_intents

    def _wrapped(self, intents, *args, **kwargs):  # type: ignore[no-untyped-def]
        for _it in (intents or []):
            _aid = getattr(_it, "actor_id", getattr(_it, "npc_id", "?"))
            if _aid == TORNIN:
                _buf.write(
                    f"[PROBE][INTENT_IN] type={type(_it).__name__} "
                    f"target_node={getattr(_it, 'target_node_id', None)} "
                    f"reason={getattr(_it, 'reason', '')} "
                    f"loc={getattr(_it, 'location_id', None)}\n"
                )
        _out = _orig(self, intents, *args, **kwargs)
        _n_t = sum(1 for sc in (_out or []) if getattr(sc, "target", "") == TORNIN)
        _buf.write(f"[PROBE][ENGINE_OUT] total={len(_out or [])} tornin={_n_t}\n")
        return _out

    _me.MovementEngine.process_intents = _wrapped  # type: ignore[method-assign]


def _dump(world: types.SimpleNamespace, tick: int) -> None:
    _sc = world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}
    if tick == 1:
        _buf.write(f"[PROBE][SCENE_KEYS] {list(_sc.keys())[:20]}\n")
    _trav = (_sc.get("active_traversals") or {}).get(TORNIN)
    if _trav is not None:
        _buf.write(f"[PROBE][TRAVERSAL] tick={tick} {dict(_trav)}\n")
    _com = (_sc.get("active_commitments") or {}).get(TORNIN)
    if _com is not None:
        _buf.write(f"[PROBE][COMMITMENT] tick={tick} {dict(_com)}\n")
    _np = (_sc.get("npc_positions") or {}).get(TORNIN)
    if _np is not None:
        _buf.write(f"[PROBE][POS] tick={tick} position={_np.get('position')} "
                   f"local={_np.get('local_position')}\n")


def main() -> int:
    _instrument()
    _tap_process_intents()
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _exec is not None and hasattr(_exec, "_router"):
        _exec._router = None
    world.game_loop.idle_tick(CAMPAIGN)  # инициализация сцены
    _st = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    _states = {n.get("npc_id", n.get("id")): n for n in _st} if isinstance(_st, list) else (_st or {})
    (_states.get(TORNIN) or {}).setdefault("needs", {})["hunger"] = 0.9
    _st2 = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    _states2 = {n.get("npc_id", n.get("id")): n for n in _st2} if isinstance(_st2, list) else (_st2 or {})
    _rb = (_states2.get(TORNIN) or {}).get("needs", {}).get("hunger")
    if _rb != 0.9:
        raise RuntimeError(f"[PROBE][FAIL_LOUD] read-back hunger={_rb} != 0.9")
    for _t in range(1, MAX_TICKS + 1):
        world.game_loop.idle_tick(CAMPAIGN)
        _dump(world, _t)
    counts: dict = {}
    for _line in _buf.getvalue().splitlines():
        for _mk in _MARKERS:
            if _mk in _line:
                _k = (_mk, "tornin" if TORNIN in _line else "other")
                counts[_k] = counts.get(_k, 0) + 1
    print("=" * 64)
    print("S330-PROBE-1: маркеры (кто/сколько за 25 тиков)")
    for _k in sorted(counts):
        print(f"  {_k[0]:<20} [{_k[1]}] = {counts[_k]}")
    REPORT.write_text(_buf.getvalue(), encoding="utf-8")
    print(f"[PROBE] полный артефакт: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
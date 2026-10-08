"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/s330_probe2_planner_trace.py
Назначение: S330-PROBE-2 — изоляция GAP_TOO_WIDE (диагностика, НЕ фикс).
    P1: query.body — max_jump_distance дефолт (2.0) или реальное тело Торнина?
    P2: первый хоп A* (src/tgt локального плана) для activity:eat.
    P3: horizontal_distance кандидата = available_clearance + max_jump_distance.
Метод: log-only обёртки LocalTraversalPlanner.compile_plan +
    MovementEngine._compile_traversal_plan (паттерн ObservabilityTap ADR-O-361).
Зависимости: eat-мир production (fixture/temp-saves), без LLM.
Основные сущности: main (прогон 20 тиков + отчёт).
Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/s330_probe2_planner_trace.py
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
settings.saves_dir = tempfile.mkdtemp(prefix="s330_probe2_")

os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
TORNIN = "tavern_keeper_tornin"
MAX_TICKS = 20
REPORT = BACKEND_ROOT / "reports" / "s330_probe2_planner_trace.txt"

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
    for _n in ("app.services.spatial", "app.services.phases"):
        _lg = logging.getLogger(_n)
        _lg.setLevel(logging.DEBUG)
        _lg.addHandler(_h)
        _lg.propagate = False


def _taps() -> None:
    from app.services.spatial import local_traversal_planner as _ltp
    from app.services.spatial import movement_engine as _me

    _orig_ctp = _me.MovementEngine._compile_traversal_plan

    def _ctp(self, intent, svc, current_pos, tick, source_xy, target_xy,
             target_node_obj):  # type: ignore[no-untyped-def]
        _aid = getattr(intent, "actor_id", "?")
        if _aid == TORNIN:
            _b = intent.body_capabilities
            _buf.write(
                f"[P2][CTP-IN] tick={tick} reason={getattr(intent, 'reason', '')} "
                f"src={current_pos} tgt_node={getattr(target_node_obj, 'node_id', '?')} "
                f"src_xy={source_xy} tgt_xy={target_xy} "
                f"body(mjd={_b.max_jump_distance}, mjh={_b.max_jump_height}, "
                f"can_jump={_b.can_jump}, speed={_b.movement_speed})\n"
            )
        _res = _orig_ctp(self, intent, svc, current_pos, tick, source_xy,
                         target_xy, target_node_obj)
        if _aid == TORNIN:
            _buf.write(f"[P2][CTP-OUT] tick={tick} status={_res.status} "
                       f"reason={getattr(_res, 'reason', None)}\n")
        return _res

    _me.MovementEngine._compile_traversal_plan = _ctp  # type: ignore[method-assign]

    _orig_cp = _ltp.LocalTraversalPlanner.compile_plan

    def _cp(self, query, geometry):  # type: ignore[no-untyped-def]
        _plan = _orig_cp(self, query, geometry)
        _mjd = query.body.max_jump_distance
        _clr = getattr(_plan, "available_clearance", None)
        _hd = (round(_clr + _mjd, 3)
               if (_clr is not None and not _plan.possible) else None)
        _buf.write(
            f"[P2][PLAN] src=({query.source_pose.x:.2f},{query.source_pose.y:.2f}) "
            f"tgt=({query.target_pose.x:.2f},{query.target_pose.y:.2f}) "
            f"mjd={_mjd} possible={_plan.possible} reason={_plan.reason} "
            f"clearance={_clr} horizontal~={_hd}\n"
        )
        return _plan

    _ltp.LocalTraversalPlanner.compile_plan = _cp  # type: ignore[method-assign]


def main() -> int:
    _instrument()
    _taps()
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _exec is not None and hasattr(_exec, "_router"):
        _exec._router = None
    world.game_loop.idle_tick(CAMPAIGN)
    _st = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    _states = {n.get("npc_id", n.get("id")): n for n in _st} if isinstance(_st, list) else (_st or {})
    (_states.get(TORNIN) or {}).setdefault("needs", {})["hunger"] = 0.9
    _st2 = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    _states2 = {n.get("npc_id", n.get("id")): n for n in _st2} if isinstance(_st2, list) else (_st2 or {})
    _rb = (_states2.get(TORNIN) or {}).get("needs", {}).get("hunger")
    if _rb != 0.9:
        raise RuntimeError(f"[P2][FAIL_LOUD] read-back hunger={_rb} != 0.9")
    for _t in range(1, MAX_TICKS + 1):
        world.game_loop.idle_tick(CAMPAIGN)
    _lines = _buf.getvalue().splitlines()
    _rej = sum(1 for _l in _lines if "status=MovementPlanStatus.REJECTED" in _l and TORNIN in _l)
    _gap = sum(1 for _l in _lines if "GAP_TOO_WIDE" in _l)
    print("=" * 64)
    print(f"S330-PROBE-2: CTP-REJECTED[tornin]={_rej}  GAP_TOO_WIDE[все]={_gap}")
    for _l in _lines:
        if "[P2][CTP-IN]" in _l and "activity:" in _l:
            print(_l)
    REPORT.write_text(_buf.getvalue(), encoding="utf-8")
    print(f"[P2] полный артефакт: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
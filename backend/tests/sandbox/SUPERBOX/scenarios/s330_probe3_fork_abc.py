"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/s330_probe3_fork_abc.py
Назначение: S330-PROBE-3 — развилка A/B/C (мандат Мастера; диагностика, НЕ фикс).
    P3-1 obstacle: солвер-кандидат отказного хопа (10.5,6.5)->(6.0,8.0).
    P3-2 alternative: по-хопная локальная проходимость A*-цепи right_table->bar_area
        телом интента (существует ли capability-проходимая альтернатива?).
    P3-3 genesis порога 2.0 — git-археология оператора (вне скрипта).
Метод: log-only обёртки (ObservabilityTap ADR-O-361); ноль правок прод-кода.
Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/s330_probe3_fork_abc.py
"""
import io
import logging
import math
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
settings.saves_dir = tempfile.mkdtemp(prefix="s330_probe3_")

os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

from app.domain.traversal import Pose, TraversalMode, TraversalQuery
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
TORNIN = "tavern_keeper_tornin"
MAX_TICKS = 18
REPORT = BACKEND_ROOT / "reports" / "s330_probe3_fork_abc.txt"
_BUF = io.StringIO()


class _H(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _BUF.write(self.format(record) + "\n")


def _instrument() -> None:
    logging.getLogger().setLevel(logging.CRITICAL)
    for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
               "app.services.llm.llama_cpp_provider",
               "app.services.game_loop.task_scheduler",
               "app.services.execution.dialogue_queue",
               "app.services.memory", "app.services.npc.npc_tick_pipeline"):
        logging.getLogger(_n).setLevel(logging.CRITICAL)
    _h = _H()
    _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    for _n in ("app.services.spatial", "app.services.phases"):
        _lg = logging.getLogger(_n)
        _lg.setLevel(logging.DEBUG)
        _lg.addHandler(_h)
        _lg.propagate = False


def _taps() -> None:
    from app.services.spatial import movement_engine as _me
    from app.services.spatial import transition_topology_solver as _tts
    _PERC = _me._DEFAULT_PERCEPTION_RADIUS

    _orig_sjc = _tts.TransitionTopologySolver.solve_jump_candidates
    _seen = {"n": 0}

    def _sjc(self, src_pose, tgt_pose, obstacles, radius):  # type: ignore[no-untyped-def]
        _hit = (abs(src_pose.x - 10.5) < 0.6 and abs(src_pose.y - 6.5) < 0.6
                and abs(tgt_pose.x - 6.0) < 0.6 and abs(tgt_pose.y - 8.0) < 0.6)
        if _hit and _seen["n"] < 4:
            _seen["n"] += 1
            for _obs, _clr in (obstacles or []):
                _BUF.write(f"[P3][OBS] rect=({_obs.x:.2f},{_obs.y:.2f},"
                           f"w={_obs.w:.2f},h={_obs.h:.2f}) "
                           f"id={getattr(_obs, 'obstacle_id', getattr(_obs, 'id', '?'))} "
                           f"clearance={_clr:.3f}\n")
        _out = _orig_sjc(self, src_pose, tgt_pose, obstacles, radius)
        if _hit and _seen["n"] <= 4:
            for _c in (_out or []):
                _BUF.write(f"[P3][CAND] id={getattr(_c, 'obstacle_id', '?')} "
                           f"h_dist={_c.horizontal_distance:.3f} "
                           f"h_obst={_c.obstacle_height} "
                           f"entry=({_c.entry_pose.x:.2f},{_c.entry_pose.y:.2f}) "
                           f"exit=({_c.exit_pose.x:.2f},{_c.exit_pose.y:.2f})\n")
        return _out

    _tts.TransitionTopologySolver.solve_jump_candidates = _sjc  # type: ignore[method-assign]

    _orig_ctp = _me.MovementEngine._compile_traversal_plan

    def _ctp(self, intent, svc, current_pos, tick, source_xy, target_xy,
             target_node_obj):  # type: ignore[no-untyped-def]
        if (getattr(intent, "actor_id", "") == TORNIN
                and str(getattr(intent, "reason", "")).startswith("activity:")):
            try:
                _path = svc.find_path(source_xy, target_node_obj)
                _chain = [tuple(source_xy)] + [(n.x, n.y) for n in (_path or [])[1:]]
                _BUF.write(f"[P3][CTP] tick={tick} src={current_pos} "
                           f"tgt={getattr(target_node_obj, 'node_id', '?')} "
                           f"chain={[getattr(n, 'node_id', '?') for n in (_path or [])]}\n")
                for _a, _b in zip(_chain, _chain[1:]):
                    _geo = svc.get_local_geometry(_a, perception_radius=_PERC)
                    _pl = self._planner.compile_plan(  # type: ignore[attr-defined]
                        TraversalQuery(source_pose=Pose(_a[0], _a[1]),
                                       target_pose=Pose(_b[0], _b[1]),
                                       body=intent.body_capabilities,
                                       allowed_modes=(TraversalMode.WALK,
                                                      TraversalMode.JUMP)),
                        _geo)
                    _BUF.write(f"[P3][HOP] ({_a[0]:.2f},{_a[1]:.2f})->"
                               f"({_b[0]:.2f},{_b[1]:.2f}) d={math.dist(_a, _b):.2f} "
                               f"possible={_pl.possible} reason={_pl.reason}\n")
            except Exception as _e:  # зонд не роняет тик (ADR-O-361)
                _BUF.write(f"[P3][HOP-ERR] {type(_e).__name__}: {_e}\n")
        return _orig_ctp(self, intent, svc, current_pos, tick, source_xy,
                         target_xy, target_node_obj)

    _me.MovementEngine._compile_traversal_plan = _ctp  # type: ignore[method-assign]


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
    _s2 = {n.get("npc_id", n.get("id")): n for n in _st2} if isinstance(_st2, list) else (_st2 or {})
    if (_s2.get(TORNIN) or {}).get("needs", {}).get("hunger") != 0.9:
        raise RuntimeError("[P3][FAIL_LOUD] read-back hunger != 0.9")
    for _t in range(1, MAX_TICKS + 1):
        world.game_loop.idle_tick(CAMPAIGN)
    _lines = _BUF.getvalue().splitlines()
    _hops = [_l for _l in _lines if "[P3][HOP]" in _l]
    _fails = [_l for _l in _hops if "possible=False" in _l]
    print("=" * 64)
    print(f"S330-PROBE-3: HOP-проверок={len(_hops)}  неуспешных={len(_fails)}")
    for _l in sorted(set(_fails))[:6]:
        print("  " + _l.split("[P3][HOP] ")[-1])
    REPORT.write_text(_BUF.getvalue(), encoding="utf-8")
    print(f"[P3] артефакт: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
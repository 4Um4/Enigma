# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/probes/d_wall_probe.py
Назначение: diagnostic blocker (вердикт Мастера) «Купец идёт сквозь стены» —
    найти ОДИН воспроизводимый эпизод геометрически невалидного перемещения
    merchant_goran. Ноль правок ядра. Полный день merchant'а; траектория +
    waypoints; пост-валидация каждого сегмента через is_segment_blocked.
Зависимости: tests.gameplay.harness, SpatialFactory
Основные сущности: main
Запуск: cd backend; python -m tests.sandbox.probes.d_wall_probe
"""

import logging as _logging
from collections import defaultdict

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_NID = "merchant_goran"
_LOCS = ("tavern", "market_square", "city_gate")
_MAX_TICKS = 400


class _Col(_logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=_logging.DEBUG)
        self.lines: list = []

    def emit(self, record: _logging.LogRecord) -> None:
        try:
            m = record.getMessage()
            if _NID in m and any(k in m for k in (
                "MOVEMENT_TRACE", "PIPELINE][MOVEMENT", "SHADOW_COMPILER",
                "PROJECTION", "[SPATIAL]", "GATE_B3", "TRAV_EXEC", "RELOCATE",
                "BOUNDARY_DWELL", "S186",
            )):
                self.lines.append(m[:240])
        except Exception:  # noqa: S110
            pass


def main() -> int:
    _col = _Col()
    _svc_log = _logging.getLogger("app.services")
    _svc_log.setLevel(_logging.DEBUG)
    _svc_log.addHandler(_col)

    _traj = []    # (tick, loc, position, x, y)
    _paths = []   # (tick, loc, target, [(wx, wy), ...])
    _snapshots = {}  # loc -> scene dict (последний живой)

    with TavernGameplayHarness(location="tavern") as h:
        from app.services.spatial.spatial_factory import SpatialFactory

        for t in range(_MAX_TICKS):
            h.advance_ticks(1)
            for _loc in _LOCS:
                sc = h.game_loop.scene_manager.get_scene_state(_C, _loc)
                if sc is not None:
                    _snapshots[_loc] = sc
                _e = ((sc or {}).get("npc_positions") or {}).get(_NID)
                if _e is None:
                    continue
                _lp = _e.get("local_position") or {}
                _traj.append((t, _loc, _e.get("position", ""),
                              float(_lp.get("x", 0.0)), float(_lp.get("y", 0.0))))
                _trav = (sc or {}).get("active_traversals", {}).get(_NID)
                if isinstance(_trav, dict) and _trav.get("status") == "MOVING":
                    _wps = [tuple(w) for w in (_trav.get("path_waypoints") or [])]
                    if _wps:
                        _paths.append((t, _loc, _trav.get("target_node", ""), _wps))

        # Пост-валидация ВНУТРИ with (живые scene_state для фабрики)
        _svc_cache = {}
        _blocked = []
        by_loc = defaultdict(list)
        for rec in _traj:
            by_loc[rec[1]].append(rec)
        for _loc, recs in by_loc.items():
            svc = _svc_cache.get(_loc)
            if svc is None:
                svc = SpatialFactory.build_for_campaign(_C, _loc, _snapshots.get(_loc))
                _svc_cache[_loc] = svc
            if svc is None:
                print(f"[WALL] WARN: svc None для {_loc} — сегменты пропущены", flush=True)
                continue
            for a, b in zip(recs, recs[1:]):
                if a[2] == b[2] and abs(a[3] - b[3]) < 0.01 and abs(a[4] - b[4]) < 0.01:
                    continue
                if svc.is_segment_blocked(a[3], a[4], b[3], b[4]):
                    _blocked.append(("TRAJ", _loc, a, b))
        for (t, loc, target, wps) in _paths:
            svc = _svc_cache.get(loc)
            if svc is None:
                continue
            for wa, wb in zip(wps, wps[1:]):
                if svc.is_segment_blocked(wa[0], wa[1], wb[0], wb[1]):
                    _blocked.append(("PATH", loc, (t, target), (wa, wb)))

    print(f"[WALL] сэмплов={len(_traj)} путей={len(_paths)}", flush=True)
    if not _blocked:
        print("[WALL] Итог: blocked-сегментов НЕ найдено — эпизод не воспроизвёлся в harness", flush=True)
        return 0
    print(f"[WALL] Итог: BLOCKED-СЕГМЕНТОВ: {len(_blocked)}", flush=True)
    for kind, loc, a, b in _blocked[:15]:
        print(f"[WALL-EPISODE] {kind} loc={loc}: {a} -> {b}", flush=True)
    with open("../d_wall_trace.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(_col.lines))
    print(f"[WALL] trace {len(_col.lines)} строк -> ../d_wall_trace.txt", flush=True)
    return 1 if _blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
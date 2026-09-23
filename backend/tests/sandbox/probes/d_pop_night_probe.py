# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/probes/d_pop_night_probe.py
Назначение: population-level ночной regression (вердикт Мастера). Все 7 NPC,
    полный день (1440 тиков, канон bsf:25). Ожидания — ИЗ КОНФИГОВ (schedule
    ночного окна + activity_map), не хардкодом. Таблица вердикта:
    NPC | expected | crossings | reached | sleep_started | failure_point.
    Failure point — последний факт цепи из capture (transfer/inject/dwell/
    sleep-маркер), без гипотез.
Зависимости: tests.gameplay.harness
Основные сущности: main
Запуск: cd backend; python -m tests.sandbox.probes.d_pop_night_probe
"""

import logging as _logging

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_LOCS = ("tavern", "city_gate", "market_square")
_NPCS = ("guard_borko", "thief_shadow", "merchant_goran",
         "tavern_keeper_tornin", "maid_lusya", "blacksmith_orm", "player")
_MAX_TICKS = 1440


class _Col(_logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=_logging.DEBUG)
        self.lines: list = []

    def emit(self, record: _logging.LogRecord) -> None:
        try:
            m = record.getMessage()
            if any(k in m for k in (
                "S186_TRANSFER", "S186_INJECT", "BOUNDARY_DWELL",
                "SPATIAL_KNOWLEDGE", "SLEEP_ONSET", "going_to_sleep",
                "sleeping", "sleep_end", "UNKNOWN_ROUTE", "EXPLORATION",
                "PERSONAL_ROUTE",
            )):
                self.lines.append(m[:220])
        except Exception:  # noqa: S110
            pass


def main() -> int:
    _col = _Col()
    _svc = _logging.getLogger("app.services")
    _svc.setLevel(_logging.DEBUG)
    _svc.addHandler(_col)

    with TavernGameplayHarness(location="tavern") as h:
        # Ожидания из конфигов (не хардкод): ночная активность каждого NPC
        h.advance_ticks(1)
        _expected = {}
        for _nid in _NPCS:
            _n = h.inspect_npc(_nid) or {}
            _sched = (_n.get("routine") or {}).get("schedule", {}) or {}
            _night = []
            for _win, _act in _sched.items():
                # ночное окно: пересекается с 22:00-08:00
                if any(hh in _win for hh in ("22:00", "23:00", "00:00", "06:00", "08:00")):
                    _night.append((_win, _act))
            _am = _n.get("activity_map", {}) or {}
            _dest = None
            for _win, _act in _night:
                _e = _am.get(_act) or {}
                if _e.get("location"):
                    _dest = (_act, _e.get("location"), _e.get("position", ""))
                    break
            _expected[_nid] = _dest
            print(f"[POP] expected {_nid}: {_dest}", flush=True)

        for t in range(_MAX_TICKS):
            h.advance_ticks(1)

        # Финальная таблица
        sm = h.game_loop.scene_manager
        print("\n[POP] ===== ТАБЛИЦА =====", flush=True)
        for _nid in _NPCS:
            _where = {}
            for _loc in _LOCS:
                _e = (sm.get_scene_state(_C, _loc) or {}).get("npc_positions", {}).get(_nid)
                if _e is not None:
                    _where[_loc] = (_e.get("position", ""), bool((_e.get("body_state") or {}).get("is_sleeping")))
            # crossings по trace
            _cross = sum(1 for ln in _col.lines if f"S186_INJECT] Importing NPC={_nid}" in ln)
            _sleep = sum(1 for ln in _col.lines if _nid in ln and "SLEEP_ONSET" in ln)
            _own = [ln for ln in _col.lines if _nid in ln]
            _last_fact = _own[-1][:160] if _own else "(нет событий)"
            print(f"[POP-T] {_nid} | expected={_expected[_nid]} | crossings={_cross} "
                  f"| где={_where} | sleep_onset_events={_sleep}", flush=True)
            print(f"[POP-F] {_nid} | last_fact={_last_fact}", flush=True)
        with open("../d_pop_trace.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(_col.lines))
        print(f"[POP] trace {len(_col.lines)} строк -> ../d_pop_trace.txt", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
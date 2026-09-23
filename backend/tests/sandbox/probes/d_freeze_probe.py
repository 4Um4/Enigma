# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/probes/d_freeze_probe.py
Назначение: диагностика заморозки thief_shadow/merchant_goran (вердикт Мастера:
    не чинить вслепую). На каждый тик для двух NPC: LifeIntent (есть/нет,
    reason/target), результат Гейт① (ARBITER), B1 (accepted/rejected), B1_5
    (MOVING-блок), B2 (spatial_changes), traversal-статус, позиция. Плюс
    capture-трасса их маркеров.
Зависимости: tests.gameplay.harness
Основные сущности: main
Запуск: cd backend; python -m tests.sandbox.probes.d_freeze_probe
"""

import logging as _logging

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_TARGETS = ("thief_shadow", "merchant_goran")
_MAX_TICKS = 30


class _Col(_logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=_logging.DEBUG)
        self.lines: list = []

    def emit(self, record: _logging.LogRecord) -> None:
        try:
            m = record.getMessage()
            if any(t in m for t in _TARGETS) or any(
                k in m for k in ("GATE_B1]", "GATE_B2", "GATE_A", "S186_")
            ):
                self.lines.append(m[:200])
        except Exception:  # noqa: S110
            pass


def main() -> int:
    _col = _Col()
    _svc = _logging.getLogger("app.services")
    _svc.setLevel(_logging.DEBUG)
    _svc.addHandler(_col)

    with TavernGameplayHarness(location="tavern") as h:
        for t in range(_MAX_TICKS):
            h.advance_ticks(1)
            sc = h.game_loop.scene_manager.get_scene_state(_C, "tavern") or {}
            for _nid in _TARGETS:
                _e = (sc.get("npc_positions") or {}).get(_nid)
                _trav = (sc.get("active_traversals") or {}).get(_nid)
                _cmt = (sc.get("active_commitments") or {}).get(_nid)
                _n = h.inspect_npc(_nid) or {}
                _am = _n.get("activity_map", {})
                _sched = _n.get("schedule", {})
                if t < 3 or t % 10 == 0:
                    print(f"[DIAG_FREEZE] tick={t} {_nid}: in_scene={'Y' if _e else 'N'} "
                          f"pos={(_e or {}).get('position', '')!r} "
                          f"trav={_trav.get('status') if isinstance(_trav, dict) else None} "
                          f"cmt={_cmt.get('status') if isinstance(_cmt, dict) else None} "
                          f"routine={(_n.get('routine') or {}).get('current', '')!r} "
                          f"am_keys={list(_am.keys())[:4]} sched_keys={list(_sched.keys())[:4] if isinstance(_sched, dict) else _sched!r}",
                          flush=True)
    print(f"[DIAG_FREEZE] trace {len(_col.lines)} строк", flush=True)
    with open("../d_freeze_trace.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(_col.lines))
    for ln in _col.lines[:40]:
        print(f"[DIAG_FREEZE-T] {ln}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
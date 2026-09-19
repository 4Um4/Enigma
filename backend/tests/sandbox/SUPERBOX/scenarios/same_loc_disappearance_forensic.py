# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/same_loc_disappearance_forensic.py
Назначение: мандат SAME-LOCATION NPC DISAPPEARANCE FORENSIC. Headless-игра,
    ВСЕ NPC, every-tick trace ДВУХ независимых каналов: (1) presence в
    npc_positions (Case A/C: delete→inject), (2) visible-флаг (Case B:
    render/visibility). Gap-детектор раздельно: PRESENCE_GAP и
    VISIBILITY_GAP, с корреляцией activity-переходов и маркеров writer'а
    (SCHED_TRACE/LIFE_ENGINE visible). Без DIAG-принтов в production code.
Зависимости: tests.gameplay.harness
Основные сущности: main, _Col, _gaps

Запуск: cd backend; python -m tests.sandbox.SUPERBOX.scenarios.same_loc_disappearance_forensic > ../sdf_out.txt 2>&1; cd ..; Select-String -Path sdf_out.txt -Pattern "SDF" | Select-Object -First 40
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_LOCS = ("tavern", "city_gate", "market_square")
_MAX_TICKS = 2880
_MARK_KEYS = ("SCHED_TRACE", "INTENT_DEGRADE", "ARBITER_REJECT",
              "S186", "BOUNDARY_DWELL", "OFFSCREEN", "SPATIAL_KNOWLEDGE")

_trace: dict[str, list] = defaultdict(list)


def _log(m: str) -> None:
    print(f"[SDF] {m}", flush=True)


def main() -> int:
    class _Col(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.INFO)
            self.lines: list[tuple[int, str, str]] = []

        def emit(self, record) -> None:
            try:
                m = record.getMessage()
                for k in _MARK_KEYS:
                    if k in m:
                        self.lines.append((_tick[0], k, m[:180]))
                        break
            except Exception:  # noqa: S110
                pass

    _tick = [0]
    col = _Col()
    svc = logging.getLogger("app.services")
    svc.setLevel(logging.INFO)
    svc.addHandler(col)

    with TavernGameplayHarness(location="tavern") as h:
        sm = h.game_loop.scene_manager
        # Множество NPC, когда-либо виденных в tavern (для absent-детекции)
        ever_in_tavern: set[str] = set()

        for tick in range(1, _MAX_TICKS + 1):
            _tick[0] = tick
            h.advance_ticks(1)
            sc = sm.get_scene_state(_C, "tavern") or {}
            positions = sc.get("npc_positions")
            pos_keys = set(positions.keys()) if isinstance(positions, dict) else set()
            ever_in_tavern |= {k for k in pos_keys if k != "player"}
            # absent-строки для тех, кто был в предыдущем тике, но исчез
            for nid in ever_in_tavern:
                if nid not in pos_keys:
                    _trace[nid].append({"tick": tick, "present": False, "loc": "tavern"})
            for nid, e in positions.items():
                if nid == "player":
                    continue
                ever_in_tavern.add(nid)
                _trace[nid].append({
                    "tick": tick, "present": True, "loc": "tavern",
                    "visible": e.get("visible"), "act": e.get("activity"),
                })

        # ── Gap-анализ ────────────────────────────────────────────────
        presence_gaps: dict[str, list] = defaultdict(list)
        visibility_gaps: dict[str, list] = defaultdict(list)
        for nid, rows in _trace.items():
            rows.sort(key=lambda r: r["tick"])
            rp = rv = None
            for r in rows:
                if not r["present"]:
                    if rp is None:
                        rp = r["tick"]
                else:
                    if rp is not None:
                        presence_gaps[nid].append((rp, r["tick"] - 1))
                        rp = None
                v = r.get("visible")
                if v is False:
                    if rv is None:
                        rv = r["tick"]
                elif v is True:
                    if rv is not None:
                        visibility_gaps[nid].append((rv, r["tick"] - 1))
                        rv = None
            # открытые хвосты не считаем (конец прогона — легально)

        print("[SDF] === PRESENCE GAPS (Case A/C) ===")
        any_p = False
        for nid, gs in presence_gaps.items():
            for g0, g1 in gs:
                any_p = True
                print(f"[SDF] PRESENCE_GAP npc={nid} ticks {g0}..{g1} ({g1-g0+1})")
        if not any_p:
            print("[SDF] PRESENCE_GAP: ни одного — authoritative state стабилен")

        print("[SDF] === VISIBILITY GAPS (Case B) ===")
        for nid, gs in visibility_gaps.items():
            total = sum(g1 - g0 + 1 for g0, g1 in gs)
            print(f"[SDF] VIS npc={nid}: интервалов={len(gs)} суммарно={total} пример={gs[0] if gs else None}")
            # Корреляция с активностью первых трёх
            rows = _trace[nid]
            for g0, g1 in gs[:3]:
                acts = sorted({str(r.get("act")) for r in rows if g0 <= r["tick"] <= g1})
                print(f"[SDF]   corr {g0}..{g1} acts={acts}")

        # Маркеры вокруг первого presence-gap (writer-след)
        for nid, gs in presence_gaps.items():
            g0 = gs[0][0]
            print(f"[SDF] MARKERS вокруг {nid} @{g0}:")
            for t, k, m in col.lines:
                if abs(t - g0) <= 3:
                    print(f"[SDF]   t={t} {k}: {m[:140]}")
            break

        out = Path(__file__).resolve().parents[3] / "reports"
        out.mkdir(parents=True, exist_ok=True)
        (out / "sdf_summary.json").write_text(json.dumps({
            "presence": {k: v for k, v in presence_gaps.items()},
            "visibility": {k: list(map(list, v)) for k, v in visibility_gaps.items()},
        }, ensure_ascii=False), encoding="utf-8")
        print(f"[SDF] summary -> {out/'sdf_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
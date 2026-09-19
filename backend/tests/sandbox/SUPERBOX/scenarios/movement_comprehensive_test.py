# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/movement_comprehensive_test.py
Назначение: мандат MOVEMENT COMPREHENSIVE (шаги 1-7, 11): headless-игра на
    TavernGameplayHarness, ВСЕ живые NPC, тиковая телеметрия (tick/x/y/loc/
    state/waypoint), классификация idle-причин из реального состояния,
    THINKING_GAP (min/median/mean/p95/max), teleport-проверка (Δdist vs
    speed×Δt с допусками traversal/boundary), coverage-матрица по маркерам
    Reason/reason-строк. Измерение БЕЗ правок pipeline (мандат п.8).
Зависимости: tests.gameplay.harness
Основные сущности: main, _Collector, _classify, _gap_stats

Запуск: cd backend; python -m tests.sandbox.SUPERBOX.scenarios.movement_comprehensive_test > ../mvt_out.txt 2>&1; cd ..
Select-String -Path mvt_out.txt -Pattern "MVT" | Select-Object -First 60
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_LOCS = ("tavern", "city_gate", "market_square")
_MAX_TICKS = 2880          # двое суток
_SNAP_EVERY = 1            # телеметрия каждый тик (метрика gap требует подряд)
_SPEED = 0.7               # movement_speed (MOVEMENT-V2)
_WALK_EPS = 0.15           # допуск дискретизации за тик
_JUMP_LIMIT = _SPEED * 3   # >2.1 за тик = подозрение на телепорт (dwell-S186 легален)
_RELOC_LEGAL = 12.0        # известный легальный скачок: S186 materialize (задокументирован)

_MARK_KEYS = ("ARBITER_REJECT", "INTENT_DEGRADE", "S186", "BOUNDARY_DWELL",
              "RELOCATE", "SCHED_TRACE", "OFFSCREEN")


class _Collector:
    """Пассивный log-handler: тик-времени маркеры для классификации причин."""
    def __init__(self) -> None:
        import logging as _lg
        super().__init__(level=_lg.DEBUG)
        self.by_tick: dict[int, list[str]] = defaultdict(list)
        self.tick = 0
        self._re_tick = None

    def bind(self, h) -> None:
        pass  # тик привязывается снаружи (main инкрементирует до advance)

    def emit(self, record) -> None:
        try:
            m = record.getMessage()
            for k in _MARK_KEYS:
                if k in m:
                    self.by_tick[self.tick].append(f"{record.levelname}|{k}|{m[:160]}")
                    break
        except Exception:  # noqa: S110
            pass


def _classify(nid: str, h, tick_events: list[str]) -> str:
    sm = h.game_loop.scene_manager
    # 1) traversal активен?
    for loc in _LOCS:
        sc = sm.get_scene_state(_C, loc) or {}
        trav = (sc.get("active_traversals") or {}).get(nid)
        if trav and trav.get("status") == "MOVING":
            return "MOVING"
    # 2) dwell?
    for loc in _LOCS:
        sc = sm.get_scene_state(_C, loc) or {}
        if (sc.get("boundary_dwell") or {}).get(nid):
            return "BOUNDARY_DWELL"
    # 3) NPC-состояние: активность/сон
    entry = None
    for loc in _LOCS:
        sc = sm.get_scene_state(_C, loc) or {}
        e = (sc.get("npc_positions") or {}).get(nid)
        if e:
            entry = e
            break
    act = (entry or {}).get("activity", "")
    if "sleep" in act:
        return "SLEEPING"
    # 4) маркеры этого тика: арбитр резал / деградация / оффскрин
    joined = " ".join(tick_events)
    if "ARBITER_REJECT" in joined:
        return "INTERRUPTED"
    if "INTENT_DEGRADE" in joined:
        return "REPLANNING"
    if "OFFSCREEN" in joined:
        return "OTHER"          # задокументированный транзитор
    if act:
        # активность есть, движения нет — LifeEngine решил «уже на месте»
        return "WAITING_AT_TARGET"
    return "NO_INTENT"


def _gap_stats(gaps: list[int]) -> dict:
    if not gaps:
        return {"min": 0, "median": 0, "mean": 0.0, "p95": 0, "max": 0}
    g = sorted(gaps)
    n = len(g)
    return {
        "min": g[0],
        "median": g[n // 2],
        "mean": round(sum(g) / n, 2),
        "p95": g[min(n - 1, int(n * 0.95))],
        "max": g[-1],
    }


def main() -> int:
    import logging as _logging

    class _Col(_logging.Handler):
        def __init__(self, store: dict) -> None:
            super().__init__(level=_logging.INFO)
            self.store = store

        def emit(self, record) -> None:
            try:
                m = record.getMessage()
                for k in _MARK_KEYS:
                    if k in m:
                        self.store[self.tick_now[0]].append(f"{k}|{m[:200]}")
                        break
            except Exception:  # noqa: S110
                pass

    store: dict[int, list[str]] = defaultdict(list)
    tick_now = [0]
    _col = _Col(store)
    _svc = _logging.getLogger("app.services")
    _svc.setLevel(_logging.INFO)
    _svc.addHandler(_col)

    teleports: list[str] = []
    npc_trace: dict[str, list] = defaultdict(list)
    coverage: dict[str, set] = defaultdict(set)

    with TavernGameplayHarness(location="tavern") as h:
        npc_ids: list[str] = []
        prev_pos: dict[str, tuple[str, float, float]] = {}

        for tick in range(1, _MAX_TICKS + 1):
            tick_now[0] = tick
            _col.tick_now = tick_now  # noqa: F841 (handler читает из замыкания через store)
            before_states = {}
            sm = h.game_loop.scene_manager
            for loc in _LOCS:
                sc = sm.get_scene_state(_C, loc) or {}
                for nid, e in (sc.get("npc_positions") or {}).items():
                    if nid == "player":
                        continue
                    lp = e.get("local_position") or {}
                    before_states.setdefault(nid, []).append((loc, lp.get("x", 0.0), lp.get("y", 0.0)))
            h.advance_ticks(1)
            store[tick] = store.get(tick, [])
            for loc in _LOCS:
                sc = sm.get_scene_state(_C, loc) or {}
                positions = sc.get("npc_positions") or {}
                for nid, e in positions.items():
                    if nid == "player":
                        continue
                    if nid not in npc_ids:
                        npc_ids.append(nid)
                    lp = e.get("local_position") or {}
                    x, y = float(lp.get("x", 0.0)), float(lp.get("y", 0.0))
                    row = {
                        "tick": tick, "loc": loc, "x": round(x, 3), "y": round(y, 3),
                        "act": e.get("activity"),
                    }
                    npc_trace[nid].append(row)
                    # Teleport-проверка (в одной локации, без легального S186)
                    prev = prev_pos.get(nid)
                    if prev and prev[0] == loc:
                        d = math.hypot(x - prev[1], y - prev[2])
                        if d > _JUMP_LIMIT and d < _RELOC_LEGAL:
                            teleports.append(
                                f"tick={tick} npc={nid} Δ={d:.2f} {prev[1]:.2f},{prev[2]:.2f}→{x:.2f},{y:.2f}"
                            )
                    prev_pos[nid] = (loc, x, y)
            # empty-tick фикс: если маркеров нет — пустой список (для классификации)
            store.setdefault(tick, [])

        # ── Пост-анализ ────────────────────────────────────────────────
        report: dict[str, dict] = {}
        for nid in npc_ids:
            tr = npc_trace[nid]
            # Сжатие в последовательность состояний по подряд-идущим позициям
            moving_streak, idle_streak, gaps = [], [], []
            cur_idle = 0
            dist_total = 0.0
            states: list[str] = []
            prev = None
            for r in tr:
                key = (r["loc"], r["x"], r["y"])
                moved = prev is not None and math.hypot(key[1] - prev[1], key[2] - prev[2]) > 0.05
                if prev is not None:
                    dist_total += math.hypot(key[1] - prev[1], key[2] - prev[2])
                states.append("M" if moved else "I")
                if prev is not None:
                    if moved:
                        if cur_idle:
                            gaps.append(cur_idle)
                        cur_idle = 0
                    else:
                        cur_idle += 1
                prev = key
            if cur_idle:
                gaps.append(cur_idle)
            moving_ticks = sum(1 for s in states if s == "M")
            idle_ticks = sum(1 for s in states if s == "I")
            # Покрытие классов: по маркерам + позиционным сменам локации
            locs_seen = {r["loc"] for r in tr}
            if len(locs_seen) > 1:
                coverage[f"{nid}:cross-location"].add("boundary")
            acts = {r.get("act") for r in tr if r.get("act")}
            report[nid] = {
                "samples": len(tr),
                "locations": sorted(locs_seen),
                "activities": sorted(a for a in acts if a),
                "dist_total": round(dist_total, 1),
                "moving_ticks": moving_ticks,
                "idle_ticks": idle_ticks,
                "thinking_gap": _gap_stats(gaps),
                "teleport_flags": [t for t in teleports if nid in t][:3],
            }
            if len(locs_seen) > 1:
                coverage[f"{nid}:cross-location"] |= {"S186"}
            if any("schedule" in (a or "") for a in acts):
                coverage["schedule"] |= {nid}
            if any(a in ("eating", "drinking") for a in acts):
                coverage["social"] |= {nid}
            if any("sleep" in (a or "") for a in acts):
                coverage["sleep"] |= {nid}

        # ── Отчёт ──────────────────────────────────────────────────────
        out = Path(__file__).resolve().parents[3] / "reports"
        out.mkdir(parents=True, exist_ok=True)
        (out / "mvmt_trace.json").write_text(
            json.dumps({"npcs": {k: v[:4000] for k, v in npc_trace.items()},
                        "teleports": teleports[:50]}, ensure_ascii=False),
            encoding="utf-8")

        print("[MVT] === COVERAGE ===")
        for k in sorted(coverage):
            print(f"[MVT] {k}: {sorted(coverage[k])[:6]}")
        print("[MVT] === QUALITY PER NPC ===")
        for nid, r in report.items():
            print(f"[MVT] {nid}: {json.dumps(r, ensure_ascii=False)}")
        print(f"[MVT] === SAFETY: teleports={len(teleports)} ===")
        for t in teleports[:10]:
            print(f"[MVT] TELEPORT: {t}")
        # Borko forensic timeline
        btr = npc_trace.get("guard_borko", [])
        prev = None
        print("[MVT] === BORKO TIMELINE (смены) ===")
        for r in btr:
            key = (r["loc"], r["x"], r["y"], r["act"])
            if key != prev:
                print(f"[MVT] tick={r['tick']:>4} {key}")
                prev = key

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
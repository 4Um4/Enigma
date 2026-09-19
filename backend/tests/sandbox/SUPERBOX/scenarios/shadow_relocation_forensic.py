# -*- coding: utf-8 -*-
"""path: /project/backend/tests/sandbox/SUPERBOX/scenarios/shadow_relocation_forensic.py
Назначение: мандат «SHADOW RELOCATION FORENSIC», шаг 1. Production probe:
    полный игровой день на TavernGameplayHarness; сбор causal-трассы
    borko/shadow (SCHED_TRACE → LIFE_ENGINE → DECISION_HUB → RELOCATE →
    BOUNDARY_DWELL → S186) через logging-handler (никаких моков, тики
    только idle_tick). Выход: reports/srf_trace.txt + snapshots по тикам.
Зависимости: tests.gameplay.harness
Основные сущности: main, _Collector"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_TARGETS = ("guard_borko", "thief_shadow")
_LOCS = ("tavern", "city_gate")
_DAY = 1440

_MARKERS = (
    "SCHED_TRACE", "LIFE_ENGINE", "DECISION_HUB", "RELOCATE",
    "BOUNDARY_DWELL", "S186", "MOVEMENT_TRACE", "cross-loc relocation",
    "SPATIAL_KNOWLEDGE", "INTENT_DEGRADE", "ARBITER_REJECT",
)


class _Collector(logging.Handler):
    """Пассивный наблюдатель (CDS §11): собирает маркерные записи."""
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if any(m in msg for m in _MARKERS):
                if any(t in msg for t in _TARGETS) or "S186" in msg or "BOUNDARY_DWELL" in msg:
                    self.lines.append(f"{record.levelname}|{msg[:240]}")
        except Exception:  # noqa: S110
            pass


def _snap(h, tick: int, out: dict) -> None:
    sm = h.game_loop.scene_manager
    for loc in _LOCS:
        scene = sm.get_scene_state(_C, loc) or {}
        pos = (scene.get("npc_positions") or {})
        for nid in _TARGETS:
            e = pos.get(nid)
            if e:
                out.setdefault(nid, []).append({
                    "tick": tick, "loc": loc,
                    "pos": copy.deepcopy(e.get("position")),
                    "lp": copy.deepcopy(e.get("local_position")),
                    "act": e.get("activity"),
                })


def main() -> int:
    print("[SRF] старт", flush=True)
    col = _Collector()
    _root = logging.getLogger("app.services")
    _root.setLevel(logging.INFO)
    _root.addHandler(col)

    with TavernGameplayHarness(location="tavern") as h:
        sm = h.game_loop.scene_manager
        snaps: dict = {}
        for tick in range(1, 2 * _DAY + 1):
            h.advance_ticks(1)
            if tick % 3 == 0:
                _snap(h, tick, snaps)
            if tick % 300 == 0:
                print(f"[SRF] ...tick {tick}", flush=True)

        # Расписание обоих: что вообще говорит их конфиг
        for nid in _TARGETS:
            n = h.inspect_npc(nid) or {}
            print(f"[SRF] {nid} routine={json.dumps(n.get('routine'), default=str)[:200]}", flush=True)
            print(f"[SRF] {nid} schedule_keys={list((n.get('schedule') or {}).keys())[:8]}", flush=True)

    out_dir = Path(__file__).resolve().parents[3] / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "srf_trace.txt").write_text(
        "\n".join(col.lines), encoding="utf-8")
    (out_dir / "srf_snaps.json").write_text(
        json.dumps(snaps, ensure_ascii=False), encoding="utf-8")
    print(f"[SRF] маркеров={len(col.lines)} -> reports/srf_trace.txt", flush=True)
    print("[SRF] снимков -> reports/srf_snaps.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
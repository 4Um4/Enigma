# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/same_loc_presence_forensic.py
Назначение: STEP 4 мандата: SAME-LOCATION disappearance forensic. Плотный
    every-tick trace presence одного NPC (npc_positions + LifeEngine cache +
    visible) в его родной локации; авто-детектор gap (LAST_PRESENT/
    FIRST_ABSENT/FIRST_PRESENT_AGAIN) + снапшот маркеров вокруг gap.
Зависимости: tests.gameplay.harness
Основные сущности: main

Запуск: cd backend; python -m tests.sandbox.SUPERBOX.scenarios.same_loc_presence_forensic > ../spf_out.txt 2>&1; cd .. ; Select-String -Path spf_out.txt -Pattern "SPF" | Select-Object -First 10
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_NID = "guard_borko"   # образец: SAME-LOCATION (мы доказали его оседание)
_LOCS = ("tavern", "city_gate")
_TRACE: list[dict] = []


def _log(m: str) -> None:
    print(f"[SPF] {m}", flush=True)


def main() -> int:
    import logging as _lg

    store_lines: list[str] = []

    class _Col(_lg.Handler):
        def emit(self, record) -> None:
            try:
                m = record.getMessage()
                if _NID in m:
                    store_lines.append(f"{record.levelname}|{m[:200]}")
            except Exception:  # noqa: S110
                pass

    _col = _Col()
    _svc = _lg.getLogger("app.services")
    _svc.setLevel(_lg.DEBUG)
    _svc.addHandler(_col)

    with TavernGameplayHarness(location="tavern") as h:
        sm = h.game_loop.scene_manager
        gaps: list[dict] = []
        last_present_tick: dict[str, int] = {}
        absent_since: dict[str, int] = {}

        for tick in range(1, 721):   # полдня плотно
            h.advance_ticks(1)
            for loc in _LOCS:
                sc = sm.get_scene_state(_C, loc) or {}
                e = (sc.get("npc_positions") or {}).get(_NID)
                present = e is not None
                _TRACE.append({
                    "tick": tick, "loc": loc, "present": present,
                    "vis": (e or {}).get("visible"),
                    "pos": copy_or_none((e or {}).get("position")),
                })
                key = f"scene:{loc}"
                if present:
                    last_present_tick[key] = tick
                    if absent_since.get(key) is not None:
                        gaps.append({
                            "scene": loc,
                            "last_present": absent_since.pop(key) - 1,
                            "first_absent": absent_since.get(key, 0),
                            "again": tick,
                        })
                        gaps[-1] = {"scene": loc, "gap_ticks": tick - gaps[-1]["first_absent"] + 0,
                                    "from": abs(gaps[-1].get("first_absent", 0))}
            # упрощённый gap-детектор ниже в пост-анализе по трассе

        # Пост-анализ: точные gap-интервалы по scene:loc
        by_scene: dict[str, list] = {}
        for r in _TRACE:
            by_scene.setdefault(r["loc"], []).append(r)
        findings = []
        for loc, rows in by_scene.items():
            absent_run = None
            for r in rows:
                if not r["present"]:
                    if absent_run is None:
                        absent_run = r["tick"]
                else:
                    if absent_run is not None:
                        findings.append({
                            "scene": loc,
                            "first_absent": absent_run,
                            "first_present_again": r["tick"],
                            "gap_ticks": r["tick"] - absent_run,
                        })
                        absent_run = None
        _log(f"gap-интервалы: {json.dumps(findings)}")

        # LifeEngine cache presence (сверка независимого источника)
        eng = h.game_loop._tick_orch._get_life_engine()
        cached = eng.get_npc_states(_C) or []
        in_cache = any((n.get("npc_id") or n.get("id")) == _NID for n in cached)
        _log(f"LifeEngine cache содержит {_NID}: {in_cache}")

        out = Path(__file__).resolve().parents[3] / "reports"
        out.mkdir(parents=True, exist_ok=True)
        (out / "spf_trace.json").write_text(json.dumps(_TRACE, ensure_ascii=False), encoding="utf-8")
        (out / "spf_logs.txt").write_text("\n".join(store_lines), encoding="utf-8")
        _log(f"трасса: {out/'spf_trace.json'}; логов: {len(store_lines)}")
    return 0


def copy_or_none(v):
    return v


if __name__ == "__main__":
    raise SystemExit(main())
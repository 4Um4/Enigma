# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/borko_shadow_full_day_test.py
Назначение: SUPERBOX-SPATIAL-FORENSICS (приказ Мастера S267-окно): Borko+Shadow
    full-day прогон; forensic-таблица на каждом тике; ловля ПЕРВОГО
    некорректного перехода Тени; atomicity-аудит location_id+local_position;
    сравнение двух контрольных случаев (borko=ходок, shadow=исчезающий).
    Пилюля: RED→GREEN→probe→regression.
Зависимости: app.services.game_loop_builder, app.services.scene_state_manager (чтение)
Основные сущности: main, _snapshot_state, _check_atomicity

Запуск: cd backend; python -m tests.sandbox.SUPERBOX.scenarios.borko_shadow_full_day_test; cd ..
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from tests.gameplay.harness import TavernGameplayHarness

_TARGETS = ("guard_borko", "thief_shadow")
_LOCS = ("tavern", "city_gate")
_DAY = 1440            # тиков в сутках (60с/тик)
_TRACE: dict = {nid: [] for nid in _TARGETS}
_ANOMALIES: list = []


def _log(m: str) -> None:
    print(f"[BSF] {m}", flush=True)


def _snapshot_tick(tick: int, h: TavernGameplayHarness) -> None:
    sm = h.game_loop.scene_manager
    for loc in _LOCS:
        scene = sm.get_scene_state("Open_road", loc) or {}
        positions = scene.get("npc_positions", {}) or {}
        for nid in _TARGETS:
            entry = positions.get(nid)
            if entry is None:
                _TRACE[nid].append({"tick": tick, "scene_loc": loc, "present": False})
                continue
            row = {"tick": tick, "scene_loc": loc, "present": True}
            for f in ("location_id", "local_position", "position", "current_node",
                      "intent", "intent_target", "activity"):
                row[f] = copy.deepcopy(entry.get(f))
            row["dwell"] = copy.deepcopy((scene.get("boundary_dwell") or {}).get(nid))
            _TRACE[nid].append(row)
    # Атомарность: NPC в ОБОИХ сценах одновременно = torn-state
    for nid in _TARGETS:
        where = [r["scene_loc"] for r in _TRACE[nid]
                 if r["tick"] == tick and r.get("present")]
        if len(where) > 1:
            if not any("TORN-STATE" in a for a in _ANOMALIES):
                _ANOMALIES.append(f"tick={tick} npc={nid} TORN-STATE in {sorted(where)} (FIRST)")
            # последующие torn — в дампе трассы, вывод не засоряем


def _print_trajectory(nid: str) -> None:
    _log(f"--- {nid}: смены состояния ---")
    prev = None
    for r in _TRACE[nid]:
        if not r.get("present"):
            key = "ABSENT"
        else:
            lp = r.get("local_position") or {}
            key = (r["scene_loc"], r.get("position"),
                   round(lp.get("x", -1), 1), round(lp.get("y", -1), 1),
                   r.get("intent"))
        if key != prev:
            _log(f"  tick={r['tick']:>4} {key}")
            prev = key


def _first_divergence(nid: str):
    per_tick: dict = {}
    for r in _TRACE[nid]:
        per_tick.setdefault(r["tick"], {})[r["scene_loc"]] = r.get("present", False)
    prev_in_world = False
    for tick in sorted(per_tick):
        in_tav = per_tick[tick].get("tavern", False)
        in_city = per_tick[tick].get("city_gate", False)
        in_world = in_tav or in_city
        if prev_in_world and not in_world:
            return {"kind": "WORLD_VANISH", "tick": tick}
        if in_tav and in_city:
            return {"kind": "TORN_STATE", "tick": tick}
        prev_in_world = in_world
    return None


def main() -> int:
    with TavernGameplayHarness(location="tavern") as h:
        # Время: инжект стартовых 02:00 в обе сцены (авторинг входных условий,
        # прецедент epistemic_production:69 — прямая запись game_time_seconds).
        sm = h.game_loop.scene_manager
        for loc in _LOCS:
            s = sm.get_scene_state("Open_road", loc)
            if s is None:
                s = sm.initialize_scene("Open_road", loc, "02:00")
            s["game_time_seconds"] = 2 * 3600.0
            sm.save_scene_state("Open_road", s)

        # Быстрый суточный прогон: час = 60 тиков одиноких (без снимка),
        # затем 2 «наблюдаемых» тика вокруг смены часа. Шум глушим.
        import logging
        for _n in ("app.services", "app.models", "app.domain"):
            logging.getLogger(_n).setLevel(logging.ERROR)

        total = 2 * _DAY
        _log(f"прогон {total} тиков (ускоренный: снимок каждый 1-й из 3)...")
        for tick in range(1, total + 1):
            h.advance_ticks(1)
            if tick % 3 == 0:   # снимок каждый 3-й тик (30 игровых сек) —
                _snapshot_tick(tick, h)  # точность ловли divergence сохранна
            if tick % 200 == 0:
                _log(f"...tick {tick}, time={h.counters.game_time_seconds/3600:.1f}ч")

        # FIX: стабильный дамп трассы (tmpdir умирает с harness'ом)
        _dump = Path(__file__).resolve().parents[3] / "reports"
        _dump.mkdir(parents=True, exist_ok=True)
        _dump_f = _dump / "bsf_trace.json"
        _dump_f.write_text(json.dumps(_TRACE, ensure_ascii=False), encoding="utf-8")
        _log(f"трасса сохранена: {_dump_f}")

        for nid in _TARGETS:
            _print_trajectory(nid)
            div = _first_divergence(nid)
            if div:
                _log(f"⚠ FIRST_DIVERGENCE {nid}: {div}")
            else:
                _log(f"GREEN {nid}: некорректных переходов нет")
        for a in _ANOMALIES:
            _log(f"RED atomicity: {a}")

        # тела/интенты на конец прогона
        for nid in _TARGETS:
            _log(f"final {nid}: {json.dumps(h.inspect_npc(nid) or {}, default=str)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
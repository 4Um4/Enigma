# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/sleep_forensic.py
Назначение: FORENSIC SLEEP (вердикт Мастера, D2 OPEN): один canonical case —
    от sleep desire до первого тика выхода из сна, каждый переход с
    writer/cause. Каналы: (1) scene_state per-tick; (2) лог app.services
    (SLEEP_ONSET/sleep_end/SCHED_TRACE/NEED_TRACE/GAP9/NO_RESOLVE/
    LIFE_ENGINE ±1 тик); (3) body_state NPC из runtime — интроспекция
    harness (fail-loud, без угадывания структуры — §VIII.5).
    Ответы: был ли physiological sleep (sleep_onset_tick); чем именно
    закончился сон (writer); двигалась ли fatigue во сне.
Зависимости: tests.gameplay.harness, app.services.npc.sleep_states
Основные сущности: main
Запуск: cd backend; python -m tests.sandbox.SUPERBOX.scenarios.sleep_forensic
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from app.services.npc.sleep_states import is_sleeping
from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"


def _norm_node(s):
    # канон сравнения узлов (тот же, что в Н-4/мониторе): хвост без зоны
    return s.split(":")[-1] if s else s
_LOCS = ("tavern", "city_gate", "market_square")
_MAX_TICKS = 2880
_MARK_KEYS = ("SLEEP_ONSET", "sleep_end", "SCHED_TRACE", "NEED_TRACE",
              "GAP9", "NO_RESOLVE", "LIFE_ENGINE", "AROUSAL",
              "PERSONAL_ROUTE", "UNKNOWN_ROUTE", "S186", "BOUNDARY_DWELL",
              # DELIVERY-канал (критерий B): полный путь intent→BED
              "INTENT_SCHEDULE", "INTENT_CREATE", "INTENT_CONSUME",
              "ARBITER_REJECT", "GATE_B1", "GATE_B3", "NPC_MOVED",
              "traversal", "MOVEMENT")

_log_lines: list[tuple[int, str, str]] = []
_trace: dict[str, list] = defaultdict(list)
_body_path: list[str] = []      # найденный путь к body_state (интроспекция)
_body_capture: dict[str, list] = defaultdict(list)  # nid -> [(tick, fatigue, stress, sp, onset)]


def _find_npc_container(obj, depth=0, path="game_loop"):
    """Fail-loud интроспекция: где живут NPC-dict'ы с body_state (§VIII.5)."""
    if depth > 3 or _body_path:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, dict) and ("body_state" in v or "npc_id" in v):
                _body_path.append(path)
                return
            _find_npc_container(v, depth + 1, f"{path}[dict]")
    elif isinstance(obj, list) and obj:
        _find_npc_container(obj[0], depth + 1, f"{path}[0]")
    elif isinstance(obj, object) and not isinstance(obj, (str, int, float, bool)):
        try:
            _names = list(getattr(obj, "__dict__", {}).keys())
        except Exception:
            _names = []
        for name in _names:
            if name.startswith("_"):
                continue
            try:
                v = getattr(obj, name)
            except Exception:
                continue
            if isinstance(v, dict) and v:
                first = next(iter(v.values()))
                if isinstance(first, dict) and ("body_state" in first or "routine" in first):
                    _body_path.append(f"{path}.{name}")
                    return
            try:
                _find_npc_container(v, depth + 1, f"{path}.{name}")
            except Exception:  # noqa: S110 — интроспекция не роняет прогон
                pass


def _capture_bodies(h, tick: int) -> None:
    if not _body_path:
        return
    obj = h.game_loop
    for part in _body_path[0].split(".")[1:]:
        for token in part.replace("]", "").split("["):
            if token.isdigit():
                obj = obj[int(token)]
            elif token == "dict":
                obj = next(iter(obj.values()))
            else:
                obj = getattr(obj, token, None)
                if obj is None:
                    return
    if isinstance(obj, dict):
        items = obj.items()
    elif isinstance(obj, list):
        items = ((d.get("id", "?"), d) for d in obj if isinstance(d, dict))
    else:
        return
    for nid, d in items:
        if not isinstance(d, dict):
            continue
        b = d.get("body_state") or {}
        _body_capture[nid].append((
            tick,
            b.get("fatigue"),
            (d.get("psyche") or {}).get("stress"),
            b.get("sleep_pressure"),
            b.get("sleep_onset_tick"),
        ))


def main() -> int:
    class _Col(logging.Handler):
        def emit(self, record) -> None:
            try:
                m = record.getMessage()
                for k in _MARK_KEYS:
                    if k in m:
                        _log_lines.append((_tick[0], k, m[:200]))
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
        for tick in range(1, _MAX_TICKS + 1):
            _tick[0] = tick
            h.advance_ticks(1)
            if tick == 1:
                _find_npc_container(h.game_loop)
                print(f"[SLEEPF] body_state container: {_body_path or 'НЕ НАЙДЕН — fatigue-канал отключён'}", flush=True)
            _capture_bodies(h, tick)
            for loc in _LOCS:
                sc = sm.get_scene_state(_C, loc) or {}
                for nid, e in (sc.get("npc_positions") or {}).items():
                    if nid == "player":
                        continue
                    _trace[nid].append({
                        "tick": tick, "loc": loc,
                        "visible": e.get("visible"),
                        "act": str(e.get("activity") or ""),
                        "pos": str(e.get("position") or ""),
                    })

        # ── Выбор canonical case (вердикт Мастера): явная классификация
        # fixtures, не подбор результата. Валиден NPC, чей sleep-лейбл
        # хотя бы раз стоял на узле с bed в имени (фиксBED-условие) —
        # иначе fixture INVALID_NO_BED (диагностика, не выброс из данных).
        print("\n[SLEEPF] ===== FIXTURE CLASSIFICATION =====", flush=True)
        # Sleep-узлы из топологии (вердикт Мастера: BED доказывается конфигом,
        # не эвристикой имени). Палатки (tent) в city_gate — легальные кровати
        # (наблюдение Мастера); собираем node_id всех узлов у объектов с
        # affordances ⊇ sleep и узлов с "bed"/"tent" в editor_id.
        import json as _json
        _sleep_nodes: set[str] = set()
        # parents: [0]=scenarios [1]=SUPERBOX [2]=sandbox [3]=tests [4]=backend [5]=repo root
        _loc_dir = Path(__file__).resolve().parents[5] / "frontend" / "map_editor" / "campaigns" / _C / "locations"
        try:
            for _f in _loc_dir.glob("*.json"):
                _loc = _json.loads(_f.read_text(encoding="utf-8-sig"))
                for _obj in (_loc.get("objects") or _loc.get("affordance_objects") or []):
                    if "sleep" in (_obj.get("affordances") or []):
                        if _obj.get("node_id"):
                            _sleep_nodes.add(str(_obj["node_id"]))
                _nodes = _loc.get("nodes") or {}
                if isinstance(_nodes, dict):
                    for _nid2 in _nodes.keys():
                        if "bed" in _nid2.lower() or "tent" in _nid2.lower():
                            _sleep_nodes.add(str(_nid2))
                elif isinstance(_nodes, list):
                    for _n in _nodes:
                        _nid2 = str(_n.get("id") or _n.get("editor_id") or "") if isinstance(_n, dict) else str(_n)
                        if _nid2 and ("bed" in _nid2.lower() or "tent" in _nid2.lower()):
                            _sleep_nodes.add(_nid2)
        except OSError:
            pass
        print(f"[SLEEPF] sleep-узлы из топологии: {sorted(_sleep_nodes)[:12]}", flush=True)
        valid = []
        for nid, rows in _trace.items():
            sleep_rows = [r for r in rows if is_sleeping(r["act"])]
            if not sleep_rows:
                continue
            on_bed = [r for r in sleep_rows
                      if _norm_node(r["pos"]) in _sleep_nodes
                      or r["pos"] in _sleep_nodes]
            cls = "SLEEP_FIXTURE_VALID" if on_bed else "SLEEP_FIXTURE_INVALID_NO_BED"
            print(f"[SLEEPF] {nid}: sleep-тиков={len(sleep_rows)} "
                  f"на-BED={len(on_bed)} → {cls}", flush=True)
            if on_bed:
                valid.append(nid)
        best = None
        for nid in valid:
            rows = _trace[nid]
            run_start = None
            _sentinel = {"tick": _MAX_TICKS + 1, "act": "", "pos": "", "loc": "", "visible": True}
            for r in rows + [_sentinel]:
                slp = is_sleeping(r["act"])
                if slp and run_start is None:
                    run_start = r["tick"]
                elif not slp and run_start is not None:
                    dur = r["tick"] - run_start
                    if best is None or dur > best[3]:
                        best = (nid, run_start, r["tick"], dur)
                    run_start = None
        if not best:
            # SLEEP-SLICE fallback (v9): canonical = первый NPC с фактом
            # SLEEP_ONSET (лейбл-проекция должна была доехать — per-tick
            # trace покажет её судьбу в scene_state).
            for _nid3, rows3 in _trace.items():
                _sleep_ticks3 = sum(1 for r3 in rows3 if is_sleeping(r3["act"]))
                if _sleep_ticks3 > 0:
                    best = (_nid3, 0, _MAX_TICKS, _sleep_ticks3)
                    break
        if not best:
            # Arrival-разрыв диагностика: ГДЕ реально стояли sleep-лейблы
            # (позиционный профиль) — локализация writer'а до вердикта.
            print("\n[SLEEPF] ARRIVAL-GAP: позиционный профиль sleep-лейблов:", flush=True)
            # (позиционный профиль) — локализация writer'а до вердикта.
            print("\n[SLEEPF] ARRIVAL-GAP: позиционный профиль sleep-лейблов:", flush=True)
            for nid2, rows2 in _trace.items():
                _from_to = defaultdict(int)
                for r2 in rows2:
                    if is_sleeping(r2["act"]):
                        _from_to[f"{r2['loc']}:{_norm_node(r2['pos'])}"] += 1
                if _from_to:
                    _top = sorted(_from_to.items(), key=lambda kv: -kv[1])[:5]
                    print(f"[SLEEPF]   {nid2}: {_top}", flush=True)
            # Маркер-дамп: все LIFE_ENGINE/SCHED_TRACE/BOUNDARY-события
            # по спящим NPC — судьба intent'ов к BED (slепое пятно stdout).
            print("\n[SLEEPF] MARKER-DUMP (sleep-коррелированные события):", flush=True)
            for t2, k2, m2 in _log_lines:
                _m_low = m2.lower()
                if any(is_sleeping(a) for a in ("sleeping",)) and (
                    "sleep" in _m_low or "kitchen_bed" in _m_low
                    or "guard_bed" in _m_low or "tent_" in _m_low
                ):
                    print(f"[SLEEPF]   t={t2} {k2}: {m2[:150]}", flush=True)
            print("[SLEEPF] ВЕРДИКТ: валидных sleep-fixtures нет (все sleep-эпизоды "
                  "без BED-позиции) — см. классификацию и профиль выше", flush=True)
            return 1
        nid, t0, t1, dur = best
        rows = {r["tick"]: r for r in _trace[nid]}
        print(f"\n[SLEEPF] ===== CANONICAL CASE: {nid} =====", flush=True)
        print(f"[SLEEPF] SLEEP START tick={t0}  END tick={t1}  duration={dur} тиков", flush=True)
        bodies = _body_capture.get(nid, [])
        bmap = {b[0]: b for b in bodies}
        onset_seen = any(b[4] is not None for b in bodies)
        print(f"[SLEEPF] PHYSIOLOGICAL SLEEP (sleep_onset_tick): "
              f"{'ДА' if onset_seen else 'НЕТ — сон был только behavioral label'}", flush=True)
        # per-tick до и во время сна + 3 тика после
        _empty = {"tick": 0, "loc": "?", "visible": None, "act": "", "pos": "?"}
        for t in range(max(1, t0 - 3), min(_MAX_TICKS, t1 + 3) + 1):
            r = rows.get(t) or _empty
            b = bmap.get(t)
            marks = [f"{k}:{m[:110]}" for (tt, k, m) in _log_lines if tt == t and nid in m]
            line = (f"[SLEEPF] t={t} act={r['act']!r} pos={r['pos']} vis={r['visible']} loc={r['loc']}"
                    + (f" fatigue={b[1]} stress={b[2]} sp={b[3]} onset={b[4]}" if b else "")
                    + (f" || {' || '.join(marks)}" if marks else ""))
            print(line, flush=True)
        # маркеры вокруг END — кандидат-writer
        print(f"\n[SLEEPF] WRITER-КАНДИДАТЫ вокруг SLEEP END (t={t1}):", flush=True)
        for tt, k, m in _log_lines:
            if abs(tt - t1) <= 2:
                print(f"[SLEEPF]   t={tt} {k}: {m}", flush=True)
        # Шторм-контроль (acceptance №1, вердикт Мастера): повторные
        # SCHED_TRACE prev='' для ОДНОГО NPC в коротком окне после того,
        # как sleeping уже был в prev-семантике. Патч going_to_sleep
        # обязан был их убить: prev='going_to_sleep' идемпотентен.
        _sched = [(t, m) for (t, k, m) in _log_lines if k == "SCHED_TRACE" and "prev=''" in m]
        _by_npc: dict[str, list[int]] = defaultdict(list)
        for t, m in _sched:
            for nid2 in _trace:
                if nid2 in m:
                    _by_npc[nid2].append(t)
        print("\n[SLEEPF] ШТОРМ-КОНТРОЛЬ (prev='' SCHED_TRACE на NPC):", flush=True)
        storm_bad = False
        for nid2, ts in sorted(_by_npc.items()):
            bursts = sum(1 for a, b in zip(ts, ts[1:]) if b - a <= 3)
            print(f"[SLEEPF]   {nid2}: всего={len(ts)} плотных повторов(<=3 тиков)={bursts}", flush=True)
            if bursts > 5:
                storm_bad = True
        print(f"[SLEEPF] ШТОРМ: {'RED — патч going_to_sleep не сработал' if storm_bad else 'GREEN (идемпотентность восстановлена)'}", flush=True)

        # fatigue динамика во сне
        if bmap:
            f0 = bmap.get(t0, (None,)*5)[1]
            f1 = bmap.get(t1, (None,)*5)[1]
            print(f"[SLEEPF] FATIGUE во сне: {f0} → {f1} "
                  f"({'двигалась' if f0 is not None and f1 is not None and f0 != f1 else 'НЕ двигалась/нет данных'})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
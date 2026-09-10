# path: diagnostics/movement_audit_probe.py
# Назначение: метрики ТЗ 2.1 по scene_changes.jsonl (пустые прибытия, пинг-понг зон) для гейта 4.1.
#   v0: таксономия субстрата. v1 (эта версия): метрики по «игровым периодам» (пауза > 30 мин режет)
#   + историческая валидация против базлайна ТЗ (756/920/25.9%/x79, окно 26.08-05.09).
#   Предикат «сопровождения» — первый срез: смена значения field=activity в окне 25с (wall-ts).
#   Ярлыки на момент прибытия и таксономия печатаются — классификация passive/engaged по данным.
#   player исключён из метрик (аудит ТЗ — про поведение NPC).
# Зависимости: stdlib. Слой diagnostics: только чтение файлов (§11 — наблюдение не создаёт причинности).
# Основные сущности: parse-pass (периоды, последовательности position/activity по NPC),
#   metrics-pass (визиты зон с дедупликацией подряд-одинаковых, возвраты A→B→A, окно пустоты).

PROBE_VERSION = "v1-metrics | GAP=1800s | WINDOW=25s | метрики ТЗ 2.1"

import json
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = _ROOT / "backend" / "data" / "logs" / "scene_changes.jsonl"

GAP_SECONDS = 1800.0      # игровой период: пауза > 30 мин режет (120с в v0 резало на всплески)
WINDOW_SECONDS = 25.0     # окно ТЗ 2.1, wall-ts (исходный аудит шёл по CDS-логам с таймстампами)
AUDIT_START = "2026-08-26"  # окно исторического movement-аудита ТЗ
AUDIT_END = "2026-09-05"


def main() -> None:
    print(f"[AUDIT] version={PROBE_VERSION}")
    periods = []
    cur = None
    last_dt = None
    pos_seq = defaultdict(list)   # (period, npc) -> [(dt, zone)]
    act_seq = defaultdict(list)   # (period, npc) -> [(dt, label)]
    activity_values = Counter()
    label_at_arrival = Counter()
    bad_lines = 0
    total = 0

    with LOG_PATH.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ts = rec.get("ts")
                dt = datetime.fromisoformat(ts) if ts else None
            except Exception:
                bad_lines += 1
                continue
            if dt is None:
                bad_lines += 1
                continue
            total += 1
            if last_dt is None or (dt - last_dt).total_seconds() > GAP_SECONDS:
                if cur:
                    periods.append(cur)
                cur = {"start": dt, "end": dt, "recs": 0, "campaigns": set(),
                       "min_tick": None, "max_tick": None, "trav": 0, "act_lifecycle": 0}
            last_dt = dt
            cur["end"] = dt
            cur["recs"] += 1
            camp = rec.get("campaign_id")
            if camp:
                cur["campaigns"].add(camp)
            tick = rec.get("tick")
            if isinstance(tick, int):
                if cur["min_tick"] is None or tick < cur["min_tick"]:
                    cur["min_tick"] = tick
                if cur["max_tick"] is None or tick > cur["max_tick"]:
                    cur["max_tick"] = tick
            cause = rec.get("cause") or ""
            if cause == "traversal_complete":
                cur["trav"] += 1
            if cause.startswith("activity_lifecycle"):
                cur["act_lifecycle"] += 1
            pid = len(periods)
            fld = rec.get("field")
            npc = rec.get("target")
            if not npc or npc == "player":
                continue
            if fld == "position":
                pos_seq[(pid, npc)].append((dt, str(rec.get("value"))))
            elif fld == "activity":
                v = str(rec.get("value"))
                act_seq[(pid, npc)].append((dt, v))
                activity_values[v] += 1
    if cur:
        periods.append(cur)

    print(f"[AUDIT] total={total} bad_lines={bad_lines} periods={len(periods)} (gap>{GAP_SECONDS:.0f}s)")
    print("[AUDIT] топ-30 значений field=activity (таксономия ярлыков):")
    for k, v in activity_values.most_common(30):
        print(f"    {k!r}: {v}")

    keys_by_pid = defaultdict(list)
    for (q, npc) in pos_seq:
        keys_by_pid[q].append(npc)

    rows = []
    for pid, p in enumerate(periods):
        moves = arrivals = empty = empty_stood = empty_departed = 0
        pp = Counter()
        for npc in keys_by_pid.get(pid, []):
            seq = pos_seq[(pid, npc)]
            # визиты = дедупликация подряд-одинаковых зон
            visits = []
            for dt, zone in seq:
                if not visits or visits[-1][1] != zone:
                    visits.append((dt, zone))
            moves += max(0, len(visits) - 1)
            arrivals += max(0, len(visits) - 1)  # прибытие = визит после переезда
            # пинг-понг: возврат в зону через ровно одну другую (A→B→A)
            for i in range(2, len(visits)):
                if visits[i][1] == visits[i - 2][1] and visits[i][1] != visits[i - 1][1]:
                    pp[(npc, visits[i][1])] += 1
            acts = act_seq.get((pid, npc), [])
            act_dts = [a[0] for a in acts]
            act_vals = [a[1] for a in acts]
            for i in range(1, len(visits)):
                t0 = visits[i][0]
                deadline = t0 + timedelta(seconds=WINDOW_SECONDS)
                bi = bisect_right(act_dts, t0) - 1
                base = act_vals[bi] if bi >= 0 else None
                wi = bisect_right(act_dts, deadline)
                changed = False
                for v in act_vals[(bi + 1 if bi >= 0 else 0):wi]:
                    if v != base:
                        changed = True
                        break
                label_at_arrival[base] += 1
                departed = i + 1 < len(visits) and visits[i + 1][0] <= deadline
                if not changed:
                    empty += 1
                    if departed:
                        empty_departed += 1
                    else:
                        empty_stood += 1
        rows.append({
            "pid": pid, "day": p["start"].strftime("%Y-%m-%d"),
            "start": p["start"].strftime("%H:%M"), "end": p["end"].strftime("%H:%M"),
            "dur_s": int((p["end"] - p["start"]).total_seconds()),
            "recs": p["recs"], "campaigns": ",".join(sorted(p["campaigns"])),
            "ticks": (p["max_tick"] - p["min_tick"]) if p["min_tick"] is not None else None,
            "npcs": len(keys_by_pid.get(pid, [])),
            "moves": moves, "arrivals": arrivals, "empty": empty,
            "empty_pct": (100.0 * empty / arrivals) if arrivals else 0.0,
            "empty_stood": empty_stood, "empty_departed": empty_departed,
            "trav": p["trav"], "act_lifecycle": p["act_lifecycle"], "pp": pp,
        })

    print("[AUDIT] периоды: day start-end dur recs [camp] ticks n moves arr empty% (s/d) trav alife")
    for r in rows:
        print(f"    #{r['pid']:>3} {r['day']} {r['start']}-{r['end']} dur={r['dur_s']:>5}s "
              f"recs={r['recs']:>6} [{r['campaigns']}] ticks={r['ticks']} n={r['npcs']} "
              f"moves={r['moves']:>4} arr={r['arrivals']:>4} empty={r['empty']:>4} "
              f"({r['empty_pct']:.1f}% | s={r['empty_stood']} d={r['empty_departed']}) "
              f"trav={r['trav']:>5} alife={r['act_lifecycle']}")

    def agg(sel, title):
        mv = sum(r["moves"] for r in sel)
        ar = sum(r["arrivals"] for r in sel)
        em = sum(r["empty"] for r in sel)
        pp = Counter()
        for r in sel:
            pp.update(r["pp"])
        print(f"[AUDIT] {title}: periods={len(sel)} moves={mv} arrivals={ar} "
              f"empty={em} ({(100.0 * em / ar if ar else 0):.1f}%)")
        for (npc, zone), c in pp.most_common(10):
            print(f"    пинг-понг: {npc} @ {zone}: x{c}")

    window_or = [r for r in rows
                 if AUDIT_START <= r["day"] <= AUDIT_END and "Open_road" in r["campaigns"]]
    agg(window_or, "ОКНО АУДИТА ТЗ 26.08-05.09 (Open_road)")
    agg(sorted(window_or, key=lambda r: -r["recs"])[:6], "ТОП-6 богатых периодов окна (Open_road)")
    agg([r for r in rows if "Open_road" in r["campaigns"] and r["day"] > AUDIT_END],
        "ПОСЛЕ ОКНА (Open_road, 06.09+; 10.09 = eat-тест, отличим по alife>0)")

    print("[AUDIT] ярлык activity НА МОМЕНТ прибытия (топ-20; для классификации passive/engaged):")
    for k, v in label_at_arrival.most_common(20):
        print(f"    {k!r}: {v}")
    print("[AUDIT] ЦЕЛИ ТЗ 2.1: пустые прибытия 25.9% -> <=10%; пинг-понг x79 -> <=x5")


if __name__ == "__main__":
    main()
# path: diagnostics/cds_session_audit.py
# Назначение: воспроизведение методики movement-аудита ТЗ 2.1 по CDS-сессиям.
#   v1: ПОДТВЕРЖДЕНО — топ-6 по DECISION_HUB: 756/393/97/93/173 точно (переезд = RELOCATE).
#   v2 (эта): остаток — прибытия (гипотеза [TRAV_EXEC] COMPLETED, цель 920),
#   пинг-понг (три прочтения: сырые / визиты / возвраты A→B→A, цели 79/58/67/55/42),
#   пустые прибытия (эмпирический поиск предиката сопровождения spoke/heard, цель 238).
# Зависимости: stdlib. Слой diagnostics: только чтение файлов (§11).
# Основные сущности: parse-pass (RELOCATE/TRAV_EXEC/SPOKE/HEARD/DH/CROSS/SHADOW),
#   metric-pass (визиты, возвраты, окно 25с, варианты предиката пустоты).

PROBE_VERSION = "v2-arrivals | TRAV_EXEC | targets: 920 / 238 / x79"

import re
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = _ROOT / "backend" / "logs"
WINDOW_DAYS = ("20260826", "20260827", "20260828", "20260830", "20260831", "20260905")

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
RELOCATE_RE = re.compile(r"\[RELOCATE\] npc=(\S+) [→>] zone=(\S+) reason=(\S+)")
SPOKE_RE = re.compile(r"npc_spoke от '([^']+)'")
HEARD_RE = re.compile(r"\[NPC_DIALOGUE_SUB\] (\S+) heard (\S+)")
DH_RE = re.compile(r"\[DECISION_HUB\] (\S+): intent=Intent\.(\S+)")
TRAV_RE = re.compile(r"\[TRAV_EXEC\] ([A-Z_]+): npc=(\S+)(?:.*?node=(\S+))?")
CROSS_RE = re.compile(r"\[CROSS_LOC_MATERIALIZE\] npc=(\S+) crossing")
SHADOW_RE = re.compile(r"\[SHADOW_COMPILER\] compiled: target=(\S+) field=(\S+) cause=(\S+)")
WINDOW = timedelta(seconds=25)


def main() -> None:
    print(f"[CDS-AUDIT] version={PROBE_VERSION}")
    files = sorted(LOG_DIR.glob("cds_session_*.log"))
    sessions = {}

    for path in files:
        fname = path.name
        day = fname.split("_")[2][:8] if "_" in fname else "?"
        s = {"day": day, "dh": 0, "reloc": [], "trav": [], "trav_status": Counter(),
             "spoke": [], "heard": [], "cross": [], "shadow_pos": Counter()}
        sessions[fname] = s
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                ts_m = TS_RE.match(line)
                if not ts_m:
                    continue
                ts = datetime.fromisoformat(ts_m.group(1))
                r = RELOCATE_RE.search(line)
                if r:
                    s["reloc"].append((ts, r.group(1), r.group(2), r.group(3)))
                    continue
                t = TRAV_RE.search(line)
                if t:
                    status, npc, node = t.group(1), t.group(2), t.group(3)
                    s["trav_status"][status] += 1
                    if status == "COMPLETED" and node:
                        s["trav"].append((ts, npc, node))
                    continue
                sp = SPOKE_RE.search(line)
                if sp:
                    s["spoke"].append((ts, sp.group(1)))
                    continue
                h = HEARD_RE.search(line)
                if h:
                    s["heard"].append((ts, h.group(1), h.group(2)))
                    continue
                if DH_RE.search(line):
                    s["dh"] += 1
                    continue
                c = CROSS_RE.search(line)
                if c:
                    s["cross"].append((ts, c.group(1)))
                    continue
                sh = SHADOW_RE.search(line)
                if sh and sh.group(2) == "position":
                    s["shadow_pos"][sh.group(3).split(":")[0]] += 1

    live = [n for n in sessions
            if sessions[n]["day"] in WINDOW_DAYS and sessions[n]["dh"] > 0]
    six = sorted(live, key=lambda n: -sessions[n]["dh"])[:6]
    print(f"[CDS-AUDIT] ШЕСТЁРКА (топ-6 по DH): {six}")

    reloc = sum(len(sessions[n]["reloc"]) for n in six)
    trav = sum(len(sessions[n]["trav"]) for n in six)
    cross = sum(len(sessions[n]["cross"]) for n in six)
    spoke = sum(len(sessions[n]["spoke"]) for n in six)
    heard = sum(len(sessions[n]["heard"]) for n in six)
    print(f"[CDS-AUDIT] ШЕСТЁРКА: moves={reloc} [цель 756] arrivals(TRAV_EXEC)={trav} "
          f"[цель 920] +cross={trav + cross} spoke={spoke} heard={heard}")

    # --- пинг-понг: три прочтения из TRAV_EXEC node-последовательностей ---
    seqs = defaultdict(list)
    for n in six:
        for ts, npc, node in sessions[n]["trav"]:
            seqs[npc].append((ts, node))
    raw = Counter()
    visits = Counter()
    returns = Counter()
    for npc, items in seqs.items():
        items.sort(key=lambda x: x[0])
        for _, node in items:
            raw[(npc, node)] += 1
        zz = []
        for _, node in items:
            if not zz or zz[-1] != node:
                zz.append(node)
        for i in range(1, len(zz)):
            visits[(npc, zz[i])] += 1
        for i in range(2, len(zz)):
            if zz[i] == zz[i - 2] and zz[i] != zz[i - 1]:
                returns[(npc, zz[i])] += 1
    print("[CDS-AUDIT] пинг-понг СЫРЫЕ [цели 79/58/67/55/42]:")
    for (npc, node), c in raw.most_common(12):
        print(f"    {npc} @ {node}: x{c}")
    print("[CDS-AUDIT] пинг-понг ВИЗИТЫ (дедуп):")
    for (npc, node), c in visits.most_common(12):
        print(f"    {npc} @ {node}: x{c}")
    print("[CDS-AUDIT] пинг-понг ВОЗВРАТЫ A→B→A:")
    for (npc, node), c in returns.most_common(12):
        print(f"    {npc} @ {node}: x{c}")

    # --- пустые прибытия: эмпирический поиск предиката ---
    dlg_by_npc = defaultdict(list)
    reloc_by_npc = defaultdict(list)
    for n in six:
        for ts, sp in sessions[n]["spoke"]:
            dlg_by_npc[sp].append(ts)
        for ts, lst, _sp in sessions[n]["heard"]:
            dlg_by_npc[lst].append(ts)
        for ts, npc, _zone, _reason in sessions[n]["reloc"]:
            reloc_by_npc[npc].append(ts)
    for d in (dlg_by_npc, reloc_by_npc):
        for k in d:
            d[k].sort()

    arrivals = []
    for n in six:
        arrivals.extend(sessions[n]["trav"])
    total_arr = len(arrivals)
    variants = Counter()
    for ts, npc, _node in arrivals:
        deadline = ts + WINDOW
        dl = dlg_by_npc.get(npc, [])
        dlg_in = bisect_right(dl, deadline) > bisect_right(dl, ts)
        rl = reloc_by_npc.get(npc, [])
        reloc_in = bisect_right(rl, deadline) > bisect_right(rl, ts)
        if not dlg_in:
            variants["P1: нет spoke/heard (уехал или стоял)"] += 1
        if not dlg_in and not reloc_in:
            variants["P2: нет spoke/heard И нет reloc (чисто стоял)"] += 1
    print(f"[CDS-AUDIT] пустые прибытия, окно 25с [цель 238 из {total_arr} = 25.9%]:")
    for k, v in variants.items():
        print(f"    {k}: {v} ({100.0 * v / total_arr:.1f}%)")

    print("[CDS-AUDIT] per-file (шестёрка): trav/statuses/cross/shadow_pos:")
    for n in six:
        s = sessions[n]
        print(f"    {n}: trav={len(s['trav'])} statuses={dict(s['trav_status'])} "
              f"cross={len(s['cross'])} shadow_pos={dict(s['shadow_pos'])}")
    print("[CDS-AUDIT] ЦЕЛИ: moves=756 ✓; arrivals=920; empty=238 (25.9%); ping-pong 79/58/67/55/42")


if __name__ == "__main__":
    main()
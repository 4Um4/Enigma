# path: diagnostics/cds_session_audit.py
# Назначение: ЗАМОРОЖЕННЫЙ инструмент гейта 4.1 (метрики ТЗ 2.1 по CDS-сессиям).
#   Восстановлено точно (отпечаток): переезд = RELOCATE (756; 393/97/93/173);
#   прибытие = TRAV_EXEC COMPLETED (920); шестёрка истории = топ-6 по DH.
#   Заморожено как ближайшее восстановимое: пустота = нет (dlg ∨ prox ∨ activity_outcome)
#   в (T, T+25с] — калибровка на истории 27.1% против ТЗ 25.9%; пинг-понг = A→B→A
#   raw-returns — историческая линейка ≈x2.2 выше, гейт относительный.
#   Режимы: без аргументов — историческая верификация; --run <файлы> — гейт-прогон.
# Зависимости: stdlib. Слой diagnostics: только чтение файлов (§11).

PROBE_VERSION = "v6-frozen | --run <files> | empty=dlg+prox+actout@25s | pp=raw-returns"

import re
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = _ROOT / "backend" / "logs"
WINDOW_DAYS = ("20260826", "20260827", "20260828", "20260830", "20260831", "20260905")
WINDOW = timedelta(seconds=25)

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
RELOCATE_RE = re.compile(r"\[RELOCATE\] npc=(\S+) [→>] zone=(\S+) reason=(\S+)")
SPOKE_ANY_RE = re.compile(r"(?i)npc_spoke от '([^']+)'")
HEARD_RE = re.compile(r"\[NPC_DIALOGUE_SUB\] (\S+) heard (\S+)")
PROXIMITY_RE = re.compile(r"\[EVENT_BUS\] npc_proximity_(?:close|leave) от '([^']+)'")
PSPOKE_RE = re.compile(r"Published: PLAYER_SPOKE, target=(\S+)")
ACTOUT_RE = re.compile(r"(?i)\[EVENT_BUS\] activity_outcome от '([^']+)'")
DH_RE = re.compile(r"\[DECISION_HUB\] (\S+): intent=Intent\.(\S+)")
TRAV_RE = re.compile(r"\[TRAV_EXEC\] ([A-Z_]+): npc=(\S+)(?:.*?node=(\S+))?")

NAME_TO_ID = {
    "Торнин": "tavern_keeper_tornin",
    "Люсья": "maid_lusya",
    "Горан": "merchant_goran",
    "Борко": "guard_borko",
    "Орм": "blacksmith_orm",
    "Тень": "thief_shadow",
}


def resolve_npc(name: str) -> str:
    # npc_id содержит "_", отображаемое имя — пробелы; ключ — первое слово
    if "_" in name:
        return name
    first = name.split()[0] if name.split() else name
    return NAME_TO_ID.get(first, name)


def load_sessions(files):
    sessions = {}
    for path in files:
        fname = path.name
        day = fname.split("_")[2][:8] if "_" in fname else "?"
        s = {"day": day, "dh": 0, "reloc": [], "trav": [], "spoke": [], "heard": [],
             "prox": [], "pspoke": [], "actout": []}
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
                if t and t.group(1) == "COMPLETED" and t.group(3):
                    s["trav"].append((ts, t.group(2), t.group(3)))
                    continue
                sp = SPOKE_ANY_RE.search(line)
                if sp:
                    s["spoke"].append((ts, resolve_npc(sp.group(1))))
                    continue
                h = HEARD_RE.search(line)
                if h:
                    s["heard"].append((ts, h.group(1)))
                    continue
                px = PROXIMITY_RE.search(line)
                if px:
                    s["prox"].append((ts, resolve_npc(px.group(1))))
                    continue
                ao = ACTOUT_RE.search(line)
                if ao:
                    s["actout"].append((ts, resolve_npc(ao.group(1))))
                    continue
                ps = PSPOKE_RE.search(line)
                if ps:
                    s["pspoke"].append((ts, ps.group(1)))
                    continue
                if DH_RE.search(line):
                    s["dh"] += 1
    return sessions


def analyze(sessions, names, label):
    reloc = sum(len(sessions[n]["reloc"]) for n in names)
    trav = sum(len(sessions[n]["trav"]) for n in names)
    causes = Counter()
    ev_ts = defaultdict(list)
    ev_kind = defaultdict(list)

    def add(npc, ts, kind):
        ev_ts[npc].append(ts)
        ev_kind[npc].append(kind)

    seqs = defaultdict(list)
    for n in names:
        s = sessions[n]
        for ts, npc, zone, reason in s["reloc"]:
            causes[reason.split(":")[0]] += 1
            seqs[npc].append((ts, zone))
        for ts, sp in s["spoke"]:
            add(sp, ts, "dlg")
        for ts, tgt in s["pspoke"]:
            add(tgt, ts, "dlg")
        for ts, lst in s["heard"]:
            add(lst, ts, "dlg")
        for ts, npc in s["prox"]:
            add(npc, ts, "prox")
        for ts, npc in s["actout"]:
            add(npc, ts, "actout")
    for k in list(ev_ts):
        pairs = sorted(zip(ev_ts[k], ev_kind[k]))
        ev_ts[k] = [p[0] for p in pairs]
        ev_kind[k] = [p[1] for p in pairs]

    arrivals = [(ts, npc) for n in names for (ts, npc, _node) in sessions[n]["trav"]]

    def count_empty(kinds):
        empty = 0
        for ts, npc in arrivals:
            tl = ev_ts.get(npc, [])
            kl = ev_kind.get(npc, [])
            i = bisect_right(tl, ts)
            j = bisect_right(tl, ts + WINDOW)
            if not any(k in kinds for k in kl[i:j]):
                empty += 1
        return empty

    pp = Counter()
    for npc, items in seqs.items():
        items.sort(key=lambda x: x[0])
        zones = [z for _, z in items]
        for i in range(2, len(zones)):
            if zones[i] == zones[i - 2] and zones[i] != zones[i - 1]:
                pp[(npc, zones[i])] += 1

    spoke = sum(len(sessions[n]["spoke"]) for n in names)
    prox = sum(len(sessions[n]["prox"]) for n in names)
    actout = sum(len(sessions[n]["actout"]) for n in names)
    print(f"[GATE] {label}: moves={reloc} arrivals={trav} spoke={spoke} prox={prox} actout={actout}")
    print(f"[GATE]   причины: {dict(causes.most_common(8))}")
    if arrivals:
        e_core = count_empty({"dlg", "prox"})
        e_full = count_empty({"dlg", "prox", "actout"})
        print(f"[GATE]   пустые: dlg+prox={e_core} ({100.0 * e_core / len(arrivals):.1f}%) | "
              f"dlg+prox+actout={e_full} ({100.0 * e_full / len(arrivals):.1f}%) [цель ТЗ <=10%]")
    if pp:
        print(f"[GATE]   пинг-понг MAX={max(pp.values())} [цель ТЗ <=5]; топ-8:")
        for (npc, zone), c in pp.most_common(8):
            print(f"        {npc} @ {zone}: x{c}")
    else:
        print("[GATE]   пинг-понг: 0 возвратов")


def main() -> None:
    print(f"[GATE] version={PROBE_VERSION}")
    if "--run" in sys.argv:
        args = sys.argv[sys.argv.index("--run") + 1:]
        paths = []
        for a in args:
            p = Path(a)
            if not p.exists():
                p = LOG_DIR / a
            if not p.exists():
                print(f"[GATE] файл не найден: {a}")
                sys.exit(1)
            paths.append(p)
        sessions = load_sessions(paths)
        analyze(sessions, [p.name for p in paths], "RUN")
        return
    files = sorted(LOG_DIR.glob("cds_session_*.log"))
    sessions = load_sessions(files)
    live = [n for n in sessions
            if sessions[n]["day"] in WINDOW_DAYS and sessions[n]["dh"] > 0]
    six = sorted(live, key=lambda n: -sessions[n]["dh"])[:6]
    analyze(sessions, six, "SIX — верификация [историч. 756/920; пустота 27.1% vs ТЗ 25.9%]")
    analyze(sessions, live, "LIVE12 — исторический фон")


if __name__ == "__main__":
    main()
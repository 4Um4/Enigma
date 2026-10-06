import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.services.adr_net.adr_parser import (  # noqa: E402
    _ADR_LINE_REGEX,
    _FILES_REGEX,
    normalize_adr_id,
    parse_impact_audit,
)

FOLDER = chr(128193)
log = []
audits_dir = os.path.join(ROOT, "docs", "audits")

# --- Часть 1: гигиена — .pyc/__pycache__ из всех Files-строк (мой недосмотр 2b) ---
hyg = 0
for fp in glob.glob(os.path.join(audits_dir, "*_IMPACT.md")):
    raw = open(fp, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    fidx = next((i for i, L in enumerate(lines) if _FILES_REGEX.search(L)), None)
    if fidx is None:
        continue
    entries = [x.strip() for x in _FILES_REGEX.search(lines[fidx]).group(1).split(",") if x.strip()]
    clean = [e for e in entries if "__pycache__" not in e and not e.endswith(".pyc")]
    if len(clean) != len(entries):
        lines[fidx] = ("Files: " + ", ".join(clean)) if clean else "Files: N/A"
        open(fp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(nl.join(lines))
        hyg += 1
        log.append("HYGIENE %s: -%d garbage" % (os.path.basename(fp), len(entries) - len(clean)))
log.append("hygiene_files=%d" % hyg)

# --- Часть 2: Wave 3 — law-📁 -> empty IMPACTs ---
atlas_path = os.path.join(ROOT, "docs", "ADR (Architecture Decision Records).md")
alines = open(atlas_path, encoding="utf-8-sig").read().splitlines()
law_re = re.compile(r"\*\*(L[\d\.]+):\s*(.+?)\*\*\s*\(([^)]*)\)")
law_map = {}
i = 0
while i < len(alines):
    m = law_re.search(alines[i])
    if m:
        ids = [normalize_adr_id(x.strip()) for x in m.group(3).split(",") if x.strip()]
        paths = []
        j = i + 1
        while j < len(alines) and j <= i + 10:
            nxt = alines[j]
            if law_re.search(nxt) or nxt.startswith("## "):
                break
            if FOLDER in nxt:
                seg = nxt.split(FOLDER, 1)[1]
                for tok in seg.split(","):
                    tok = tok.strip().strip(chr(96)).strip()
                    while tok.endswith("."):
                        tok = tok[:-1]
                    if tok and "/" in tok:
                        paths.append(tok)
                break
            j += 1
        for aid in ids:
            if aid and paths:
                law_map.setdefault(aid, [])
                for p in paths:
                    if p not in law_map[aid]:
                        law_map[aid].append(p)
    i += 1

PREFIX = ("backend/", "frontend/", "scripts/", "architecture/", "docs/", "reports/", "diagnostics/", "config/")
ALIAS = [
    ("svc/", "backend/app/services/"), ("dom/", "backend/app/domain/"),
    ("mod/", "backend/app/models/"), ("app/", "backend/app/"),
    ("tests/", "backend/tests/"),
]
def resolve(p):
    cand = p if p.startswith(PREFIX) else None
    if cand is None:
        for a, full in ALIAS:
            if p.startswith(a):
                cand = full + p[len(a):]
                break
    if cand is None:
        return None
    if cand.endswith("/*"):
        base = os.path.join(ROOT, cand[:-2])
        if os.path.isdir(base):
            return sorted(os.path.relpath(g, ROOT).replace(os.sep, "/") for g in glob.glob(os.path.join(base, "*.py")))
        return None
    return [cand] if os.path.isfile(os.path.join(ROOT, cand)) else None

empty_nodes = {}
for fp in glob.glob(os.path.join(audits_dir, "*_IMPACT.md")):
    try:
        n = parse_impact_audit(fp)
    except Exception:
        continue
    if n is not None and not n.files:
        empty_nodes[n.adr_id] = fp

inserted, drops = 0, []
for aid, fp in sorted(empty_nodes.items()):
    if aid not in law_map:
        continue
    final = []
    for p in law_map[aid]:
        g = resolve(p)
        if g:
            final.extend([x for x in g if x not in final])
        else:
            drops.append("%s: %s" % (aid, p))
    if not final:
        continue
    raw = open(fp, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    hidx = next((k for k, L in enumerate(lines) if _ADR_LINE_REGEX.search(L)), None)
    if hidx is None:
        log.append("SKIP no-header: %s" % aid)
        continue
    lines.insert(hidx + 1, "Files: " + ", ".join(final))
    open(fp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(nl.join(lines))
    inserted += 1
    log.append("W3 %s: %d paths" % (aid, len(final)))
log.append("wave3_inserted=%d drop_paths=%d" % (inserted, len(drops)))
log += ["  DROP " + d for d in drops]

# --- Часть 3: финальный ценз + disposition ---
filled = empty = nohdr = 0
empty_list = []
for fp in glob.glob(os.path.join(audits_dir, "*_IMPACT.md")):
    try:
        n = parse_impact_audit(fp)
    except Exception:
        continue
    if n is None:
        nohdr += 1
    elif n.files:
        filled += 1
    else:
        empty += 1
        empty_list.append(n.adr_id)
log.append("CENSUS filled=%d empty=%d no_header=%d" % (filled, empty, nohdr))
open(os.path.join(ROOT, "reports", "d1_wave3_log.txt"), "w", encoding="utf-8").write("\n".join(log))

disp = ["D1 DISPOSITION — итог волн 1/1b/2/2b/3 (долговая ветка)",
        "filled=%d empty=%d no_header=%d (старт: filled=1, no_header=12)" % (filled, empty, nohdr),
        "== REMAINING EMPTY (%d) — нет атласного источника; пер-файловая археология тел аудитов"
        " (отдельная работа)" % len(empty_list)]
disp += ["  " + a for a in empty_list]
disp += ["== STALE ATLAS PATHS (владелец: Мастер/владелец атласа)",
         "  O-367: backend/tests/calibration_lab/test_m1_trust_intervention.py — жив только в ветке"
         " V.0.5.4.2.3 (S320 doc-drift)",
         "  O-414: scripts/consumer_gap_debts.py — удалён (S321: реестр поглощён causality_manifest);"
         ".pyc-мусор вычищен гигиеной",
         "== STRUCTURAL FINDINGS (владелец: Мастер)",
         "  F1: конвенция S311 'IMPACT-шапки без бэктиков'"
         " противоречит _ADR_LINE_REGEX/тесту — 12 аудитов были невидимы графу целиком"
         " (канонизированы батчем 2, §13.5: прав код)",
         "  F2: 📁-строки законов атласа невидимы парсеру (law-ветка ищет литерал Files)"
         " — Wave 3 переносит их в IMPACT; семантика наследования law->members сохранена",
         "== IPT GATE (честный статус)",
         "  На закрытие IPT не завершается: SyntaxError backend/app/services/npc/state_applicator.py:185"
         " — незакоммиченный WIP параллельной ветки M2/D (не мой контур, Anti-Race). Последний валидный прогон: 50/1"
         " (INV-CONSUMER-GAP-ORPHAN = их WIP). Дока-батчи верифицированы цензом парсера ADR-Net; код не менялся."]
open(os.path.join(ROOT, "reports", "d1_disposition.txt"), "w", encoding="utf-8").write("\n".join(disp))
print("\n".join(log[:2] + log[-3:]))
print("disposition -> reports/d1_disposition.txt")

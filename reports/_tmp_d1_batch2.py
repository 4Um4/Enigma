import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.services.adr_net.adr_parser import parse_master_index, parse_impact_audit, _ADR_LINE_REGEX, _FILES_REGEX

atlas = {n.adr_id: n for n in parse_master_index(os.path.join(ROOT, "docs", "ADR (Architecture Decision Records).md"))}

# (файл, ID, TYPE-fallback, Title-fallback) — источники: H1-строки файлов (прочитаны), TYPE/Title при наличии берутся из атласа
ENTRIES = [
    ("ADR-NET-CLI-QUIET_FIX_IMPACT.md", "ADR-NET-CLI-QUIET", "FIX", "IMPACT"),
    ("ADR-NET-PARSER-V2_IMPACT.md", "ADR-NET-PARSER-V2", "FIX", "IMPACT"),
    ("ADR-O-383_IMPACT.md", "ADR-O-383", "ONTO", "Embodied Constraint - Chronic Body Axes -> Feasibility (V1)"),
    ("ADR-O-393_IMPACT.md", "ADR-O-393", "ONTO", "Determinism Foundation - IRON RIVER"),
    ("ADR-O-396_IMPACT.md", "ADR-O-396", "ONTO", "SOCIAL Vertical Slice"),
    ("ADR-O-413_IMPACT.md", "ADR-O-413", "ONTO", "Causal Slice 4 - Affection (R8)"),
    ("ADR-O-414_IMPACT.md", "ADR-O-414", "STANDARD", "INV-CONSUMER-GAP / Causal Anatomy (Stage 1)"),
    ("ADR-O-415_IMPACT.md", "ADR-O-415", "STANDARD", "RE-01 M1b.3.7 grep-guard"),
    ("ADR-O-416_IMPACT.md", "ADR-O-416", "STANDARD", "RE-01 GC-11 L3-gate"),
    ("ADR-O-417_IMPACT.md", "ADR-O-417", "STANDARD", "IMPACT"),
    ("ADR-O-R2_IMPACT.md", "ADR-O-R2", "STANDARD", "Feasibility Enforcement"),
    ("ADR-RE-M1B3_6_IMPACT.md", "ADR-RE-M1b.3.6", "STANDARD", "RE-01 M1b.3.6 S128"),
]
log = []
for fname, aid, fb_type, fb_title in ENTRIES:
    fp = os.path.join(ROOT, "docs", "audits", fname)
    raw = open(fp, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    if any(_ADR_LINE_REGEX.search(L) for L in lines[:6]):
        log.append("SKIP already-canonical: " + fname)
        continue
    an = atlas.get(aid.replace("ADR-", "ADR-"))
    a_type = an.adr_type if (an and an.adr_type and an.adr_type != "LAW") else fb_type
    a_title = an.title if (an and an.title and an.title != "IMPACT") else fb_title
    src = "atlas" if an and an.adr_type and an.adr_type != "LAW" else "fallback"
    canon = "`%s` [%s] **%s**" % (aid, a_type, a_title)
    # O-417: строка 1 уже "ADR-O-417 [STANDARD] **IMPACT**" без бэктиков — правка на месте
    if lines and lines[0].startswith(aid + " ["):
        lines[0] = canon
        action = "INPLACE"
    else:
        lines.insert(1, canon)
        action = "INSERT"
    open(fp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(nl.join(lines))
    log.append("%s %s: %s (type-src=%s)" % (action, aid, canon, src))

# === Волна 1b: rerun fill — добор atlas-Files у ставших видимыми ===
import glob
amap = {}
for n in atlas.values():
    if n.files:
        amap.setdefault(n.adr_id, []).extend(n.files)
for k in list(amap):
    seen = set(); amap[k] = [x for x in amap[k] if not (x in seen or seen.add(x))]
PREFIX = ("backend/", "frontend/", "scripts/", "architecture/", "docs/", "reports/")
ALIAS = [("svc/", "backend/app/services/"), ("dom/", "backend/app/domain/"), ("mod/", "backend/app/models/"), ("app/", "backend/app/")]
def resolve_one(p):
    p = p.strip().strip(chr(96))
    while p.endswith("."):
        p = p[:-1]
    cand = p if p.startswith(PREFIX) else None
    if cand is None:
        for a, full in ALIAS:
            if p.startswith(a):
                cand = full + p[len(a):]
                break
    if cand is None:
        return None, "unresolved-prefix:" + p
    if cand.endswith("/*"):
        base = os.path.join(ROOT, cand[:-2])
        if os.path.isdir(base):
            return sorted(os.path.relpath(g, ROOT).replace(os.sep, "/") for g in glob.glob(os.path.join(base, "*.py"))), None
        return [], "wildcard-dir-missing:" + cand
    if os.path.isfile(os.path.join(ROOT, cand)):
        return [cand], None
    return [], "missing-on-disk:" + cand
drops = []
for fp in sorted(glob.glob(os.path.join(ROOT, "docs", "audits", "*_IMPACT.md"))):
    try:
        node = parse_impact_audit(fp)
    except Exception:
        continue
    if node is None or node.files or node.adr_id not in amap:
        continue
    final = []
    for p in amap[node.adr_id]:
        got, why = resolve_one(p)
        if got:
            final.extend([g for g in got if g not in final])
        elif why:
            drops.append(node.adr_id + ": " + why)
    if not final:
        continue
    raw = open(fp, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    hidx = next(i for i, L in enumerate(lines) if _ADR_LINE_REGEX.search(L))
    lines.insert(hidx + 1, "Files: " + ", ".join(final))
    open(fp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(nl.join(lines))
    log.append("1b-INSERT %s: %d paths" % (node.adr_id, len(final)))
if drops:
    log.append("== 1b DROPS"); log += ["  " + d for d in drops]
open(os.path.join(ROOT, "reports", "d1_batch2_log.txt"), "w", encoding="utf-8").write("\n".join(log))
print("\n".join(log))

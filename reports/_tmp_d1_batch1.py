import glob, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.services.adr_net.adr_parser import parse_master_index, parse_impact_audit, _ADR_LINE_REGEX, _FILES_REGEX

atlas_nodes = parse_master_index(os.path.join(ROOT, "docs", "ADR (Architecture Decision Records).md"))
amap = {}
for n in atlas_nodes:
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
            got = sorted(os.path.relpath(g, ROOT).replace(os.sep, "/") for g in glob.glob(os.path.join(base, "*.py")))
            return got, None
        return [], "wildcard-dir-missing:" + cand
    if os.path.isfile(os.path.join(ROOT, cand)):
        return [cand], None
    return [], "missing-on-disk:" + cand

log, inserted, replaced, skipped, all_drops = [], 0, 0, 0, []
audits_dir = os.path.join(ROOT, "docs", "audits")
for fp in sorted(glob.glob(os.path.join(audits_dir, "*_IMPACT.md"))):
    name = os.path.basename(fp)
    try:
        node = parse_impact_audit(fp)
    except Exception:
        continue
    if node is None or node.files:
        continue
    aid = node.adr_id
    if aid not in amap:
        continue
    final, drops = [], []
    for p in amap[aid]:
        got, why = resolve_one(p)
        if got:
            for g in got:
                if g not in final:
                    final.append(g)
        elif why:
            drops.append(why)
    if drops:
        all_drops.append("%s: %s" % (aid, "; ".join(drops)))
    if not final:
        log.append("SKIP no-valid-paths: %s" % aid)
        skipped += 1
        continue
    raw = open(fp, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    newline = "Files: " + ", ".join(final)
    fidx = next((i for i, L in enumerate(lines) if _FILES_REGEX.search(L)), None)
    if fidx is not None:
        lines[fidx] = newline
        action = "REPLACE"
        replaced += 1
    else:
        hidx = next((i for i, L in enumerate(lines) if _ADR_LINE_REGEX.search(L)), None)
        if hidx is None:
            log.append("SKIP no-header-line: %s" % aid)
            skipped += 1
            continue
        lines.insert(hidx + 1, newline)
        action = "INSERT"
        inserted += 1
    open(fp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(nl.join(lines))
    log.append("%s %s: %d paths" % (action, aid, len(final)))

log.insert(0, "inserted=%d replaced=%d skipped=%d drop-groups=%d" % (inserted, replaced, skipped, len(all_drops)))
if all_drops:
    log.append("== DROPS")
    log += ["  " + d for d in all_drops]
open(os.path.join(ROOT, "reports", "d1_batch1_log.txt"), "w", encoding="utf-8").write("\n".join(log))
print(log[0])
print("\n".join(log[1:10]))

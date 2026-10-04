import glob, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.services.adr_net.adr_parser import parse_impact_audit, _FILES_REGEX

log = []
def bounded_search(pattern):
    hits = []
    for sub in ("backend", "frontend", "scripts", "docs", "architecture", "config"):
        base = os.path.join(ROOT, sub)
        if os.path.isdir(base):
            for p in glob.glob(os.path.join(base, "**", pattern), recursive=True):
                hits.append(os.path.relpath(p, ROOT).replace(os.sep, "/"))
    return sorted(set(hits))

add = {}
ir = sorted(os.path.relpath(p, ROOT).replace(os.sep, "/")
            for p in glob.glob(os.path.join(ROOT, "backend", "tests", "sandbox", "iron_river_*.py")))
if ir: add["ADR-O-393"] = ir; log.append("O-393 mid-glob resolved: %d files" % len(ir))
else: log.append("O-393: NONE (disposition)")
cg = bounded_search("consumer_gap_debts*")
if cg: add["ADR-O-414"] = cg; log.append("O-414 found: %s" % ", ".join(cg))
else: log.append("O-414 consumer_gap_debts*: NOT FOUND (S321: реестр поглощён манифестом — disposition)")
gy = bounded_search("gc11_*.yaml")
if gy: add["ADR-O-416"] = gy; log.append("O-416 found: %s" % ", ".join(gy))
else: log.append("O-416 gc11_*.yaml: NOT FOUND (disposition)")

if add:
    id2fp = {}
    for fp in glob.glob(os.path.join(ROOT, "docs", "audits", "*_IMPACT.md")):
        try: n = parse_impact_audit(fp)
        except Exception: continue
        if n is not None: id2fp[n.adr_id] = fp
    for aid, paths in sorted(add.items()):
        fp = id2fp.get(aid)
        if not fp: log.append("SKIP no-impact-file: %s" % aid); continue
        raw = open(fp, "rb").read(); bom = raw[:3] == b"\xef\xbb\xbf"
        text = raw.decode("utf-8-sig"); nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(nl)
        fidx = next((i for i, L in enumerate(lines) if _FILES_REGEX.search(L)), None)
        if fidx is None: log.append("SKIP no-files-line: %s" % aid); continue
        existing = [x.strip() for x in _FILES_REGEX.search(lines[fidx]).group(1).split(",") if x.strip()]
        merged = existing + [p for p in paths if p not in existing]
        lines[fidx] = "Files: " + ", ".join(merged)
        open(fp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(nl.join(lines))
        log.append("APPEND %s: +%d (total %d)" % (aid, len(merged) - len(existing), len(merged)))
else:
    log.append("nothing to append")
open(os.path.join(ROOT, "reports", "d1_2b_log.txt"), "w", encoding="utf-8").write("\n".join(log))
print("\n".join(log))

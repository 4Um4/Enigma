import glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app.services.adr_net.adr_parser import parse_impact_audit, normalize_adr_id

FOLDER = chr(128193)
atlas_path = os.path.join(ROOT, "docs", "ADR (Architecture Decision Records).md")
lines = open(atlas_path, encoding="utf-8-sig").read().splitlines()
law_re = re.compile(r"\*\*(L[\d\.]+):\s*(.+?)\*\*\s*\(([^)]*)\)")
law_map = {}
i = 0
while i < len(lines):
    m = law_re.search(lines[i])
    if m:
        ids = [normalize_adr_id(x.strip()) for x in m.group(3).split(",") if x.strip()]
        paths = []
        j = i + 1
        while j < len(lines) and j <= i + 10:
            nxt = lines[j]
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
ALIAS = [("svc/", "backend/app/services/"), ("dom/", "backend/app/domain/"), ("mod/", "backend/app/models/"), ("app/", "backend/app/"), ("tests/", "backend/tests/")]
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

audits = os.path.join(ROOT, "docs", "audits")
empty_ids = []
for fp in glob.glob(os.path.join(audits, "*_IMPACT.md")):
    try: n = parse_impact_audit(fp)
    except Exception: continue
    if n is not None and not n.files:
        empty_ids.append(n.adr_id)

res, dropped, no_law = {}, 0, []
for aid in empty_ids:
    if aid not in law_map:
        no_law.append(aid); continue
    got_all = []
    for p in law_map[aid]:
        g = resolve(p)
        if g:
            got_all.extend([x for x in g if x not in got_all])
        else:
            dropped += 1
    if got_all:
        res[aid] = got_all

out = []
out.append("EMPTY=%d law_mapped=%d WAVE3_FILLABLE=%d no_law_entry=%d total_drop_paths=%d" % (len(empty_ids), len(empty_ids) - len(no_law), len(res), len(no_law), dropped))
out.append("== WAVE3 SAMPLE (30)")
for k in list(res)[:30]:
    out.append("  %s: %d paths" % (k, len(res[k])))
out.append("== NO-LAW (%d)" % len(no_law))
out.extend("  " + a for a in no_law[:60])
open(os.path.join(ROOT, "reports", "d1_wave3_probe.txt"), "w", encoding="utf-8").write("\n".join(out))
print(out[0])
print("\n".join(out[2:12]))

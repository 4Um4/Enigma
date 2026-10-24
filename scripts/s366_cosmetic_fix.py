# -*- coding: utf-8 -*-
# S366 cosmetic fix: two missing spaces in roadmap CCH-S366 line.
# Idempotent, fail-loud.
import io
import sys

PATH = "docs/ENIGMA_ROADMAP_v4_11_WPS.md"
REPL = [
    ("действияавтора", "действия автора"),
    ("4–6(прямой", "4–6 (прямой"),
]

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    src = f.read()

report = []
for old, new in REPL:
    n = src.count(old)
    if n == 0:
        report.append("skip (already fixed): %r" % old)
        continue
    if n > 1:
        sys.exit("FATAL: %d hits for %r (expected 1)" % (n, old))
    src = src.replace(old, new, 1)
    report.append("fixed: %r -> %r" % (old, new))

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(src)

for r in report:
    print(" - " + r)
print("DONE")

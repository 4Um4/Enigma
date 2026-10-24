# -*- coding: utf-8 -*-
# S366/L4: add logger.warning into two single-statement except->return
# blocks of record-npc-belief endpoint (routes_chronicle.py).
# Linter flags single-statement except bodies that are Return.
# In-file convention (lines 136/170): logger.warning inside except.
# Client behavior (BAD_REQUEST dict) unchanged. Idempotent.
import io
import sys

PATH = "backend/app/api/routes_chronicle.py"

TARGETS = [
    (
        'return {"status": "BAD_REQUEST", "error": f"invalid enum value: {e}"}',
        'logger.warning("[CCH_BELIEF] invalid enum value: %s", e)',
    ),
    (
        'return {"status": "BAD_REQUEST", "error": f"belief validation failed: {e}"}',
        'logger.warning("[CCH_BELIEF] belief validation failed: %s", e)',
    ),
]

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    lines = f.readlines()

report = []
for target, warn in TARGETS:
    hits = [i for i, ln in enumerate(lines) if target in ln]
    if len(hits) != 1:
        sys.exit("FATAL: expected exactly 1 hit, got %d for: %s" % (len(hits), target[:70]))
    i = hits[0]
    prev = lines[i - 1] if i > 0 else ""
    if "logger.warning" in prev:
        report.append("already fixed (skip): %s" % target[:60])
        continue
    raw = lines[i]
    eol = "\r\n" if raw.endswith("\r\n") else ("\n" if raw.endswith("\n") else "")
    stripped = raw.rstrip("\r\n")
    indent = stripped[: len(stripped) - len(stripped.lstrip())]
    lines.insert(i, indent + warn + eol)
    report.append("inserted before line %d: %s" % (i + 1, warn))

with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.writelines(lines)

print("OK:")
for r in report:
    print(" - " + r)

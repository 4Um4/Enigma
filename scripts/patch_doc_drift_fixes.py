"""S363-doc-fix: validate_doc_refs RED #1 (roadmap line-drift) + RED #2 (EXCLUDE_DIRS)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# === RED #1: roadmap decision_hub.py:2133 → 2030 ===
roadmap = ROOT / "docs" / "ENIGMA_ROADMAP_v4_11_WPS.md"
text = roadmap.read_text(encoding="utf-8")
old_ref = "decision_hub.py:2133"
new_ref = "decision_hub.py:2030"
count1 = text.count(old_ref)
print(f"RED#1 pre-check: {count1} matches (expected 1)")
if count1 == 1:
    text = text.replace(old_ref, new_ref)
    roadmap.write_text(text, encoding="utf-8")
    print("RED#1 PATCH APPLIED (roadmap)")
else:
    print("RED#1 ABORT: not unique")

# === RED #2: validate_doc_refs.py — add EXCLUDE_DIRS ===
vdr = ROOT / "scripts" / "validate_doc_refs.py"
code = vdr.read_text(encoding="utf-8")

# 2a. Add EXCLUDE_DIRS constant after SCAN_DIRS
old_scan = 'SCAN_DIRS = [\n    "docs/",\n]'
new_scan = 'SCAN_DIRS = [\n    "docs/",\n]\n\n# Директории, исключаемые из сканирования (архивные исторические снимки)\nEXCLUDE_DIRS = ["docs/Архив/"]'
if "EXCLUDE_DIRS" not in code:
    code = code.replace(old_scan, new_scan)
    print("RED#2a PATCH APPLIED (EXCLUDE_DIRS constant)")
else:
    print("RED#2a SKIP: EXCLUDE_DIRS already exists")

# 2b. Add filter in main loop
old_loop = '        for md_file in dir_path.rglob("*.md"):\n            all_refs.extend(find_refs(md_file))'
new_loop = '        for md_file in dir_path.rglob("*.md"):\n            if any(exc in str(md_file) for exc in EXCLUDE_DIRS):\n                continue\n            all_refs.extend(find_refs(md_file))'
if "EXCLUDE_DIRS" in code and "exc in str(md_file)" not in code:
    code = code.replace(old_loop, new_loop)
    print("RED#2b PATCH APPLIED (filter in main loop)")
elif "exc in str(md_file)" in code:
    print("RED#2b SKIP: filter already exists")
else:
    print("RED#2b ABORT: main loop pattern not found")

vdr.write_text(code, encoding="utf-8")
print("DONE")
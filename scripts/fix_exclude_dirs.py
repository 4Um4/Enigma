"""Fix RED#2: platform-independent EXCLUDE_DIRS via Path.parts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
vdr = ROOT / "scripts" / "validate_doc_refs.py"
code = vdr.read_text(encoding="utf-8")

# Заменить EXCLUDE_DIRS на directory names (не paths)
old_const = 'EXCLUDE_DIRS = ["docs/Архив/"]'
new_const = 'EXCLUDE_DIRS = ["Архив"]  # directory names to exclude (platform-independent via Path.parts)'
if old_const in code:
    code = code.replace(old_const, new_const)
    print("EXCLUDE_DIRS updated to directory names")

# Заменить filter на Path.parts check
old_filter = 'if any(exc in str(md_file) for exc in EXCLUDE_DIRS):'
new_filter = 'if any(exc in md_file.parts for exc in EXCLUDE_DIRS):'
if old_filter in code:
    code = code.replace(old_filter, new_filter)
    print("Filter updated to Path.parts check")
else:
    print("Filter pattern not found — may already be fixed")

vdr.write_text(code, encoding="utf-8")
print("DONE")
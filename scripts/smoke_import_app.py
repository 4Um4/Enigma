# -*- coding: utf-8 -*-
"""SMOKE :: импорт всех модулей backend/app. Ловит битые импорты до прода."""
import importlib
import pkgutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import app  # noqa: E402

ok = fail = 0
failures = []
for m in sorted(pkgutil.walk_packages(app.__path__, prefix="app."), key=lambda x: x.name):
    try:
        importlib.import_module(m.name)
        ok += 1
    except Exception as e:
        fail += 1
        tb = traceback.format_exc(limit=3)
        failures.append((m.name, f"{type(e).__name__}: {e}", tb))

print(f"OK={ok} FAIL={fail}")
for name, err, tb in failures:
    print("=" * 70)
    print(f"[FAIL] {name}\n  {err}\n{tb}")
sys.exit(1 if fail else 0)
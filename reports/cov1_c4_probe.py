from __future__ import annotations

# reports/cov1_c4_probe.py
"""Одноразовый зонд C4-RED: @dataclass внутри модуля, загруженного
importlib-ом без регистрации в sys.modules (Python 3.13). Воспроизводит
условия _load_linter() и проверяет кандидат-фикс. После разбора удалить."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "scripts" / "lint_sqlite_registry.py"

print("python:", sys.version)

# (a) как в _load_linter сейчас — без регистрации
spec = importlib.util.spec_from_file_location("probe_no_reg", LINT)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    print("(a) exec_module БЕЗ sys.modules: OK — гипотеза ОПРОВЕРГНУТА")
except Exception as exc:
    print(f"(a) exec_module БЕЗ sys.modules: {type(exc).__name__}: {exc}")

# (b) кандидат-фикс — с регистрацией
spec2 = importlib.util.spec_from_file_location("probe_with_reg", LINT)
mod2 = importlib.util.module_from_spec(spec2)
sys.modules["probe_with_reg"] = mod2
try:
    spec2.loader.exec_module(mod2)
    print("(b) exec_module С sys.modules: OK")
except Exception as exc:
    print(f"(b) exec_module С sys.modules: {type(exc).__name__}: {exc}")

# (d)/(e) минимальный репро без файла линтера — голый @dataclass
SRC = (
    "from dataclasses import dataclass, field\n"
    "\n"
    "@dataclass\n"
    "class X:\n"
    "    a: dict = field(default_factory=dict)\n"
)
m = types.ModuleType("probe_exec_minimal")
try:
    exec(compile(SRC, "probe_minimal.py", "exec"), m.__dict__)
    print("(d) ModuleType-exec БЕЗ sys.modules: OK")
except Exception as exc:
    print(f"(d) ModuleType-exec БЕЗ sys.modules: {type(exc).__name__}: {exc}")
m2 = types.ModuleType("probe_exec_minimal_reg")
sys.modules["probe_exec_minimal_reg"] = m2
try:
    exec(compile(SRC, "probe_minimal_reg.py", "exec"), m2.__dict__)
    print("(e) ModuleType-exec С sys.modules: OK")
except Exception as exc:
    print(f"(e) ModuleType-exec С sys.modules: {type(exc).__name__}: {exc}")
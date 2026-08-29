"""
path: scripts/lint_frontend_isolation.py
Назначение: AST-анализатор для запрета импорта backend.app во фронтенде (Устав §1.1).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("frontend")

# ADR-O-368: Calibration Lab — изолированный developer/testing enclave.
# Ограниченное исключение из frontend isolation policy ТОЛЬКО для
# экспериментального чтения SSOT (Вариант B: Pygame-окно редактора,
# мастер-решение N2/S220). Исключение НЕ распространяется на production UI
# и НЕ ослабляет INV-FRONTEND-ISOLATION. Расширение списка — только через
# новый ADR.
_ALLOWLIST = {
    os.path.normpath(os.path.join("frontend", "map_editor", "ui", "lab_screen.py")),
}

def find_violations(filepath: str) -> list:
    violations = []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # Ищем: import backend.app...
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("backend.app") or alias.name.startswith("app."):
                    violations.append((node.lineno, f"import {alias.name}"))
        # Ищем: from backend.app... import ...
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module.startswith("backend.app") or node.module.startswith("app.")):
                violations.append((node.lineno, f"from {node.module} import ..."))

    return violations

def run_lint() -> list:
    all_violations = []
    for root, _, files in os.walk(ROOT):
        if "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if os.path.normpath(filepath) in _ALLOWLIST:
                    continue  # ADR-O-368: dev-enclave исключение (см. шапку)
                for line, msg in find_violations(filepath):
                    all_violations.append(f"[§1.1 VIOLATION] {filepath}:{line} -> {msg}")
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} нарушений изоляции фронтенда (§1.1):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ §1.1: Нарушений изоляции фронтенда не найдено.")
        exit(0)
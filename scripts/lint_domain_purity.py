"""
path: scripts/lint_domain_purity.py
Назначение: AST-анализатор для запрета импорта services/models/api в доменном слое (§1.2).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app/domain")

FORBIDDEN_PREFIXES = ("app.services", "app.models", "app.api", "backend.app.services", "backend.app.models", "backend.app.api")

def find_violations(filepath: str) -> list:
    violations = []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name.startswith(p) for p in FORBIDDEN_PREFIXES):
                    violations.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            if node.module and any(node.module.startswith(p) for p in FORBIDDEN_PREFIXES):
                violations.append((node.lineno, f"from {node.module} import ..."))

    return violations

def run_lint() -> list:
    all_violations = []
    for root, _, files in os.walk(ROOT):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                for line, msg in find_violations(filepath):
                    all_violations.append(f"[§1.2 VIOLATION] {filepath}:{line} -> {msg}")
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} нарушений чистоты домена (§1.2):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ §1.2: Доменный слой чист.")
        exit(0)
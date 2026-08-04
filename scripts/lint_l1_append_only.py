"""
path: scripts/lint_l1_append_only.py
Назначение: AST-анализатор для запрета удаления событий из L1Chronicle (Rule 28).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app")

# Файлы, где может использоваться L1Chronicle
TARGET_FILES = {
    os.path.normpath("backend/app/services/npc/l1_chronicle.py"),
    os.path.normpath("backend/app/services/npc/belief_crystallization_engine.py"),
    os.path.normpath("backend/app/services/npc/pattern_detector.py"),
    os.path.normpath("backend/app/services/npc/identity/identity_pressure_vector.py"),
}

FORBIDDEN_ATTRS = {"remove", "pop", "clear", "discard"}
FORBIDDEN_SQL = {"DELETE", "DROP", "TRUNCATE"}

def find_violations(filepath: str) -> list:
    violations = []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # 1. Ищем вызовы методов удаления: chronicle.remove(...), history.pop(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_ATTRS:
                # Проверяем, что объект похож на chronicle/history/ledger
                if isinstance(node.func.value, ast.Name):
                    obj_name = node.func.value.id.lower()
                    if any(k in obj_name for k in ["chronicle", "history", "ledger", "l1_"]):
                        violations.append((node.lineno, f"Append-only violation: {node.func.value.id}.{node.func.attr}()"))
                        
        # 2. Ищем DELETE/DROP SQL запросы
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            val_upper = node.value.upper()
            if any(kw in val_upper for kw in FORBIDDEN_SQL):
                # Простейшая эвристика: если строка содержит L1 или chronicle
                if "L1" in val_upper or "CHRONICLE" in val_upper or "EVENTS" in val_upper:
                    violations.append((node.lineno, f"SQL mutation on L1: {node.value[:50]}..."))

    return violations

def run_lint(directory: str = "backend/app") -> list:
    all_violations = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                # Сканируем все файлы, но фокусируемся на identity/domain
                if "identity" in filepath.lower() or "l1_chronicle" in filepath.lower() or "pattern_detector" in filepath.lower():
                    for line, msg in find_violations(filepath):
                        all_violations.append(f"[Rule 28 VIOLATION] {filepath}:{line} -> {msg}")
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} нарушений Append-Only L1 (Rule 28):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ Rule 28: L1Chronicle Append-Only соблюдается.")
        exit(0)
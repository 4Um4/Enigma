"""
path: scripts/lint_epistemic_boundary.py
Назначение: AST-анализатор для запрета чтения ментальных полей (§17 Epistemic Boundary).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app")

# Файлы, которые находятся на границе эпистемики и не должны читать raw-ментальные поля
TARGET_FILES = {
    os.path.normpath("backend/app/agents/dm_agent.py"),
}

# Директории для сканирования
TARGET_DIRS = {
    os.path.normpath("backend/app/services/verbalization"),
}

FORBIDDEN_FIELDS = {"stress", "fear", "psyche", "real_state", "trust_delta", "recalled_facts"}

def find_violations(filepath: str) -> list:
    violations = []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # 1. Ищем чтение атрибутов: state.stress, npc.fear
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_FIELDS:
            # Игнорируем запись (obj.stress = ...), нас интересует только чтение
            # В AST чтение это просто ast.Attribute, а запись - ast.Assign с target=ast.Attribute
            is_assignment = False
            # Это грубая проверка, но для линтера достаточно
            if hasattr(node, 'ctx') and isinstance(node.ctx, ast.Store):
                is_assignment = True
            
            if not is_assignment:
                violations.append((node.lineno, f"Read mental attribute: .{node.attr}"))
                
        # 2. Ищем чтение по ключу словаря: state["stress"], npc.get("fear")
        elif isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str) and node.slice.value in FORBIDDEN_FIELDS:
                violations.append((node.lineno, f"Read mental subscript: ['{node.slice.value}']"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and node.args[0].value in FORBIDDEN_FIELDS:
                violations.append((node.lineno, f"Read mental via .get(): .get('{node.args[0].value}')"))

    return violations

def run_lint() -> list:
    all_violations = []
    files_to_check = set()
    
    for f in TARGET_FILES:
        if os.path.exists(f):
            files_to_check.add(f)
            
    for d in TARGET_DIRS:
        for root, _, files in os.walk(d):
            for file in files:
                if file.endswith(".py"):
                    files_to_check.add(os.path.join(root, file))
                    
    for filepath in files_to_check:
        for line, msg in find_violations(filepath):
            all_violations.append(f"[§17 VIOLATION] {filepath}:{line} -> {msg}")
            
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} нарушений Эпистемической Границы (§17):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ §17: Нарушений Эпистемической Границы не найдено.")
        exit(0)
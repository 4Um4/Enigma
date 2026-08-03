"""
path: scripts/lint_hp_ssot.py
Назначение: AST-анализатор для запрета прямого присваивания state.hp / npc.hp (ADR-HP-UNIFICATION).
Зависимости: ast, os

Запуск: 
"""
import ast
import os
from typing import List, Tuple

FORBIDDEN_ATTRS = {"hp", "max_hp"}

# Файлы, где разрешено определять/синхронизировать эти поля (dataclass init, адаптеры)
WHITELIST_FILES = {
    os.path.normpath("backend/app/models/npc_state.py"),
}

def find_violations(filepath: str) -> List[Tuple[int, str]]:
    violations = []
    rel_path = os.path.normpath(filepath)
    
    if rel_path in WHITELIST_FILES:
        return violations
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # Ищем прямое присваивание: obj.hp = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_ATTRS:
                    # Пропускаем, если это self.hp внутри __init__ (редкое исключение)
                    violations.append((node.lineno, f"Direct assignment to {target.attr}"))
        # Ищем аугментированное присваивание: obj.hp -= 5
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Attribute) and node.target.attr in FORBIDDEN_ATTRS:
                violations.append((node.lineno, f"Augmented assignment to {node.target.attr}"))

    return violations

def run_lint(directory: str = "backend/app") -> List[Tuple[str, int, str]]:
    all_violations = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                for line, msg in find_violations(filepath):
                    all_violations.append((filepath, line, msg))
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print("❌ Найдены нарушения ADR-HP-UNIFICATION:")
        for f, l, m in viol:
            print(f"  {f}:{l} - {m}")
        exit(1)
    else:
        print("✅ ADR-HP-UNIFICATION: Прямых записей в state.hp не найдено.")
        exit(0)
"""
path: scripts/lint_retro_simulation.py
Назначение: AST-анализатор для запрета циклов с вызовами tick/execute (Rule 25 / ADR-047).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app")

FORBIDDEN_FUNCS = {"tick", "execute", "idle_tick", "run_turn"}

def find_violations(filepath: str) -> list:
    violations = []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            # Проверяем тело цикла
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    if child.func.attr in FORBIDDEN_FUNCS:
                        # Игнорируем self.execute внутри самого TickOrchestrator (это определение метода, но мы ищем вызовы)
                        # Эвристика: если вызывается у объекта life_engine, orchestrator, game_loop, tick_orch
                        if isinstance(child.func.value, ast.Name):
                            obj_name = child.func.value.id.lower()
                            if any(k in obj_name for k in ["engine", "orchestrator", "loop", "tick"]):
                                violations.append((child.lineno, f"Retro-simulation: loop contains {child.func.value.id}.{child.func.attr}()"))

    return violations

def run_lint(directory: str = "backend/app") -> list:
    all_violations = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                for line, msg in find_violations(filepath):
                    all_violations.append(f"[Rule 25 VIOLATION] {filepath}:{line} -> {msg}")
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} ретро-симуляций (Rule 25):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ Rule 25: Ретро-симуляций не найдено.")
        exit(0)
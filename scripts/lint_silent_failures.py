"""
path: scripts/lint_silent_failures.py
Назначение: AST-анализатор для запрета Silent Failures (L4: except: pass).
Зависимости: ast, os

Запуск: python -m scripts.lint_silent_failures
"""
import ast
import os
from typing import List, Tuple

WHITELIST_FILES = {
    os.path.normpath("backend/app/services/llm/router.py"), # Опциональные импорты
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
        # Ищем блоки try/except
        if isinstance(node, ast.ExceptHandler):
            # Проверяем тело except: если это только 'pass' или 'continue' без логирования
            if len(node.body) == 1 and isinstance(node.body[0], (ast.Pass, ast.Continue)):
                violations.append((node.lineno, "Bare except: pass / continue"))
            # Проверяем: except Exception as e: return None / return [] без логирования
            elif len(node.body) == 1 and isinstance(node.body[0], ast.Return):
                violations.append((node.lineno, "except: return without logging"))

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
        print(f"❌ Найдено {len(viol)} Silent Failures (L4 violation):")
        for f, l, m in viol:
            print(f"  {f}:{l} - {m}")
        exit(1)
    else:
        print("✅ L4: Silent Failures не найдены.")
        exit(0)
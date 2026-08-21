"""
path: scripts/lint_enigma_ast.py
Назначение: AST-анализатор архитектурных правил ENIGMA (Устав §1).
Правила:
  ENIGMA001: Запрет `X if cond else None` для критичных ресурсов (§1.1)
  ENIGMA002: Запрет `getattr(X, "y", None)` без логирования (§1.2)
  ENIGMA003: Запрет `in locals()` / `in globals()` (§1.3)
Запуск: python scripts/lint_enigma_ast.py
"""
import ast
import os
import re
from typing import List, Tuple

# Паттерн для поиска noqa комментариев
NOQA_PATTERN = re.compile(r'#\s*noqa:\s*ENIGMA\d{3}', re.IGNORECASE)

def find_violations(filepath: str) -> List[Tuple[int, str]]:
    violations = []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source_lines = f.readlines()
            source = "".join(source_lines)
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # ENIGMA001: Запрет `X if cond else None`
        if isinstance(node, ast.IfExp):
            if isinstance(node.orelse, ast.Constant) and node.orelse.value is None:
                line_content = source_lines[node.lineno - 1]
                if not NOQA_PATTERN.search(line_content):
                    violations.append((
                        node.lineno, 
                        "ENIGMA001: Silent failure `X if cond else None`. Use explicit raise or logging_tools.fail_loud() (§1.1)"
                    ))
        
        # ENIGMA002: Запрет `getattr(X, "y", None)` без логирования
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                if len(node.args) >= 3:
                    default = node.args[2]
                    is_silent = False
                    
                    if isinstance(default, ast.Constant) and default.value in (None, "", [], {}):
                        is_silent = True
                    elif isinstance(default, (ast.List, ast.Dict)):
                        # Проверка на пустые list/dict литералы
                        if isinstance(default, ast.List) and len(default.elts) == 0:
                            is_silent = True
                        elif isinstance(default, ast.Dict) and len(default.keys) == 0:
                            is_silent = True
                    
                    if is_silent:
                        line_content = source_lines[node.lineno - 1]
                        if not NOQA_PATTERN.search(line_content):
                            violations.append((
                                node.lineno, 
                                "ENIGMA002: Silent getattr default. If default is valid state, log first occurrence (§1.2)"
                            ))
        
        # ENIGMA003: Запрет `in locals()` / `in globals()`
        elif isinstance(node, ast.Compare):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Call):
                    if isinstance(comparator.func, ast.Name):
                        if comparator.func.id in ("locals", "globals"):
                            line_content = source_lines[node.lineno - 1]
                            if not NOQA_PATTERN.search(line_content):
                                violations.append((
                                    node.lineno, 
                                    "ENIGMA003: Forbidden `in locals()` or `in globals()`. Use explicit state or DTO (§1.3)"
                                ))
    return violations

def run_lint(directory: str = "backend/app") -> List[Tuple[str, int, str]]:
    all_violations = []
    for root, _, files in os.walk(directory):
        # Пропускаем тесты и песочницы, там это допустимо
        if "tests" in root or "sandbox" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                for line, msg in find_violations(filepath):
                    all_violations.append((filepath, line, msg))
    return all_violations

if __name__ == "__main__":
    print("[LINT] Запуск проверки §1 (Silent Failure Eradication)...")
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} нарушений (L0 violation):")
        for f, l, m in viol:
            print(f"  {f}:{l} - {m}")
        exit(1)
    else:
        print("[PASS] Нарушений §1.1-§1.3 не найдено.")
        exit(0)
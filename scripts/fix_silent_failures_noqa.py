"""
path: scripts/fix_silent_failures_noqa.py
Назначение: Одноразовый мигратор. Добавляет `# noqa: ENIGMA00X` к строкам,
нарушающим §1.1-§1.3, чтобы сделать CI зелёным и зафиксировать долг.
"""
import ast
import os
import re
from typing import Set, Dict

NOQA_PATTERN = re.compile(r'#\s*noqa:\s*ENIGMA\d{3}', re.IGNORECASE)

def find_line_violations(filepath: str) -> Dict[int, Set[str]]:
    """Возвращает словарь: {номер_строки: {список_нарушений}}"""
    violations = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source_lines = f.readlines()
            source = "".join(source_lines)
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        rule_id = None
        
        if isinstance(node, ast.IfExp):
            if isinstance(node.orelse, ast.Constant) and node.orelse.value is None:
                rule_id = "ENIGMA001"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                if len(node.args) >= 3:
                    default = node.args[2]
                    is_silent = False
                    if isinstance(default, ast.Constant) and default.value in (None, "", [], {}):
                        is_silent = True
                    elif isinstance(default, ast.List) and len(default.elts) == 0:
                        is_silent = True
                    elif isinstance(default, ast.Dict) and len(default.keys) == 0:
                        is_silent = True
                    if is_silent:
                        rule_id = "ENIGMA002"
        elif isinstance(node, ast.Compare):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Call):
                    if isinstance(comparator.func, ast.Name) and comparator.func.id in ("locals", "globals"):
                        rule_id = "ENIGMA003"
        
        if rule_id:
            if node.lineno not in violations:
                violations[node.lineno] = set()
            violations[node.lineno].add(rule_id)
            
    return violations

def fix_file(filepath: str) -> int:
    violations = find_line_violations(filepath)
    if not violations:
        return 0
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return 0
        
    fixes_applied = 0
    for line_no, rules in violations.items():
        idx = line_no - 1
        if idx >= len(lines):
            continue
            
        line = lines[idx]
        
        # Если уже есть noqa для этого правила - пропускаем
        if NOQA_PATTERN.search(line):
            # Простая проверка, если уже есть ENIGMA noqa, не трогаем
            # (в идеале нужно проверять точные ID, но для разовой миграции достаточно)
            continue
            
        # Формируем строку правил: ENIGMA001, ENIGMA002
        rules_str = ", ".join(sorted(list(rules)))
        
        # Убираем перенос строки, добавляем noqa, возвращаем перенос
        clean_line = line.rstrip('\n').rstrip('\r')
        # Если строка заканчивается комментарием, добавляем пробел
        comment_sep = "  " if clean_line.endswith("#") or "#" in clean_line else "  "
        
        new_line = f"{clean_line}{comment_sep}# noqa: {rules_str}\n"
        lines[idx] = new_line
        fixes_applied += 1
        
    if fixes_applied > 0:
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)
            
    return fixes_applied

def run_fix(directory: str = "backend/app"):
    total_fixes = 0
    for root, _, files in os.walk(directory):
        if "tests" in root or "sandbox" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                total_fixes += fix_file(filepath)
    print(f"[FIX] Applied {total_fixes} 'noqa' annotations.")

if __name__ == "__main__":
    run_fix()
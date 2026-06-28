import ast
import os

def remove_code_by_pattern(filepath, patterns):
    if not os.path.exists(filepath):
        print(f"[SKIP] Файл не найден: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"[ERROR] Синтаксическая ошибка в {filepath}: {e}")
        return

    lines = source.splitlines(keepends=True)
    lines_to_delete = set()

    for node in ast.walk(tree):
        # Удаление классов (ast.ClassDef)
        if isinstance(node, ast.ClassDef) and node.name in patterns.get("classes", []):
            start_line = node.lineno
            if node.decorator_list:
                start_line = min(d.lineno for d in node.decorator_list)
            end_line = node.end_lineno
            for i in range(start_line - 1, end_line):
                lines_to_delete.add(i)
            i = end_line
            while i < len(lines) and lines[i].strip() == '':
                lines_to_delete.add(i)
                i += 1

        # Удаление импортов (ast.ImportFrom)
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in patterns.get("imports", []):
                    start_line = node.lineno
                    end_line = node.end_lineno
                    for i in range(start_line - 1, end_line):
                        lines_to_delete.add(i)
                    break

        # Удаление аннотаций полей в dataclass (ast.AnnAssign)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in patterns.get("fields", []):
                start_line = node.lineno
                end_line = node.end_lineno
                for i in range(start_line - 1, end_line):
                    lines_to_delete.add(i)

    # Удаление конкретных строк инициализации (простое текстовое совпадение)
    init_patterns = patterns.get("inits", [])
    for i, line in enumerate(lines):
        stripped = line.strip()
        for pat in init_patterns:
            if pat in stripped:
                lines_to_delete.add(i)
                break

    if not lines_to_delete:
        print(f"[SKIP] Ничего не найдено в {filepath}")
        return
        
    new_lines = [line for i, line in enumerate(lines) if i not in lines_to_delete]
    
    with open(filepath, 'w', encoding='utf-8-sig') as f:
        f.writelines(new_lines)
        
    print(f"[OK] Удалено {len(lines_to_delete)} строк из {filepath}")

targets = [
    ("frontend/game_screen.py", {
        "imports": ["PlayerMemory", "EncounterHistory"],
        "inits": ["memory = PlayerMemory()", "encounters = EncounterHistory()"]
    }),
    ("frontend/game_types.py", {
        "classes": ["PlayerMemory", "EncounterHistory"],
        "fields": ["player_memory", "encounter_history"]
    })
]

print("=== ТЗ-6 ШАГ 3: Удаление мёртвых полей PlayerMemory и EncounterHistory ===")
for filepath, patterns in targets:
    remove_code_by_pattern(filepath, patterns)

print("=== Готово ===")
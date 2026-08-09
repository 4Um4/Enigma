"""
path: scripts/lint_position_mutation.py
Назначение: AST-анализатор для запрета прямой мутации позиции вне SceneStateManager (§4.1).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app")

# Файлы, где разрешено менять позицию (редьюсеры и проекции)
WHITELIST_FILES = {
    os.path.normpath("backend/app/services/scene_state_manager.py"),
    os.path.normpath("backend/app/services/event_compiler.py"),
    os.path.normpath("backend/app/services/spatial/movement_engine.py"), # Создаёт SceneChange
    os.path.normpath("backend/app/services/spatial/traversal_execution_system.py"),
    os.path.normpath("backend/app/models/npc_state.py"), # write_to_legacy
    os.path.normpath("backend/app/services/game_loop/scene_init.py"), # Легальная инициализация позиции игрока (Phase 0)
}

FORBIDDEN_KEYS = {"position", "local_position"}

def find_violations(filepath: str) -> list:
    violations = []
    rel_path = os.path.normpath(filepath)
    
    # BUG-LINT-PATH: IPT передаёт абсолютные пути, а WHITELIST содержит относительные.
    # Пробуем оба варианта сравнения.
    if rel_path in WHITELIST_FILES:
        return violations
    if os.path.isabs(filepath):
        for wf in WHITELIST_FILES:
            if rel_path.endswith(wf):
                return violations
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # 1. Ищем запись по ключу словаря: npc["position"] = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str) and target.slice.value in FORBIDDEN_KEYS:
                        violations.append((node.lineno, f"Direct mutation: ['{target.slice.value}'] = ..."))
                # 2. Ищем запись атрибута: npc.position = ...
                elif isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_KEYS:
                    violations.append((node.lineno, f"Direct mutation: .{target.attr} = ..."))

    return violations

def run_lint(directory: str = "backend/app") -> list:
    all_violations = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                for line, msg in find_violations(filepath):
                    all_violations.append(f"[§4.1 VIOLATION] {filepath}:{line} -> {msg}")
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} прямых мутаций позиции (§4.1):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ §4.1: Прямых мутаций позиции не найдено.")
        exit(0)
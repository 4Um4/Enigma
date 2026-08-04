"""
path: scripts/lint_spatial_ssot.py
Назначение: AST-анализатор для запрета прямой сборки SpatialService вне фабрики (L9 / ADR-048).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app")
WHITELIST_FILES = {
    os.path.normpath("backend/app/services/spatial/spatial_factory.py"),
    os.path.normpath("backend/app/services/spatial/spatial_service.py"),
}

def find_violations(filepath: str) -> list:
    violations = []
    rel_path = os.path.normpath(filepath)
    
    # ADR-O-342: Проверяем по концу пути, чтобы работало с абсолютными путями
    if rel_path.endswith("spatial_factory.py") or rel_path.endswith("spatial_service.py"):
        return violations
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # Ищем вызовы методов класса: SpatialService.build_for_location(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "SpatialService":
                if node.func.attr.startswith("build_for"):
                    violations.append((node.lineno, f"SpatialService.{node.func.attr}()"))
        # Ищем прямое инстанцирование: SpatialService(...)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "SpatialService":
                violations.append((node.lineno, "SpatialService() instantiation"))

    return violations

def run_lint(directory: str = "backend/app") -> list:
    all_violations = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                for line, msg in find_violations(filepath):
                    all_violations.append(f"[L9 VIOLATION] {filepath}:{line} -> {msg}")
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} нарушений Spatial SSOT (L9):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ L9: Нарушений Spatial SSOT не найдено.")
        exit(0)
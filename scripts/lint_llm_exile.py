"""
path: scripts/lint_llm_exile.py
Назначение: AST-анализатор для запрета вызовов LLM в ядре симуляции (L7).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app")

# Файлы симуляционного ядра, где запрещены LLM-вызовы
KERNEL_FILES = {
    os.path.normpath("backend/app/services/tick_orchestrator.py"),
    os.path.normpath("backend/app/services/npc/npc_tick_pipeline.py"),
    os.path.normpath("backend/app/services/npc/decision_hub.py"),
    os.path.normpath("backend/app/services/npc/life_engine.py"),
    os.path.normpath("backend/app/services/phases/decision.py"),
}

# Запрещённые вызовы методов (llm.invoke, router.invoke, provider.invoke)
FORBIDDEN_METHODS = {"invoke", "complete", "chat", "generate"}

def find_violations(filepath: str) -> list:
    violations = []
    rel_path = os.path.normpath(filepath)
    
    if rel_path not in KERNEL_FILES:
        return violations
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        # Ищем вызовы: llm.invoke(...), router.invoke(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_METHODS:
                # Проверяем, что объект похож на LLM (router, llm, provider, client)
                if isinstance(node.func.value, ast.Name):
                    obj_name = node.func.value.id.lower()
                    if any(k in obj_name for k in ["llm", "router", "provider", "client", "openai", "llama"]):
                        violations.append((node.lineno, f"LLM call: {node.func.value.id}.{node.func.attr}()"))

    return violations

def run_lint(directory: str = "backend/app") -> list:
    all_violations = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                for line, msg in find_violations(filepath):
                    all_violations.append(f"[L7 VIOLATION] {filepath}:{line} -> {msg}")
    return all_violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} LLM-вызовов в ядре (L7):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ L7: LLM-вызовов в ядре не найдено.")
        exit(0)
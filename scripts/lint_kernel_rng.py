"""
path: scripts/lint_kernel_rng.py
Назначение: AST-анализатор для запрета random.* в симуляционном слое (ADR-O-301).
Зависимости: ast, os
"""
import ast
import os
from pathlib import Path

ROOT = Path("backend/app")

SIMULATION_LAYER_FILES = {
    "services/tick_orchestrator.py",
    "services/npc/life_engine.py",
    "services/npc/decision_hub.py",
    "services/memory/memory_manager.py",
    "services/affective/affective_integrator.py",
    "services/spatial/spatial_service.py",
    "services/spatial/movement_engine.py",
    "services/npc/perception_engine.py",
    "services/verbalization/verbal_stance.py",
    "services/temporal/temporal_engine.py",
    "services/npc/npc_tick_pipeline.py",
    "services/npc/expectation_store.py",
    "services/npc/break_progress_engine.py",
    "services/npc/l1_chronicle.py",
    "services/npc/drive_resolver.py",
    "services/npc/belief_crystallization_engine.py",
    "services/npc/pattern_detector.py",
    "services/motion/motion_pipeline.py",
    "services/scene_state_manager.py",
    "services/event_compiler.py",
    "services/combat/impact_engine.py",
    "services/game/combat_math.py",
    "services/reaction/reaction_rules.py"
}

WHITELIST_FILES = {
    "services/npc/kernel_rng.py"  # Очевидно
}

FORBIDDEN_FUNCS = {"uniform", "choice", "randint", "random", "randrange", "shuffle", "sample"}

def find_violations(filepath: str) -> list:
    violations = []
    rel_path = os.path.normpath(filepath).replace("\\", "/")
    if "backend/app/" in rel_path:
        rel_path = rel_path.split("backend/app/")[1]
        
    if rel_path in WHITELIST_FILES:
        return violations
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "random":
                    if node.func.attr in FORBIDDEN_FUNCS:
                        violations.append((node.lineno, f"random.{node.func.attr}"))
    return violations

def run_lint() -> list:
    violations = []
    for rel_path in SIMULATION_LAYER_FILES:
        abs_path = ROOT / rel_path
        if not abs_path.exists():
            continue
        for line, msg in find_violations(abs_path):
            violations.append(f"[ADR-O-301 VIOLATION] {abs_path}:{line} -> {msg}")
    return violations

if __name__ == "__main__":
    viol = run_lint()
    if viol:
        print(f"❌ Найдено {len(viol)} нарушений ADR-O-301 (random.*):")
        for v in viol:
            print(f"  {v}")
        exit(1)
    else:
        print("✅ ADR-O-301: Нарушений изоляции случайности не найдено.")
        exit(0)
"""
Запуск: python scripts/lint_wall_clock.py

Назначение:
- Строгий AST-линтер для проверки Закона Изоляции Реального Времени (§15).
- Уровень 1: Прямые вызовы (time.time, datetime.now)
- Уровень 2: Детекция алиасов и прямых импортов (import time as t; t.time())
- Уровень 3: Семантические утечки (Path.stat().st_mtime, CURRENT_TIMESTAMP)
- Исключения: Маркируются явно инлайн-комментарием # §15.2: (легальный тип источника).
- Возвращает код 1 при обнаружении нарушений (для CI/CD).
"""

import ast
import sys
from pathlib import Path

ROOT = Path("backend/app")

# Список файлов симуляционного слоя (§15.1)
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
    "services/scene_state_manager.py",  # Включён для аудита REAL_TIME_BRIDGE
}

# Уровень 1 & 2: Запрещённые функции
FORBIDDEN_FUNCS = {
    "time",
    "monotonic",
    "monotonic_ns",
    "perf_counter",
    "perf_counter_ns",
    "time_ns",
    "now",
    "utcnow",
}

# Уровень 3: Семантические утечки (атрибуты)
FORBIDDEN_ATTRS = {"st_mtime", "st_ctime", "st_atime"}

# Уровень 3: Семантические утечки (строки)
FORBIDDEN_STRINGS = {"CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"}

EXCEPTION_MARKER = "§15.2"


class WallClockVisitor(ast.NodeVisitor):
    def __init__(self, filepath: Path, source: str):
        self.filepath = filepath
        self.source_lines = source.splitlines()
        self.violations = []

        self.time_aliases = set()  # Имена, связанные с модулем time
        self.datetime_aliases = set()  # Имена, связанные с модулем datetime
        self.direct_funcs = set()  # Прямые импорты (from time import time)

    def visit_Import(self, node):
        for n in node.names:
            orig = n.name
            local = n.asname if n.asname else n.name
            if orig == "time":
                self.time_aliases.add(local)
            elif orig == "datetime":
                self.datetime_aliases.add(local)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module == "time":
            for n in node.names:
                local = n.asname if n.asname else n.name
                if n.name in FORBIDDEN_FUNCS:
                    self.direct_funcs.add(local)
        elif node.module == "datetime":
            for n in node.names:
                local = n.asname if n.asname else n.name
                self.datetime_aliases.add(local)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        call_chain = self._get_chain(node.func)

        # Уровень 1 & 2: Прямые вызовы или алиасы
        if call_chain:
            if len(call_chain) == 1 and call_chain[0] in self.direct_funcs:
                self._check_violation(node, call_chain[0])
            elif len(call_chain) == 2:
                prefix, func = call_chain
                if func in FORBIDDEN_FUNCS:
                    if prefix in self.time_aliases or prefix in self.datetime_aliases:
                        self._check_violation(node, ".".join(call_chain))
            elif len(call_chain) == 3:
                # Обработка вложенных вызовов: datetime.datetime.now()
                prefix, _, func = call_chain
                if prefix in self.datetime_aliases and func in FORBIDDEN_FUNCS:
                    self._check_violation(node, ".".join(call_chain))

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Уровень 3: Семантические утечки (filesystem metadata)
        if node.attr in FORBIDDEN_ATTRS:
            self._check_violation(node, node.attr)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        # Уровень 3: Семантические утечки (SQL/DB функции)
        if isinstance(node.value, str) and node.value.strip() in FORBIDDEN_STRINGS:
            self._check_violation(node, node.value)
        self.generic_visit(node)

    def _get_chain(self, node) -> list:
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
        return list(reversed(parts))

    def _check_violation(self, node, call_name: str):
        line_no = node.lineno
        if line_no <= len(self.source_lines):
            line_content = self.source_lines[line_no - 1]
            if EXCEPTION_MARKER in line_content:
                return  # Легальное исключение (тип источника времени подтверждён)

        self.violations.append(
            f"[§15 VIOLATION] {self.filepath}:{line_no} -> {call_name}"
        )


def lint_file(filepath: Path, violations: list):
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            source = f.read()
    except Exception as e:
        print(f"[SKIP] {filepath} -> {e}")
        return

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        print(f"[SYNTAX ERROR] {filepath} -> {e}")
        return

    visitor = WallClockVisitor(filepath, source)
    visitor.visit(tree)
    violations.extend(visitor.violations)


def run_lint() -> list:
    """Возвращает список нарушений без sys.exit (для интеграции в IPT)."""
    violations = []

    for rel_path in SIMULATION_LAYER_FILES:
        abs_path = ROOT / rel_path
        if not abs_path.exists():
            print(f"[WARN] Файл не найден: {abs_path}")
            continue
        lint_file(abs_path, violations)

    return violations

def main():
    print("[LINT] Запуск проверки §15 (Wall-Clock Isolation)...")
    violations = run_lint()

    if violations:
        print("\n[FAIL] Обнаружены нарушения изоляции реального времени:")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)
    else:
        print("[PASS] Нарушений не найдено. Симуляционный слой изолирован.")
        sys.exit(0)


if __name__ == "__main__":
    main()

"""
path: backend/tests/sandbox/micro/test_x1_intent_shadowing.py
Назначение: X1 — запрет веточных импортов Intent в npc_tick_pipeline.run (затенение → UnboundLocalError на :939)
Зависимости: ast (только чтение исходника)
Основные сущности: NpcTickPipeline

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_x1_intent_shadowing.py -v --tb=short; cd ..
"""

import ast
from pathlib import Path

_SRC = Path("app/services/npc/npc_tick_pipeline.py").read_text(encoding="utf-8")


def _imports_of_intent():
    tree = ast.parse(_SRC)
    found = []  # (line, col) для ImportFrom ... import Intent
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.models.npc_state":
            for alias in node.names:
                if alias.name == "Intent":
                    found.append((node.lineno, node.col_offset))
    return found


def test_intent_imported_at_module_level():
    tops = [ln for ln, col in _imports_of_intent() if col == 0]
    assert tops, "нет канонического модульного импорта Intent (регрессия X1)"


def test_no_function_level_intent_imports():
    shadowed = [(ln, col) for ln, col in _imports_of_intent() if col > 0]
    assert not shadowed, (
        f"веточные импорты Intent создают локальную тень внутри run() "
        f"(строки {[ln for ln, _ in shadowed]}) → UnboundLocalError, регрессия X1"
    )
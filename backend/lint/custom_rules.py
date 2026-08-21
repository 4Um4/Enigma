"""
path: backend/lint/custom_rules.py
Назначение: Кастомные правила Flake8 для архитектуры ENIGMA.
Правила:
  ENIGMA001: Запрет `X if cond else None` для критичных ресурсов (§1.1)
  ENIGMA002: Запрет `getattr(X, "y", None)` без логирования (§1.2)
  ENIGMA003: Запрет `in locals()` / `in globals()` (§1.3)
"""
from __future__ import annotations

import ast
from typing import Any, Generator, List, Tuple, Type

class EnigmaCustomRules:
    """Точка входа для Flake8."""
    name = "enigma-custom-rules"
    version = "1.0.0"

    def __init__(self, tree: ast.AST) -> None:
        self._tree = tree

    def run(self) -> Generator[Tuple[int, int, str, Type[Any]], None, None]:
        visitor = EnigmaVisitor()
        visitor.visit(self._tree)

        for line, col, msg in visitor.violations:
            yield line, col, msg, type(self)

class EnigmaVisitor(ast.NodeVisitor):
    """AST-визитёр для поиска нарушений."""

    def __init__(self) -> None:
        self.violations: List[Tuple[int, int, str]] = []

    def visit_IfExp(self, node: ast.IfExp) -> None:
        """ENIGMA001: Запрет `X if cond else None`"""
        if isinstance(node.orelse, ast.Constant) and node.orelse.value is None:
            self.violations.append((
                node.lineno, node.col_offset,
                "ENIGMA001: Silent failure `X if cond else None`. Use explicit raise or logging_tools.fail_loud() (§1.1)",
            ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """ENIGMA002: Запрет `getattr(X, "y", None)` без логирования"""
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 3:
                default = node.args[2]
                # Ловим None, пустую строку, пустой список/словарь
                is_silent = False
                if isinstance(default, ast.Constant) and default.value in (None, "", [], {}):
                    is_silent = True
                elif isinstance(default, (ast.List, ast.Dict)) and len(getattr(default, 'elts', getattr(default, 'keys', []))) == 0:
                    is_silent = True
                
                if is_silent:
                    self.violations.append((
                        node.lineno, node.col_offset,
                        "ENIGMA002: Silent getattr default. If default is valid state, log first occurrence (§1.2)",
                    ))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        """ENIGMA003: Запрет `in locals()` / `in globals()`"""
        for comparator in node.comparators:
            if isinstance(comparator, ast.Call):
                if isinstance(comparator.func, ast.Name):
                    if comparator.func.id in ("locals", "globals"):
                        self.violations.append((
                            node.lineno, node.col_offset,
                            "ENIGMA003: Forbidden `in locals()` or `in globals()`. Use explicit state or DTO (§1.3)",
                        ))
        self.generic_visit(node)
# path: /project/scripts/check_discovery_monopoly.py
"""
Файл: scripts/check_discovery_monopoly.py
Назначение: P6/T5 — статический CI-гейт R1-монополии (санкция S255
    Step 2): TruthState.mark_discovered должен иметь РОВНО ОДИН
    production-вызов в backend/app — внутри DiscoveryBridge
    (services/player_cognition/discovery_bridge.py).
    Гейт сознательно узкий (Мастер: «его задача — конкретно
    R1-монополия»): НЕ универсальный анализатор epistemic-writers.
Метод: AST (Call-узлы с атрибутом mark_discovered) — комментарии и
    docstring-упоминания вызовами не считаются.
Выход: GREEN (exit 0) — монополия доказана; RED (exit 1) — список
    нарушений = живая карта остатка миграции (E3 / E1+deprecation).
Запуск: python scripts/check_discovery_monopoly.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "backend" / "app"
BRIDGE_REL = "services/player_cognition/discovery_bridge.py"
TRUTH_MODEL_REL = "models/truth_state.py"
METHOD = "mark_discovered"


def _scan(path: Path) -> List[Tuple[int, str]]:
    """(строка, текст) для каждого Call-узла с атрибутом METHOD."""
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    src_lines = text.splitlines()
    found: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == METHOD
        ):
            lineno = node.lineno
            line_text = src_lines[lineno - 1].strip() if lineno <= len(src_lines) else ""
            found.append((lineno, line_text))
    return found


def _has_def(path: Path, name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return any(
        isinstance(node, ast.FunctionDef) and node.name == name
        for node in ast.walk(tree)
    )


def main() -> int:
    bridge = APP_DIR / BRIDGE_REL
    truth_model = APP_DIR / TRUTH_MODEL_REL

    if not bridge.exists():
        print(f"RED: Bridge отсутствует: {BRIDGE_REL}")
        return 1
    if not truth_model.exists() or not _has_def(truth_model, METHOD):
        print(f"RED: определение {METHOD} не найдено в {TRUTH_MODEL_REL}")
        return 1

    legit = _scan(bridge)
    if not legit:
        print(f"RED: {BRIDGE_REL} не вызывает {METHOD} — монополия вакуумна")
        return 1

    violations: List[str] = []
    for py in sorted(APP_DIR.rglob("*.py")):
        rel = py.relative_to(APP_DIR).as_posix()
        if rel in (BRIDGE_REL, TRUTH_MODEL_REL):
            continue
        try:
            found = _scan(py)
        except SyntaxError as exc:
            violations.append(f"{rel}: PARSE ERROR: {exc}")
            continue
        for lineno, line_text in found:
            violations.append(f"{rel}:{lineno}: {line_text}")

    print(f"[T5] Легитимный вызывающий: {BRIDGE_REL} (вызовов: {len(legit)})")
    if violations:
        print(f"RED: {METHOD} вызывается вне Bridge — {len(violations)}:")
        for v in violations:
            print(f"  - {v}")
        print("Карта остатка миграции: E3 = компилятор (:129/:166); "
              "E1+deprecation = парсер (:109).")
        return 1

    print(f"GREEN: TruthState.{METHOD} вызывается ТОЛЬКО из "
          f"discovery_bridge.py — R1-монополия доказана")
    return 0


if __name__ == "__main__":
    sys.exit(main())

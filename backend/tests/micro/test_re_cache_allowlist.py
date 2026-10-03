# -*- coding: utf-8 -*-
"""
path: backend/tests/micro/test_re_cache_allowlist.py
Назначение: Негативный микротест греп-стража relationship_cache (ADR-O-415, RE-01 M1b.3.7).
Зависимости: pytest; scripts/lint_relationship_cache_allowlist (через sys.path)
Основные сущности: test_clean_tree, test_growth_violation, test_new_file_violation,
                   test_shrink_violation, test_missing_entry_violation,
                   test_baseline_pinned, test_real_tree_green
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lint_relationship_cache_allowlist import ALLOWLIST, run_lint  # noqa: E402


# Мини-allowlist для tmp-дерева (изолирован от боевого ALLOWLIST)
_ALLOW = {"pkg/a.py": 1, "pkg/b.py": 2}


def _write(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _base_tree(root: Path) -> None:
    _write(root / "pkg" / "a.py", ["x = 1  # relationship_cache"])
    _write(
        root / "pkg" / "b.py",
        ["# relationship_cache один", "# relationship_cache два"],
    )


def test_clean_tree(tmp_path: Path) -> None:
    """Заморозка соблюдена — нарушений нет."""
    _base_tree(tmp_path)
    assert run_lint(tmp_path, _ALLOW) == []


def test_growth_violation(tmp_path: Path) -> None:
    """Новый сайт в разрешённом файле = GROWTH (ценз обязателен)."""
    _base_tree(tmp_path)
    _write(
        tmp_path / "pkg" / "b.py",
        [
            "# relationship_cache один",
            "# relationship_cache два",
            "# relationship_cache три",
        ],
    )
    violations = run_lint(tmp_path, _ALLOW)
    assert len(violations) == 1
    assert violations[0].startswith("GROWTH pkg/b.py")


def test_new_file_violation(tmp_path: Path) -> None:
    """Файл с токеном вне allowlist = NEW-FILE."""
    _base_tree(tmp_path)
    _write(tmp_path / "pkg" / "c.py", ["from x import relationship_cache"])
    violations = run_lint(tmp_path, _ALLOW)
    assert len(violations) == 1
    assert violations[0].startswith("NEW-FILE pkg/c.py")


def test_shrink_violation(tmp_path: Path) -> None:
    """Молчаливое сжатие поверхности = SHRINK (миграция документируется в ADR)."""
    _base_tree(tmp_path)
    _write(tmp_path / "pkg" / "b.py", ["# relationship_cache один"])
    violations = run_lint(tmp_path, _ALLOW)
    assert len(violations) == 1
    assert violations[0].startswith("SHRINK pkg/b.py")


def test_missing_entry_violation(tmp_path: Path) -> None:
    """Файл исчез или потерял все сайты = MISSING (оба ключа allowlist)."""
    _write(tmp_path / "pkg" / "a.py", ["x = 1"])
    violations = run_lint(tmp_path, _ALLOW)
    assert len(violations) == 2
    assert any(v.startswith("MISSING pkg/a.py") for v in violations)
    assert any(v.startswith("MISSING pkg/b.py") for v in violations)


def test_baseline_pinned() -> None:
    """Baseline заморозки запинен: 19 файлов / 52 сайта (пересчитан прогоном-судом)."""
    assert len(ALLOWLIST) == 19
    assert sum(ALLOWLIST.values()) == 52


def test_real_tree_green() -> None:
    """Боевой прогон на живом дереве: freeze соблюдён (ADR-O-415)."""
    assert run_lint() == []
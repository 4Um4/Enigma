from __future__ import annotations

# backend/tests/micro/test_lint_sqlite_registry.py
"""
path: backend/tests/micro/test_lint_sqlite_registry.py
Назначение: позитивные/негативные тесты scripts/lint_sqlite_registry.py
(вердикт Мастера I.2: собственные тесты линтера обязательны; новый
незарегистрированный стор = блокирующий RED). Все сценарии на tmp-деревьях;
живое дерево не участвует.
Зависимости: pytest, importlib.util, pathlib.
Основные сущности: _load_linter, _make_tree, _write, сценарии census.
"""

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_LINT_PATH = _ROOT / "scripts" / "lint_sqlite_registry.py"
_LINT_MODNAME = "lint_sqlite_registry_under_test"


def _load_linter():
    # Регистрация в sys.modules ДО exec: на Python 3.13 @dataclass
    # резолвит модуль-владелец класса (cls.__module__) через sys.modules;
    # exec_module незарегистрированного модуля роняет декоратор
    # (AttributeError в dataclasses; доказательство — reports/cov1_c4_probe.py,
    # прогон C4). Стандартная практика importlib.
    sys.modules.pop(_LINT_MODNAME, None)
    spec = importlib.util.spec_from_file_location(_LINT_MODNAME, _LINT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[_LINT_MODNAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_LINT_MODNAME, None)
        raise
    return module


def _make_tree(tmp_path: Path):
    app = tmp_path / "app"
    tests = tmp_path / "tests"
    scripts = tmp_path / "scripts"
    for d in (app, tests, scripts):
        d.mkdir(parents=True, exist_ok=True)
    return app, tests, scripts


def _write(base: Path, name: str, source: str) -> str:
    p = base / name
    p.write_text(source, encoding="utf-8")
    return p.as_posix()


def test_green_registered(tmp_path):
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(app, "a.py", "import sqlite3\nconn = sqlite3.connect('x.db')\n")
    res = lsr.run_census(app, tests, scripts, {rel: ("RUNNER-OWNED", "t", "")})
    assert res.ok, res.reasons
    assert rel in res.prod_connects


def test_red_unregistered_new_store(tmp_path):
    """Ядро вердикта I.2: незарегистрированный prod-стор = RED, не warning."""
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(app, "new_store.py", "import sqlite3\nsqlite3.connect('new.db')\n")
    res = lsr.run_census(app, tests, scripts, {})
    assert not res.ok
    assert rel in res.unregistered


def test_tests_scope_auto_ok(tmp_path):
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(tests, "t.py", "import sqlite3\nsqlite3.connect('t.db')\n")
    res = lsr.run_census(app, tests, scripts, {})
    assert res.ok, res.reasons
    assert rel in res.auto_tests
    assert not res.prod_connects


def test_scripts_scope_auto_ok(tmp_path):
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(scripts, "s.py", "import sqlite3\nsqlite3.connect('s.db')\n")
    res = lsr.run_census(app, tests, scripts, {})
    assert res.ok, res.reasons
    assert rel in res.auto_scripts


def test_excluded_requires_reason(tmp_path):
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(app, "a.py", "import sqlite3\nsqlite3.connect('x.db')\n")
    res = lsr.run_census(app, tests, scripts, {rel: ("EXCLUDED", "t", "")})
    assert not res.ok
    assert any("EXCLUDED без причины" in r for r in res.reasons)

    res2 = lsr.run_census(app, tests, scripts, {rel: ("EXCLUDED", "t", "легальное соединение вне контура")})
    assert res2.ok, res2.reasons


def test_uncovered_sqlalchemy_is_red(tmp_path):
    """Полнота: непокрытый способ создания соединения = RED полноты (I.2)."""
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(app, "b.py", "from sqlalchemy import create_engine\nengine = create_engine('sqlite:///x')\n")
    res = lsr.run_census(app, tests, scripts, {rel: ("EXCLUDED", "t", "x")})
    assert not res.ok
    assert "sqlalchemy/create_engine" in res.uncovered
    assert rel in res.uncovered["sqlalchemy/create_engine"][0] or any(
        rel in h for h in res.uncovered["sqlalchemy/create_engine"]
    )


def test_uncovered_connection_ctor_is_red(tmp_path):
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(app, "c.py", "import sqlite3\nc = sqlite3.Connection('x.db')\n")
    res = lsr.run_census(app, tests, scripts, {rel: ("EXCLUDED", "t", "x")})
    assert not res.ok
    assert "sqlite3.Connection()" in res.uncovered


def test_alias_and_from_import_detected(tmp_path):
    """Импорт-алиасы не обходят census."""
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel1 = _write(app, "d.py", "import sqlite3 as sq\nsq.connect('x.db')\n")
    rel2 = _write(app, "e.py", "from sqlite3 import connect as cc\ncc('y.db')\n")
    res = lsr.run_census(app, tests, scripts, {})
    assert rel1 in res.unregistered
    assert rel2 in res.unregistered


def test_stale_entries_are_red(tmp_path):
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    ghost = (app / "ghost.py").as_posix()
    outside = "C:/definitely/outside.py"
    res = lsr.run_census(app, tests, scripts, {
        ghost: ("RUNNER-OWNED", "t", ""),
        outside: ("RUNNER-OWNED", "t", ""),
    })
    assert not res.ok
    assert any("файла нет" in s for s in res.stale_registry)
    assert any("вне областей скана" in s for s in res.stale_registry)


def test_parse_error_is_red(tmp_path):
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    _write(app, "f.py", "def (:\n")
    res = lsr.run_census(app, tests, scripts, {})
    assert not res.ok
    assert any("НЕЧИТАЕМ" in r for r in res.reasons)


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    """main() = гейт: 0 GREEN / 1 RED с блокирующей формулировкой."""
    lsr = _load_linter()
    app, tests, scripts = _make_tree(tmp_path)
    rel = _write(app, "a.py", "import sqlite3\nsqlite3.connect('x.db')\n")
    monkeypatch.setattr(lsr, "APP_DIR", app)
    monkeypatch.setattr(lsr, "TESTS_DIR", tests)
    monkeypatch.setattr(lsr, "SCRIPTS_DIR", scripts)
    monkeypatch.setattr(lsr, "REGISTRY", {rel: ("RUNNER-OWNED", "t", "")})
    assert lsr.main() == 0

    monkeypatch.setattr(lsr, "REGISTRY", {})
    assert lsr.main() == 1
    out = capsys.readouterr().out
    assert "НЕРЕГИСТРИРОВАННЫЙ СТОР" in out
    assert "SQLITE-REGISTRY RED" in out
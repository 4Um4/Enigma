from __future__ import annotations

# scripts/lint_sqlite_registry.py
"""
path: scripts/lint_sqlite_registry.py
Назначение: INV-SQLITE-REGISTRY — машинное закрепление ADR-O-426 §9
(вердикт Мастера I.2): census способов открытия SQLite; каждый prod-файл,
открывающий SQLite-соединение, обязан иметь статус в REGISTRY;
новый незарегистрированный стор = БЛОКИРУЮЩАЯ ошибка гейта (RED),
не предупреждение. Выход: 0 GREEN / 1 RED.
Зависимости: ast, re, sys, dataclasses, pathlib (стандартная библиотека).
Основные сущности: REGISTRY, CensusResult, run_census, main.

Покрытые способы открытия (закрытый список, печатается в отчёте):
- sqlite3.connect(...) — прямой вызов, включая import-алиасы
  (import sqlite3 as X; from sqlite3 import connect [as Y]).
Непокрытые механизмы детектируются отдельным сканером и дают RED
(полнота НЕ декларируется при дыре): apsw / sqlalchemy(create_engine) /
dataset.connect / sqlite3.Connection( / from sqlite3 import ...Connection.
Скан непокрытых — только prod-область (угроза-модель: рантайм).

Классификация областей:
- backend/app/**  — PROD: требует явной записи в REGISTRY;
- backend/tests/** — TEST-ONLY (авто, по пути);
- scripts/**       — TOOLING (авто, по пути; dev-инструменты).
Инстанцирование зарегистрированных стор-классов не является способом
открытия (соединением владеет стор-класс, он и в реестре) — в census
не входит. Изменение REGISTRY = коммит контура COV-1.
"""

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "backend" / "app"
TESTS_DIR = ROOT / "backend" / "tests"
SCRIPTS_DIR = ROOT / "scripts"

# ── Реестр статусов prod-сторов (SSOT; ADR-O-426 §9) ────────────────
# path (posix от корня) : (status, store_id/role, reason)
# RUNNER-OWNED — файл в контуре MigrationRunner (стор или сам раннер).
# EXCLUDED — легальное соединение вне контура; reason ОБЯЗАТЕЛЕН.
REGISTRY: dict[str, tuple[str, str, str]] = {
    "backend/app/services/memory/sqlite_store.py": ("RUNNER-OWNED", "enigma_memory", ""),
    "backend/app/services/state/sqlite_persistence_adapter.py": ("RUNNER-OWNED", "enigma_runtime", ""),
    "backend/app/services/replay/replay_store.py": ("RUNNER-OWNED", "replay", ""),
    "backend/app/services/state/migration_runner.py": (
        "RUNNER-OWNED",
        "runner",
        "соединения backup/verify/apply/stamp (ADR-O-426)",
    ),
}

# Детектор непокрытых механизмов (prod-only; тупой regex-слой).
_UNCOVERED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bapsw\b", "apsw"),
    (r"\bsqlalchemy\b|\bcreate_engine\s*\(", "sqlalchemy/create_engine"),
    (r"\bdataset\.connect\s*\(", "dataset.connect"),
    (r"sqlite3\.Connection\s*\(", "sqlite3.Connection()"),
    (r"from\s+sqlite3\s+import\s+[^\n]*\bConnection\b", "from sqlite3 import Connection"),
)


@dataclass
class CensusResult:
    ok: bool = True
    scanned: dict[str, int] = field(default_factory=dict)
    prod_connects: dict[str, list[int]] = field(default_factory=dict)
    auto_tests: dict[str, list[int]] = field(default_factory=dict)
    auto_scripts: dict[str, list[int]] = field(default_factory=dict)
    uncovered: dict[str, list[str]] = field(default_factory=dict)
    unregistered: list[str] = field(default_factory=list)
    stale_registry: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _connect_lines(tree: ast.Module) -> list[int]:
    """Номера строк вызовов sqlite3.connect(...) с учётом import-алиасов."""
    sqlite_aliases: set[str] = {"sqlite3"}
    connect_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3":
                    sqlite_aliases.add(alias.asname or "sqlite3")
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "sqlite3" or node.module.startswith("sqlite3.")):
                for alias in node.names:
                    if alias.name == "connect":
                        connect_names.add(alias.asname or "connect")
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "connect"
            and isinstance(func.value, ast.Name)
            and func.value.id in sqlite_aliases
        ):
            lines.append(node.lineno)
        elif isinstance(func, ast.Name) and func.id in connect_names:
            lines.append(node.lineno)
    return sorted(lines)


def _uncovered_hits(source: str, rel: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for pattern, name in _UNCOVERED_PATTERNS:
        for m in re.finditer(pattern, source):
            line_no = source.count("\n", 0, m.start()) + 1
            hits.append((name, f"{rel}:{line_no}"))
    return hits


def run_census(
    app_dir: Path,
    tests_dir: Path,
    scripts_dir: Path,
    registry: dict[str, tuple[str, str, str]] | None = None,
) -> CensusResult:
    """Параметризуемый census (тесты гоняют на tmp-деревьях; main — живое)."""
    reg = REGISTRY if registry is None else registry
    res = CensusResult()

    def _scan(base: Path, scope: str) -> dict[str, list[int]]:
        found: dict[str, list[int]] = {}
        if not base.is_dir():
            res.reasons.append(f"область скана отсутствует: {base}")
            res.ok = False
            return found
        count = 0
        for path in sorted(base.rglob("*.py")):
            count += 1
            rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            except SyntaxError as exc:
                res.reasons.append(f"НЕЧИТАЕМ [PARSE]: {rel}:{exc.lineno} — {exc.msg}")
                res.ok = False
                continue
            lines = _connect_lines(tree)
            if lines:
                found[rel] = lines
            if scope == "app":
                for name, hit in _uncovered_hits(path.read_text(encoding="utf-8-sig"), rel):
                    res.uncovered.setdefault(name, []).append(hit)
        res.scanned[scope] = count
        return found

    res.prod_connects = _scan(app_dir, "app")
    res.auto_tests = _scan(tests_dir, "tests")
    res.auto_scripts = _scan(scripts_dir, "scripts")

    # 1) Незарегистрированный prod-стор = блокирующий RED (вердикт I.2).
    for rel in res.prod_connects:
        if rel not in reg:
            res.unregistered.append(rel)
            res.ok = False

    # 2) Честность реестра: stale/вне-скоуп/пустые reason.
    allowed_roots = (app_dir, tests_dir, scripts_dir)
    for rel, (status, _store, reason) in reg.items():
        target = ROOT / rel
        if not any(target.is_relative_to(r) for r in allowed_roots):
            res.stale_registry.append(f"{rel} — путь вне областей скана")
            res.ok = False
            continue
        if not target.exists():
            res.stale_registry.append(f"{rel} — файла нет (удалён?)")
            res.ok = False
            continue
        if status == "EXCLUDED" and not reason:
            res.reasons.append(f"{rel}: EXCLUDED без причины — reason обязателен (ADR-O-426 §9)")
            res.ok = False
        if status not in ("RUNNER-OWNED", "EXCLUDED"):
            res.reasons.append(f"{rel}: неизвестный статус {status!r}")
            res.ok = False

    # 3) Непокрытые механизмы = RED полноты (вердикт I.2).
    if res.uncovered:
        res.ok = False
    return res


def main() -> int:
    res = run_census(APP_DIR, TESTS_DIR, SCRIPTS_DIR)
    n_sites = sum(len(v) for v in res.prod_connects.values())
    n_excl = sum(1 for _s, _i, _r in REGISTRY.values() if _s == "EXCLUDED")
    print(
        f"[CENSUS] scanned: app={res.scanned.get('app', 0)}, "
        f"tests={res.scanned.get('tests', 0)}, scripts={res.scanned.get('scripts', 0)}"
    )
    print("[CENSUS] механизмы: покрыт sqlite3.connect(+алиасы); "
          "детектор непокрытых: apsw/sqlalchemy/dataset/Connection (prod)")
    print(f"[CENSUS] prod connect-сайты: файлов={len(res.prod_connects)}, сайтов={n_sites} | "
          f"реестр: RUNNER-OWNED={len(REGISTRY) - n_excl}, EXCLUDED={n_excl}")
    print(f"[CENSUS] non-prod (авто по пути): TEST-ONLY={len(res.auto_tests)} ф., "
          f"TOOLING={len(res.auto_scripts)} ф.")
    if res.ok:
        print("SQLITE-REGISTRY GREEN: все prod SQLite-сторы учтены (ADR-O-426 §9 / INV-SQLITE-REGISTRY)")
        return 0
    for rel in res.unregistered:
        print(f"[RED] НЕРЕГИСТРИРОВАННЫЙ СТОР: {rel} — новый SQLite-файл обязан пройти реестр (ADR-O-426 §9)")
    for entry in res.stale_registry:
        print(f"[RED] STALE-ЗАПИСЬ реестра: {entry}")
    for name, hits in sorted(res.uncovered.items()):
        for hit in hits:
            print(f"[RED] НЕПОКРЫТЫЙ МЕХАНИЗМ ({name}): {hit}")
    for reason in res.reasons:
        print(f"[RED] {reason}")
    print("SQLITE-REGISTRY RED — блокирующая ошибка гейта (см. строки выше)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
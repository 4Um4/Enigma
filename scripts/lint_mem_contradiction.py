"""
path: scripts/lint_mem_contradiction.py
Назначение: INV-MEM-CONTRADICTION (#10) — превентивный gate против новых
             явно обозначенных механизмов авторезолюции (§16.1.10, ADR-O-443).
Зависимости: stdlib only (ast, sys, pathlib).
Основные сущности: FORBIDDEN_IDENTIFIERS, FORBIDDEN_STRINGS,
                   FORBIDDEN_CLASS_PREFIXES, HEURISTIC_METHOD_MARKERS,
                   ALLOWLIST, LEGACY_BASELINE_KEYS, run_lint, main.
Запуск: python scripts/lint_mem_contradiction.py

Контракт (design v2 + Master technical clarifications):
- A-1 (CRIT, backend/app/**): forbidden identifier (latest_wins /
  highest_confidence_wins) после casefold() в 10 AST identifier-полях:
  Name.id, arg.arg, Attribute.attr, keyword.arg, alias.name (все
  компоненты dotted import), alias.asname, FunctionDef/AsyncFunctionDef
  name, ClassDef.name, Global.names, Nonlocal.names. Строгое равенство.
- A-2 (CRIT, backend/app/**): forbidden string literal после нормализации
  casefold + replace('-','_'); docstrings исключаются (AB-Q5).
- C-1 (CRIT, services/memory/**): ClassDef.name.startswith один из
  ConfidenceResolution / AutoResolver / AutoResolution.
- C-2 (WARN, services/memory/**): ClassDef.name.endswith("Resolver")
  и собственные объявления (FunctionDef/AsyncFunctionDef/Assign/
  AnnAssign/AugAssign) содержат resolve_conflict/pick_winner/auto_resolve;
  nested ClassDef не наследует маркеры.
- B5: allowlist с XOR adr/historical_basis, rationale, status, role.
- B8: ORPHAN по точному AST-совпадению (rel, kind, key).
- B9/v7: production=(root is None and allowlist is None); KEYS_MISMATCH
  только в production-режиме.
- B10: baseline production = [] (пустой список целиком).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


FORBIDDEN_IDENTIFIERS: frozenset[str] = frozenset({"latest_wins", "highest_confidence_wins"})
FORBIDDEN_STRINGS: frozenset[str] = frozenset({"latest_wins", "highest_confidence_wins"})
FORBIDDEN_CLASS_PREFIXES: tuple[str, ...] = (
    "ConfidenceResolution", "AutoResolver", "AutoResolution",
)
HEURISTIC_METHOD_MARKERS: frozenset[str] = frozenset({
    "resolve_conflict", "pick_winner", "auto_resolve",
})
MEMORY_DOMAIN_PREFIX: str = "services/memory/"
ALLOWED_ROLES: frozenset[str] = frozenset({
    "policy_constant_named", "class_legacy", "identifier_legacy",
})
ALLOWED_STATUSES: frozenset[str] = frozenset({"legacy_baseline", "approved"})
LEGACY_BASELINE_KEYS: frozenset[tuple[str, str, str]] = frozenset()
ALLOWLIST: dict[tuple[str, str, str], dict[str, str]] = {}

_DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"


def _norm_string(s: str) -> str:
    return s.casefold().replace("-", "_")


def _is_forbidden_identifier(s: str) -> bool:
    return s.casefold() in FORBIDDEN_IDENTIFIERS


def _is_forbidden_policy_string(s: str) -> bool:
    return _norm_string(s) in FORBIDDEN_STRINGS


def _collect_docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _target_name(t: ast.AST) -> str | None:
    if isinstance(t, ast.Name):
        return t.id
    if isinstance(t, ast.Attribute):
        return t.attr
    return None


def _own_class_markers(class_node: ast.ClassDef) -> set[str]:
    markers: set[str] = set()
    for stmt in class_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name in HEURISTIC_METHOD_MARKERS:
                markers.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                n = _target_name(t)
                if n in HEURISTIC_METHOD_MARKERS:
                    markers.add(n)
        elif isinstance(stmt, ast.AnnAssign):
            n = _target_name(stmt.target)
            if n in HEURISTIC_METHOD_MARKERS:
                markers.add(n)
        elif isinstance(stmt, ast.AugAssign):
            n = _target_name(stmt.target)
            if n in HEURISTIC_METHOD_MARKERS:
                markers.add(n)
    return markers


def _emit_identifier(rel, line, s, allowlist, violations, discovered):
    if not _is_forbidden_identifier(s):
        return
    key = (rel, "identifier", s.casefold())
    discovered.add(key)
    if key in allowlist:
        return
    violations.append(f"CRIT|{rel}:{line}|forbidden identifier: {s}")


def _scan_file(path, root, allowlist, violations):
    rel = path.relative_to(root).as_posix()
    discovered: set[tuple[str, str, str]] = set()
    try:
        src = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        violations.append(f"CRIT|{rel}|UNREADABLE: {e!r}")
        return discovered
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        violations.append(f"CRIT|{rel}|PARSE_ERROR: {e!r}")
        return discovered

    docstring_ids = _collect_docstring_ids(tree)

    for node in ast.walk(tree):
        # A-1: 10 identifier fields
        if isinstance(node, ast.Name):
            _emit_identifier(rel, node.lineno, node.id, allowlist, violations, discovered)
        elif isinstance(node, ast.arg):
            _emit_identifier(rel, getattr(node, "lineno", 0), node.arg, allowlist, violations, discovered)
        elif isinstance(node, ast.Attribute):
            _emit_identifier(rel, node.lineno, node.attr, allowlist, violations, discovered)
        elif isinstance(node, ast.keyword):
            if node.arg is not None:
                _emit_identifier(rel, getattr(node, "lineno", 0), node.arg, allowlist, violations, discovered)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                for comp in node.module.split("."):
                    _emit_identifier(rel, node.lineno, comp, allowlist, violations, discovered)
            for alias in node.names:
                for comp in alias.name.split("."):
                    _emit_identifier(rel, node.lineno, comp, allowlist, violations, discovered)
                if alias.asname:
                    _emit_identifier(rel, node.lineno, alias.asname, allowlist, violations, discovered)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _emit_identifier(rel, node.lineno, node.name, allowlist, violations, discovered)
        elif isinstance(node, ast.ClassDef):
            _emit_identifier(rel, node.lineno, node.name, allowlist, violations, discovered)
        elif isinstance(node, ast.Global):
            for n in node.names:
                _emit_identifier(rel, node.lineno, n, allowlist, violations, discovered)
        elif isinstance(node, ast.Nonlocal):
            for n in node.names:
                _emit_identifier(rel, node.lineno, n, allowlist, violations, discovered)

        # A-2: string literal (skip docstring)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            if _is_forbidden_policy_string(node.value):
                key = (rel, "string_literal", _norm_string(node.value))
                discovered.add(key)
                if key not in allowlist:
                    line = getattr(node, "lineno", 0)
                    violations.append(f"CRIT|{rel}:{line}|forbidden policy string: {node.value!r}")

        # C-1 / C-2 (services/memory/ only)
        if isinstance(node, ast.ClassDef) and rel.startswith(MEMORY_DOMAIN_PREFIX):
            matched = next((p for p in FORBIDDEN_CLASS_PREFIXES if node.name.startswith(p)), None)
            if matched is not None:
                key = (rel, "class", node.name)
                discovered.add(key)
                if key not in allowlist:
                    violations.append(f"CRIT|{rel}:{node.lineno}|forbidden class prefix ({matched}): {node.name}")
            elif node.name.endswith("Resolver"):
                markers = _own_class_markers(node)
                if markers:
                    key = (rel, "class_heuristic_warn", node.name)
                    discovered.add(key)
                    if key not in allowlist:
                        violations.append(f"WARN|{rel}:{node.lineno}|heuristic Resolver with markers {sorted(markers)}: {node.name}")

    return discovered


def _validate_allowlist_entry(key, meta, violations):
    rel, kind, ident = key
    status = meta.get("status", "")
    role = meta.get("role", "")
    rationale = (meta.get("rationale") or "").strip()
    adr = (meta.get("adr") or "").strip()
    hist = (meta.get("historical_basis") or "").strip()

    if status not in ALLOWED_STATUSES:
        violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — status={status!r}")
        return
    if role not in ALLOWED_ROLES:
        violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — role={role!r}")
        return
    if not rationale:
        violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — rationale пустой")
        return

    is_legacy = key in LEGACY_BASELINE_KEYS
    if status == "legacy_baseline":
        if not is_legacy:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — legacy_baseline для не-baseline")
            return
        if not hist:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — нет historical_basis")
            return
        if adr:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — adr+historical_basis")
            return
    if status == "approved":
        if is_legacy:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — approved на legacy-ключе")
            return
        if not adr:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — нет adr")
            return
        if hist:
            violations.append(f"CRIT|{rel}|ALLOWLIST_MALFORMED: {kind}:{ident} — adr+historical_basis")
            return


def _check_allowlist(allowlist, root, violations, discovered, *, production):
    if production:
        actual = set(allowlist.keys())
        expected = set(LEGACY_BASELINE_KEYS)
        if actual != expected:
            only_allow = actual - expected
            only_keys = expected - actual
            violations.append(
                f"CRIT|<root>|KEYS_MISMATCH: ALLOWLIST vs LEGACY_BASELINE_KEYS: "
                f"only_allowlist={sorted(only_allow)}, only_keys={sorted(only_keys)}"
            )

    for key, meta in allowlist.items():
        _validate_allowlist_entry(key, meta, violations)

    for key, meta in allowlist.items():
        if key not in discovered:
            rel, kind, ident = key
            violations.append(f"CRIT|{rel}|ORPHAN: allowlist entry ({kind}:{ident}) не встречен")


def run_lint(root=None, allowlist=None):
    """B10: baseline production = []. B9/v7: production = (root is None and allowlist is None)."""
    if root is None:
        _root = _DEFAULT_ROOT
    else:
        _root = Path(root)

    if allowlist is None and root is None:
        production = True
        _allow = dict(ALLOWLIST)
    elif allowlist is None:
        production = False
        _allow = {}
    else:
        production = False
        _allow = dict(allowlist)

    if not _root.exists():
        return [f"CRIT|<root>|ROOT_MISSING: {_root}"]

    violations: list[str] = []
    discovered: set[tuple[str, str, str]] = set()
    for path in sorted(_root.rglob("*.py")):
        discovered |= _scan_file(path, _root, _allow, violations)

    _check_allowlist(_allow, _root, violations, discovered, production=production)
    return violations


def main() -> int:
    violations = run_lint()
    crit = [v for v in violations if v.startswith("CRIT|")]
    warn = [v for v in violations if v.startswith("WARN|")]
    if crit:
        print(f"[MEM-CONTRADICTION] CRIT={len(crit)}, WARN={len(warn)}")
        for v in crit[:10]:
            print(f"  - {v}")
        return 1
    if warn:
        print(f"[MEM-CONTRADICTION] WARN={len(warn)} (invariant PASS)")
        for v in warn[:10]:
            print(f"  - {v}")
        return 0
    print("[MEM-CONTRADICTION] OK: 0 CRIT, 0 WARN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

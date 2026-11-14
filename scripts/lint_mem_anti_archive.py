"""
path: scripts/lint_mem_anti_archive.py
Назначение: INV-MEM-ANTI-ARCHIVE (#9) — запрет vector/embedding-DB как memory (ADR-O-443, §16.1.9).
Зависимости: stdlib only (ast, sys, pathlib, re).
Основные сущности: FORBIDDEN_PREFIXES, HEURISTIC_TOKENS, ALLOWLIST, run_lint, main.
Запуск: python scripts/lint_mem_anti_archive.py
Семантика:
- CRIT| — доказанное нарушение (Class A prefix; Class C literal с Class A; Class D vector-specific artifact).
- WARN| — эвристика / нелитеральный динамический импорт / heuristic Class B.
- Contract (B10): baseline backend/app = [] (пустой список целиком, не только CRIT).
- B11: for ast.ImportFrom берётся node.module, импортируемые символы НЕ добавляются.
- UNREADABLE / PARSE_ERROR — CRIT, не silent-skip.
- root от __file__, CWD-независимость (S314).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# ---------- Class A: запрещённые модульные префиксы (B9) ----------
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "chromadb", "faiss", "pinecone", "weaviate", "qdrant_client", "qdrant",
    "milvus", "pymilvus", "sentence_transformers", "gensim", "annoy",
    "hnswlib", "lancedb", "marqo", "vespa", "pgvector",
    "openai.embeddings", "cohere.embeddings",
)

# ---------- Class B: эвристические токены (B4 → WARN, не CRIT) ----------
HEURISTIC_TOKENS: tuple[str, ...] = (
    "embed", "vector", "faiss", "annoy", "hnsw", "knn", "similar", "retriev", "chroma",
)

# ---------- Class D: артефакты (B1) ----------
ARTIFACT_NAMES_EXACT: tuple[str, ...] = (
    "chroma.sqlite3", "vectors.db", "embeddings.db", "faiss.index", "hnsw.index",
)
ARTIFACT_SUFFIX_VECTOR_SPECIFIC: tuple[str, ...] = (".faiss", ".hnsw")
ARTIFACT_SUFFIX_COMMON: tuple[str, ...] = (".pkl", ".npy", ".ann")
VECTOR_CONTEXT_TOKENS: tuple[str, ...] = (
    "embed", "vector", "faiss", "annoy", "hnsw", "knn", "chroma",
)

# ---------- stdlib / project / tooling (B3) ----------
STDLIB_MODULES: frozenset[str] = frozenset(sys.stdlib_module_names)
PROJECT_MODULE_PREFIXES: tuple[str, ...] = ("app.", "backend.")
TOOLING_ALLOW: frozenset[str] = frozenset()  # пусто на старте

# ---------- Allowlist (B5 + B8 + B11): (rel_path, exact_path) -> {adr, rationale} ----------
ALLOWLIST: dict[tuple[str, str], dict[str, str]] = {}

# ---------- Root от __file__ (S314) ----------
_DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"

_DYNAMIC_FUNCS = {"importlib.import_module", "builtins.__import__"}


def _make_alias_map(tree: ast.AST) -> dict[str, str]:
    """Собрать alias-карту: local_name -> полный модульный путь.
    import importlib as il            -> {'il': 'importlib'}
    from importlib import import_module as lm -> {'lm': 'importlib.import_module'}
    from importlib import import_module       -> {'import_module': 'importlib.import_module'}
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                local = a.asname or a.name.split(".")[0]
                aliases[local] = a.name
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            for a in node.names:
                if a.name == "*":
                    continue
                local = a.asname or a.name
                aliases[local] = f"{node.module}.{a.name}"
    return aliases


def _resolve_call_target(call: ast.Call, aliases: dict[str, str]) -> str | None:
    """Разрешить target вызова до полного пути.
    lm(...)           -> 'importlib.import_module'
    il.import_module  -> 'importlib.import_module'
    import_module(...) -> 'importlib.import_module'
    __import__(...)   -> 'builtins.__import__'
    """
    func = call.func
    if isinstance(func, ast.Name):
        local = func.id
        if local == "__import__":
            return "builtins.__import__"
        return aliases.get(local)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        base = aliases.get(func.value.id, func.value.id)
        return f"{base}.{func.attr}"
    return None


def _is_forbidden(path: str) -> bool:
    for p in FORBIDDEN_PREFIXES:
        if path == p or path.startswith(p + "."):
            return True
    return False


def _is_heuristic_warn(top: str) -> bool:
    low = top.lower()
    if not any(tok in low for tok in HEURISTIC_TOKENS):
        return False
    if top in STDLIB_MODULES:
        return False
    if top in TOOLING_ALLOW:
        return False
    for pre in PROJECT_MODULE_PREFIXES:
        if top.startswith(pre.rstrip(".")):
            return False
    return True


def _artifact_violation(s: str) -> str | None:
    """Class D: вернуть 'CRIT' если vector-specific, иначе None.
    B1: .pkl/.npy/.ann — только при vector-context в самой строке.
    """
    low = s.lower()
    # exact name
    for name in ARTIFACT_NAMES_EXACT:
        if name in low:
            return "CRIT"
    # vector-specific suffix
    for suf in ARTIFACT_SUFFIX_VECTOR_SPECIFIC:
        if low.endswith(suf):
            return "CRIT"
    # common suffix — требуется vector-context
    for suf in ARTIFACT_SUFFIX_COMMON:
        if low.endswith(suf):
            if any(tok in low for tok in VECTOR_CONTEXT_TOKENS):
                return "CRIT"
            return None
    return None


def _process_import(path: str, rel: str, line: int,
                    allowlist: dict, violations: list) -> None:
    """Классифицировать один импортированный путь (Class A / B / allowlist)."""
    if _is_forbidden(path):
        if (rel, path) in allowlist:
            return
        violations.append(f"CRIT|{rel}:{line}|forbidden import path: {path}")
        return
    top = path.split(".")[0]
    if _is_heuristic_warn(top):
        violations.append(
            f"WARN|{rel}:{line}|heuristic vector/embedding match: {path}"
        )


def _scan_file(path: Path, root: Path, allowlist: dict, violations: list) -> None:
    rel = path.relative_to(root).as_posix()
    try:
        src = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        violations.append(f"CRIT|{rel}|UNREADABLE: {e!r}")
        return
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        violations.append(f"CRIT|{rel}|PARSE_ERROR: {e!r}")
        return

    aliases = _make_alias_map(tree)

    for node in ast.walk(tree):
        # --- Class A + B (import-узлы) ---
        if isinstance(node, ast.Import):
            for a in node.names:
                _process_import(a.name, rel, node.lineno, allowlist, violations)
        elif isinstance(node, ast.ImportFrom):
            # B11: только node.module, символы не добавляем
            if node.module is not None:
                _process_import(node.module, rel, node.lineno, allowlist, violations)
        # --- Class C (dynamic imports) ---
        elif isinstance(node, ast.Call):
            target = _resolve_call_target(node, aliases)
            if target in _DYNAMIC_FUNCS:
                if node.args and isinstance(node.args[0], ast.Constant)                         and isinstance(node.args[0].value, str):
                    dyn_path = node.args[0].value
                    if _is_forbidden(dyn_path):
                        if (rel, dyn_path) not in allowlist:
                            violations.append(
                                f"CRIT|{rel}:{node.lineno}|dynamic forbidden import: {dyn_path}"
                            )
                    else:
                        top = dyn_path.split(".")[0]
                        if _is_heuristic_warn(top):
                            violations.append(
                                f"WARN|{rel}:{node.lineno}|heuristic dynamic import: {dyn_path}"
                            )
                else:
                    violations.append(
                        f"WARN|{rel}:{node.lineno}|dynamic import (non-literal) — недоказуемый канал"
                    )
        # --- Class D (string literal artifacts) ---
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            sev = _artifact_violation(node.value)
            if sev == "CRIT":
                violations.append(
                    f"CRIT|{rel}:{getattr(node, 'lineno', 0)}|vector artifact literal: {node.value!r}"
                )


def _check_allowlist(allowlist: dict, root: Path, violations: list,
                     file_texts: dict[str, str]) -> None:
    """Orphan-entry / malformed-entry checks (B5).

    file_texts: rel_path -> raw text; B5 orphan is substring-based.
    Ограничение: модуль, упомянутый в комментарии, не считается orphan.
    Production ALLOWLIST пуст; при добавлении entry — ADR-required.
    """
    for (rel, path), meta in allowlist.items():
        if not meta.get("adr") or not meta.get("rationale"):
            violations.append(
                f"CRIT|{rel}|ALLOWLIST_MALFORMED: (path, module)={path} — нет adr/rationale"
            )
            continue
        if path not in file_texts.get(rel, ""):
            violations.append(
                f"CRIT|{rel}|ORPHAN: allowlist entry ({path}) не встречен в файле"
            )


def run_lint(
    root: str | Path | None = None,
    allowlist: dict[tuple[str, str], dict[str, str]] | None = None,
) -> list[str]:
    """B10: baseline production = [] (пустой список целиком).

    Формат строк:
      "CRIT|<rel_path>:<line>|<message>"
      "WARN|<rel_path>:<line>|<message>"
      "CRIT|<rel_path>|UNREADABLE: ..."  (без line)
    """
    _root = Path(root) if root is not None else _DEFAULT_ROOT
    _allow = dict(allowlist) if allowlist is not None else dict(ALLOWLIST)

    if not _root.exists():
        return [f"CRIT|<root>|ROOT_MISSING: {_root}"]

    violations: list[str] = []
    file_texts: dict[str, str] = {}

    for path in sorted(_root.rglob("*.py")):
        rel = path.relative_to(_root).as_posix()
        try:
            file_texts[rel] = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            file_texts[rel] = ""  # UNREADABLE уже добавлен в _scan_file
        _scan_file(path, _root, _allow, violations)

    _check_allowlist(_allow, _root, violations, file_texts)
    return violations


def main() -> int:
    violations = run_lint()
    crit = [v for v in violations if v.startswith("CRIT|")]
    warn = [v for v in violations if v.startswith("WARN|")]
    if crit:
        print(f"[MEM-ANTI-ARCHIVE] 🔴 CRIT={len(crit)}, WARN={len(warn)}")
        for v in crit[:10]:
            print(f"  - {v}")
        return 1
    if warn:
        print(f"[MEM-ANTI-ARCHIVE] 🟡 WARN={len(warn)} (invariant PASS, сигнал)")
        for v in warn[:10]:
            print(f"  - {v}")
        return 0
    print("[MEM-ANTI-ARCHIVE] ✅ Freeze соблюдён: 0 CRIT, 0 WARN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

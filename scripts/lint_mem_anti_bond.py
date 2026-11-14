"""
path: scripts/lint_mem_anti_bond.py
Назначение: INV-MEM-ANTI-BOND (#12) — запрет второго Store под memory-домен
             (§16.1.12 ADR-O-443). Gate против конкурирующих хранилищ.
Зависимости: stdlib only (ast, sys, pathlib).
Основные сущности: MEMORY_TOKENS, ALLOWED_ROLES, ALLOWED_STATUSES,
                   LEGACY_BASELINE_KEYS, ALLOWLIST, run_lint, main.
Запуск: python scripts/lint_mem_anti_bond.py

Контракт:
- Class A: ClassDef *Store + memory-token, не в allowlist -> CRIT
- Class B: ClassDef *Store без memory-token, не в allowlist -> WARN
- Class C: dynamic setattr/__setattr__/type() с literal memory-token -> CRIT;
           нелитеральное имя — пропуск (B3 residual, v6+A: AST не доказывает)
- B1: status=legacy_baseline только для ключей из LEGACY_BASELINE_KEYS;
       новые ключи только status=approved с непустым adr.
- B5: XOR adr / historical_basis; rationale обязателен.
- B8: ORPHAN по точному AST ClassDef, не substring.
- B9: production sanity KEYS_MISMATCH только при production=True
       (allowlist is None на уровне run_lint).
- B10: baseline production = [] (пустой список целиком).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


# ---------- Tokens / roles / statuses ----------
MEMORY_TOKENS: tuple[str, ...] = (
    "memory", "belief", "narrative", "biography", "chronicle",
    "relationship", "epistemic", "conclusion", "crystal",
    "expectation", "working", "bond",
)

ALLOWED_ROLES: frozenset[str] = frozenset({
    "memory_backend_primary", "memory_backend_legacy",
    "relationship_backend_legacy", "relationship_backend_v2",
    "belief_conclusion", "belief_crystallized", "belief_epistemic",
    "expectation", "chronicle", "world_object", "infra_replay",
})

ALLOWED_STATUSES: frozenset[str] = frozenset({"legacy_baseline", "approved"})


# ---------- B5: fixed set of legacy-baseline keys ----------
LEGACY_BASELINE_KEYS: frozenset[tuple[str, str]] = frozenset({
    ("services/memory/sqlite_store.py", "SqliteMemoryStore"),
    ("services/memory/layered_memory.py", "JsonMemoryStore"),
    ("services/memory/relationship_store.py", "RelationshipStore"),
    ("services/social/relationship_state_store.py", "RelationshipStateStore"),
    ("services/npc/conclusion_store.py", "ConclusionStore"),
    ("services/npc/crystallized_belief_store.py", "CrystallizedBeliefStore"),
    ("services/npc/epistemic_store.py", "EpistemicStore"),
    ("services/npc/expectation_store.py", "ContextualExpectationStore"),
    ("services/chronicle/chronicle_store.py", "ChronicleStore"),
    ("services/world/world_object_store.py", "WorldObjectStore"),
    ("services/replay/replay_store.py", "ReplayStore"),
})


# ---------- Baseline allowlist (11 legacy_baseline) ----------
ALLOWLIST: dict[tuple[str, str], dict[str, str]] = {
    ("services/memory/sqlite_store.py", "SqliteMemoryStore"): {
        "role": "memory_backend_primary",
        "status": "legacy_baseline",
        "historical_basis": "§16.2.1 - SQLite SSOT for EventMemory (pre-MEM-0)",
        "rationale": "Persistence backend for EventMemory; canonical SQLite store",
    },
    ("services/memory/layered_memory.py", "JsonMemoryStore"): {
        "role": "memory_backend_legacy",
        "status": "legacy_baseline",
        "historical_basis": "legacy dual-backend; MEM-2 absorbs",
        "rationale": "Legacy JSON backend for memory, still used in some paths",
    },
    ("services/memory/relationship_store.py", "RelationshipStore"): {
        "role": "relationship_backend_legacy",
        "status": "legacy_baseline",
        "historical_basis": "RE-01 M1b.4.2 legacy backend",
        "rationale": "Legacy 5-scalar relationship backend",
    },
    ("services/social/relationship_state_store.py", "RelationshipStateStore"): {
        "role": "relationship_backend_v2",
        "status": "legacy_baseline",
        "historical_basis": "RE-01 M1b.4 V2 cutover",
        "rationale": "V2 relationship backend post cutover",
    },
    ("services/npc/conclusion_store.py", "ConclusionStore"): {
        "role": "belief_conclusion",
        "status": "legacy_baseline",
        "historical_basis": "BC-1 (S247, ADR-O-381), MEM-D20",
        "rationale": "Cognitive result BC-1 (conclusion layer)",
    },
    ("services/npc/crystallized_belief_store.py", "CrystallizedBeliefStore"): {
        "role": "belief_crystallized",
        "status": "legacy_baseline",
        "historical_basis": "L2.5, pre-MEM-0",
        "rationale": "Belief crystallization persistence (L2.5)",
    },
    ("services/npc/epistemic_store.py", "EpistemicStore"): {
        "role": "belief_epistemic",
        "status": "legacy_baseline",
        "historical_basis": "§16.9 canonical SSOT",
        "rationale": "Epistemic SSOT (canonical per §16.9)",
    },
    ("services/npc/expectation_store.py", "ContextualExpectationStore"): {
        "role": "expectation",
        "status": "legacy_baseline",
        "historical_basis": "BC-2 (ADR-O-381), dormant",
        "rationale": "Contextual expectation store; MEM-3 gated",
    },
    ("services/chronicle/chronicle_store.py", "ChronicleStore"): {
        "role": "chronicle",
        "status": "legacy_baseline",
        "historical_basis": "CCH, ADR-O-420",
        "rationale": "Chronicle SSOT for CCH track",
    },
    ("services/world/world_object_store.py", "WorldObjectStore"): {
        "role": "world_object",
        "status": "legacy_baseline",
        "historical_basis": "ADR-O-371",
        "rationale": "World object substrate",
    },
    ("services/replay/replay_store.py", "ReplayStore"): {
        "role": "infra_replay",
        "status": "legacy_baseline",
        "historical_basis": "ADR-O-426",
        "rationale": "Replay infra (not NPC memory, but *Store with token)",
    },
}


_DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "backend" / "app"


def _has_memory_token(name: str) -> bool:
    low = name.lower()
    return any(tok in low for tok in MEMORY_TOKENS)


def _classify_store_class(
    rel: str,
    node: ast.ClassDef,
    allowlist: dict[tuple[str, str], dict[str, str]],
    violations: list[str],
) -> None:
    """Class A (memory-token -> CRIT) / Class B (no token -> WARN)."""
    if not node.name.endswith("Store"):
        return
    key = (rel, node.name)
    if key in allowlist:
        return
    if _has_memory_token(node.name):
        violations.append(
            f"CRIT|{rel}:{node.lineno}|new memory-domain Store class: {node.name}"
        )
    else:
        violations.append(
            f"WARN|{rel}:{node.lineno}|non-memory Store class (review): {node.name}"
        )


def _scan_dynamic_call(
    rel: str,
    node: ast.Call,
    allowlist: dict[tuple[str, str], dict[str, str]],
    violations: list[str],
) -> None:
    """Class C: setattr / __setattr__ / type() with literal memory-token Store name.

    B3 + v7-bis: name_idx зависит от формы func:
    - setattr(obj, name, value)          -> args[1]
    - __setattr__(obj, name, value)      -> args[1]
    - obj.__setattr__(name, value)       -> args[0] (bound)
    - obj.setattr(name, value)           -> args[0] (bound, консервативно)
    - type(name, ...) / obj.type(name,..)-> args[0]
    """
    func = node.func
    name_idx = None
    label = None
    if isinstance(func, ast.Name):
        if func.id in ("setattr", "__setattr__"):
            name_idx = 1
            label = "dynamic Store registration"
        elif func.id == "type":
            name_idx = 0
            label = "dynamic type() Store"
    elif isinstance(func, ast.Attribute):
        if func.attr in ("setattr", "__setattr__"):
            name_idx = 0  # bound call: obj.__setattr__(name, value)
            label = "dynamic Store registration (bound)"
        elif func.attr == "type":
            name_idx = 0
            label = "dynamic type() Store"

    if name_idx is None or len(node.args) <= name_idx:
        return
    name_arg = node.args[name_idx]
    if not (isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str)):
        return  # non-literal skip (decision A)
    s = name_arg.value
    if not s.endswith("Store") or not _has_memory_token(s):
        return
    if (rel, s) in allowlist:
        return
    violations.append(
        f"CRIT|{rel}:{node.lineno}|{label}: {s}"
    )


def _scan_file(
    path: Path,
    root: Path,
    allowlist: dict[tuple[str, str], dict[str, str]],
    violations: list[str],
) -> set[tuple[str, str]]:
    """B8: returns discovered ClassDef names (rel_path, class_name)."""
    rel = path.relative_to(root).as_posix()
    discovered: set[tuple[str, str]] = set()
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

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            discovered.add((rel, node.name))
            _classify_store_class(rel, node, allowlist, violations)
        elif isinstance(node, ast.Call):
            _scan_dynamic_call(rel, node, allowlist, violations)

    return discovered


def _validate_allowlist_entry(
    key: tuple[str, str],
    meta: dict[str, str],
    violations: list[str],
) -> None:
    """B5/B6: per-entry validation (status, role, rationale, XOR adr/hist)."""
    rel, cls = key
    status = meta.get("status", "")
    role = meta.get("role", "")
    rationale = (meta.get("rationale") or "").strip()
    adr = (meta.get("adr") or "").strip()
    hist = (meta.get("historical_basis") or "").strip()

    if status not in ALLOWED_STATUSES:
        violations.append(
            f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — status={status!r} вне enum"
        )
        return
    if role not in ALLOWED_ROLES:
        violations.append(
            f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — role={role!r} вне enum"
        )
        return
    if not rationale:
        violations.append(
            f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — rationale пустой"
        )
        return

    is_legacy_key = key in LEGACY_BASELINE_KEYS

    if status == "legacy_baseline":
        if not is_legacy_key:
            violations.append(
                f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — legacy_baseline для НЕ-baseline ключа"
            )
            return
        if not hist:
            violations.append(
                f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — нет historical_basis"
            )
            return
        if adr:
            violations.append(
                f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — adr+historical_basis взаимоисключающие"
            )
            return

    if status == "approved":
        if is_legacy_key:
            violations.append(
                f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — approved на baseline-ключе"
            )
            return
        if not adr:
            violations.append(
                f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — нет adr"
            )
            return
        if hist:
            violations.append(
                f"CRIT|{rel}|ALLOWLIST_MALFORMED: {cls} — adr+historical_basis взаимоисключающие"
            )
            return


def _check_allowlist(
    allowlist: dict[tuple[str, str], dict[str, str]],
    root: Path,
    violations: list[str],
    discovered_classes: set[tuple[str, str]],
    *,
    production: bool,
) -> None:
    """B5/B8/B9: validate + KEYS_MISMATCH + ORPHAN."""
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
        rel, cls = key
        if key not in discovered_classes:
            violations.append(
                f"CRIT|{rel}|ORPHAN: allowlist entry ({cls}) не встречен в файле (AST ClassDef)"
            )


def run_lint(
    root: str | Path | None = None,
    allowlist: dict[tuple[str, str], dict[str, str]] | None = None,
) -> list[str]:
    """B10: baseline = []. B9/v7: production = (root is None and allowlist is None)."""
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
    discovered_classes: set[tuple[str, str]] = set()

    for path in sorted(_root.rglob("*.py")):
        discovered_classes |= _scan_file(path, _root, _allow, violations)

    _check_allowlist(
        _allow, _root, violations, discovered_classes, production=production
    )
    return violations


def main() -> int:
    violations = run_lint()
    crit = [v for v in violations if v.startswith("CRIT|")]
    warn = [v for v in violations if v.startswith("WARN|")]
    if crit:
        print(f"[MEM-ANTI-BOND] CRIT={len(crit)}, WARN={len(warn)}")
        for v in crit[:10]:
            print(f"  - {v}")
        return 1
    if warn:
        print(f"[MEM-ANTI-BOND] WARN={len(warn)} (invariant PASS, сигнал)")
        for v in warn[:10]:
            print(f"  - {v}")
        return 0
    print("[MEM-ANTI-BOND] OK: 0 CRIT, 0 WARN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

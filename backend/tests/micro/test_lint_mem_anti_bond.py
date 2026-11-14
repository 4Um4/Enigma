"""Tests for INV-MEM-ANTI-BOND (#12), design v6 + fix A.

All 42 test cases T01–T42.
T17/T18 expect [] (no WARN) per decision A.
"""
import sys
from pathlib import Path

import pytest

_SCRIPTS = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import lint_mem_anti_bond as lint_module  # noqa: E402
from lint_mem_anti_bond import run_lint  # noqa: E402


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _crit(result: list[str]) -> list[str]:
    return [v for v in result if v.startswith("CRIT|")]


def _warn(result: list[str]) -> list[str]:
    return [v for v in result if v.startswith("WARN|")]


# ============================================================
# Class A — direct bond (CRIT)
# ============================================================
@pytest.mark.parametrize("store_name", [
    "MemoryStore", "BeliefStore", "NarrativeStore", "BiographyStore",
    "EpisodicMemoryStore", "PlayerBeliefStore", "NpcRelationshipStore", "MemoryCrystalStore",
])
def test_t01_t08_class_a_direct_bond_crit(tmp_path, store_name):
    _write(tmp_path, "m.py", f"class {store_name}:\n    pass\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for {store_name}: {r}"


# ============================================================
# Class B — indirect (WARN)
# ============================================================
@pytest.mark.parametrize("store_name", [
    "CacheStore", "ConfigStore", "SessionStore", "KitchenStore",
])
def test_t09_t12_class_b_indirect_warn(tmp_path, store_name):
    _write(tmp_path, "m.py", f"class {store_name}:\n    pass\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) and not _crit(r), f"expected WARN not CRIT for {store_name}: {r}"


# ============================================================
# Class C — dynamic registration
# ============================================================
@pytest.mark.parametrize("stmt", [
    'setattr(module, "BeliefStore", cls)\n',
    'module.__setattr__("BeliefStore", cls)\n',
    '__setattr__(module, "BeliefStore", cls)\n',
    'MemoryStore = type("MemoryStore", (BaseStore,), {})\n',
])
def test_t13_t16_class_c_literal_crit(tmp_path, stmt):
    _write(tmp_path, "m.py", stmt)
    r = run_lint(root=tmp_path)
    assert _crit(r), f"expected CRIT for {stmt!r}: {r}"


def test_t17_class_c_non_literal_setattr_empty(tmp_path):
    _write(tmp_path, "m.py", 'name = get_name()\nsetattr(module, name, cls)\n')
    r = run_lint(root=tmp_path)
    assert r == [], f"non-literal setattr must be [] (no WARN): {r}"


def test_t18_class_c_non_literal_type_empty(tmp_path):
    _write(tmp_path, "m.py", 'name = get_name()\ntype(name, (BaseStore,), {})\n')
    r = run_lint(root=tmp_path)
    assert r == [], f"non-literal type() must be [] (no WARN): {r}"


# ============================================================
# Not-a-store
# ============================================================
@pytest.mark.parametrize("cls", ["MemoryManager", "WorkingMemory", "MemoryCrystal"])
def test_t19_t21_not_a_store_ignored(tmp_path, cls):
    _write(tmp_path, "m.py", f"class {cls}:\n    pass\n")
    r = run_lint(root=tmp_path)
    assert r == [], f"{cls} must be ignored: {r}"


# ============================================================
# Allowlist
# ============================================================
def test_t22_allowlist_exact_match_passes(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "approved",
        "adr": "ADR-O-TEST",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert r == [], f"exact allowlist match must pass: {r}"


def test_t23_allowlist_missing_adr_crit(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "approved",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"missing adr must CRIT: {r}"


def test_t24_allowlist_legacy_missing_hist_crit(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "legacy_baseline",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"missing historical_basis must CRIT: {r}"


def test_t25_allowlist_invalid_status_crit(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "bogus",
        "rationale": "test",
        "adr": "ADR-O-TEST"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"invalid status must CRIT: {r}"


def test_t26_allowlist_orphan_crit(tmp_path):
    _write(tmp_path, "m.py", "class OtherStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "approved",
        "adr": "ADR-O-TEST",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ORPHAN" in v for v in _crit(r)), f"orphan must CRIT: {r}"


def test_t27_allowlist_invalid_role_crit(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "bogus_role",
        "status": "approved",
        "adr": "ADR-O-TEST",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"invalid role must CRIT: {r}"


# T33-T36 (legacy/approved constraints)
def test_t33_legacy_for_new_key_crit(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "legacy_baseline",
        "historical_basis": "new key",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"legacy for non-baseline must CRIT: {r}"


def test_t34_approved_on_legacy_crit(tmp_path, monkeypatch):
    # take a real legacy key
    key = ("services/memory/sqlite_store.py", "SqliteMemoryStore")
    _write(tmp_path, "m.py", f"class {key[1]}:\n    pass\n")
    # allowlist includes approved status for legacy key
    allow = {key: {
        "role": "memory_backend_primary",
        "status": "approved",
        "adr": "ADR-O-TEST",
        "rationale": "test"
    }}
    # Need to monkeypatch LEGACY_BASELINE_KEYS? No, key is in real LEGACY_BASELINE_KEYS,
    # so approved on legacy triggers ALLOWLIST_MALFORMED (B5.3).
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"approved on legacy must CRIT: {r}"


def test_t35_approved_with_both_adr_and_hist_crit(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStore:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "approved",
        "adr": "ADR-O-TEST",
        "historical_basis": "also present",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"both adr+hist must CRIT: {r}"


def test_t36_legacy_with_adr_crit(tmp_path):
    # Use a real legacy key to pass first check
    key = ("services/memory/sqlite_store.py", "SqliteMemoryStore")
    _write(tmp_path, "m.py", f"class {key[1]}:\n    pass\n")
    allow = {key: {
        "role": "memory_backend_primary",
        "status": "legacy_baseline",
        "adr": "ADR-O-TEST",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), f"legacy with adr must CRIT: {r}"


# ============================================================
# Robustness
# ============================================================
def test_t28_syntax_error_crit(tmp_path):
    _write(tmp_path, "m.py", "def broken(:\n")
    r = run_lint(root=tmp_path)
    assert any("PARSE_ERROR" in v for v in _crit(r)), f"syntax error must CRIT: {r}"


def test_t29_binary_encoding_crit(tmp_path):
    p = tmp_path / "m.py"
    p.write_bytes(b"\xff\xfe\x00bad")
    r = run_lint(root=tmp_path)
    assert any(("UNREADABLE" in v or "PARSE_ERROR" in v) for v in _crit(r)), f"bad encoding must CRIT: {r}"


def test_t30_baseline_production_empty():
    result = run_lint()
    assert result == [], f"production baseline != []: {result[:5]}"


# ============================================================
# Frozen baseline
# ============================================================
def test_t31_allowlist_frozen_keys():
    expected = {
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
    }
    assert set(lint_module.ALLOWLIST.keys()) == expected


def test_t32_allowlist_frozen_roles():
    expected_roles = {
        ("services/memory/sqlite_store.py", "SqliteMemoryStore"): "memory_backend_primary",
        ("services/memory/layered_memory.py", "JsonMemoryStore"): "memory_backend_legacy",
        ("services/memory/relationship_store.py", "RelationshipStore"): "relationship_backend_legacy",
        ("services/social/relationship_state_store.py", "RelationshipStateStore"): "relationship_backend_v2",
        ("services/npc/conclusion_store.py", "ConclusionStore"): "belief_conclusion",
        ("services/npc/crystallized_belief_store.py", "CrystallizedBeliefStore"): "belief_crystallized",
        ("services/npc/epistemic_store.py", "EpistemicStore"): "belief_epistemic",
        ("services/npc/expectation_store.py", "ContextualExpectationStore"): "expectation",
        ("services/chronicle/chronicle_store.py", "ChronicleStore"): "chronicle",
        ("services/world/world_object_store.py", "WorldObjectStore"): "world_object",
        ("services/replay/replay_store.py", "ReplayStore"): "infra_replay",
    }
    actual = {k: v["role"] for k, v in lint_module.ALLOWLIST.items()}
    assert actual == expected_roles


def test_t37_legacy_baseline_frozen_keys():
    expected = {
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
    }
    assert lint_module.LEGACY_BASELINE_KEYS == frozenset(expected)


# ============================================================
# ORPHAN AST precision
# ============================================================
def test_t38_orphan_memorystoreextra(tmp_path):
    _write(tmp_path, "m.py", "class MemoryStoreExtra:\n    pass\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "approved",
        "adr": "ADR-O-TEST",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ORPHAN" in v for v in _crit(r)), f"MemoryStoreExtra must not satisfy MemoryStore: {r}"


def test_t39_orphan_comment_or_docstring(tmp_path):
    # comment
    _write(tmp_path, "m.py", "# class MemoryStore\n")
    allow = {("m.py", "MemoryStore"): {
        "role": "memory_backend_primary",
        "status": "approved",
        "adr": "ADR-O-TEST",
        "rationale": "test"
    }}
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ORPHAN" in v for v in _crit(r)), f"comment must not satisfy: {r}"
    # docstring
    _write(tmp_path, "m.py", '"""class MemoryStore"""\n')
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ORPHAN" in v for v in _crit(r)), f"docstring must not satisfy: {r}"
    # string literal
    _write(tmp_path, "m.py", 'x = "class MemoryStore"\n')
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ORPHAN" in v for v in _crit(r)), f"string literal must not satisfy: {r}"


# ============================================================
# Production sanity (B9)
# ============================================================
def test_t40_production_sanity_default_no_mismatch():
    r = run_lint()  # production=True, consistent config
    assert not any("KEYS_MISMATCH" in v for v in r), f"unexpected KEYS_MISMATCH: {r}"


def test_t41_explicit_allowlist_bypasses_sanity(monkeypatch):
    # deliberately break LEGACY_BASELINE_KEYS (add extra key)
    extra = ("fake/path.py", "FakeStore")
    new_set = frozenset(lint_module.LEGACY_BASELINE_KEYS | {extra})
    monkeypatch.setattr(lint_module, "LEGACY_BASELINE_KEYS", new_set)
    # explicit allowlist -> production=False, sanity skipped
    r = run_lint(allowlist=dict(lint_module.ALLOWLIST))
    assert not any("KEYS_MISMATCH" in v for v in r), f"explicit allowlist must bypass sanity: {r}"


def test_t42_production_sanity_catches_mismatch(monkeypatch):
    extra = ("fake/path.py", "FakeStore")
    new_set = frozenset(lint_module.LEGACY_BASELINE_KEYS | {extra})
    monkeypatch.setattr(lint_module, "LEGACY_BASELINE_KEYS", new_set)
    r = run_lint()  # production=True
    assert any("KEYS_MISMATCH" in v for v in r), f"must catch KEYS_MISMATCH: {r}"

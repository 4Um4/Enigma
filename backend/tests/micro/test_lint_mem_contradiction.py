"""INV-MEM-CONTRADICTION (#10) — 50 tests.

49 from design v2 matrix + 1 invariant-WARN semantic (Master technical #3).
"""

import sys
from pathlib import Path

import pytest

_SCRIPTS = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import lint_mem_contradiction as lint_module
from lint_mem_contradiction import run_lint


def _write(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _crit(result):
    return [v for v in result if v.startswith("CRIT|")]


def _warn(result):
    return [v for v in result if v.startswith("WARN|")]


# ============================================================
# A-1 Identifier positives — 11 (T01-T11)
# ============================================================
def test_t01_name_id(tmp_path):
    _write(tmp_path, "m.py", "latest_wins = 1\n")
    assert _crit(run_lint(root=tmp_path))


def test_t02_name_casefold(tmp_path):
    _write(tmp_path, "m.py", "LATEST_WINS = 1\n")
    assert _crit(run_lint(root=tmp_path))


def test_t03_arg_arg(tmp_path):
    _write(tmp_path, "m.py", "def f(highest_confidence_wins):\n    pass\n")
    assert _crit(run_lint(root=tmp_path))


def test_t04_attribute_attr(tmp_path):
    _write(tmp_path, "m.py", "obj.latest_wins = 1\n")
    assert _crit(run_lint(root=tmp_path))


def test_t05_keyword_arg(tmp_path):
    _write(tmp_path, "m.py", "g(latest_wins=True)\n")
    assert _crit(run_lint(root=tmp_path))


def test_t06_alias_dotted_crit(tmp_path):
    # Master technical #1: dotted import component
    _write(tmp_path, "m.py", "import latest_wins.module\n")
    assert _crit(run_lint(root=tmp_path))


def test_t06b_from_module_crit(tmp_path):
    # Stage 1.5 defensive: from <forbidden> import
    _write(tmp_path, "m.py", "from latest_wins import x\n")
    assert _crit(run_lint(root=tmp_path))


def test_t07_alias_asname(tmp_path):
    _write(tmp_path, "m.py", "from x import y as latest_wins\n")
    assert _crit(run_lint(root=tmp_path))


def test_t08_function_name(tmp_path):
    _write(tmp_path, "m.py", "def latest_wins():\n    pass\n")
    assert _crit(run_lint(root=tmp_path))


def test_t09_class_name(tmp_path):
    _write(tmp_path, "m.py", "class highest_confidence_wins:\n    pass\n")
    assert _crit(run_lint(root=tmp_path))


def test_t10_global(tmp_path):
    _write(tmp_path, "m.py", "def f():\n    global latest_wins\n    latest_wins = 1\n")
    assert _crit(run_lint(root=tmp_path))


def test_t11_nonlocal(tmp_path):
    _write(
        tmp_path,
        "m.py",
        "def outer():\n    x = 0\n    def inner():\n        nonlocal x\n        x = 1\n    return inner\n",
    )
    # no forbidden here — use a forbidden nonlocal
    _write(
        tmp_path,
        "m.py",
        "def outer():\n    latest_wins = 0\n    def inner():\n        nonlocal latest_wins\n        latest_wins = 1\n    return inner\n",
    )
    assert _crit(run_lint(root=tmp_path))


# ============================================================
# A-1 negatives — 6 (T12-T17)
# ============================================================
@pytest.mark.parametrize(
    "code",
    [
        "latest_event_id = 1\n",
        "my_latest_wins_cache = {}\n",
        "highest_confidence = 0.9\n",
    ],
)
def test_t12_t14_substring_negatives(tmp_path, code):
    _write(tmp_path, "m.py", code)
    assert run_lint(root=tmp_path) == []


@pytest.mark.parametrize(
    "code",
    [
        "resolve_all = None\n",
        "confidence = 0.5\n",
        "get_latest_wins = None\n",
    ],
)
def test_t15_t17_extra_negatives(tmp_path, code):
    _write(tmp_path, "m.py", code)
    assert run_lint(root=tmp_path) == []


# ============================================================
# A-2 String literals — 8 (T18-T25)
# ============================================================
def test_t18_string_latest_wins(tmp_path):
    _write(tmp_path, "m.py", 'policy = "latest_wins"\n')
    assert _crit(run_lint(root=tmp_path))


def test_t19_string_hyphen(tmp_path):
    _write(tmp_path, "m.py", 'policy = "latest-wins"\n')
    assert _crit(run_lint(root=tmp_path))


def test_t20_string_casefold(tmp_path):
    _write(tmp_path, "m.py", 'policy = "LATEST_WINS"\n')
    assert _crit(run_lint(root=tmp_path))


def test_t21_string_highest_hyphen(tmp_path):
    _write(tmp_path, "m.py", 's = "highest-confidence-wins"\n')
    assert _crit(run_lint(root=tmp_path))


def test_t22_string_resolve_all_neg(tmp_path):
    _write(tmp_path, "m.py", 's = "resolve_all"\n')
    assert run_lint(root=tmp_path) == []


def test_t23_string_confidence_neg(tmp_path):
    _write(tmp_path, "m.py", 's = "confidence"\n')
    assert run_lint(root=tmp_path) == []


def test_t24_comment_neg(tmp_path):
    _write(tmp_path, "m.py", "# latest_wins\nx = 1\n")
    assert run_lint(root=tmp_path) == []


def test_t25_docstring_neg(tmp_path):
    _write(tmp_path, "m.py", '"""latest_wins"""\nx = 1\n')
    assert run_lint(root=tmp_path) == []


# ============================================================
# C-1 Class prefix (services/memory/) — 4 (T26-T29)
# ============================================================
def test_t26_conf_resolution_crit(tmp_path):
    _write(tmp_path, "services/memory/x.py", "class ConfidenceResolution:\n    pass\n")
    assert _crit(run_lint(root=tmp_path))


def test_t27_auto_resolver_crit(tmp_path):
    _write(tmp_path, "services/memory/x.py", "class AutoResolver:\n    pass\n")
    assert _crit(run_lint(root=tmp_path))


def test_t28_auto_resolution_crit(tmp_path):
    _write(tmp_path, "services/memory/x.py", "class AutoResolution:\n    pass\n")
    assert _crit(run_lint(root=tmp_path))


def test_t29_contradiction_resolver_not_prefix(tmp_path):
    _write(tmp_path, "services/memory/x.py", "class ContradictionResolver:\n    pass\n")
    assert run_lint(root=tmp_path) == []


# ============================================================
# C-2 Heuristic Resolver — 5 (T30-T34)
# ============================================================
def test_t30_resolver_with_method_warn(tmp_path):
    _write(tmp_path, "services/memory/x.py", "class FooResolver:\n    def resolve_conflict(self):\n        pass\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) and not _crit(r), r


def test_t31_resolver_with_field_warn(tmp_path):
    _write(tmp_path, "services/memory/x.py", "class FooResolver:\n    pick_winner = None\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) and not _crit(r), r


def test_t32_resolver_no_markers_pass(tmp_path):
    _write(tmp_path, "services/memory/x.py", "class FooResolver:\n    def other(self):\n        pass\n")
    assert run_lint(root=tmp_path) == []


def test_t33_nested_class_no_inherit(tmp_path):
    # outer no own marker; nested has marker -> outer not WARN
    _write(
        tmp_path,
        "services/memory/x.py",
        "class FooResolver:\n    class Bar:\n        def resolve_conflict(self):\n            pass\n",
    )
    assert run_lint(root=tmp_path) == []


def test_t34_resolver_outside_memory_pass(tmp_path):
    _write(tmp_path, "services/npc/x.py", "class FooResolver:\n    def resolve_conflict(self):\n        pass\n")
    assert run_lint(root=tmp_path) == []


# ============================================================
# Robustness — 3 (T35-T37)
# ============================================================
def test_t35_syntax_error_crit(tmp_path):
    _write(tmp_path, "m.py", "def broken(:\n")
    r = run_lint(root=tmp_path)
    assert any("PARSE_ERROR" in v for v in _crit(r))


def test_t36_binary_crit(tmp_path):
    (tmp_path / "m.py").write_bytes(b"\xff\xfe\x00bad")
    r = run_lint(root=tmp_path)
    assert any(("UNREADABLE" in v or "PARSE_ERROR" in v) for v in _crit(r))


def test_t37_deep_nested_crit(tmp_path):
    _write(tmp_path, "deep/a/b/c/m.py", "latest_wins = 1\n")
    assert _crit(run_lint(root=tmp_path))


# ============================================================
# Allowlist — 5 (T38-T42)
# ============================================================
def test_t38_allowlist_exact_pass(tmp_path):
    _write(tmp_path, "m.py", "latest_wins = 1\n")
    allow = {
        ("m.py", "identifier", "latest_wins"): {
            "status": "approved",
            "role": "identifier_legacy",
            "adr": "ADR-O-TEST",
            "rationale": "test",
        }
    }
    assert run_lint(root=tmp_path, allowlist=allow) == []


def test_t39_allowlist_no_adr_crit(tmp_path):
    _write(tmp_path, "m.py", "latest_wins = 1\n")
    allow = {
        ("m.py", "identifier", "latest_wins"): {
            "status": "approved",
            "role": "identifier_legacy",
            "rationale": "test",
        }
    }
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r))


def test_t40_legacy_for_non_baseline_crit(tmp_path):
    _write(tmp_path, "m.py", "latest_wins = 1\n")
    allow = {
        ("m.py", "identifier", "latest_wins"): {
            "status": "legacy_baseline",
            "role": "identifier_legacy",
            "historical_basis": "new",
            "rationale": "test",
        }
    }
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r))


def test_t41_approved_on_legacy_crit(tmp_path, monkeypatch):
    key = ("services/memory/x.py", "identifier", "latest_wins")
    _write(tmp_path, "services/memory/x.py", "latest_wins = 1\n")
    # Temporarily treat this key as legacy baseline (B5.3 check):
    # approved on legacy -> ALLOWLIST_MALFORMED.
    monkeypatch.setattr(lint_module, "LEGACY_BASELINE_KEYS", frozenset({key}))
    allow = {
        key: {
            "status": "approved",
            "role": "identifier_legacy",
            "adr": "ADR-O-TEST",
            "rationale": "test",
        }
    }
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ALLOWLIST_MALFORMED" in v for v in _crit(r)), r


def test_t42_orphan_crit(tmp_path):
    _write(tmp_path, "m.py", "x = 1\n")
    allow = {
        ("m.py", "identifier", "latest_wins"): {
            "status": "approved",
            "role": "identifier_legacy",
            "adr": "ADR-O-TEST",
            "rationale": "test",
        }
    }
    r = run_lint(root=tmp_path, allowlist=allow)
    assert any("ORPHAN" in v for v in _crit(r))


# ============================================================
# Frozen baseline — 2 (T43-T44)
# ============================================================
def test_t43_allowlist_frozen_keys():
    assert set(lint_module.ALLOWLIST.keys()) == set()


def test_t44_legacy_frozen_keys():
    assert lint_module.LEGACY_BASELINE_KEYS == frozenset()


# ============================================================
# Production baseline — 1 (T45)
# ============================================================
def test_t45_baseline_empty():
    assert run_lint() == []


# ============================================================
# T46 Live files no violation — 4 cases
# ============================================================
@pytest.mark.parametrize(
    "real_file",
    [
        "backend/app/services/memory/contradiction_resolver.py",
        "backend/app/services/phases/integration.py",
        "backend/app/models/npc/beliefs.py",
        "backend/app/services/npc/npc_tick_pipeline.py",
    ],
)
def test_t46_live_files_clean(tmp_path, real_file):
    root = Path(__file__).resolve().parents[3]
    p = root / real_file
    if not p.exists():
        pytest.skip(f"missing {real_file}")
    src = p.read_text(encoding="utf-8", errors="replace")
    rel = real_file.replace("backend/app/", "")
    _write(tmp_path, rel, src)
    r = run_lint(root=tmp_path)
    assert r == [], f"{real_file} -> {r}"


# ============================================================
# Master technical #3: invariant-WARN semantic (not CRITICAL)
# ============================================================
def test_invariant_warn_does_not_fail(monkeypatch):
    """WARN-only must yield InvariantResult(passed=True, severity=WARNING)."""
    # Import IPT lazily
    from backend.tests import IPT

    # Patch run_lint in lint module to return WARN only
    monkeypatch.setattr(lint_module, "run_lint", lambda: ["WARN|x.py:1|heuristic"])
    result = IPT.inv_mem_contradiction(None)
    assert result.passed is True, result
    assert result.severity == "WARNING", result
    assert "WARN" in result.message

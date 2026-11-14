"""INV-MEM-TRIPLE (#1) — v7.1 narrow tests.

Coverage: A-1 (NPCState field write), A-2 (BeliefState.update), A-3 (setattr),
B8 (narrow skip: setattr in own __setattr__), V3-Q1 (narrow skip: setattr
in frozen __post_init__), construction WARN, scope/walrus/annotation/infer.
Baseline: 10 CRIT in life_project_resolver = MEM-TRIPLE-DEBT-01 (accepted).
"""
import sys
from pathlib import Path

import pytest

_SCRIPTS = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import lint_mem_triple as lint_module
from lint_mem_triple import run_lint


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _crit(result):
    return [v for v in result if v.startswith("CRIT|")]


def _warn(result):
    return [v for v in result if v.startswith("WARN|")]


# ============================================================
# A-1 NPCState field write
# ============================================================
def test_a1_authorized_module_authorized_field_pass(tmp_path):
    # module = app.services.npc.state_applicator (ALLOWED_WRITERS: "*")
    _write(tmp_path, "services/npc/state_applicator.py",
           "from app.models.npc_state import NPCState\n"
           "def apply(state: NPCState):\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], r


def test_a1_authorized_module_unauthorized_field_crit(tmp_path):
    # belief_transition_engine: _ALLOWED_WRITERS = {"beliefs"}
    _write(tmp_path, "services/npc/belief_transition_engine.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), r


def test_a1_unauthorized_module_crit(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    state.narrative_cache = ()\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), r


def test_a1_unknown_type_pass(tmp_path):
    # `state` no annotation, no evidence -> PASS (residual)
    _write(tmp_path, "services/random.py",
           "def f(state):\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    assert r == [], r


def test_a1_evidence_conflicted_warn(tmp_path):
    # `state = NPCState(); state = {}; state.stress = 10` -> WARN
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f():\n"
           "    state = NPCState()\n"
           "    state = {}\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) and not _crit(r), r


def test_a1_augassign_crit(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    state.stress += 5\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), r


def test_a1_annassign_crit(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    state.stress: float = 10\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), r


# ============================================================
# A-2 BeliefState.update
# ============================================================
def test_a2_authorized_module_pass(tmp_path):
    # _UPDATE_ALLOWED_WRITERS includes state_applicator, belief_aggregator, etc.
    _write(tmp_path, "services/npc/state_applicator.py",
           "from app.models.npc.beliefs import BeliefState\n"
           "def f(b: BeliefState, k, v):\n"
           "    b.update(k, v)\n")
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], r


def test_a2_unauthorized_module_crit(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc.beliefs import BeliefState\n"
           "def f(b: BeliefState, k, v):\n"
           "    b.update(k, v)\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), r


def test_a2_dict_update_pass(tmp_path):
    # `cache` unknown type -> PASS (no evidence)
    _write(tmp_path, "services/random.py",
           "def f(cache, k, v):\n"
           "    cache.update({k: v})\n")
    r = run_lint(root=tmp_path)
    assert r == [], r


def test_a2_evidence_conflicted_warn(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc.beliefs import BeliefState\n"
           "def f(k, v):\n"
           "    b = BeliefState()\n"
           "    b = {}\n"
           "    b.update(k, v)\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) and not _crit(r), r


# ============================================================
# A-3 object.__setattr__
# ============================================================
def test_a3_unknown_target_pass(tmp_path):
    _write(tmp_path, "services/random.py",
           "def f(obj):\n"
           "    object.__setattr__(obj, 'x', 1)\n")
    r = run_lint(root=tmp_path)
    assert r == [], r


def test_a3_npcstate_evidence_crit(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    object.__setattr__(state, 'stress', 10)\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), r


def test_a3_authorized_module_pass(tmp_path):
    _write(tmp_path, "services/npc/state_applicator.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    object.__setattr__(state, 'stress', 10)\n")
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], r


def test_a3_beliefstate_setattr_warn(tmp_path):
    # BeliefState `object.__setattr__` -> WARN (no authority)
    _write(tmp_path, "services/random.py",
           "from app.models.npc.beliefs import BeliefState\n"
           "def f(b: BeliefState):\n"
           "    object.__setattr__(b, 'x', 1)\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) and not _crit(r), r


def test_a3_npcstate_evidence_conflicted_warn(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f():\n"
           "    s = NPCState()\n"
           "    s = {}\n"
           "    object.__setattr__(s, 'stress', 10)\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) and not _crit(r), r


# ============================================================
# B8 — narrow skip in own __setattr__
# ============================================================
def test_b8_npcstate_own_setattr_skip(tmp_path):
    # NPCState.__setattr__ pattern: object.__setattr__(self, name, value)
    _write(tmp_path, "models/npc_state.py",
           "from dataclasses import dataclass\n"
           "@dataclass\n"
           "class NPCState:\n"
           "    x: int = 0\n"
           "    def __setattr__(self, name, value):\n"
           "        object.__setattr__(self, name, value)\n")
    r = run_lint(root=tmp_path)
    # No CRIT — should be skipped as internal writer-guard impl
    assert _crit(r) == [], r


def test_b8_literal_field_not_skip_crit(tmp_path):
    # literal field in __setattr__ -> CRIT (not narrow pattern).
    # Path intentionally outside domain module: 'models/npc_state.py' maps
    # to 'app.models.npc_state' (authority '*') and would silence CRIT via
    # registry. Class defined inline so _infer('self') still sees NPCState.
    _write(tmp_path, "models/custom_npc.py",
           "from dataclasses import dataclass\n"
           "@dataclass\n"
           "class NPCState:\n"
           "    stress: float = 0.0\n"
           "    def __setattr__(self, name, value):\n"
           "        object.__setattr__(self, 'stress', value)\n")
    r = run_lint(root=tmp_path)
    # CRIT — literal field bypass (not narrow)
    assert _crit(r), r


def test_b8_other_method_not_skip(tmp_path):
    # object.__setattr__(self, name, value) in non-__setattr__ -> CRIT/WARN
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    name = 'stress'\n"
           "    object.__setattr__(state, name, 10)\n")
    r = run_lint(root=tmp_path)
    # `state` evidence NPCState, unknown field name -> WARN (non-literal field)
    assert _warn(r) and not _crit(r), r


# ============================================================
# V3-Q1 — skip only in __post_init__ of frozen=True
# ============================================================
def test_v3q1_frozen_post_init_pass(tmp_path):
    _write(tmp_path, "models/x.py",
           "from dataclasses import dataclass\n"
           "@dataclass(frozen=True)\n"
           "class Foo:\n"
           "    x: int = 0\n"
           "    def __post_init__(self):\n"
           "        object.__setattr__(self, 'x', 1)\n")
    r = run_lint(root=tmp_path)
    assert _crit(r) == [], r


def test_v3q1_mutable_post_init_crit_or_warn(tmp_path):
    # frozen=False -> no skip -> not in registry -> WARN (unknown field? or CRIT?)
    _write(tmp_path, "models/x.py",
           "from dataclasses import dataclass\n"
           "@dataclass\n"
           "class Foo:\n"
           "    x: int = 0\n"
           "    def __post_init__(self):\n"
           "        object.__setattr__(self, 'x', 1)\n")
    r = run_lint(root=tmp_path)
    # Not guarded class (Foo) -> PASS (unknown evidence) per narrowing
    assert r == [], r


# ============================================================
# Construction WARN
# ============================================================
def test_construction_unauthorized_warn(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "s = NPCState()\n")
    r = run_lint(root=tmp_path)
    assert _warn(r), r


def test_construction_authorized_pass(tmp_path):
    _write(tmp_path, "services/npc/npc_loader.py",
           "from app.models.npc_state import NPCState\n"
           "s = NPCState()\n")
    r = run_lint(root=tmp_path)
    assert _warn(r) == [], r


# ============================================================
# Scope inference
# ============================================================
def test_scope_nested_function_isolated(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def outer():\n"
           "    state = NPCState()\n"
           "    def inner():\n"
           "        state = {}\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    # outer: state = NPCState (1 assignment); inner `state = {}` isolated
    assert _crit(r), r


def test_scope_conditional_assign_warn(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f(flag):\n"
           "    if flag:\n"
           "        state = NPCState()\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    # conditional_binding -> infer returns NPCState? no — cond=True -> WARN
    assert _warn(r) and not _crit(r), r


def test_scope_walrus_invalidates(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f():\n"
           "    state = NPCState()\n"
           "    (state := NPCState())\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    # walrus -> has_namedexpr=True -> unknown -> WARN
    assert _warn(r) and not _crit(r), r


def test_scope_annotated_param_proves(tmp_path):
    _write(tmp_path, "services/random.py",
           "from app.models.npc_state import NPCState\n"
           "def f(state: NPCState):\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    assert _crit(r), r


def test_scope_unannotated_param_unknown(tmp_path):
    _write(tmp_path, "services/random.py",
           "def f(state):\n"
           "    state.stress = 10\n")
    r = run_lint(root=tmp_path)
    assert r == [], r


# ============================================================
# Authority extraction
# ============================================================
def test_extraction_authority_loaded():
    auth, errs = lint_module._extract_all()
    assert errs == [], errs
    npc_reg = auth.get("NPCState")
    assert npc_reg is not None, "NPCState registry should extract"
    assert "app.services.npc.state_applicator" in npc_reg
    assert npc_reg["app.services.npc.state_applicator"] == {"*"}
    belief_reg = auth.get("BeliefState")
    assert belief_reg is not None
    assert "app.services.npc.state_applicator" in belief_reg
    pk_reg = auth.get("PerceptualKernel")
    assert pk_reg is not None


# ============================================================
# Construction snapshot
# ============================================================
def test_construction_snapshot_modules():
    assert lint_module.AUTHORIZED_CONSTRUCTION_MODULES["NPCState"] == frozenset({
        "app.models.npc_state", "app.services.npc.npc_loader",
        "app.services.player_avatar_service",
    })
    assert lint_module.AUTHORIZED_CONSTRUCTION_MODULES["BeliefState"] == frozenset({
        "app.services.npc.npc_loader",
    })
    assert "app.services.chronicle.chronicle_seeder" in lint_module.AUTHORIZED_CONSTRUCTION_MODULES["EventMemory"]


# ============================================================
# Baseline — MEM-TRIPLE-DEBT-01 (10 CRIT in life_project_resolver)
# ============================================================
def test_baseline_10_crit_in_life_project_resolver():
    """Baseline on HEAD: exactly 10 CRIT in life_project_resolver (MEM-TRIPLE-DEBT-01).

    This is REAL PRODUCTION DEBT per Master verdict, not allowlisted.
    """
    result = run_lint()
    crit = _crit(result)
    warn = _warn(result)
    assert len(crit) == 10, f"expected 10 CRIT (MEM-TRIPLE-DEBT-01), got {len(crit)}: {crit[:5]}"
    assert all("services/npc/life_project_resolver.py" in c for c in crit), \
        f"all CRIT should be in life_project_resolver: {crit[:3]}"
    assert len(warn) == 0, f"expected 0 WARN (narrowed), got {len(warn)}: {warn[:5]}"

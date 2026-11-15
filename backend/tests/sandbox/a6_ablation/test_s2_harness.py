"""A6 S2 harness tests — patch/restore + probe + scope (variant C: 2 of 4)."""

import hashlib
import shutil
from pathlib import Path

import pytest

from tests.sandbox.a6_ablation.s2_patch import (
    _ALLIES_MARKER,
    _PATCHED_ALLIES,
    _PROUDUCER_MARKERS,
    _REPLACED_COUNT,
    apply_patch,
    restore_patch,
)
from tests.sandbox.a6_ablation.s2_probe import (
    _PRODUCER_TAGS,
    probe_producer_calls,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ── Scope tests (variant C) ──────────────────────────────────────────────


def test_scope_two_producers_threat_and_grievance():
    markers = [tag for _, tag in _PROUDUCER_MARKERS]
    assert markers == ["threat", "grievance"], markers
    assert "hunger" not in markers
    assert "affection" not in markers
    assert _REPLACED_COUNT == 2


def test_probe_scope_two_producers():
    tags = [tag for _, tag in _PRODUCER_TAGS]
    assert tags == ["threat", "grievance"], tags


# ── Probe tests ──────────────────────────────────────────────────────────


def test_probe_captures_threat_and_grievance_calls():
    from app.services.npc.causal_slice_threat import ThreatDesiredChangeProducer
    from app.services.npc.causal_slice_grievance import GrievanceDesiredChangeProducer

    class _State:
        npc_id = "test_npc"
        tick_id = 42

    with probe_producer_calls() as captured:
        ThreatDesiredChangeProducer.resolve(
            state=_State(),
            rel={},
            disposition={},
            allies=3,
            belief_source=None,
        )
        GrievanceDesiredChangeProducer.resolve(
            who="test_npc2",
            state=_State(),
            rel={},
            disposition={},
            allies=2,
        )

    assert len(captured) == 2
    c1, c2 = captured
    assert c1.tag == "threat" and c1.npc_id == "test_npc" and c1.tick_id == 42 and c1.allies == 3
    assert c2.tag == "grievance" and c2.npc_id == "test_npc2" and c2.allies == 2


def test_probe_restores_2_producers():
    originals = {cls: cls.__dict__["resolve"] for cls, _ in _PRODUCER_TAGS}
    with probe_producer_calls():
        pass
    for cls, orig in originals.items():
        assert cls.__dict__["resolve"] is orig


def test_probe_restores_on_exception():
    originals = {cls: cls.__dict__["resolve"] for cls, _ in _PRODUCER_TAGS}
    with pytest.raises(RuntimeError):
        with probe_producer_calls():
            raise RuntimeError("boom")
    for cls, orig in originals.items():
        assert cls.__dict__["resolve"] is orig


# ── Patch/restore tests (2-producer fake) ────────────────────────────────

_FAKE_SRC = """# fake pipeline
import logging
from app.services.npc.causal_slice_threat import ThreatDesiredChangeProducer
from app.services.npc.causal_slice_grievance import GrievanceDesiredChangeProducer

logger = logging.getLogger(__name__)


def run(state, npc_id, _epistemic_ctx):
    _dc = ThreatDesiredChangeProducer.resolve(
        state=state,
        rel={},
        disposition={},
        allies=0,
        belief_source=None,
    )
    _dc_g = GrievanceDesiredChangeProducer.resolve(
        who=npc_id,
        state=state,
        rel={},
        disposition={},
        allies=0,
    )
"""


def _write_fake(tmp_path: Path) -> Path:
    src = tmp_path / "fake_pipeline.py"
    src.write_bytes(_FAKE_SRC.encode("utf-8"))
    return src


def test_apply_restore_cycle_byte_exact(tmp_path):
    src = _write_fake(tmp_path)
    sha_before = _sha256(src)
    state = apply_patch(src, backup_dir=tmp_path)
    try:
        assert state.sha_pre == sha_before
        assert state.sha_patched != state.sha_pre
        assert _sha256(src) == state.sha_patched
        assert _sha256(state.backup_path) == state.sha_pre
        patched_text = src.read_text(encoding="utf-8")
        assert patched_text.count("_a6_allies = len(") == 2
        assert patched_text.count("allies=_a6_allies,") == 2
        assert patched_text.count("allies=0,") == 0
    finally:
        sha_post = restore_patch(state)
    assert sha_post == state.sha_pre
    assert _sha256(src) == sha_before


def test_restore_idempotent(tmp_path):
    src = _write_fake(tmp_path)
    state = apply_patch(src, backup_dir=tmp_path)
    sha1 = restore_patch(state)
    sha2 = restore_patch(state)
    assert sha1 == sha2 == state.sha_pre


def test_restore_aborts_on_parallel_edit(tmp_path):
    src = _write_fake(tmp_path)
    state = apply_patch(src, backup_dir=tmp_path)
    src.write_bytes(src.read_bytes() + b"\n# parallel edit\n")
    try:
        with pytest.raises(RuntimeError, match="parallel edit"):
            restore_patch(state)
    finally:
        shutil.copy2(state.backup_path, src)


def test_apply_patch_requires_markers(tmp_path):
    src = tmp_path / "bad.py"
    src.write_bytes(b"# no markers\n")
    with pytest.raises(RuntimeError, match="marker not found"):
        apply_patch(src, backup_dir=tmp_path)


def test_apply_patch_requires_unique_allies_in_block(tmp_path):
    src = tmp_path / "double.py"
    src.write_bytes(
        b"from app.services.npc.causal_slice_threat import ThreatDesiredChangeProducer\n"
        b"from app.services.npc.causal_slice_grievance import GrievanceDesiredChangeProducer\n"
        b"def run(state, npc_id, _epistemic_ctx):\n"
        b"    _dc = ThreatDesiredChangeProducer.resolve(state=state, allies=0, y=1, allies=0, z=2)\n"
        b"    _dc_g = GrievanceDesiredChangeProducer.resolve(who=npc_id, allies=0)\n"
    )
    with pytest.raises(RuntimeError, match="expected exactly 1"):
        apply_patch(src, backup_dir=tmp_path)

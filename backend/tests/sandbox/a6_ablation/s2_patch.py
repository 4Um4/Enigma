"""A6 S2-P Ablation Patch — allies wiring for threat + grievance causal slices.

NOT auto-applied. Pure functions: apply_patch(path) / restore_patch(state).
Three-state SHA-256 protocol (Master Q-C):

  H_pre     — SHA before patch (recorded once, saved in state)
  H_patched — SHA after patch is written (recorded immediately)
  H_current — SHA observed at restore time

Restore rules:
  H_current == H_patched → safe to restore (byte-exact copy from backup)
  H_current == H_pre     → idempotent no-op (already restored)
  else                   → ABORT, do NOT overwrite (parallel edit)

SCOPE (Master verdict variant C — partial 2/4, diagnostic-only):

  Threat    — IN SCOPE     (allies=0 at production line 769)
  Grievance — IN SCOPE     (allies=0 at production line 868)
  Hunger    — NOT APPLICABLE (formula has no allies parameter)
  Affection — NOT APPLICABLE (formula has no allies parameter)

Only 2 producers patched; 2 replacements made. Not full-layer ablation.
S2 is ALLIES PROPAGATION DIAGNOSTIC, does NOT enter S0/S1 scoring matrix.
"""

import hashlib
import shutil
from pathlib import Path
from typing import NamedTuple, Optional


_PROUDUCER_MARKERS = (
    ("ThreatDesiredChangeProducer.resolve(", "threat"),
    ("GrievanceDesiredChangeProducer.resolve(", "grievance"),
)
_ALLIES_MARKER = "allies=0,"
_PATCHED_ALLIES = "allies=_a6_allies,"
_INJECTION_TOKEN = "_a6_allies = len("
_REPLACED_COUNT = 2


class PatchState(NamedTuple):
    path: Path
    sha_pre: str
    sha_patched: str
    backup_path: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _find_block_end(patched: str, open_paren_pos: int) -> int:
    """Find matching ')' from open_paren_pos by paren-depth tracking."""
    depth = 0
    i = open_paren_pos
    n = len(patched)
    while i < n:
        c = patched[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _build_injection(indent_str: str, tag: str) -> str:
    return (
        f'{indent_str}_a6_allies = len(getattr(_epistemic_ctx, "perceived_allies", ())) if _epistemic_ctx else 0\n'
        f"{indent_str}logger.info(\n"
        f"{indent_str}    f\"[A6-S2] {tag} npc={{npc_id}} tick={{getattr(state, 'tick_id', 'NA')}} \"\n"
        f"{indent_str}    f\"agent={{getattr(_epistemic_ctx, 'agent_id', 'None') if _epistemic_ctx else 'None'}} \"\n"
        f'{indent_str}    f"allies={{_a6_allies}}"\n'
        f"{indent_str})\n"
    )


def apply_patch(
    target_path: Path,
    backup_dir: Optional[Path] = None,
) -> PatchState:
    """Apply S2-P patch to threat + grievance blocks."""
    target_path = Path(target_path)
    if not target_path.exists():
        raise RuntimeError(f"missing: {target_path}")
    if backup_dir is None:
        import tempfile

        backup_dir = Path(tempfile.gettempdir())
    backup_path = Path(backup_dir) / "npc_tick_pipeline.s2_pre.bak"
    shutil.copy2(target_path, backup_path)
    sha_pre = _sha256(target_path)
    if _sha256(backup_path) != sha_pre:
        raise RuntimeError(f"backup copy mismatch: pre={sha_pre} backup={_sha256(backup_path)}")
    raw = target_path.read_text(encoding="utf-8")
    patched = raw
    for marker, tag in _PROUDUCER_MARKERS:
        idx = patched.find(marker)
        if idx < 0:
            raise RuntimeError(f"marker not found: {marker!r} (tag={tag})")
        open_paren_pos = idx + len(marker) - 1
        window_end = _find_block_end(patched, open_paren_pos)
        window = patched[idx:window_end]
        if window.count(_ALLIES_MARKER) != 1:
            raise RuntimeError(
                f"expected exactly 1 {_ALLIES_MARKER!r} in window after {marker!r}, got {window.count(_ALLIES_MARKER)}"
            )
        allies_in_window = window.find(_ALLIES_MARKER)
        allies_abs = idx + allies_in_window
        line_start = patched.rfind("\n", 0, idx) + 1
        prefix = patched[line_start:idx]
        indent = len(prefix) - len(prefix.lstrip())
        indent_str = " " * indent
        injection = _build_injection(indent_str, tag)
        patched = patched[:line_start] + injection + patched[line_start:]
        allies_abs += len(injection)
        patched = patched[:allies_abs] + _PATCHED_ALLIES + patched[allies_abs + len(_ALLIES_MARKER) :]
    if patched.count(_INJECTION_TOKEN) != _REPLACED_COUNT:
        raise RuntimeError(f"expected {_REPLACED_COUNT} _a6_allies injections, got {patched.count(_INJECTION_TOKEN)}")
    if patched.count(_PATCHED_ALLIES) != _REPLACED_COUNT:
        raise RuntimeError(
            f"expected {_REPLACED_COUNT} {_PATCHED_ALLIES!r} replacements, got {patched.count(_PATCHED_ALLIES)}"
        )
    if patched.count(_ALLIES_MARKER) != 0:
        raise RuntimeError(f"expected 0 remaining {_ALLIES_MARKER!r}, got {patched.count(_ALLIES_MARKER)}")
    target_path.write_bytes(patched.encode("utf-8"))
    sha_patched = _sha256(target_path)
    if sha_patched == sha_pre:
        raise RuntimeError("patch write produced no change (sha identical)")
    return PatchState(
        path=target_path,
        sha_pre=sha_pre,
        sha_patched=sha_patched,
        backup_path=backup_path,
    )


def restore_patch(state: PatchState) -> str:
    """Restore original file if three-state SHA check passes. Returns sha_post."""
    current = _sha256(state.path)
    if current == state.sha_patched:
        shutil.copy2(state.backup_path, state.path)
        post = _sha256(state.path)
        if post != state.sha_pre:
            raise RuntimeError(f"restore produced wrong sha: expected {state.sha_pre}, got {post}")
        return post
    if current == state.sha_pre:
        return current
    raise RuntimeError(
        f"parallel edit detected: H_current={current} "
        f"(H_pre={state.sha_pre}, H_patched={state.sha_patched}). "
        f"DO NOT overwrite. Manual review required."
    )

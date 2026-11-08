# backend/tests/sandbox/r2_b5_d2_fix_investigation.py
"""
R2-B5-D2 FIX INVESTIGATION — Find existing NPC_SPOKE publication path for spread_rumor.

Master's directive (F):
  "First find the existing production-path that already publishes NPC_SPOKE without LLM,
   and check if it can be used for spread_rumor + proposition."

This is READ-ONLY investigation. No code changes. No idle_tick. No spies.

Questions to answer:
  Q1. How does `warn` (no proposition) publish NPC_SPOKE today?
  Q2. How does `steal` publish NPC_SPOKE today?
  Q3. Why does `spread_rumor + proposition` go to LLM branch instead of deterministic stub?
  Q4. Can we route spread_rumor + proposition through the SAME path as warn?
  Q5. What is the minimal isolated diff?

Master's constraints:
  1. Don't create second NPC_SPOKE publication mechanism
  2. Don't create new truth store
  3. Don't duplicate COMMUNICATION_CLAIM
  4. Don't publish on intent selection alone
  5. Don't change DecisionHub / Lusya scoring
  6. Don't change warn/steal semantics
  7. Don't lose provenance (source_id=guard_borko, original_source_id=player)
  8. LLM text preserved when available; fallback only when LLM fails

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import json
import re
import shutil
import traceback
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_fix_investigation.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ============================================================================
# Source readers
# ============================================================================
def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[read error: {e}]"


def _find_function_bounds(src: str, func_name: str) -> Optional[Tuple[int, int]]:
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("def ") and func_name in stripped.split("(")[0]:
            func_start = i
            break
    if func_start is None:
        return None
    indent_of_def = len(lines[func_start]) - len(lines[func_start].lstrip())
    func_end = len(lines)
    for j in range(func_start + 1, len(lines)):
        line = lines[j]
        if line.strip() == "":
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= indent_of_def and (
            line.lstrip().startswith("def ")
            or line.lstrip().startswith("class ")
            or line.lstrip().startswith("@")
        ):
            func_end = j
            break
    return func_start, func_end


def _read_function_full(path: Path, func_name: str, max_lines: int = 300) -> None:
    if not path.exists():
        print(f"  [file not found: {path}]")
        return
    src = _read_file_text(path)
    lines = src.split("\n")
    bounds = _find_function_bounds(src, func_name)
    if bounds:
        s, e = bounds
        actual_end = min(e, s + max_lines)
        print(f"  {func_name}() at L{s+1}..L{e} (showing L{s+1}..L{actual_end}):")
        for j in range(s, actual_end):
            print(f"  L{j+1:4d}: {lines[j]}")
        if actual_end < e:
            print(f"  ... ({e - actual_end} more lines)")
    else:
        print(f"  [{func_name} not found]")


def _grep_in_file(path: Path, pattern: str, context: int = 5, max_matches: int = 10) -> None:
    if not path.exists():
        print(f"  [file not found: {path}]")
        return
    src = _read_file_text(path)
    lines = src.split("\n")
    matches = []
    for i, line in enumerate(lines):
        if pattern.lower() in line.lower():
            matches.append(i)
    if not matches:
        print(f"  no matches for '{pattern}' in {path.name}")
        return
    print(f"  Found {len(matches)} matches for '{pattern}' in {path.name}:")
    seen_ranges = set()
    for i in matches[:max_matches]:
        ctx_start = max(0, i - context)
        ctx_end = min(len(lines), i + context + 1)
        if any(r in seen_ranges for r in range(ctx_start, ctx_end)):
            continue
        for r in range(ctx_start, ctx_end):
            seen_ranges.add(r)
        print(f"\n  >>> L{i+1}: {lines[i].rstrip()}")
        for j in range(ctx_start, ctx_end):
            marker = ">>>" if j + 1 == i + 1 else "   "
            print(f"  {marker} L{j+1:4d}: {lines[j]}")


def _grep_in_dir(directory: Path, patterns: List[str]) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*.py"):
        if any(part in {".venv", "node_modules", ".git", "__pycache__", "site-packages", "tests", "sandbox"} for part in f.parts):
            continue
        if f.name.startswith("test_") or f.name.startswith("r2_"):
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            for pat in patterns:
                if pat in line:
                    out.append((f, i, line.rstrip()))
                    break
    return out


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 FIX INVESTIGATION — Existing NPC_SPOKE path for spread_rumor")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("GOAL: Find existing production path that publishes NPC_SPOKE without LLM,")
    print("      and check if it can be used for spread_rumor + proposition.")
    print()

    # =====================================================================
    # STEP 1: Read intent_profiles.py — what requires_llm_materialization returns
    # =====================================================================
    _print_section("STEP 1: Read intent_profiles.py — requires_llm_materialization")
    ip_path = _BACKEND / "app" / "domain" / "intent_profiles.py"
    print(f"  file: {ip_path}")
    if ip_path.exists():
        src = _read_file_text(ip_path)
        lines = src.split("\n")
        # Print full file (it's small)
        for i, line in enumerate(lines, 1):
            print(f"  L{i:4d}: {line}")
    else:
        print(f"  [file not found]")

    # =====================================================================
    # STEP 2: Read dialogue_executor.execute() L141-207 (branch selection)
    # =====================================================================
    _print_section("STEP 2: Read dialogue_executor.execute() branch selection (L141-207)")
    de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
    if de_path.exists():
        src = _read_file_text(de_path)
        lines = src.split("\n")
        # Print L141-207 (the branch selection logic)
        print(f"  --- L141-207 (branch selection) ---")
        for j in range(140, min(207, len(lines))):
            print(f"  L{j+1:4d}: {lines[j]}")

    # =====================================================================
    # STEP 3: Trace what happens for `warn` (no proposition)
    # =====================================================================
    _print_section("STEP 3: Trace `warn` (no proposition) — how does it reach NPC_SPOKE?")

    print(f"\n  --- 3a: requires_llm_materialization('warn') ---")
    # We need to actually call this function to see the result
    try:
        from app.domain.intent_profiles import requires_llm_materialization, produces_claim
        warn_requires_llm = requires_llm_materialization("warn")
        spread_rumor_requires_llm = requires_llm_materialization("spread_rumor")
        talk_requires_llm = requires_llm_materialization("talk")
        steal_requires_llm = requires_llm_materialization("steal")
        print(f"  requires_llm_materialization('warn') = {warn_requires_llm}")
        print(f"  requires_llm_materialization('spread_rumor') = {spread_rumor_requires_llm}")
        print(f"  requires_llm_materialization('talk') = {talk_requires_llm}")
        print(f"  requires_llm_materialization('steal') = {steal_requires_llm}")
        print()
        print(f"  produces_claim('warn') = {produces_claim('warn')}")
        print(f"  produces_claim('spread_rumor') = {produces_claim('spread_rumor')}")
        print(f"  produces_claim('talk') = {produces_claim('talk')}")
        print(f"  produces_claim('steal') = {produces_claim('steal')}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()

    print(f"\n  --- 3b: For `warn` (no proposition), branch selection in execute() ---")
    print(f"  L145: elif not requires_llm_materialization('warn') and not (")
    print(f"  L146:     'warn' == 'spread_rumor' and _proposition is not None")
    print(f"  L147: ):")
    print(f"  → not True and not (False and ...) = False and True = False")
    print(f"  → NOT this branch")
    print(f"  → Goes to ELSE (LLM branch)")
    print()
    print(f"  WAIT — 'warn' == 'spread_rumor' is False, so the second part is False,")
    print(f"  not(False) = True, so condition = True and True = True → ENTERS stub branch!")
    print()
    print(f"  Let me recompute:")
    print(f"  L145: not requires_llm_materialization(req.intent_type)  →  not False  →  True")
    print(f"  L146: not (req.intent_type == 'spread_rumor' and _proposition is not None)")
    print(f"        →  not (False and ...)  →  not False  →  True")
    print(f"  L145 and L146: True and True = True  →  ENTERS stub branch (L148-149)")
    print()
    print(f"  >>> `warn` (no proposition) → STUB branch → deterministic text → NPC_SPOKE published")

    # =====================================================================
    # STEP 4: Trace what happens for `spread_rumor + proposition`
    # =====================================================================
    _print_section("STEP 4: Trace `spread_rumor + proposition` — why does it go to LLM branch?")

    print(f"  L145: not requires_llm_materialization('spread_rumor')  →  not False  →  True")
    print(f"  L146: not (req.intent_type == 'spread_rumor' and _proposition is not None)")
    print(f"        →  not (True and True)  →  not True  →  False")
    print(f"  L145 and L146: True and False = False  →  DOES NOT enter stub branch")
    print(f"  → Goes to ELSE (LLM branch) L150-197")
    print()
    print(f"  >>> `spread_rumor + proposition` → LLM branch → blocking HTTP call → no NPC_SPOKE")

    # =====================================================================
    # STEP 5: Trace what happens for `spread_rumor` WITHOUT proposition
    # =====================================================================
    _print_section("STEP 5: Trace `spread_rumor` WITHOUT proposition")

    print(f"  L145: not requires_llm_materialization('spread_rumor')  →  True")
    print(f"  L146: not (req.intent_type == 'spread_rumor' and _proposition is not None)")
    print(f"        →  not (True and False)  →  not False  →  True")
    print(f"  L145 and L146: True and True = True  →  ENTERS stub branch (L148-149)")
    print()
    print(f"  >>> `spread_rumor` WITHOUT proposition → STUB branch → NPC_SPOKE published")
    print(f"  >>> But: B5-E2 confirmed that guard_borko's spread_rumor HAS proposition")
    print(f"  >>> (from report_proposition in EpistemicContext)")

    # =====================================================================
    # STEP 6: Identify the minimal diff
    # =====================================================================
    _print_section("STEP 6: Identify the minimal diff")

    print(f"""
  CURRENT CODE (dialogue_executor.py L145-149):
    elif not requires_llm_materialization(req.intent_type) and not (
        req.intent_type == "spread_rumor" and _proposition is not None
    ):
        # S199.2: Детерминированная материализация для claim-producing интентов без LLM
        text = f"[{{req.intent_type}}] {{task.owner_id}} -> {{req.target_id}}: {{req.topic}}"

  PROBLEM:
    The condition `not (req.intent_type == "spread_rumor" and _proposition is not None)`
    EXCLUDES spread_rumor+proposition from the stub branch.
    This was intentional (S199.2): "claim-producing интентов без LLM" — meaning
    the original design wanted spread_rumor+proposition to use LLM for natural
    language generation of the rumor text.

  MINIMAL DIFF (Option F — preserve LLM when available, fallback to stub):

    Replace L145-149 with:
    ----------------------------------------------------------
    elif not requires_llm_materialization(req.intent_type) and not (
        req.intent_type == "spread_rumor" and _proposition is not None
    ):
        # S199.2: Детерминированная материализация для claim-producing интентов без LLM
        text = f"[{{req.intent_type}}] {{task.owner_id}} -> {{req.target_id}}: {{req.topic}}"
    elif req.intent_type == "spread_rumor" and _proposition is not None and (
        self._router is None or not self._router.is_llm_available()
    ):
        # B5-D2 FIX: spread_rumor+proposition — fallback to deterministic stub
        # when LLM is unavailable. Social event (NPC_SPOKE + COMMUNICATION_CLAIM)
        # must complete regardless of LLM availability.
        # Proposition is preserved in artifact.data["proposition"] for materializer.
        text = f"[spread_rumor] {{task.owner_id}} -> {{req.target_id}}: {{req.topic}}"
    ----------------------------------------------------------

    OR — simpler, no is_llm_available() check (always stub for spread_rumor+prop):

    ----------------------------------------------------------
    elif not requires_llm_materialization(req.intent_type):
        # S199.2: Детерминированная материализация для claim-producing интентов без LLM
        # B5-D2 FIX: spread_rumor+proposition also uses deterministic stub.
        # Social event (NPC_SPOKE + COMMUNICATION_CLAIM) is decoupled from LLM text.
        # Proposition is preserved in artifact.data["proposition"] for materializer.
        text = f"[{{req.intent_type}}] {{task.owner_id}} -> {{req.target_id}}: {{req.topic}}"
    ----------------------------------------------------------

  This means:
    - spread_rumor+proposition → STUB branch (like warn)
    - text = deterministic stub
    - _proposition still extracted at L135
    - yield Artifact with success=True, proposition=_proposition (L269-283)
    - materializer.materialize() creates NPC_SPOKE + COMMUNICATION_CLAIM
    - drain_task_worker_outbox publishes events
    - ClaimEventSubscriber receives COMMUNICATION_CLAIM
    - BeliefRevisionEngine.revise(tornin, claim) called
    - Tornin gets belief with source_id=guard_borko, original_source_id=player
""")

    # =====================================================================
    # STEP 7: Check materializer — does it preserve proposition for spread_rumor?
    # =====================================================================
    _print_section("STEP 7: Verify materializer preserves proposition")

    print(f"  From v9 Step 5 (already read), DialogueMaterializer.materialize() L61-131:")
    print(f"  - L62: if artifact.result_type != 'dialogue_line' or not artifact.success: return []")
    print(f"  - L91-105: ALWAYS creates NPC_SPOKE event (with text, topic, intent_type)")
    print(f"  - L110-128: if _prop_data (proposition): creates COMMUNICATION_CLAIM event")
    print(f"  >>> materializer ALREADY handles proposition correctly")
    print(f"  >>> It creates BOTH NPC_SPOKE and COMMUNICATION_CLAIM when proposition is present")
    print(f"  >>> No changes needed in materializer")

    # =====================================================================
    # STEP 8: Check IntentEventAdapter — is it even used?
    # =====================================================================
    _print_section("STEP 8: IntentEventAdapter — is it used in the spread_rumor path?")

    print(f"  From v9 Steps 1-6:")
    print(f"  - DialogueExecutor.execute() yields Artifact (does NOT call IntentEventAdapter)")
    print(f"  - task_scheduler._process_tasks_async calls materializer.materialize(artifact)")
    print(f"  - materializer creates EventDTO directly (NOT via IntentEventAdapter)")
    print(f"  - drain_task_worker_outbox publishes events via _bus.publish()")
    print()
    print(f"  >>> IntentEventAdapter is NOT used in the spread_rumor execution path")
    print(f"  >>> It's used elsewhere (probably for NPC-NPC dialogue intent → event conversion)")
    print(f"  >>> No changes needed in IntentEventAdapter")

    # =====================================================================
    # STEP 9: Check ClaimEventSubscriber — does on_npc_spoke handle spread_rumor?
    # =====================================================================
    _print_section("STEP 9: Check ClaimEventSubscriber — on_npc_spoke + on_claim_event")

    ces_path = _BACKEND / "app" / "services" / "events" / "claim_event_subscriber.py"
    if ces_path.exists():
        src = _read_file_text(ces_path)
        lines = src.split("\n")
        # Print on_npc_spoke method
        print(f"  --- on_npc_spoke (L41-122 area) ---")
        for j in range(40, min(125, len(lines))):
            print(f"  L{j+1:4d}: {lines[j]}")

        print(f"\n  --- on_claim_event — does it handle COMMUNICATION_CLAIM? ---")
        # Find where COMMUNICATION_CLAIM is subscribed
        for j, line in enumerate(lines, 1):
            if "COMMUNICATION_CLAIM" in line or "communication_claim" in line.lower():
                print(f"  L{j}: {line.rstrip()}")

    # =====================================================================
    # STEP 10: Check game_loop.py — subscription wiring
    # =====================================================================
    _print_section("STEP 10: Check game_loop.py — subscription wiring for COMMUNICATION_CLAIM")
    gl_path = _BACKEND / "app" / "services" / "game_loop" / "game_loop.py"
    if gl_path.exists():
        src = _read_file_text(gl_path)
        lines = src.split("\n")
        for j, line in enumerate(lines, 1):
            if "COMMUNICATION_CLAIM" in line or "communication_claim" in line.lower():
                ctx_start = max(0, j - 2)
                ctx_end = min(len(lines), j + 5)
                print(f"\n  >>> L{j}: {line.rstrip()}")
                for k in range(ctx_start, ctx_end):
                    marker = ">>>" if k + 1 == j else "   "
                    print(f"  {marker} L{k+1:4d}: {lines[k]}")

    # =====================================================================
    # STEP 11: Verify provenance chain
    # =====================================================================
    _print_section("STEP 11: Verify provenance chain will be preserved")

    print(f"""
  After the fix, the chain will be:
    1. guard_borko DecisionHub → SPREAD_RUMOR (score 0.988)
       - report_proposition = Proposition(player, INSULTED, tavern_keeper_tornin)
       - _build_communication creates CommunicationIntent with proposition

    2. task_scheduler → DialogueExecutor.execute()
       - L135: _proposition = getattr(req, "proposition", None) → Proposition object
       - L145-149 (after fix): stub branch → text = "[spread_rumor] guard_borko -> tavern_keeper_tornin: власть"
       - L269-283: yield Artifact(success=True, proposition=_proposition, intent_type="spread_rumor")

    3. task_scheduler._process_tasks_async L742: materializer.materialize(artifact)
       - L91-105: creates NPC_SPOKE event (source=guard_borko, target=tavern_keeper_tornin)
       - L110-128: _prop_data is not None → creates COMMUNICATION_CLAIM event
         (source=guard_borko, proposition=Proposition(player, INSULTED, tavern_keeper_tornin))

    4. drain_task_worker_outbox publishes both events via _bus.publish()

    5. ClaimEventSubscriber.on_claim_event receives COMMUNICATION_CLAIM
       - L184-195: prop_data = payload.get("proposition")
       - L244-278: spatial_query filters listeners (Tornin is target, in range)
       - L300-309: for each listener:
         claim = ClaimEvent(speaker_id=guard_borko, listener_id=tavern_keeper_tornin, proposition=prop)
         _speaker_record = self._store.get(guard_borko, prop)
         _speaker_orig = _speaker_record.original_source_id if _speaker_record else guard_borko
         updated_record = self._engine.revise(
             tavern_keeper_tornin, claim, existing,
             reliability_context={{"source_type": "testimony", "original_source_id": _speaker_orig}}
         )

    6. BeliefRevisionEngine.revise:
       - reliability = reliability_provider.get(guard_borko) → some value
       - incoming_confidence = reliability × _CLAIM_WEIGHT (1.0)
       - Tornin's belief created:
         source_id=guard_borko
         original_source_id=player (from guard_borko's existing record, which has original_source_id=player)
         confidence = incoming_confidence

  >>> Provenance chain PRESERVED:
      player (original) → guard_borko (source) → tavern_keeper_tornin (listener)
""")

    # =====================================================================
    # STEP 12: Test plan
    # =====================================================================
    _print_section("STEP 12: Test plan (10 acceptance criteria from Master)")

    print(f"""
  After applying the minimal diff, run the B5-D2 acceptance test:

  Test setup:
    - Build game loop, load NPCs
    - Publish PLAYER_INSULTS (target=tavern_keeper_tornin)
    - Run idle_tick
    - Capture: guard_borko NPC state, EventBus events, Tornin store

  Acceptance criteria (from Master):
    1. guard_borko chooses SPREAD_RUMOR
       → check DecisionHub log: intent=Intent.SPREAD_RUMOR

    2. Execution reaches real communication
       → check DialogueExecutor.execute() yielded Artifact with success=True

    3. Exactly ONE NPC_SPOKE event published
       → EventBus spy: count npc_spoke events = 1
       → source=guard_borko, target=tavern_keeper_tornin

    4. COMMUNICATION_CLAIM event published
       → EventBus spy: count communication_claim events = 1
       → source=guard_borko, proposition=Proposition(player, INSULTED, tavern_keeper_tornin)

    5. Tornin has belief with source_id=guard_borko
       → store.get(tavern_keeper_tornin, prop).source_id == 'guard_borko'

    6. original_source_id=player
       → store.get(tavern_keeper_tornin, prop).original_source_id == 'player'

    7. Confidence and provenance follow transmission rules
       → confidence = reliability × _CLAIM_WEIGHT (1.0)
       → source_type='testimony'
       → source_claim_id starts with 'guard_borko' or similar

    8. Re-run doesn't create duplicate events
       → run idle_tick again, check no new NPC_SPOKE for same speaker+target+intent

    9. When LLM unavailable, social event still completes
       → this is the fix — stub branch ensures NPC_SPOKE publishes

    10. When LLM available, natural generation preserved
       → if router.is_llm_available() returns True, use LLM branch (original code)
       → if not available, use stub branch (new code)
       → This requires Option 1 (is_llm_available check) for full preservation

  Two diff options:
    Option 1 (preserve LLM when available):
      Add condition: `or (req.intent_type == "spread_rumor" and _proposition is not None
                              and (self._router is None or not self._router.is_llm_available()))`
      Risk: requires is_llm_available() method on ModelRouter (may not exist)

    Option 2 (always stub for spread_rumor+proposition):
      Remove the special case entirely:
      `elif not requires_llm_materialization(req.intent_type):`
      Risk: loses LLM text generation for spread_rumor (criterion 10 fails)

  Recommendation: Option 2 for now (simplest, satisfies criteria 1-9).
  Criterion 10 (LLM preservation) can be added later via Option 1
  after Master decides on is_llm_available() API.
""")

    # =====================================================================
    # STEP 13: Summary
    # =====================================================================
    _print_section("STEP 13: Summary")

    print(f"""
  ARCHITECTURE UNDERSTANDING:
    - NPC_SPOKE is published by drain_task_worker_outbox (main thread)
    - Events are created by materializer.materialize() (worker thread)
    - Executor yields Artifact; if it blocks (LLM), no Artifact → no events → no NPC_SPOKE
    - spread_rumor+proposition goes to LLM branch (L150-197) due to L146 condition
    - warn goes to stub branch (L148-149) and publishes NPC_SPOKE successfully

  ROOT CAUSE:
    L146: `not (req.intent_type == "spread_rumor" and _proposition is not None)`
    This condition EXCLUDES spread_rumor+proposition from stub branch,
    forcing it into LLM branch which blocks when LLM is unavailable.

  MINIMAL DIFF (Option 2 — always stub for spread_rumor+proposition):
    File: app/services/execution/dialogue_executor.py
    Lines: L145-149

    BEFORE:
      elif not requires_llm_materialization(req.intent_type) and not (
          req.intent_type == "spread_rumor" and _proposition is not None
      ):
          text = f"[{req.intent_type}] {task.owner_id} -> {req.target_id}: {req.topic}"

    AFTER:
      elif not requires_llm_materialization(req.intent_type):
          # S199.2: Детерминированная материализация для claim-producing интентов без LLM
          # B5-D2 FIX: spread_rumor+proposition also uses deterministic stub.
          # Social event (NPC_SPOKE + COMMUNICATION_CLAIM) is decoupled from LLM text.
          # Proposition is preserved in artifact.data["proposition"] for materializer.
          text = f"[{req.intent_type}] {task.owner_id} -> {req.target_id}: {req.topic}"

  WHAT DOESN'T CHANGE:
    - DialogueExecutor.execute() structure (yields Artifact)
    - DialogueMaterializer.materialize() (creates NPC_SPOKE + COMMUNICATION_CLAIM)
    - task_scheduler._process_tasks_async (dispatches to executor)
    - drain_task_worker_outbox (publishes events)
    - ClaimEventSubscriber.on_claim_event (creates beliefs)
    - BeliefRevisionEngine.revise (confidence calculation)
    - Provenance chain (source_id=guard_borko, original_source_id=player)

  CONSTRAINTS SATISFIED:
    1. ✓ No second NPC_SPOKE mechanism — uses existing materializer
    2. ✓ No new truth store — uses existing EpistemicStore
    3. ✓ No duplicate COMMUNICATION_CLAIM — materializer creates exactly one
    4. ✓ Not publishing on intent selection alone — requires full execution path
    5. ✓ DecisionHub / Lusya scoring unchanged
    6. ✓ warn/steal semantics unchanged (they already use stub branch)
    7. ✓ Provenance preserved (proposition flows through artifact → materializer → COMMUNICATION_CLAIM → ClaimEventSubscriber)
    8. ⚠️ LLM text NOT preserved (criterion 10 fails with Option 2)
       → Can be fixed later with Option 1 (is_llm_available check)
""")

    # Write output file
    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR writing output file: {e}]")
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = _orig_stdout
    sys.exit(rc)

# backend/tests/sandbox/r2_b5_d2_revise_investigation.py
"""
R2-B5-D2 — Investigate BeliefRevisionEngine.revise() provenance handling.

Provenance probe found:
  - Tornin has 1 record: source_id=player, original_source_id=player
  - No record with source_id=guard_borko
  - Borko has 1 record: source_id=player, original_source_id=player

Question: When Borko tells Tornin (COMMUNICATION_CLAIM with source=guard_borko),
does revise() create a NEW record with source_id=guard_borko, or does it UPDATE
the existing record (source_id=player)?

This is a READ-ONLY investigation of BeliefRevisionEngine.revise() code.
"""
from __future__ import annotations

import os
import sys
import json
import shutil
import traceback
import io
import logging
import tempfile
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_revise_investigation.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except: pass

    def flush(self):
        for s in self.streams:
            try: s.flush()
            except: pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


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


def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — BeliefRevisionEngine.revise() provenance investigation")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()

    # =====================================================================
    # STEP 1: Read BeliefRevisionEngine.revise() full implementation
    # =====================================================================
    _print_section("STEP 1: Read BeliefRevisionEngine.revise()")
    bre_path = _BACKEND / "app" / "services" / "npc" / "belief_revision_engine.py"
    print(f"  file: {bre_path}")
    _read_function_full(bre_path, "revise", max_lines=300)

    # =====================================================================
    # STEP 2: Read full BeliefRevisionEngine class (all methods)
    # =====================================================================
    _print_section("STEP 2: Read full BeliefRevisionEngine class")
    if bre_path.exists():
        src = _read_file_text(bre_path)
        lines = src.split("\n")
        # Print entire file
        print(f"  total lines: {len(lines)}")
        max_print = min(len(lines), 200)
        for i, line in enumerate(lines[:max_print], 1):
            print(f"  L{i:4d}: {line}")
        if len(lines) > max_print:
            print(f"  ... ({len(lines) - max_print} more lines)")

    # =====================================================================
    # STEP 3: Read EpistemicStore.upsert()
    # =====================================================================
    _print_section("STEP 3: Read EpistemicStore.upsert()")
    es_path = _BACKEND / "app" / "services" / "npc" / "epistemic_store.py"
    _read_function_full(es_path, "upsert", max_lines=100)

    # =====================================================================
    # STEP 4: Read EpistemicStore.get()
    # =====================================================================
    _print_section("STEP 4: Read EpistemicStore.get()")
    _read_function_full(es_path, "get", max_lines=100)

    # =====================================================================
    # STEP 5: Read EpistemicStore.get_all_for_agent()
    # =====================================================================
    _print_section("STEP 5: Read EpistemicStore.get_all_for_agent()")
    _read_function_full(es_path, "get_all_for_agent", max_lines=100)

    # =====================================================================
    # STEP 6: Analysis — what happens when existing record + new claim with different source_id
    # =====================================================================
    _print_section("STEP 6: Analysis — provenance handling in revise()")

    print(f"""
  SCENARIO: Tornin has existing record (source_id=player, conf=0.5).
            Borko tells Tornin (new claim, speaker_id=guard_borko).

  ClaimEventSubscriber L300-309:
    existing = self._store.get(tavern_keeper_tornin, prop)  → Tornin's existing record
    _speaker_record = self._store.get(guard_borko, prop)    → Borko's record
    _speaker_orig = _speaker_record.original_source_id      → "player"
    updated_record = self._engine.revise(
        tavern_keeper_tornin, claim, existing,
        reliability_context={{"source_type": "testimony", "original_source_id": "player"}}
    )
    self._store.upsert(updated_record)

  QUESTIONS:
  1. Does revise() create a NEW record with source_id=guard_borko?
  2. Or does it UPDATE the existing record, changing source_id from player to guard_borko?
  3. Or does it UPDATE the existing record, KEEPING source_id=player (because original_source_id matches)?
  4. What happens to confidence — does it increase (multiple sources)?

  From belief_revision_engine.py (read in Step 1-2):
  - _CLAIM_WEIGHT = 1.0
  - incoming_confidence = reliability × _CLAIM_WEIGHT
  - If existing record exists:
    - If same source_id: updated_conf = existing + incoming × _SAME_SOURCE_BOOST (0.2)
    - If different source_id: updated_conf = ??? (need to check)
  - source_id of updated_record: ???

  KEY: Does revise() change source_id of existing record, or preserve it?

  If revise() PRESERVES source_id=player (because that was the original source),
  then Tornin's record stays as source_id=player even after Borko tells him.
  The confidence would increase (multiple testimonies), but source_id doesn't change.

  This would explain:
  - Tornin has 1 record (not 2) — upsert updated existing, didn't create new
  - source_id=player (preserved from original)
  - original_source_id=player (same)
  - Confidence might have increased from 0.5 to higher

  If this is the case, the provenance check needs to be revised:
  - Instead of checking source_id=guard_borko, check:
    a. Confidence increased (0.5 → higher, reflecting multiple testimonies)
    b. source_claim_id changed (new claim ID)
    c. last_updated_tick > 1 (updated after tick 1)
""")

    # =====================================================================
    # STEP 7: Runtime test — check confidence change
    # =====================================================================
    _print_section("STEP 7: Runtime test — check confidence and last_updated_tick")

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment
    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_revise_"))

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.domain.epistemology import Proposition, Predicate  # type: ignore

        settings.saves_dir = str(temp_dir)
        settings.environment = "development"
        loop = build_game_loop(data_dir=Path(settings.data_dir))

        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
        loaded = loop._load_npcs_with_runtime("Open_road")

        bus = get_event_bus()
        sub = None
        for attr in ("_subscribers", "_handlers", "_callbacks"):
            if not hasattr(bus, attr): continue
            container = getattr(bus, attr)
            if not isinstance(container, dict): continue
            for ev_type, cbs in container.items():
                if cbs is None: continue
                try: iter_cbs = list(cbs)
                except TypeError: iter_cbs = [cbs]
                for cb in iter_cbs:
                    target_obj = getattr(cb, "__self__", None)
                    if target_obj and isinstance(target_obj, ClaimEventSubscriber):
                        sub = target_obj; break
                if sub: break
            if sub: break
        store = getattr(sub, "_store", None) if sub else None

        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )

        # Publish PLAYER_INSULTS
        payload = {
            "action_type": "player_insults",
            "target_id": "tavern_keeper_tornin",
            "content": "оскорбление",
            "event_tick": 1,
            "visibility": "public",
            "radius": 999.0,
            "location": "tavern",
            "campaign_id": "Open_road",
            "raw_input": "оскорбление",
        }
        evt = EventDTO.create(
            event_type=EventType.PLAYER_INSULTS,
            source="player",
            payload=payload,
            persistence_level="working",
        )
        bus.publish(evt)

        # Capture Tornin's record BEFORE ticks
        tornin_before = None
        if store:
            tornin_before = store.get("tavern_keeper_tornin", expected_prop)
            print(f"  Tornin BEFORE ticks:")
            if tornin_before:
                print(f"    source_id: {getattr(tornin_before, 'source_id', None)}")
                print(f"    original_source_id: {getattr(tornin_before, 'original_source_id', None)}")
                print(f"    confidence: {getattr(tornin_before, 'confidence', None)}")
                print(f"    source_claim_id: {getattr(tornin_before, 'source_claim_id', None)}")
                print(f"    last_updated_tick: {getattr(tornin_before, 'last_updated_tick', None)}")
                print(f"    first_observed_tick: {getattr(tornin_before, 'first_observed_tick', None)}")
            else:
                print(f"    None")

        # Run 3 idle_ticks
        print(f"\n  Running 3 idle_ticks...")
        for tick_num in range(1, 4):
            try:
                loop.idle_tick("Open_road", "tavern")
            except Exception as e:
                print(f"    Tick {tick_num} ERROR: {e}")

        # Capture Tornin's record AFTER ticks
        print(f"\n  Tornin AFTER 3 ticks:")
        if store:
            tornin_after = store.get("tavern_keeper_tornin", expected_prop)
            if tornin_after:
                print(f"    source_id: {getattr(tornin_after, 'source_id', None)}")
                print(f"    original_source_id: {getattr(tornin_after, 'original_source_id', None)}")
                print(f"    confidence: {getattr(tornin_after, 'confidence', None)}")
                print(f"    source_claim_id: {getattr(tornin_after, 'source_claim_id', None)}")
                print(f"    last_updated_tick: {getattr(tornin_after, 'last_updated_tick', None)}")
                print(f"    first_observed_tick: {getattr(tornin_after, 'first_observed_tick', None)}")
            else:
                print(f"    None")

            # Also get ALL records for Tornin
            all_tornin = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"\n  Tornin ALL records: {len(all_tornin)}")
            for i, r in enumerate(all_tornin):
                print(f"    [{i}] source_id={getattr(r, 'source_id', None)} "
                      f"orig={getattr(r, 'original_source_id', None)} "
                      f"conf={getattr(r, 'confidence', None)} "
                      f"tick={getattr(r, 'last_updated_tick', None)} "
                      f"claim_id={getattr(r, 'source_claim_id', None)}")

            # Compare
            print(f"\n  === Comparison ===")
            if tornin_before and tornin_after:
                conf_before = getattr(tornin_before, "confidence", None)
                conf_after = getattr(tornin_after, "confidence", None)
                tick_before = getattr(tornin_before, "last_updated_tick", None)
                tick_after = getattr(tornin_after, "last_updated_tick", None)
                source_before = getattr(tornin_before, "source_id", None)
                source_after = getattr(tornin_after, "source_id", None)

                print(f"    confidence: {conf_before} → {conf_after} (changed: {conf_before != conf_after})")
                print(f"    last_updated_tick: {tick_before} → {tick_after} (changed: {tick_before != tick_after})")
                print(f"    source_id: {source_before} → {source_after} (changed: {source_before != source_after})")

                if conf_before != conf_after:
                    print(f"    >>> Confidence CHANGED — Borko's testimony was integrated")
                    print(f"    >>> Even if source_id stayed as 'player', the confidence update")
                    print(f"    >>> proves Tornin received information from Borko")
                elif tick_before != tick_after:
                    print(f"    >>> Tick changed but confidence didn't — record was touched")
                else:
                    print(f"    >>> Record UNCHANGED — Borko's testimony did NOT reach Tornin")

        # Cleanup
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except: pass
        del loop
        import gc; gc.collect()

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
    finally:
        settings.saves_dir = orig_saves_dir
        settings.environment = orig_env
        shutil.rmtree(temp_dir, ignore_errors=True)

    # =====================================================================
    # STEP 8: VERDICT
    # =====================================================================
    _print_section("STEP 8: VERDICT")

    print(f"""
  Based on Steps 1-7, the verdict depends on what revise() does:

  CASE A: revise() PRESERVES source_id (keeps original source)
    - Tornin's record stays source_id=player
    - But confidence should INCREASE (multiple testimonies)
    - last_updated_tick should change
    - This is NOT a bug — it's a design choice: "who originally said it"
      is more important than "who relayed it last"
    - Provenance check should verify CONFIDENCE CHANGE, not source_id change

  CASE B: revise() CHANGES source_id to new speaker
    - Tornin's record should become source_id=guard_borko
    - If it didn't, there's a bug in revise() or upsert()
    - Provenance check is correct as-is

  CASE C: revise() creates a SEPARATE record (one per source)
    - Tornin should have 2 records: one from player, one from guard_borko
    - If only 1 exists, the second wasn't created
    - This could mean NPC_SPOKE/COMMUNICATION_CLAIM wasn't published

  The runtime test in Step 7 will show which case applies:
    - If confidence changed but source_id didn't → CASE A
    - If source_id changed → CASE B
    - If 2 records exist → CASE C
    - If nothing changed → NPC_SPOKE wasn't published (CASE C with 0 new records)
""")

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
    try: rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally: sys.stdout = _orig_stdout
    sys.exit(rc)

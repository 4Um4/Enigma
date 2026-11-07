# backend/tests/sandbox/r2_b5_d1_v3_store_query.py
"""
R2-B5-D1 v3 — direct EpistemicStore query after PLAYER_INSULTS.

v2 confirmed:
  - Provider is callable, returns working SpatialQueryService
  - maid_lusya is in _npc_positions
  - distance(player, maid_lusya) = 10.09m
  - can_observe uses event.radius (999.0), not HEARING_RADIUS (10.0)
  - engine.revise IS called for maid_lusya (call #3 of 6)

v2 could NOT confirm:
  - Whether engine.revise succeeded or raised
  - Whether store.upsert was called
  - Whether the belief actually exists in EpistemicStore

v3 fixes this by directly querying EpistemicStore AFTER publish — NO SPY.

Checks:
  1. Build game loop, get sub, engine, store
  2. Capture store state BEFORE publish (baseline)
  3. Publish PLAYER_INSULTS (target_id=tavern_keeper_tornin)
  4. Capture store state AFTER publish
  5. Diff: which NPCs got new belief records?
  6. For maid_lusya specifically:
     - Proposition(player, INSULTED, tavern_keeper_tornin) — exists?
     - confidence?
     - source_id?
     - original_source_id?

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import json
import math
import traceback
import io
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

PROJECT_ROOT = _BACKEND.parent

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_d1_v3_store_query.txt"


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


def _dump_record(r: Any) -> Dict[str, Any]:
    """Extract printable fields from a belief record."""
    out: Dict[str, Any] = {}
    for field in ("proposition", "confidence", "source_id", "original_source_id",
                  "last_updated_tick", "tick", "reliability"):
        try:
            val = getattr(r, field, None)
            if val is not None:
                out[field] = str(val)[:200] if not isinstance(val, (int, float, bool)) else val
        except Exception:
            pass
    # Also try .__dict__
    try:
        d = vars(r)
        for k, v in d.items():
            if k not in out:
                try:
                    out[k] = str(v)[:200] if not isinstance(v, (int, float, bool)) else v
                except Exception:
                    out[k] = "<unrepr>"
    except Exception:
        pass
    return out


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D1 v3 — direct EpistemicStore query after PLAYER_INSULTS")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("GOAL: Confirm whether belief is actually created in EpistemicStore")
    print("      after PLAYER_INSULTS, by directly querying the store.")
    print("      NO SPY — just publish, then query.")
    print()

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.domain.epistemology import Proposition, Predicate, ClaimEvent, EpistemicRecord  # type: ignore
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d1_v3_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        bus = get_event_bus()

        # ---- 1. Find the ClaimEventSubscriber instance ----
        _print_section("STEP 1: locate ClaimEventSubscriber instance")
        sub: Optional[ClaimEventSubscriber] = None
        for attr in ("_subscribers", "_handlers", "_callbacks"):
            if not hasattr(bus, attr):
                continue
            container = getattr(bus, attr)
            if not isinstance(container, dict):
                continue
            for ev_type, cbs in container.items():
                if cbs is None:
                    continue
                try:
                    iter_cbs = list(cbs)
                except TypeError:
                    iter_cbs = [cbs]
                for cb in iter_cbs:
                    target_obj = getattr(cb, "__self__", None)
                    if target_obj and isinstance(target_obj, ClaimEventSubscriber):
                        sub = target_obj
                        print(f"  Found ClaimEventSubscriber id={id(sub)}")
                        print(f"  via bus.{attr}[{ev_type}] → {cb.__name__}")
                        break
                if sub:
                    break
            if sub:
                break

        if sub is None:
            print("  [FATAL: ClaimEventSubscriber not found]")
            return 1

        engine = getattr(sub, "_engine", None)
        store = getattr(sub, "_store", None)
        print(f"  engine: {engine} ({type(engine).__name__})")
        print(f"  store:  {store} ({type(store).__name__})")

        if store is None:
            print("  [FATAL: store is None]")
            return 1

        # ---- 2. Identify all NPCs in scene ----
        _print_section("STEP 2: enumerate NPCs in scene_state")
        npc_positions = scene.get("npc_positions", {}) or {}
        npc_ids = [nid for nid in npc_positions.keys() if nid != "player"]
        print(f"  NPCs (excluding player): {npc_ids}")
        print(f"  target_id for PLAYER_INSULTS: tavern_keeper_tornin")
        print(f"  expected proposition: Proposition(player, INSULTED, tavern_keeper_tornin)")

        # ---- 3. Capture store state BEFORE publish (baseline) ----
        _print_section("STEP 3: capture store state BEFORE publish (baseline)")

        # The expected proposition: player INSULTED tavern_keeper_tornin
        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )
        print(f"  Expected proposition: {expected_prop}")

        baseline: Dict[str, Any] = {}
        for nid in npc_ids + ["player"]:
            try:
                rec = store.get(nid, expected_prop)
                baseline[nid] = rec
                if rec is not None:
                    print(f"  [BEFORE] {nid}: HAS record = {_dump_record(rec)}")
                else:
                    print(f"  [BEFORE] {nid}: None")
            except Exception as e:
                baseline[nid] = f"ERROR: {e}"
                print(f"  [BEFORE] {nid}: ERROR: {e}")

        # Also try get_all_for_agent
        print()
        print(f"  --- store.get_all_for_agent for each NPC (BEFORE) ---")
        baseline_all: Dict[str, int] = {}
        for nid in npc_ids + ["player"]:
            try:
                recs = store.get_all_for_agent(nid)
                baseline_all[nid] = len(recs) if recs else 0
                print(f"  {nid}: {baseline_all[nid]} records")
            except Exception as e:
                baseline_all[nid] = -1
                print(f"  {nid}: ERROR: {e}")

        # ---- 4. Publish PLAYER_INSULTS ----
        _print_section("STEP 4: publish PLAYER_INSULTS")
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
        print(f"  event.source={evt.source}")
        print(f"  event.type={getattr(evt, 'type', '?')}")
        print(f"  event.visibility={getattr(evt, 'visibility', '?')}")
        print(f"  payload.target_id={payload['target_id']}")
        print(f"  payload.radius={payload['radius']}")
        print()
        print(f"  Publishing...")
        bus.publish(evt)
        print(f"  Published.")

        # ---- 5. Capture store state AFTER publish ----
        _print_section("STEP 5: capture store state AFTER publish")

        after: Dict[str, Any] = {}
        after_records_detail: Dict[str, List[Dict[str, Any]]] = {}
        new_records: Dict[str, bool] = {}
        for nid in npc_ids + ["player"]:
            try:
                rec = store.get(nid, expected_prop)
                after[nid] = rec
                if rec is not None:
                    dumped = _dump_record(rec)
                    after_records_detail[nid] = [dumped]
                    new_records[nid] = baseline[nid] is None
                    print(f"  [AFTER] {nid}: HAS record (NEW: {new_records[nid]})")
                    for k, v in dumped.items():
                        print(f"           {k}: {v}")
                else:
                    after_records_detail[nid] = []
                    new_records[nid] = False
                    print(f"  [AFTER] {nid}: None (no belief created)")
            except Exception as e:
                after[nid] = f"ERROR: {e}"
                after_records_detail[nid] = [{"error": str(e)}]
                new_records[nid] = False
                print(f"  [AFTER] {nid}: ERROR: {e}")

        print()
        print(f"  --- store.get_all_for_agent for each NPC (AFTER) ---")
        after_all: Dict[str, int] = {}
        for nid in npc_ids + ["player"]:
            try:
                recs = store.get_all_for_agent(nid)
                after_all[nid] = len(recs) if recs else 0
                delta = after_all[nid] - baseline_all[nid]
                marker = " (NEW: +%d)" % delta if delta > 0 else ""
                print(f"  {nid}: {after_all[nid]} records{marker}")
            except Exception as e:
                after_all[nid] = -1
                print(f"  {nid}: ERROR: {e}")

        # ---- 6. Specifically check maid_lusya ----
        _print_section("STEP 6: maid_lusya — detailed belief inspection")
        try:
            lusya_rec = store.get("maid_lusya", expected_prop)
            if lusya_rec is None:
                print(f"  >>> maid_lusya has NO belief about Proposition(player, INSULTED, tavern_keeper_tornin)")
                print(f"  >>> engine.revise was called (per v2), but belief was NOT created")
                print(f"  >>> This means engine.revise either:")
                print(f"        - raised an exception (caught by try/except at L310-315)")
                print(f"        - returned None or invalid record")
                print(f"        - store.upsert failed silently")
            else:
                print(f"  >>> maid_lusya HAS belief about Proposition(player, INSULTED, tavern_keeper_tornin)")
                dumped = _dump_record(lusya_rec)
                for k, v in dumped.items():
                    print(f"    {k}: {v}")
                # Check confidence threshold
                conf = getattr(lusya_rec, "confidence", None)
                if conf is not None:
                    print()
                    print(f"    confidence = {conf}")
                    print(f"    REPORT_CONFIDENCE_THRESHOLD = 0.25")
                    print(f"    activates report_proposition (third-party spread): {conf >= 0.25}")
                    print(f"    activates claims_about_self (Lusya as victim): N/A (Lusya != object_id=tavern_keeper_tornin)")
        except Exception as e:
            print(f"  ERROR querying maid_lusya: {e}")
            traceback.print_exc()

        # ---- 7. Also check tavern_keeper_tornin (the victim) ----
        _print_section("STEP 7: tavern_keeper_tornin (the victim) — belief inspection")
        try:
            tornin_rec = store.get("tavern_keeper_tornin", expected_prop)
            if tornin_rec is None:
                print(f"  >>> tavern_keeper_tornin has NO belief (unexpected — he is the victim)")
            else:
                print(f"  >>> tavern_keeper_tornin HAS belief:")
                dumped = _dump_record(tornin_rec)
                for k, v in dumped.items():
                    print(f"    {k}: {v}")
                conf = getattr(tornin_rec, "confidence", None)
                if conf is not None:
                    print()
                    print(f"    confidence = {conf}")
                    print(f"    activates claims_about_self (Tornin as victim): {conf > 0}")
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()

        # ---- 8. Summary table ----
        _print_section("STEP 8: summary table — all NPCs")
        print(f"  {'NPC':<25} {'baseline':>10} {'after':>10} {'delta':>8}  {'expected_prop':<20}")
        for nid in npc_ids + ["player"]:
            b = baseline_all.get(nid, -1)
            a = after_all.get(nid, -1)
            d = a - b if b >= 0 and a >= 0 else "?"
            has_expected = "YES" if after.get(nid) is not None else "no"
            print(f"  {nid:<25} {b:>10} {a:>10} {d:>8}  {has_expected:<20}")

        # ---- 9. Verdict ----
        _print_section("STEP 9: VERDICT")
        maid_lusya_belief_exists = after.get("maid_lusya") is not None
        maid_lusya_count_delta = after_all.get("maid_lusya", 0) - baseline_all.get("maid_lusya", 0)
        tornin_belief_exists = after.get("tavern_keeper_tornin") is not None

        print(f"  maid_lusya belief about (player, INSULTED, tavern_keeper_tornin): {'EXISTS' if maid_lusya_belief_exists else 'MISSING'}")
        print(f"  maid_lusya total records delta: {maid_lusya_count_delta}")
        print(f"  tavern_keeper_tornin belief: {'EXISTS' if tornin_belief_exists else 'MISSING'}")
        print()

        if maid_lusya_belief_exists:
            print(f"  >>> VERDICT: B5-D1 IS NOT A DEFECT")
            print(f"  >>> maid_lusya DID receive the belief after PLAYER_INSULTS")
            print(f"  >>> engine.revise was called (v2 confirmed) AND store.upsert succeeded")
            print(f"  >>> The B5 chain works at least to: PLAYER_INSULTS → maid_lusya belief")
            print(f"  >>> The bug is DOWNSTREAM — investigate:")
            print(f"        - EpistemicContextResolver: does it see maid_lusya's belief?")
            print(f"        - DecisionHub: does SPREAD_RUMOR boost activate?")
            print(f"        - Lusya's decision: does she choose SPREAD_RUMOR?")
            print(f"        - NPC_SPOKE propagation to Tornin (B5-D2 territory)")
        else:
            print(f"  >>> VERDICT: BELIEF NOT CREATED despite engine.revise being called")
            print(f"  >>> engine.revise was called for maid_lusya (v2 confirmed)")
            print(f"  >>> But belief is NOT in EpistemicStore")
            print(f"  >>> Possible causes:")
            print(f"        - engine.revise raised exception (try/except at L310-315 swallowed it)")
            print(f"        - engine.revise returned None (no belief created)")
            print(f"        - store.upsert failed silently")
            print(f"  >>> NEXT STEP: instrument engine.revise to capture return value + exceptions")

        # ---- 10. Cleanup ----
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        del loop
        import gc
        gc.collect()
        import shutil
        shutil.rmtree(saves_dir, ignore_errors=True)

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()

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

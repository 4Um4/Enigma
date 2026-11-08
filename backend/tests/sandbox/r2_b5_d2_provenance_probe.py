# backend/tests/sandbox/r2_b5_d2_provenance_probe.py
"""
R2-B5-D2 PROVENANCE PROBE — verify full provenance chain.

Master's requirement:
  - Full Tornin record from EpistemicStore after tick 3
  - Full Borko record for same proposition before transmission
  - source_id, original_source_id, source_type, confidence,
    first_observed_tick, last_updated_tick
  - Proposition identity to exclude comparing different records

Expected:
  Tornin source_id          = guard_borko
  Tornin original_source_id  = player
  Borko original_source_id   = player (before transmission)
  Tornin source_type         = testimony

Strategy:
  1. Build loop, load NPCs, publish PLAYER_INSULTS
  2. Run 3 idle_ticks (tick 3 is where Borko transmits)
  3. After tick 3, extract:
     a. ALL Tornin records (full dump)
     b. ALL Borko records (full dump)
  4. Compare provenance fields

READ-ONLY. No production changes.
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_provenance_probe.txt"


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


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        try: self.records.append(record)
        except: pass

    def messages(self) -> List[str]:
        return [f"[{r.levelname}] {r.name}: {r.getMessage()}" for r in self.records]


_log_capture = _LogCapture()


def _install_log_capture() -> None:
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h, _LogCapture)]
    if not any(isinstance(h, _LogCapture) for h in root.handlers):
        root.addHandler(_log_capture)
    root.setLevel(logging.DEBUG)


def _reset_log_capture() -> None:
    _log_capture.records.clear()


def _dump_record(r: Any) -> Dict[str, Any]:
    """Extract all provenance fields from an EpistemicRecord."""
    out: Dict[str, Any] = {}
    for field in ("proposition", "confidence", "source_id", "original_source_id",
                  "source_type", "source_claim_id", "first_observed_tick",
                  "last_updated_tick", "agent_id", "polarity"):
        try:
            val = getattr(r, field, None)
            if field == "proposition":
                # Dump proposition details
                prop = val
                if prop is not None:
                    out["proposition_subject_id"] = getattr(prop, "subject_id", None)
                    out["proposition_predicate"] = str(getattr(prop, "predicate", None))
                    out["proposition_object_id"] = getattr(prop, "object_id", None)
                    out["proposition_polarity"] = getattr(prop, "polarity", None)
                else:
                    out["proposition"] = None
            else:
                out[field] = val
        except Exception:
            out[field] = "<error>"
    return out


def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 PROVENANCE PROBE — verify full provenance chain")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Strategy: publish PLAYER_INSULTS → 3 idle_ticks → dump Tornin + Borko records")
    print()

    _install_log_capture()
    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment
    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_prov_"))

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
        _install_log_capture()

        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
        loaded = loop._load_npcs_with_runtime("Open_road")
        print(f"  loaded {len(loaded)} NPCs")

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

        # =====================================================================
        # STEP 1: Baseline — capture Borko and Tornin records BEFORE PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 1: Baseline records (before PLAYER_INSULTS)")
        if store:
            for npc_id in ("guard_borko", "tavern_keeper_tornin"):
                records = store.get_all_for_agent(npc_id) or []
                print(f"  {npc_id}: {len(records)} records")
                for r in records:
                    print(f"    {r}")

        # =====================================================================
        # STEP 2: Publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 2: Publish PLAYER_INSULTS")
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
        print(f"  published")

        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )

        # =====================================================================
        # STEP 3: Capture records AFTER publish, BEFORE tick
        # =====================================================================
        _print_section("STEP 3: Records after publish, before tick")
        if store:
            for npc_id in ("guard_borko", "tavern_keeper_tornin"):
                records = store.get_all_for_agent(npc_id) or []
                print(f"\n  {npc_id}: {len(records)} records")
                for r in records:
                    dumped = _dump_record(r)
                    print(f"    {json.dumps(dumped, indent=2, default=str, ensure_ascii=False)}")

        # =====================================================================
        # STEP 4: Run 3 idle_ticks
        # =====================================================================
        _print_section("STEP 4: Run 3 idle_ticks")
        for tick_num in range(1, 4):
            _reset_log_capture()
            try:
                result = loop.idle_tick("Open_road", "tavern")
                status = result.get("status") if isinstance(result, dict) else "N/A"
            except Exception as e:
                status = f"ERROR: {e}"

            all_logs = _log_capture.messages()
            dh_sr_logs = [l for l in all_logs if "DECISION_HUB" in l and "spread_rumor" in l.lower()]
            epistemic_logs = [l for l in all_logs if "EPISTEMIC_REPORT_TARGET" in l]
            print(f"  Tick {tick_num}: status={status}")
            print(f"    DH spread_rumor: {len(dh_sr_logs)}, EPISTEMIC_REPORT: {len(epistemic_logs)}")
            for l in dh_sr_logs[:2]:
                print(f"      {l[:200]}")
            for l in epistemic_logs[:1]:
                print(f"      {l[:200]}")

        # =====================================================================
        # STEP 5: Dump ALL Tornin records (full provenance)
        # =====================================================================
        _print_section("STEP 5: ALL Tornin records (full provenance dump)")
        tornin_records: List[Any] = []
        if store:
            tornin_records = store.get_all_for_agent("tavern_keeper_tornin") or []
            print(f"  Tornin total records: {len(tornin_records)}")
            for i, r in enumerate(tornin_records):
                dumped = _dump_record(r)
                print(f"\n  Record [{i}]:")
                print(f"  {json.dumps(dumped, indent=2, default=str, ensure_ascii=False)}")

        # =====================================================================
        # STEP 6: Dump ALL Borko records (full provenance)
        # =====================================================================
        _print_section("STEP 6: ALL Borko records (full provenance dump)")
        borko_records: List[Any] = []
        if store:
            borko_records = store.get_all_for_agent("guard_borko") or []
            print(f"  Borko total records: {len(borko_records)}")
            for i, r in enumerate(borko_records):
                dumped = _dump_record(r)
                print(f"\n  Record [{i}]:")
                print(f"  {json.dumps(dumped, indent=2, default=str, ensure_ascii=False)}")

        # =====================================================================
        # STEP 7: Provenance verification
        # =====================================================================
        _print_section("STEP 7: Provenance verification")

        # Find Tornin's record with source_id=guard_borko
        tornin_from_borko = None
        for r in tornin_records:
            if getattr(r, "source_id", None) == "guard_borko":
                tornin_from_borko = r
                break

        # Find Borko's record for the same proposition (player INSULTED tavern_keeper_tornin)
        borko_player_belief = None
        for r in borko_records:
            prop = getattr(r, "proposition", None)
            if prop and getattr(prop, "subject_id", None) == "player" \
               and getattr(prop, "predicate", None) == Predicate.INSULTED \
               and getattr(prop, "object_id", None) == "tavern_keeper_tornin":
                borko_player_belief = r
                break

        print(f"\n  === Tornin's record from guard_borko ===")
        if tornin_from_borko:
            dumped = _dump_record(tornin_from_borko)
            print(f"  {json.dumps(dumped, indent=2, default=str, ensure_ascii=False)}")
        else:
            print(f"  NOT FOUND — Tornin has no record with source_id=guard_borko")

        print(f"\n  === Borko's record for player INSULTED tavern_keeper_tornin ===")
        if borko_player_belief:
            dumped = _dump_record(borko_player_belief)
            print(f"  {json.dumps(dumped, indent=2, default=str, ensure_ascii=False)}")
        else:
            print(f"  NOT FOUND — Borko has no record for this proposition")

        # =====================================================================
        # STEP 8: Provenance check (4 fields)
        # =====================================================================
        _print_section("STEP 8: Provenance check (4 fields)")

        checks: List[Tuple[str, bool]] = []

        # Check 1: Tornin source_id = guard_borko
        tornin_source = getattr(tornin_from_borko, "source_id", None) if tornin_from_borko else None
        check1 = tornin_source == "guard_borko"
        checks.append(("Tornin source_id = guard_borko", check1))
        print(f"  Tornin source_id: {tornin_source} → {'✅' if check1 else '❌'}")

        # Check 2: Tornin original_source_id = player
        tornin_orig = getattr(tornin_from_borko, "original_source_id", None) if tornin_from_borko else None
        check2 = tornin_orig == "player"
        checks.append(("Tornin original_source_id = player", check2))
        print(f"  Tornin original_source_id: {tornin_orig} → {'✅' if check2 else '❌'}")

        # Check 3: Borko original_source_id = player (before transmission)
        borko_orig = getattr(borko_player_belief, "original_source_id", None) if borko_player_belief else None
        check3 = borko_orig == "player"
        checks.append(("Borko original_source_id = player", check3))
        print(f"  Borko original_source_id: {borko_orig} → {'✅' if check3 else '❌'}")

        # Check 4: Tornin source_type = testimony
        tornin_stype = getattr(tornin_from_borko, "source_type", None) if tornin_from_borko else None
        check4 = tornin_stype == "testimony"
        checks.append(("Tornin source_type = testimony", check4))
        print(f"  Tornin source_type: {tornin_stype} → {'✅' if check4 else '❌'}")

        # Summary
        passed = sum(1 for _, p in checks if p)
        total = len(checks)
        print(f"\n  {passed}/{total} provenance checks passed")

        if passed == total:
            print(f"\n  >>> PROVENANCE PASS — full chain verified:")
            print(f"  >>> player (original) → guard_borko (source) → tavern_keeper_tornin (listener)")
            print(f"  >>> original_source_id=player preserved through testimony chain")
        else:
            print(f"\n  >>> PROVENANCE NEEDS ATTENTION — some fields mismatch")
            if not check2:
                print(f"  >>> Tornin's original_source_id = {tornin_orig} (expected 'player')")
                print(f"  >>> This means Tornin's belief came from someone other than player directly")
                if borko_player_belief:
                    borko_orig_val = getattr(borko_player_belief, "original_source_id", None)
                    print(f"  >>> Borko's original_source_id = {borko_orig_val}")
                    if borko_orig_val != "player":
                        print(f"  >>> Borko's belief ALSO doesn't trace to player — chain deeper")
                    else:
                        print(f"  >>> Borko's belief traces to player, but Tornin's doesn't trace to player through Borko")
                        print(f"  >>> Possible: ClaimEventSubscriber didn't use _speaker_record.original_source_id correctly")

        # ---- Cleanup ----
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

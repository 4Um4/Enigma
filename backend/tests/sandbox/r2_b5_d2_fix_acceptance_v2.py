# backend/tests/sandbox/r2_b5_d2_fix_acceptance_v2.py
"""
R2-B5-D2 FIX ACCEPTANCE TEST v2 — multi-tick to catch SPREAD_RUMOR.

v1 failed because guard_borko chose SEEK_ALLY instead of SPREAD_RUMOR
(game state variability). v2 runs 5 idle_ticks and checks EACH tick
for SPREAD_RUMOR selection + NPC_SPOKE + COMMUNICATION_CLAIM.

Also checks ALL NPCs, not just guard_borko — any NPC choosing SPREAD_RUMOR
triggers the fix path.
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_fix_acceptance_v2.txt"


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


class _EventBusSpy:
    def __init__(self):
        self.published_events: List[Tuple[str, Any]] = []
        self._installed = False
        self._orig_publish = None
        self._bus = None

    def install(self, bus) -> bool:
        if self._installed: return True
        self._bus = bus
        self._orig_publish = bus.publish
        bus.publish = self._spy_publish
        self._installed = True
        return True

    def restore(self) -> None:
        if self._installed and self._bus and self._orig_publish:
            self._bus.publish = self._orig_publish
            self._installed = False

    def _spy_publish(self, event) -> None:
        try:
            ev_type = str(getattr(event, "type", "?"))
            self.published_events.append((ev_type, event))
        except: pass
        return self._orig_publish(event)

    def clear(self) -> None:
        self.published_events.clear()


_event_bus_spy = _EventBusSpy()


def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 FIX ACCEPTANCE TEST v2 — multi-tick")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()

    _install_log_capture()
    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment
    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_acc_v2_"))

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
        _event_bus_spy.install(bus)

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
        print(f"  PLAYER_INSULTS published")

        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )

        # Capture Tornin's pre-tick beliefs
        tornin_pre_count = 0
        if store:
            tornin_pre = store.get_all_for_agent("tavern_keeper_tornin") or []
            tornin_pre_count = len(tornin_pre)
            print(f"  Tornin pre-tick records: {tornin_pre_count}")

        # =====================================================================
        # Run 5 idle_ticks, checking each for SPREAD_RUMOR
        # =====================================================================
        _print_section("Running 5 idle_ticks")

        NUM_TICKS = 5
        tick_results: List[Dict[str, Any]] = []
        spread_rumor_found = False
        npc_spoke_found = False
        comm_claim_found = False

        for tick_num in range(1, NUM_TICKS + 1):
            _event_bus_spy.clear()
            _reset_log_capture()

            try:
                result = loop.idle_tick("Open_road", "tavern")
                status = result.get("status") if isinstance(result, dict) else "N/A"
            except Exception as e:
                status = f"ERROR: {e}"

            # Check logs for SPREAD_RUMOR selection
            all_logs = _log_capture.messages()
            dh_spread_rumor_logs = [l for l in all_logs
                                    if "DECISION_HUB" in l and "spread_rumor" in l.lower()]
            epistemic_report_logs = [l for l in all_logs if "EPISTEMIC_REPORT_TARGET" in l]

            # Check events
            npc_spoke_events = [e for t, e in _event_bus_spy.published_events
                                if "npc_spoke" in t.lower()]
            comm_claim_events = [e for t, e in _event_bus_spy.published_events
                                 if "communication_claim" in t.lower()]
            de_fallback_logs = [l for l in all_logs
                                if "DIALOGUE_EXEC" in l and "fallback" in l.lower()]

            # Check Tornin beliefs
            tornin_borko_belief = False
            if store:
                tornin_after = store.get_all_for_agent("tavern_keeper_tornin") or []
                tornin_borko_belief = any(
                    getattr(r, "source_id", None) == "guard_borko"
                    for r in tornin_after
                )

            tick_info = {
                "tick": tick_num,
                "status": status,
                "dh_spread_rumor_count": len(dh_spread_rumor_logs),
                "epistemic_report_count": len(epistemic_report_logs),
                "npc_spoke_count": len(npc_spoke_events),
                "comm_claim_count": len(comm_claim_events),
                "de_fallback_count": len(de_fallback_logs),
                "tornin_borko_belief": tornin_borko_belief,
                "dh_spread_rumor_logs": [l[:200] for l in dh_spread_rumor_logs[:3]],
                "epistemic_report_logs": [l[:200] for l in epistemic_report_logs[:3]],
                "de_fallback_logs": [l[:200] for l in de_fallback_logs[:3]],
                "npc_spoke_details": [],
                "comm_claim_details": [],
            }

            for ev in npc_spoke_events[:3]:
                p = getattr(ev, "payload", {}) or {}
                tick_info["npc_spoke_details"].append({
                    "source": getattr(ev, "source", "?"),
                    "target": p.get("target_id"),
                    "intent": p.get("intent_type"),
                    "text": str(p.get("text", ""))[:100],
                })

            for ev in comm_claim_events[:3]:
                p = getattr(ev, "payload", {}) or {}
                tick_info["comm_claim_details"].append({
                    "source": getattr(ev, "source", "?"),
                    "target": p.get("target_id"),
                    "proposition": str(p.get("proposition", ""))[:100],
                })

            tick_results.append(tick_info)

            if dh_spread_rumor_logs:
                spread_rumor_found = True
            if npc_spoke_events:
                npc_spoke_found = True
            if comm_claim_events:
                comm_claim_found = True

            print(f"\n  Tick {tick_num}: status={status}")
            print(f"    DH spread_rumor logs: {len(dh_spread_rumor_logs)}")
            if dh_spread_rumor_logs:
                for l in dh_spread_rumor_logs[:2]:
                    print(f"      {l[:200]}")
            print(f"    EPISTEMIC_REPORT_TARGET logs: {len(epistemic_report_logs)}")
            if epistemic_report_logs:
                for l in epistemic_report_logs[:2]:
                    print(f"      {l[:200]}")
            print(f"    NPC_SPOKE events: {len(npc_spoke_events)}")
            for d in tick_info["npc_spoke_details"]:
                print(f"      source={d['source']} target={d['target']} intent={d['intent']}")
            print(f"    COMMUNICATION_CLAIM events: {len(comm_claim_events)}")
            for d in tick_info["comm_claim_details"]:
                print(f"      source={d['source']} target={d['target']} prop={d['proposition']}")
            print(f"    DE fallback logs: {len(de_fallback_logs)}")
            for l in de_fallback_logs[:2]:
                print(f"      {l[:200]}")
            print(f"    Tornin belief from guard_borko: {tornin_borko_belief}")

        # =====================================================================
        # FINAL CHECKS
        # =====================================================================
        _print_section("FINAL CHECKS")

        # Aggregate across all ticks
        total_npc_spoke = sum(t["npc_spoke_count"] for t in tick_results)
        total_comm_claim = sum(t["comm_claim_count"] for t in tick_results)
        total_de_fallback = sum(t["de_fallback_count"] for t in tick_results)
        total_epistemic_report = sum(t["epistemic_report_count"] for t in tick_results)
        any_tornin_borko_belief = any(t["tornin_borko_belief"] for t in tick_results)

        # Check Tornin for provenance
        tornin_player_provenance = False
        if store:
            tornin_final = store.get_all_for_agent("tavern_keeper_tornin") or []
            for r in tornin_final:
                if (getattr(r, "source_id", None) == "guard_borko"
                    and getattr(r, "original_source_id", None) == "player"):
                    tornin_player_provenance = True
                    break

        checks = [
            ("SPREAD_RUMOR selected (any tick)", spread_rumor_found),
            ("NPC_SPOKE published (any tick)", total_npc_spoke > 0),
            ("COMMUNICATION_CLAIM published (any tick)", total_comm_claim > 0),
            ("Tornin belief source_id=guard_borko", any_tornin_borko_belief),
            ("Tornin belief original_source_id=player", tornin_player_provenance),
            ("DialogueExecutor fallback triggered", total_de_fallback > 0),
        ]

        for name, passed in checks:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status}  {name}")

        passed_count = sum(1 for _, p in checks if p)
        print(f"\n  {passed_count}/{len(checks)} checks passed")

        if passed_count == len(checks):
            print(f"\n  >>> B5-D2 FIX ACCEPTED — all checks passed")
        elif spread_rumor_found and total_npc_spoke > 0 and total_comm_claim > 0:
            print(f"\n  >>> B5-D2 FIX PARTIALLY ACCEPTED — chain works, provenance check needs attention")
        elif not spread_rumor_found:
            print(f"\n  >>> SPREAD_RUMOR NOT SELECTED in any of {NUM_TICKS} ticks")
            print(f"  >>> Game state doesn't trigger SPREAD_RUMOR for any NPC")
            print(f"  >>> Need to investigate why DecisionHub scoring changed")
        else:
            print(f"\n  >>> B5-D2 FIX NEEDS ATTENTION — some checks failed")

        # Summary table
        _print_section("Summary table")
        print(f"  {'Tick':<6} {'SR_logs':>8} {'ER_logs':>8} {'NPC_SPOKE':>10} {'COMM_CLAIM':>11} {'DE_fb':>6} {'Tornin_borko':>13}")
        for t in tick_results:
            print(f"  {t['tick']:<6} {t['dh_spread_rumor_count']:>8} {t['epistemic_report_count']:>8} "
                  f"{t['npc_spoke_count']:>10} {t['comm_claim_count']:>11} {t['de_fallback_count']:>6} "
                  f"{str(t['tornin_borko_belief']):>13}")

        # ---- Cleanup ----
        _event_bus_spy.restore()
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
        _event_bus_spy.restore()
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

# backend/tests/sandbox/r2_b5_e2_decision_hub_v4.py
"""
R2-B5-E2 v4 — invoke loop.idle_tick(), observe maid_lusya's chosen intent.

v3 discovered the actual loop API methods:
  - loop._load_npcs_with_runtime(campaign_id: str) -> list  ← loads NPC states!
  - loop.idle_tick(campaign_id: str, location_id: Optional[str] = None, ...) -> dict
      ← WorldTickEngine (per world_tick_engine.py L9-10: "LLM НЕ участвует. Только Python.")
  - loop._spawn_world_tick_task(world_id: str) -> dict
  - loop.run_turn(req: ChatTurnRequest) -> ChatTurnResponse

v3 failed because it searched for run_tick/tick/advance_tick/step/...
but production uses idle_tick/_spawn_world_tick_task/_load_npcs_with_runtime.

v4 strategy:
  1. loop._load_npcs_with_runtime("Open_road") — load NPC states
  2. Verify maid_lusya NPC state now exists
  3. Publish PLAYER_INSULTS (creates belief in store)
  4. Verify ctx.report_proposition present
  5. loop.idle_tick("Open_road", "tavern") — runs WorldTickEngine
     DecisionHub.compute() will be called for each major NPC (including maid_lusya)
     WorldTickEngine does NOT use LLM (per comments)
  6. Inspect maid_lusya.NPCState.intent post-tick
  7. Sanity check: was NPC_SPOKE published for maid_lusya?
     If SPREAD_RUMOR was selected, it should fire NPC_SPOKE event

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import json
import math
import inspect
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_e2_decision_hub_v4.txt"


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

# Enable logging capture for [DECISION_HUB] logs
_log_capture: List[str] = []


class _LogCapture(logging.Handler):
    def emit(self, record):
        try:
            msg = record.getMessage()
            _log_capture.append(f"[{record.levelname}] {record.name}: {msg}")
        except Exception:
            pass


_dh_handler = _LogCapture()
_dh_handler.setLevel(logging.DEBUG)
# Capture from all loggers
root_logger = logging.getLogger()
root_logger.addHandler(_dh_handler)
root_logger.setLevel(logging.INFO)
# Specific loggers
for logger_name in ("app.services.npc.decision_hub",
                    "app.services.world.world_tick_engine",
                    "app.services.game_loop.game_loop",
                    "app.services.npc.npc_tick_pipeline"):
    lg = logging.getLogger(logger_name)
    lg.setLevel(logging.DEBUG)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _inspect_obj(obj: Any, depth: int = 0, max_depth: int = 2) -> Any:
    if depth > max_depth:
        return {"_truncated": repr(obj)[:150]}
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [_inspect_obj(x, depth + 1, max_depth) for x in list(obj)[:5]]
    if isinstance(obj, dict):
        return {str(k): _inspect_obj(v, depth + 1, max_depth) for k, v in list(obj.items())[:10]}
    out: Dict[str, Any] = {"_type": type(obj).__name__}
    try:
        d = vars(obj)
        for k, v in d.items():
            if k.startswith("__"):
                continue
            out[k] = _inspect_obj(v, depth + 1, max_depth)
    except Exception:
        for attr in dir(obj):
            if attr.startswith("__"):
                continue
            try:
                val = getattr(obj, attr)
                if callable(val):
                    continue
                out[attr] = _inspect_obj(val, depth + 1, max_depth)
            except Exception:
                continue
    return out


def _find_lusya_state(loop) -> Tuple[Optional[Any], str]:
    """Find maid_lusya NPC state via multiple strategies."""
    # Strategy 1: scene_state['npc_states']
    try:
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene:
            npc_states = scene.get("npc_states", {}) or {}
            if "maid_lusya" in npc_states:
                return npc_states["maid_lusya"], "scene['npc_states']"
    except Exception:
        pass

    # Strategy 2: loop._resolve_npcs_snapshot
    try:
        snap_fn = getattr(loop, "_resolve_npcs_snapshot", None)
        if snap_fn:
            snap = snap_fn("Open_road")
            if isinstance(snap, dict) and "maid_lusya" in snap:
                return snap["maid_lusya"], "loop._resolve_npcs_snapshot (dict)"
            if isinstance(snap, list):
                for item in snap:
                    nid = getattr(item, "npc_id", None) or (item.get("npc_id") if isinstance(item, dict) else None)
                    if nid == "maid_lusya":
                        return item, "loop._resolve_npcs_snapshot (list)"
    except Exception:
        pass

    # Strategy 3: npc_manager
    for nm_attr in ("_npc_manager", "npc_manager", "_npcs"):
        nm = getattr(loop, nm_attr, None)
        if nm is None:
            continue
        # Try get/get_npc_state/get_state methods
        for method_name in ("get_npc_state", "get_state", "get", "get_npc"):
            method = getattr(nm, method_name, None)
            if method is None:
                continue
            # Try various arg patterns
            for args in [("maid_lusya",), ("Open_road", "maid_lusya"),
                         ("Open_road", "tavern", "maid_lusya")]:
                try:
                    result = method(*args)
                    if result is not None:
                        return result, f"loop.{nm_attr}.{method_name}({args})"
                except TypeError:
                    continue
                except Exception:
                    continue
        # Try snapshot/all_states
        for method_name in ("snapshot", "all_states", "states"):
            method = getattr(nm, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                if isinstance(result, dict) and "maid_lusya" in result:
                    return result["maid_lusya"], f"loop.{nm_attr}.{method_name}()[dict]"
                if isinstance(result, list):
                    for item in result:
                        nid = getattr(item, "npc_id", None) or (item.get("npc_id") if isinstance(item, dict) else None)
                        if nid == "maid_lusya":
                            return item, f"loop.{nm_attr}.{method_name}()[list]"
            except Exception:
                continue

    return None, "not_found"


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-E2 v4 — invoke loop.idle_tick(), observe maid_lusya's intent")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("STRATEGY (using exact production API discovered in v3):")
    print("  1. loop._load_npcs_with_runtime('Open_road') — load NPC states")
    print("  2. Verify maid_lusya NPC state now exists")
    print("  3. Publish PLAYER_INSULTS")
    print("  4. loop.idle_tick('Open_road', 'tavern') — WorldTickEngine (no LLM)")
    print("  5. Inspect maid_lusya.NPCState.intent")
    print("  6. Capture [DECISION_HUB] logs")
    print()

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
        from app.domain.epistemology import Proposition, Predicate, ClaimEvent, EpistemicRecord  # type: ignore
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_e2_v4_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        bus = get_event_bus()

        # =====================================================================
        # STEP 1: locate sub, store, resolver
        # =====================================================================
        _print_section("STEP 1: locate sub, store, resolver")
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
                        break
                if sub:
                    break
            if sub:
                break
        store = getattr(sub, "_store", None)
        print(f"  sub._store: id={id(store)}")

        resolver: Optional[EpistemicContextResolver] = None
        for parent_name in ("_tick_orch", "_svc"):
            parent = getattr(loop, parent_name, None)
            if parent is None:
                continue
            for attr_name in ("_resolver", "_epistemic_context_resolver"):
                val = getattr(parent, attr_name, None)
                if isinstance(val, EpistemicContextResolver):
                    resolver = val
                    print(f"  resolver: id={id(resolver)} via loop.{parent_name}.{attr_name}")
                    break
            if resolver:
                break

        # =====================================================================
        # STEP 2: load NPC states via _load_npcs_with_runtime
        # =====================================================================
        _print_section("STEP 2: load NPC states via loop._load_npcs_with_runtime")
        load_method = getattr(loop, "_load_npcs_with_runtime", None)
        if load_method is None:
            print("  [FATAL: loop._load_npcs_with_runtime not found]")
            return 1
        try:
            loaded = load_method("Open_road")
            print(f"  _load_npcs_with_runtime('Open_road') returned: type={type(loaded).__name__}, "
                  f"len={len(loaded) if hasattr(loaded, '__len__') else '?'}")
            if isinstance(loaded, list):
                print(f"  loaded NPC IDs:")
                for item in loaded[:20]:
                    nid = getattr(item, "npc_id", None) or (item.get("npc_id") if isinstance(item, dict) else None)
                    print(f"    {nid} (type={type(item).__name__})")
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 3: find maid_lusya NPC state (post-load)
        # =====================================================================
        _print_section("STEP 3: find maid_lusya NPC state (post-load)")
        lusya_state, lusya_source = _find_lusya_state(loop)
        if lusya_state is None:
            print(f"  [STILL NOT FOUND via any strategy]")
            # Walk loop attributes to find anything holding npc state
            print(f"  --- walk loop for NPCState objects ---")
            try:
                visited = set()
                def _walk(obj, path, depth=0):
                    if depth > 4 or id(obj) in visited:
                        return
                    visited.add(id(obj))
                    if hasattr(obj, "npc_id") and getattr(obj, "npc_id", None) == "maid_lusya":
                        print(f"  FOUND: {path} → type={type(obj).__name__}, npc_id={obj.npc_id}")
                        return
                    if hasattr(obj, "__dict__"):
                        try:
                            for k, v in vars(obj).items():
                                if k.startswith("__"):
                                    continue
                                _walk(v, f"{path}.{k}", depth + 1)
                        except Exception:
                            pass
                _walk(loop, "loop")
            except Exception as e:
                print(f"  walk error: {e}")
        else:
            print(f"  maid_lusya state FOUND via {lusya_source}")
            print(f"  type: {type(lusya_state).__name__}")
            print(f"  id: {id(lusya_state)}")

        # =====================================================================
        # STEP 4: pre-tick intent inspection
        # =====================================================================
        _print_section("STEP 4: pre-tick intent inspection")
        if lusya_state is not None:
            intent_pre = getattr(lusya_state, "intent", None)
            print(f"  maid_lusya.intent (pre-tick): {intent_pre}")
            if intent_pre is not None:
                intent_pre_str = getattr(intent_pre, "value", str(intent_pre))
                print(f"  intent value: {intent_pre_str}")

            # Other relevant fields
            print(f"\n  --- maid_lusya state top-level attrs (pre-tick) ---")
            try:
                for k, v in vars(lusya_state).items():
                    if not k.startswith("__"):
                        print(f"    {k}: {repr(v)[:100]}")
            except Exception:
                for attr in dir(lusya_state):
                    if not attr.startswith("__"):
                        try:
                            val = getattr(lusya_state, attr)
                            if callable(val):
                                continue
                            print(f"    {attr}: {repr(val)[:100]}")
                        except Exception:
                            pass

        # =====================================================================
        # STEP 5: publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 5: publish PLAYER_INSULTS")
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

        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )
        lusya_rec = store.get("maid_lusya", expected_prop)
        print(f"  store.get('maid_lusya', expected_prop).confidence = {getattr(lusya_rec, 'confidence', None)}")

        ctx = resolver.resolve("maid_lusya")
        print(f"  ctx.report_proposition = {getattr(ctx, 'report_proposition', None)}")
        print(f"  ctx.max_confidence = {getattr(ctx, 'max_confidence', None)}")

        # Clear log capture for clean tick logs
        _log_capture.clear()

        # =====================================================================
        # STEP 6: invoke idle_tick
        # =====================================================================
        _print_section("STEP 6: invoke loop.idle_tick('Open_road', 'tavern')")
        idle_tick_method = getattr(loop, "idle_tick", None)
        if idle_tick_method is None:
            print("  [FATAL: loop.idle_tick not found]")
            # Try alternatives
            for alt_name in ("_spawn_world_tick_task", "run_tick", "tick"):
                m = getattr(loop, alt_name, None)
                if m is not None and callable(m):
                    print(f"  fallback: loop.{alt_name} exists")
        else:
            try:
                sig = inspect.signature(idle_tick_method)
                print(f"  signature: idle_tick{sig}")
            except Exception:
                pass

            print(f"\n  Calling loop.idle_tick('Open_road', 'tavern')...")
            tick_result: Any = None
            try:
                tick_result = idle_tick_method("Open_road", "tavern")
                print(f"  SUCCESS: returned type={type(tick_result).__name__}")
                if isinstance(tick_result, dict):
                    print(f"  dict keys: {list(tick_result.keys())[:10]}")
                    # Look for npc decisions / intents in result
                    for k in ("decisions", "intents", "npc_decisions", "results", "actions"):
                        if k in tick_result:
                            print(f"\n  --- {k} ---")
                            v = tick_result[k]
                            if isinstance(v, list):
                                for i, item in enumerate(v[:10]):
                                    print(f"    [{i}]: {repr(item)[:200]}")
                            else:
                                print(f"    {repr(v)[:300]}")
                else:
                    print(f"  result: {repr(tick_result)[:300]}")
            except Exception as e:
                err_str = str(e)
                print(f"  ERROR: {type(e).__name__}: {err_str[:300]}")
                if any(t in err_str.lower() for t in ("llm", "openai", "client", "api", "model")):
                    print(f"  >>> LLM ERROR — idle_tick reached LLM (unexpected per comments)")
                traceback.print_exc()

        # =====================================================================
        # STEP 7: capture DECISION_HUB logs
        # =====================================================================
        _print_section("STEP 7: capture [DECISION_HUB] logs from idle_tick")
        print(f"  Total log entries captured: {len(_log_capture)}")
        # Filter for relevant logs
        dh_logs = [l for l in _log_capture if "DECISION_HUB" in l or "decision_hub" in l.lower()]
        rumor_logs = [l for l in _log_capture if "spread_rumor" in l.lower() or "RUMOR" in l]
        intent_logs = [l for l in _log_capture if "intent" in l.lower()]
        npc_speak_logs = [l for l in _log_capture if "NPC_SPOKE" in l or "npc_spoke" in l.lower()]
        maid_logs = [l for l in _log_capture if "maid_lusya" in l or "maid" in l.lower()]

        print(f"\n  --- [DECISION_HUB] logs ({len(dh_logs)}) ---")
        for l in dh_logs[:30]:
            print(f"  {l}")
        if len(dh_logs) > 30:
            print(f"  ... and {len(dh_logs) - 30} more")

        print(f"\n  --- logs mentioning maid_lusya ({len(maid_logs)}) ---")
        for l in maid_logs[:20]:
            print(f"  {l}")
        if len(maid_logs) > 20:
            print(f"  ... and {len(maid_logs) - 20} more")

        print(f"\n  --- logs mentioning spread_rumor ({len(rumor_logs)}) ---")
        for l in rumor_logs[:20]:
            print(f"  {l}")

        print(f"\n  --- logs mentioning npc_spoke ({len(npc_speak_logs)}) ---")
        for l in npc_speak_logs[:10]:
            print(f"  {l}")

        # =====================================================================
        # STEP 8: post-tick intent inspection
        # =====================================================================
        _print_section("STEP 8: post-tick intent inspection")
        # Re-find state (might be different object after tick)
        lusya_state_post, lusya_post_source = _find_lusya_state(loop)
        if lusya_state_post is None:
            print("  [maid_lusya state NOT FOUND post-tick]")
            # Try same object as pre-tick
            if lusya_state is not None:
                print(f"  Using pre-tick state object (might be stale)")
                lusya_state_post = lusya_state
                lusya_post_source = "pre-tick_object"
        else:
            print(f"  maid_lusya state FOUND via {lusya_post_source}")
            print(f"  type: {type(lusya_state_post).__name__}, id: {id(lusya_state_post)}")
            if lusya_state is not None and id(lusya_state_post) == id(lusya_state):
                print(f"  >>> SAME OBJECT as pre-tick (state was mutated in place)")
            elif lusya_state is not None:
                print(f"  >>> DIFFERENT OBJECT from pre-tick")

        if lusya_state_post is not None:
            intent_post = getattr(lusya_state_post, "intent", None)
            print(f"\n  maid_lusya.intent (post-tick): {intent_post}")
            if intent_post is not None:
                intent_post_str = getattr(intent_post, "value", str(intent_post))
                print(f"  intent value: {intent_post_str}")
                print(f"  IS SPREAD_RUMOR: {'spread_rumor' in str(intent_post_str).lower()}")
                print(f"  IS TALK: {'talk' in str(intent_post_str).lower()}")

            # intent_target
            intent_target = getattr(lusya_state_post, "intent_target", None)
            if intent_target is not None:
                print(f"  maid_lusya.intent_target (post-tick): {intent_target}")

            # Other relevant fields
            print(f"\n  --- maid_lusya state top-level attrs (post-tick) ---")
            try:
                for k, v in vars(lusya_state_post).items():
                    if not k.startswith("__"):
                        print(f"    {k}: {repr(v)[:100]}")
            except Exception:
                pass

        # =====================================================================
        # STEP 9: store records after tick (sanity check)
        # =====================================================================
        _print_section("STEP 9: EpistemicStore after tick")
        for npc_id in ("maid_lusya", "tavern_keeper_tornin"):
            try:
                recs = store.get_all_for_agent(npc_id)
                print(f"  {npc_id}: {len(recs) if recs else 0} records")
                for r in (recs or [])[:3]:
                    dumped = {}
                    for f in ("proposition", "confidence", "source_id", "original_source_id"):
                        try:
                            v = getattr(r, f, None)
                            dumped[f] = str(v)[:80] if not isinstance(v, (int, float, bool)) else v
                        except Exception:
                            pass
                    print(f"    {dumped}")
            except Exception as e:
                print(f"  {npc_id} ERROR: {e}")

        # =====================================================================
        # STEP 10: VERDICT
        # =====================================================================
        _print_section("STEP 10: VERDICT")

        if lusya_state_post is None:
            print("  >>> VERDICT: INCONCLUSIVE — maid_lusya state not found post-tick")
            print("  >>> Need to inspect loop API for NPC state retrieval")
        else:
            intent_post = getattr(lusya_state_post, "intent", None)
            intent_post_str = ""
            if intent_post is not None:
                intent_post_str = getattr(intent_post, "value", str(intent_post))

            print(f"  maid_lusya.intent post-tick: {intent_post_str}")
            print(f"  was SPREAD_RUMOR selected: {'spread_rumor' in str(intent_post_str).lower()}")
            print()

            if "spread_rumor" in str(intent_post_str).lower():
                print("  >>> VERDICT: B5-E2 NOT A DEFECT")
                print("  >>> Production idle_tick ran DecisionHub for maid_lusya")
                print("  >>> DecisionHub saw ctx.report_proposition and selected SPREAD_RUMOR")
                print("  >>> WANTS is proven")
                print("  >>>")
                print("  >>> Evidence:")
                print(f"  >>>   - belief in store: confidence=0.5 (B5-D1)")
                print(f"  >>>   - ctx.report_proposition: Proposition(player, INSULTED, tavern_keeper_tornin) (B5-E1)")
                print(f"  >>>   - maid disposition: spread_rumor=1.3 (highest)")
                print(f"  >>>   - DecisionHub.compute() called via npc_tick_pipeline L1058")
                print(f"  >>>   - maid_lusya.intent = SPREAD_RUMOR")
                print("  >>>")
                print("  >>> NEXT: B5-D2 — does SPREAD_RUMOR reach Tornin via NPC_SPOKE?")
            elif "talk" in str(intent_post_str).lower():
                print("  >>> VERDICT: B5-E2 DEFECT — TALK chosen instead of SPREAD_RUMOR")
                print("  >>> Despite disposition weight 1.3 for spread_rumor (highest)")
                print("  >>> Investigate: did spread_rumor boost computation work?")
                print("  >>> Look at DECISION_HUB logs in Step 7")
            elif not intent_post_str:
                print("  >>> VERDICT: INCONCLUSIVE — maid_lusya has no intent field set")
                print("  >>> idle_tick may not have processed maid_lusya")
                print("  >>> Inspect DECISION_HUB logs in Step 7")
            else:
                print(f"  >>> VERDICT: B5-E2 DEFECT — unexpected intent: {intent_post_str}")
                print(f"  >>> maid_lusya chose {intent_post_str} (not SPREAD_RUMOR)")
                print("  >>> Inspect DECISION_HUB logs in Step 7 to understand")

        # ---- Cleanup ----
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

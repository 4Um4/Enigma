# backend/tests/sandbox/r2_b5_e2_decision_hub_v3.py
"""
R2-B5-E2 v3 — invoke production tick, observe maid_lusya's chosen intent.

v2 confirmed:
  - DecisionHub class imported via `from app.services.npc.decision_hub import DecisionHub`
  - Main method is `compute()` at L462 (NOT `decide()`)
  - Production call site: npc_tick_pipeline.py L1058:
        DecisionHub(rng=_rng).compute(state=state_l2, personality=profile_l0, ...)
  - SPREAD_RUMOR boost reads `epistemic_context.report_proposition` (L356-366, L2026-2031)
  - maid disposition: spread_rumor=1.3 (highest)
  - scene['npc_states'] is empty — NPC states load lazily during tick

v3 approach:
  - Don't try to invoke DecisionHub directly (15+ params, too complex)
  - Instead: publish PLAYER_INSULTS, then run ONE production tick
  - After tick: inspect maid_lusya's NPCState.intent field
  - Check whether intent == SPREAD_RUMOR

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_e2_decision_hub_v3.txt"


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


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-E2 v3 — invoke production tick, observe maid_lusya's intent")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("STRATEGY:")
    print("  1. Build game loop")
    print("  2. Initialize scene")
    print("  3. Publish PLAYER_INSULTS")
    print("  4. Find & invoke tick method on game loop")
    print("  5. After tick, find maid_lusya NPC state")
    print("  6. Inspect NPCState.intent — is it SPREAD_RUMOR?")
    print()

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
        from app.domain.epistemology import Proposition, Predicate, ClaimEvent, EpistemicRecord  # type: ignore
        from app.models.npc_state import NPCState, Intent  # type: ignore
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_e2_v3_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        bus = get_event_bus()

        # =====================================================================
        # STEP 1: locate sub, store, resolver (already known from B5-D1, B5-E1)
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
        # STEP 2: identify tick invocation method on game loop
        # =====================================================================
        _print_section("STEP 2: identify tick invocation method on game loop")
        tick_candidates: List[str] = []
        for attr_name in sorted(dir(loop)):
            if attr_name.startswith("__"):
                continue
            lowered = attr_name.lower()
            if any(kw in lowered for kw in ("tick", "step", "advance", "run", "process")):
                try:
                    val = getattr(loop, attr_name)
                    if callable(val):
                        tick_candidates.append(attr_name)
                        try:
                            sig = inspect.signature(val)
                            print(f"  loop.{attr_name}{sig}")
                        except (ValueError, TypeError):
                            print(f"  loop.{attr_name}(...)  [no signature]")
                except Exception:
                    continue
        if not tick_candidates:
            print("  [no tick-related method found on loop]")
            # Walk loop._tick_orch
            to = getattr(loop, "_tick_orch", None)
            if to is not None:
                print(f"  --- searching loop._tick_orch ---")
                for attr_name in sorted(dir(to)):
                    if attr_name.startswith("__"):
                        continue
                    lowered = attr_name.lower()
                    if any(kw in lowered for kw in ("tick", "step", "advance", "run", "process", "execute")):
                        try:
                            val = getattr(to, attr_name)
                            if callable(val):
                                try:
                                    sig = inspect.signature(val)
                                    print(f"  _tick_orch.{attr_name}{sig}")
                                except (ValueError, TypeError):
                                    print(f"  _tick_orch.{attr_name}(...)")
                        except Exception:
                            continue

        # =====================================================================
        # STEP 3: publish PLAYER_INSULTS + verify belief
        # =====================================================================
        _print_section("STEP 3: publish PLAYER_INSULTS + verify belief")
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

        # =====================================================================
        # STEP 4: pre-tick — try to find maid_lusya NPC state
        # =====================================================================
        _print_section("STEP 4: pre-tick — try to find maid_lusya NPC state")
        # Try loop._resolve_npcs_snapshot
        npc_states_pre: Dict[str, Any] = {}
        try:
            resolve_fn = getattr(loop, "_resolve_npcs_snapshot", None)
            if resolve_fn:
                snap = resolve_fn("Open_road")
                if isinstance(snap, dict):
                    npc_states_pre = snap
                    print(f"  loop._resolve_npcs_snapshot('Open_road') returned {len(snap)} entries")
                elif isinstance(snap, list):
                    print(f"  loop._resolve_npcs_snapshot returned LIST of {len(snap)} items")
                    if snap:
                        print(f"    first item type: {type(snap[0]).__name__}")
        except Exception as e:
            print(f"  _resolve_npcs_snapshot error: {e}")

        # Try npc_manager
        try:
            for attr_name in ("_npc_manager", "npc_manager", "_npcs", "_npc_states"):
                val = getattr(loop, attr_name, None)
                if val is None:
                    continue
                print(f"  loop.{attr_name} found: type={type(val).__name__}")
                # Try common methods
                for method_name in ("get_npc_state", "get_state", "get", "get_npc", "all_states", "states", "snapshot"):
                    method = getattr(val, method_name, None)
                    if method and callable(method):
                        try:
                            if method_name in ("states", "snapshot", "all_states"):
                                result = method()
                            elif method_name == "get":
                                result = method("maid_lusya")
                            elif method_name in ("get_npc_state", "get_state", "get_npc"):
                                # Try various signatures
                                try:
                                    result = method("maid_lusya")
                                except TypeError:
                                    try:
                                        result = method("Open_road", "maid_lusya")
                                    except TypeError:
                                        result = method("Open_road", "tavern", "maid_lusya")
                            else:
                                result = method()
                            if result is not None:
                                print(f"    .{method_name}() → type={type(result).__name__}, "
                                      f"len={len(result) if hasattr(result, '__len__') else '?'}")
                                if isinstance(result, dict) and "maid_lusya" in result:
                                    npc_states_pre = result
                                    print(f"    >>> FOUND maid_lusya in result dict")
                                    break
                                elif isinstance(result, list) and result:
                                    print(f"    first item type: {type(result[0]).__name__}")
                                    # Look for npc_id field
                                    for item in result[:3]:
                                        if hasattr(item, "npc_id"):
                                            print(f"      npc_id={item.npc_id}")
                                        elif isinstance(item, dict) and "npc_id" in item:
                                            print(f"      npc_id={item.get('npc_id')}")
                        except Exception as e:
                            print(f"    .{method_name}() error: {e}")
                if npc_states_pre and "maid_lusya" in npc_states_pre:
                    break
        except Exception as e:
            print(f"  npc_manager search error: {e}")

        lusya_state_pre = npc_states_pre.get("maid_lusya") if isinstance(npc_states_pre, dict) else None
        if lusya_state_pre is not None:
            print(f"\n  maid_lusya state found pre-tick: type={type(lusya_state_pre).__name__}")
            intent_pre = getattr(lusya_state_pre, "intent", None)
            print(f"  intent (pre-tick): {intent_pre}")
        else:
            print(f"\n  [maid_lusya state NOT FOUND pre-tick — expected; tick will load it]")

        # =====================================================================
        # STEP 5: invoke tick
        # =====================================================================
        _print_section("STEP 5: invoke tick")

        tick_method: Optional[callable] = None
        tick_method_name: Optional[str] = None
        tick_args: Tuple = ()
        tick_kwargs: Dict = {}

        # Try common tick method names with various signatures
        candidates_with_signatures: List[Tuple[str, callable]] = []
        for attr_name in ("run_tick", "tick", "advance_tick", "step", "process_tick", "execute_tick", "run"):
            method = getattr(loop, attr_name, None)
            if method and callable(method):
                candidates_with_signatures.append((attr_name, method))
        # Also try _tick_orch
        to = getattr(loop, "_tick_orch", None)
        if to is not None:
            for attr_name in ("run_tick", "tick", "advance_tick", "step", "process_tick", "execute_tick"):
                method = getattr(to, attr_name, None)
                if method and callable(method):
                    candidates_with_signatures.append((f"_tick_orch.{attr_name}", method))

        print(f"  tick method candidates: {[name for name, _ in candidates_with_signatures]}")

        # Try each candidate with various arg patterns
        tick_succeeded = False
        tick_error: Optional[str] = None
        for name, method in candidates_with_signatures:
            print(f"\n  --- trying {name}() ---")
            # Try various arg patterns
            arg_patterns: List[Tuple[str, Tuple, Dict]] = [
                ("()", (), {}),
                ("('Open_road',)", ("Open_road",), {}),
                ("('Open_road', 'tavern')", ("Open_road", "tavern"), {}),
                ("('Open_road', 'tavern', 1)", ("Open_road", "tavern", 1), {}),
                ("(campaign_id='Open_road', location='tavern')", (), {"campaign_id": "Open_road", "location": "tavern"}),
                ("(tick=1)", (), {"tick": 1}),
                ("(campaign_id='Open_road', tick=1)", (), {"campaign_id": "Open_road", "tick": 1}),
                ("('Open_road', 'tavern', 'player_insults', 'tavern_keeper_tornin')",
                 ("Open_road", "tavern", "player_insults", "tavern_keeper_tornin"), {}),
            ]
            for desc, args, kwargs in arg_patterns:
                try:
                    print(f"    {name}{desc} ...", end=" ")
                    result = method(*args, **kwargs)
                    print(f"OK → {type(result).__name__ if result is not None else 'None'}")
                    tick_succeeded = True
                    tick_method = method
                    tick_method_name = name
                    tick_args = args
                    tick_kwargs = kwargs
                    break
                except TypeError as e:
                    print(f"TypeError: {str(e)[:80]}")
                except Exception as e:
                    err_str = str(e)
                    print(f"{type(e).__name__}: {err_str[:120]}")
                    # Check for LLM errors
                    if any(t in err_str.lower() for t in ("llm", "openai", "client", "api", "model")):
                        tick_error = f"LLM_ERROR ({name}{desc}): {err_str[:200]}"
                        print(f"    >>> LLM required — {name} reached LLM call")
                        break
                    # Other errors might indicate progress — capture them
                    if "npc" in err_str.lower() or "decision" in err_str.lower():
                        tick_error = f"DOWNSTREAM_ERROR ({name}{desc}): {err_str[:200]}"
            if tick_succeeded or (tick_error and "LLM_ERROR" in tick_error):
                break

        if tick_succeeded:
            print(f"\n  >>> TICK SUCCEEDED via {tick_method_name}")
        elif tick_error:
            print(f"\n  >>> TICK REACHED LLM/DOWNSTREAM: {tick_error}")
        else:
            print(f"\n  >>> ALL TICK METHODS FAILED — could not invoke tick")
            print(f"  >>> Inspect candidate signatures above; loop API may differ")

        # =====================================================================
        # STEP 6: post-tick — find maid_lusya NPC state
        # =====================================================================
        _print_section("STEP 6: post-tick — find maid_lusya NPC state")
        npc_states_post: Dict[str, Any] = {}
        # Re-try scene_state['npc_states']
        scene_after = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene_after:
            npc_states_post = scene_after.get("npc_states", {}) or {}
            print(f"  scene_after['npc_states']: {len(npc_states_post)} entries")

        if not npc_states_post:
            try:
                resolve_fn = getattr(loop, "_resolve_npcs_snapshot", None)
                if resolve_fn:
                    snap = resolve_fn("Open_road")
                    if isinstance(snap, dict) and snap:
                        npc_states_post = snap
                        print(f"  loop._resolve_npcs_snapshot('Open_road') post-tick: {len(snap)} entries")
            except Exception as e:
                print(f"  post-tick _resolve_npcs_snapshot error: {e}")

        if not npc_states_post:
            # Try npc_manager again
            try:
                nm = getattr(loop, "_npc_manager", None) or getattr(loop, "npc_manager", None)
                if nm:
                    for method_name in ("snapshot", "all_states", "states"):
                        method = getattr(nm, method_name, None)
                        if method and callable(method):
                            try:
                                result = method()
                                if isinstance(result, dict) and result:
                                    npc_states_post = result
                                    print(f"  _npc_manager.{method_name}() post-tick: {len(result)} entries")
                                    break
                                elif isinstance(result, list) and result:
                                    # Convert list of objects to dict by npc_id
                                    converted = {}
                                    for item in result:
                                        nid = getattr(item, "npc_id", None) or (item.get("npc_id") if isinstance(item, dict) else None)
                                        if nid:
                                            converted[nid] = item
                                    if converted:
                                        npc_states_post = converted
                                        print(f"  _npc_manager.{method_name}() list → {len(converted)} entries")
                                        break
                            except Exception as e:
                                print(f"  _npc_manager.{method_name}() error: {e}")
            except Exception as e:
                print(f"  _npc_manager post-tick search error: {e}")

        print(f"\n  available NPCs post-tick: {list(npc_states_post.keys())[:20] if hasattr(npc_states_post, 'keys') else 'N/A'}")
        lusya_state_post = npc_states_post.get("maid_lusya") if isinstance(npc_states_post, dict) else None

        if lusya_state_post is None:
            print("  [maid_lusya NPC state NOT FOUND post-tick]")
            print("  >>> Trying to find NPC state via NPCManager.get(npc_id) ...")
            try:
                nm = getattr(loop, "_npc_manager", None) or getattr(loop, "npc_manager", None)
                if nm:
                    method = getattr(nm, "get", None) or getattr(nm, "get_npc_state", None) or getattr(nm, "get_state", None)
                    if method:
                        try:
                            lusya_state_post = method("maid_lusya")
                            print(f"  nm.get('maid_lusya'): {lusya_state_post!r}")
                        except Exception as e:
                            print(f"  nm.get('maid_lusya') error: {e}")
                        if lusya_state_post is None:
                            try:
                                lusya_state_post = method("Open_road", "maid_lusya")
                                print(f"  nm.get('Open_road', 'maid_lusya'): {lusya_state_post!r}")
                            except Exception as e:
                                print(f"  nm.get('Open_road', 'maid_lusya') error: {e}")
            except Exception as e:
                print(f"  final search error: {e}")

        # =====================================================================
        # STEP 7: inspect maid_lusya intent post-tick
        # =====================================================================
        _print_section("STEP 7: inspect maid_lusya intent post-tick")
        if lusya_state_post is None:
            print("  [STILL not found — cannot inspect intent]")
        else:
            print(f"  maid_lusya state found: type={type(lusya_state_post).__name__}")
            intent_value = getattr(lusya_state_post, "intent", None)
            print(f"  maid_lusya.intent = {intent_value}")
            if intent_value is not None:
                # Try .value if it's an Enum
                intent_str = getattr(intent_value, "value", str(intent_value))
                print(f"  intent value: {intent_str}")
                if "spread_rumor" in str(intent_str).lower():
                    print(f"\n  >>> maid_lusya's intent IS SPREAD_RUMOR!")
                elif "talk" in str(intent_str).lower():
                    print(f"\n  >>> maid_lusya's intent IS TALK (not SPREAD_RUMOR)")
                else:
                    print(f"\n  >>> maid_lusya's intent is something else")

            # Other relevant fields
            for field in ("intent_target", "current_intent_target", "target", "speech_target"):
                val = getattr(lusya_state_post, field, None)
                if val is not None:
                    print(f"  maid_lusya.{field} = {val!r}")

            # Print full state top-level
            print(f"\n  --- maid_lusya state top-level attrs ---")
            try:
                for k, v in vars(lusya_state_post).items():
                    if not k.startswith("__"):
                        print(f"    {k}: {repr(v)[:100]}")
            except Exception:
                for attr in dir(lusya_state_post):
                    if not attr.startswith("__"):
                        try:
                            val = getattr(lusya_state_post, attr)
                            if callable(val):
                                continue
                            print(f"    {attr}: {repr(val)[:100]}")
                        except Exception:
                            pass

        # =====================================================================
        # STEP 8: also inspect EpistemicStore after tick (sanity check)
        # =====================================================================
        _print_section("STEP 8: EpistemicStore after tick (sanity check)")
        try:
            recs = store.get_all_for_agent("maid_lusya")
            print(f"  maid_lusya records: {len(recs) if recs else 0}")
            for r in (recs or [])[:5]:
                dumped = {}
                for f in ("proposition", "confidence", "source_id", "original_source_id"):
                    try:
                        v = getattr(r, f, None)
                        dumped[f] = str(v)[:80] if not isinstance(v, (int, float, bool)) else v
                    except Exception:
                        pass
                print(f"    {dumped}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # =====================================================================
        # STEP 9: VERDICT
        # =====================================================================
        _print_section("STEP 9: VERDICT")

        if not tick_succeeded and not (tick_error and "LLM_ERROR" in tick_error):
            print("  >>> VERDICT: INCONCLUSIVE — could not invoke production tick")
            print("  >>> Need to inspect loop API and adapt probe")
        elif tick_error and "LLM_ERROR" in tick_error:
            print("  >>> VERDICT: INCONCLUSIVE — tick requires LLM")
            print(f"  >>> Error: {tick_error[:200]}")
            print("  >>> Need to run full tick with real LLM (port 8181)")
        elif lusya_state_post is None:
            print("  >>> VERDICT: INCONCLUSIVE — tick ran but maid_lusya state still not found")
            print("  >>> NPC state may be stored elsewhere; inspect Step 6 output")
        else:
            intent_value = getattr(lusya_state_post, "intent", None)
            intent_str = ""
            if intent_value is not None:
                intent_str = getattr(intent_value, "value", str(intent_value))

            if "spread_rumor" in str(intent_str).lower():
                print("  >>> VERDICT: B5-E2 NOT A DEFECT")
                print("  >>> maid_lusya's intent post-tick = SPREAD_RUMOR")
                print("  >>> DecisionHub received EpistemicContext with report_proposition")
                print("  >>> and selected SPREAD_RUMOR over TALK")
                print("  >>> WANTS is proven")
                print("  >>> NEXT: B5-D2 — does SPREAD_RUMOR reach Tornin via NPC_SPOKE?")
            elif "talk" in str(intent_str).lower():
                print("  >>> VERDICT: B5-E2 DEFECT — TALK chosen instead of SPREAD_RUMOR")
                print("  >>> maid_lusya had report_proposition, but chose TALK")
                print("  >>> Investigate: did spread_rumor boost computation work?")
                print("  >>> Investigate: were competing intents scored higher?")
            else:
                print(f"  >>> VERDICT: B5-E2 DEFECT — unexpected intent: {intent_value!r}")
                print(f"  >>> maid_lusya chose {intent_str} (not SPREAD_RUMOR)")
                print("  >>> Investigate: which intents were in the candidate pool?")

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

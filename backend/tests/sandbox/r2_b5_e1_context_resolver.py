# backend/tests/sandbox/r2_b5_e1_context_resolver.py
"""
R2-B5-E1 — EpistemicContextResolver.resolve("maid_lusya") after PLAYER_INSULTS.

GOAL: Confirm that Lusya's belief record (created by B5-D1) actually appears
      in the EpistemicContext returned by the production resolver.

REQUIREMENTS (from Master):
  1. Call the production EpistemicContextResolver instance — NOT manual computation.
  2. Verify resolver.store IS the same store where the belief landed.
  3. Inspect actual contents of the returned EpistemicContext — not just field
     presence or threshold pass.
  4. Confirm the exact proposition: player / INSULTED / tavern_keeper_tornin.
  5. Capture confidence, source_id, original_source_id, source_type, classification.
  6. If report_proposition is missing — identify the exact exclusion condition.

DO NOT:
  - Fix anything
  - Move to DecisionHub
  - Touch B5-D2

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_e1_context_resolver.txt"


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


def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[read error: {e}]"


def _inspect_obj(obj: Any, depth: int = 0, max_depth: int = 3) -> Dict[str, Any]:
    """Recursively inspect an object into a dict of primitives."""
    if depth > max_depth:
        return {"_truncated": repr(obj)[:200]}
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [_inspect_obj(x, depth + 1, max_depth) for x in list(obj)[:10]]
    if isinstance(obj, dict):
        return {str(k): _inspect_obj(v, depth + 1, max_depth) for k, v in list(obj.items())[:20]}
    # Object: dump __dict__ if available
    out: Dict[str, Any] = {"_type": type(obj).__name__}
    try:
        d = vars(obj)
        for k, v in d.items():
            if k.startswith("_"):
                # Allow single underscore (common in records)
                if not k.startswith("__"):
                    out[k] = _inspect_obj(v, depth + 1, max_depth)
            else:
                out[k] = _inspect_obj(v, depth + 1, max_depth)
    except Exception:
        # Try iterating public attrs
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
    print("R2-B5-E1 — EpistemicContextResolver.resolve('maid_lusya') after PLAYER_INSULTS")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("GOAL: Confirm Lusya's belief record appears in EpistemicContext")
    print("      returned by production resolver — NOT manual threshold calc.")
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

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_e1_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        bus = get_event_bus()

        # =====================================================================
        # STEP 1: locate ClaimEventSubscriber + EpistemicStore
        # =====================================================================
        _print_section("STEP 1: locate ClaimEventSubscriber + EpistemicStore")
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
                        print(f"  Found ClaimEventSubscriber id={id(sub)} via bus.{attr}[{ev_type}]")
                        break
                if sub:
                    break
            if sub:
                break

        if sub is None:
            print("  [FATAL: ClaimEventSubscriber not found]")
            return 1

        store = getattr(sub, "_store", None)
        if store is None:
            print("  [FATAL: sub._store is None]")
            return 1
        print(f"  sub._store: id={id(store)} type={type(store).__name__}")

        # =====================================================================
        # STEP 2: locate production EpistemicContextResolver
        # =====================================================================
        _print_section("STEP 2: locate production EpistemicContextResolver")
        # In game_loop.py L608: _resolver = EpistemicContextResolver(store=_epistemic_store)
        # Look for resolver attribute on loop or sub
        resolver: Optional[EpistemicContextResolver] = None
        resolver_path_desc = ""

        # Try loop._resolver
        for attr_name in ("_resolver", "_epistemic_context_resolver", "epistemic_context_resolver", "context_resolver"):
            val = getattr(loop, attr_name, None)
            if isinstance(val, EpistemicContextResolver):
                resolver = val
                resolver_path_desc = f"loop.{attr_name}"
                break

        # Try loop._svc or loop._tick_orch
        if resolver is None:
            for parent_name in ("_svc", "_tick_orch", "_tick_orchestrator"):
                parent = getattr(loop, parent_name, None)
                if parent is None:
                    continue
                for attr_name in ("_resolver", "_epistemic_context_resolver", "context_resolver", "epistemic_context_resolver"):
                    val = getattr(parent, attr_name, None)
                    if isinstance(val, EpistemicContextResolver):
                        resolver = val
                        resolver_path_desc = f"loop.{parent_name}.{attr_name}"
                        break
                if resolver:
                    break

        # Walk vars of loop
        if resolver is None:
            try:
                for k, v in vars(loop).items():
                    if isinstance(v, EpistemicContextResolver):
                        resolver = v
                        resolver_path_desc = f"loop.{k} (vars)"
                        break
                    if hasattr(v, "__dict__"):
                        for k2, v2 in vars(v).items():
                            if isinstance(v2, EpistemicContextResolver):
                                resolver = v2
                                resolver_path_desc = f"loop.{k}.{k2}"
                                break
                        if resolver:
                            break
            except Exception:
                pass

        if resolver is None:
            print("  [FATAL: EpistemicContextResolver NOT FOUND in runtime]")
            print("  Inspecting loop attributes for any *resolver* field:")
            for attr_name in sorted(dir(loop)):
                if "resolver" in attr_name.lower() or "context" in attr_name.lower():
                    try:
                        val = getattr(loop, attr_name)
                        print(f"    loop.{attr_name}: type={type(val).__name__}, is_resolver={isinstance(val, EpistemicContextResolver)}")
                    except Exception:
                        pass
            return 1

        print(f"  Found EpistemicContextResolver id={id(resolver)}")
        print(f"  via {resolver_path_desc}")

        # Inspect resolver attributes
        print()
        print(f"  --- resolver attributes ---")
        try:
            for k, v in vars(resolver).items():
                print(f"    resolver.{k}: {v!r} (type={type(v).__name__})")
        except Exception as e:
            print(f"  [vars error: {e}]")

        # =====================================================================
        # STEP 3: verify resolver.store IS sub._store (SAME instance)
        # =====================================================================
        _print_section("STEP 3: verify resolver.store IS sub._store (same instance)")
        resolver_store = getattr(resolver, "_store", None) or getattr(resolver, "store", None)
        if resolver_store is None:
            print("  [resolver has no _store attribute — searching]")
            try:
                for k, v in vars(resolver).items():
                    if "store" in k.lower():
                        print(f"    resolver.{k}: {v!r}")
                        if v is store:
                            resolver_store = v
                            print(f"    >>> MATCH: resolver.{k} IS sub._store")
                            break
            except Exception:
                pass
        else:
            print(f"  resolver._store: id={id(resolver_store)} type={type(resolver_store).__name__}")
            print(f"  sub._store:     id={id(store)} type={type(store).__name__}")
            print(f"  SAME INSTANCE: {resolver_store is store}")

        if resolver_store is not store:
            print()
            print(f"  >>> WARNING: resolver.store IS NOT sub._store")
            print(f"  >>> Belief was created in sub._store (id={id(store)})")
            print(f"  >>> But resolver reads from different store (id={id(resolver_store) if resolver_store else 'None'})")
            print(f"  >>> If they are different instances, resolver will NOT see Lusya's belief!")
        else:
            print(f"  >>> CONFIRMED: same store instance — resolver will see Lusya's belief")

        # =====================================================================
        # STEP 4: read production source of resolve() and helpers
        # =====================================================================
        _print_section("STEP 4: read production source of EpistemicContextResolver.resolve()")
        ecr_path = _BACKEND / "app" / "services" / "npc" / "epistemic_context_resolver.py"
        if ecr_path.exists():
            src = _read_file_text(ecr_path)
            lines_arr = src.split("\n")
            # Print resolve() method
            bounds = _find_function_bounds(src, "resolve")
            if bounds:
                s, e = bounds
                print(f"  resolve() at L{s+1}..L{e}:")
                for j in range(s, e):
                    print(f"  L{j+1:4d}: {lines_arr[j]}")
            else:
                print("  [resolve() not found]")

            # Print REPORT_CONFIDENCE_THRESHOLD constant
            print()
            print(f"  --- REPORT_CONFIDENCE_THRESHOLD constant ---")
            for i, line in enumerate(lines_arr, 1):
                if "REPORT_CONFIDENCE_THRESHOLD" in line and "=" in line:
                    print(f"  L{i}: {line.rstrip()}")

            # Print report_proposition assignment
            print()
            print(f"  --- report_proposition assignment sites ---")
            for i, line in enumerate(lines_arr, 1):
                if "report_proposition" in line and ("=" in line or "append" in line):
                    print(f"  L{i}: {line.rstrip()}")

            # Print claims_about_self assignment
            print()
            print(f"  --- claims_about_self assignment sites ---")
            for i, line in enumerate(lines_arr, 1):
                if "claims_about_self" in line and ("=" in line or "append" in line):
                    print(f"  L{i}: {line.rstrip()}")
        else:
            print(f"  [file not found: {ecr_path}]")

        # =====================================================================
        # STEP 5: baseline — resolver.resolve("maid_lusya") BEFORE publish
        # =====================================================================
        _print_section("STEP 5: baseline — resolver.resolve('maid_lusya') BEFORE publish")
        baseline_ctx = None
        baseline_ctx_dict = None
        try:
            baseline_ctx = resolver.resolve("maid_lusya")
            print(f"  resolver.resolve('maid_lusya') returned: {baseline_ctx!r}")
            print(f"  type: {type(baseline_ctx).__name__}")
            if baseline_ctx is not None:
                baseline_ctx_dict = _inspect_obj(baseline_ctx)
                print(f"  --- EpistemicContext dump (BEFORE) ---")
                print(json.dumps(baseline_ctx_dict, indent=2, default=str, ensure_ascii=False)[:3000])
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 6: publish PLAYER_INSULTS
        # =====================================================================
        _print_section("STEP 6: publish PLAYER_INSULTS")
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
        print(f"  payload.target_id={payload['target_id']}")
        print(f"  payload.radius={payload['radius']}")
        print(f"  Publishing...")
        bus.publish(evt)
        print(f"  Published.")

        # Sanity: confirm belief exists in store (B5-D1 was closed, but reconfirm here)
        expected_prop = Proposition(
            subject_id="player",
            predicate=Predicate.INSULTED,
            object_id="tavern_keeper_tornin",
            polarity=True,
        )
        print()
        print(f"  --- sanity: store.get('maid_lusya', expected_prop) ---")
        try:
            lusya_rec = store.get("maid_lusya", expected_prop)
            if lusya_rec is None:
                print(f"  [STORE HAS NO RECORD for maid_lusya] — B5-D1 was supposed to be closed!")
            else:
                print(f"  store record: confidence={getattr(lusya_rec, 'confidence', '?')}, source_id={getattr(lusya_rec, 'source_id', '?')}")
        except Exception as e:
            print(f"  ERROR: {e}")

        # =====================================================================
        # STEP 7: after — resolver.resolve("maid_lusya") AFTER publish
        # =====================================================================
        _print_section("STEP 7: after — resolver.resolve('maid_lusya') AFTER publish")
        after_ctx = None
        after_ctx_dict = None
        try:
            after_ctx = resolver.resolve("maid_lusya")
            print(f"  resolver.resolve('maid_lusya') returned: {after_ctx!r}")
            print(f"  type: {type(after_ctx).__name__}")
            if after_ctx is not None:
                after_ctx_dict = _inspect_obj(after_ctx)
                print(f"  --- EpistemicContext dump (AFTER) ---")
                print(json.dumps(after_ctx_dict, indent=2, default=str, ensure_ascii=False)[:6000])
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()

        # =====================================================================
        # STEP 8: focused inspection — report_proposition field
        # =====================================================================
        _print_section("STEP 8: focused inspection — report_proposition field")
        rp_value = None
        rp_source = None
        if after_ctx is not None:
            # Try direct attr
            rp_value = getattr(after_ctx, "report_proposition", "ATTR_NOT_FOUND")
            if rp_value == "ATTR_NOT_FOUND":
                # Try dict-like
                if isinstance(after_ctx, dict):
                    rp_value = after_ctx.get("report_proposition", "KEY_NOT_FOUND")
                else:
                    # Try vars
                    try:
                        d = vars(after_ctx)
                        for k, v in d.items():
                            if "report_prop" in k.lower():
                                rp_value = v
                                rp_source = f"vars[{k}]"
                                break
                    except Exception:
                        pass
            else:
                rp_source = "attr report_proposition"
        print(f"  report_proposition access: {rp_source}")
        print(f"  report_proposition value: {rp_value!r}")
        print(f"  type: {type(rp_value).__name__ if rp_value is not None else 'None'}")

        if rp_value is not None and rp_value != "ATTR_NOT_FOUND" and rp_value != "KEY_NOT_FOUND":
            print()
            print(f"  --- report_proposition details ---")
            rp_inspect = _inspect_obj(rp_value)
            print(json.dumps(rp_inspect, indent=2, default=str, ensure_ascii=False)[:2000])

            # Check exact match
            if hasattr(rp_value, "subject_id") and hasattr(rp_value, "predicate") and hasattr(rp_value, "object_id"):
                rp_subj = getattr(rp_value, "subject_id")
                rp_pred = getattr(rp_value, "predicate")
                rp_obj = getattr(rp_value, "object_id")
                # Handle Enum predicate
                rp_pred_val = rp_pred.value if hasattr(rp_pred, "value") else rp_pred
                print()
                print(f"  --- exact match check ---")
                print(f"  expected: subject_id=player, predicate=insulted, object_id=tavern_keeper_tornin")
                print(f"  actual:   subject_id={rp_subj!r}, predicate={rp_pred_val!r}, object_id={rp_obj!r}")
                print(f"  MATCH: {rp_subj == 'player' and rp_pred_val == 'insulted' and rp_obj == 'tavern_keeper_tornin'}")

        # =====================================================================
        # STEP 9: also inspect claims_about_self (for completeness)
        # =====================================================================
        _print_section("STEP 9: inspect claims_about_self (for completeness)")
        cas_value = None
        if after_ctx is not None:
            cas_value = getattr(after_ctx, "claims_about_self", "ATTR_NOT_FOUND")
            if cas_value == "ATTR_NOT_FOUND":
                if isinstance(after_ctx, dict):
                    cas_value = after_ctx.get("claims_about_self", "KEY_NOT_FOUND")
        print(f"  claims_about_self: {cas_value!r}")
        print(f"  type: {type(cas_value).__name__ if cas_value is not None else 'None'}")
        if cas_value is not None and cas_value != "ATTR_NOT_FOUND" and cas_value != "KEY_NOT_FOUND":
            print()
            print(f"  --- claims_about_self details ---")
            print(json.dumps(_inspect_obj(cas_value), indent=2, default=str, ensure_ascii=False)[:2000])

        # =====================================================================
        # STEP 10: comparison baseline vs after
        # =====================================================================
        _print_section("STEP 10: baseline vs after comparison")
        print(f"  baseline_ctx: {baseline_ctx!r}")
        print(f"  after_ctx:    {after_ctx!r}")
        if baseline_ctx_dict and after_ctx_dict:
            print()
            print(f"  --- baseline keys ---")
            for k in sorted(baseline_ctx_dict.keys() if isinstance(baseline_ctx_dict, dict) else []):
                v = baseline_ctx_dict.get(k) if isinstance(baseline_ctx_dict, dict) else None
                print(f"    {k}: {str(v)[:80]}")
            print()
            print(f"  --- after keys ---")
            for k in sorted(after_ctx_dict.keys() if isinstance(after_ctx_dict, dict) else []):
                v = after_ctx_dict.get(k) if isinstance(after_ctx_dict, dict) else None
                print(f"    {k}: {str(v)[:80]}")

        # =====================================================================
        # STEP 11: VERDICT
        # =====================================================================
        _print_section("STEP 11: VERDICT")

        rp_exists = rp_value is not None and rp_value != "ATTR_NOT_FOUND" and rp_value != "KEY_NOT_FOUND"
        rp_match = False
        if rp_exists and hasattr(rp_value, "subject_id") and hasattr(rp_value, "predicate") and hasattr(rp_value, "object_id"):
            rp_subj = getattr(rp_value, "subject_id")
            rp_pred = getattr(rp_value, "predicate")
            rp_obj = getattr(rp_value, "object_id")
            rp_pred_val = rp_pred.value if hasattr(rp_pred, "value") else rp_pred
            rp_match = (rp_subj == "player" and rp_pred_val == "insulted" and rp_obj == "tavern_keeper_tornin")

        print(f"  resolver found:               {resolver is not None}")
        print(f"  resolver.store IS sub._store:  {resolver_store is store}")
        print(f"  report_proposition exists:     {rp_exists}")
        if rp_exists:
            print(f"  report_proposition matches expected: {rp_match}")
        print()

        if rp_exists and rp_match:
            print(f"  >>> VERDICT: B5-E1 IS NOT A DEFECT")
            print(f"  >>> Production EpistemicContextResolver.resolve('maid_lusya') DID return")
            print(f"  >>> the report_proposition = Proposition(player, INSULTED, tavern_keeper_tornin)")
            print(f"  >>> in the EpistemicContext, after PLAYER_INSULTS.")
            print(f"  >>>")
            print(f"  >>> B5-E1 chain segment works:")
            print(f"  >>>   belief(Lusya, confidence=0.5) → resolver → report_proposition in context")
            print(f"  >>>")
            print(f"  >>> NEXT: investigate B5-E2 — DecisionHub — does it produce SPREAD_RUMOR intent")
            print(f"  >>> when given this EpistemicContext?")
        elif rp_exists and not rp_match:
            print(f"  >>> VERDICT: B5-E1 DEFECT — report_proposition EXISTS but does NOT match expected")
            print(f"  >>> Expected: Proposition(player, INSULTED, tavern_keeper_tornin)")
            print(f"  >>> Got: {rp_value!r}")
            print(f"  >>> Need to inspect resolver filtering by predicate or object_id")
        elif not rp_exists:
            print(f"  >>> VERDICT: B5-E1 DEFECT — report_proposition IS MISSING from EpistemicContext")
            print(f"  >>> Despite B5-D1 confirming belief exists in store with confidence=0.5 ≥ 0.25")
            print(f"  >>> Possible causes:")
            print(f"  >>>   1. resolver.store IS NOT sub._store (different instance)")
            print(f"  >>>   2. resolver has additional filter beyond REPORT_CONFIDENCE_THRESHOLD")
            print(f"  >>>   3. resolver expects different proposition shape (e.g., polarity=False)")
            print(f"  >>>   4. resolve() signature takes more params than just agent_id")
            print(f"  >>>   5. resolver caches baseline and doesn't refresh")
            print(f"  >>> Examine Step 4 (source) + Step 3 (store identity) to identify the cause")
        else:
            print(f"  >>> VERDICT: UNKNOWN — needs manual inspection of Step 7 dump")

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

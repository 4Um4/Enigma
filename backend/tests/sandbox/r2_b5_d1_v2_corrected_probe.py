# backend/tests/sandbox/r2_b5_d1_v2_corrected_probe.py
"""
R2-B5-D1 CORRECTED PROBE v2.

Previous probe (r2_b5_d1_final_provider_perception.py) had two bugs:
  1. Spy was attached to on_claim_event, but PLAYER_INSULTS is handled
     by a DIFFERENT method (likely on_player_spoke). Spy never fired.
  2. bus.clear() may have removed subscriber registrations, making
     bus.publish() a no-op.

This probe corrects both:
  A. Reads _get_spatial_query_for_subscriber() source (same as before)
  B. Reads PerceptualKernel.can_observe() source (same as before)
  C. CORRECTED runtime verification:
     C.0  Directly inspects sub._get_spatial_query (NOT via spy)
     C.1  Identifies which method handles PLAYER_INSULTS (via cb.__name__)
     C.2  Reads source of that handler method
     C.3  Attaches spy to the CORRECT method
     C.4  Does NOT call bus.clear() — preserves subscribers
     C.5  Publishes PLAYER_INSULTS and captures 9 values
     C.6  Also reads on_player_spoke source for analysis
  D. Verdict based on ACTUAL runtime data, not defaults

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import json
import math
import types
import inspect
import traceback
import io
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d1_v2_corrected_probe.txt"


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


def _is_production_file(path: Path) -> bool:
    if not path.exists():
        return False
    parts_lower = [p.lower() for p in path.parts]
    for bad in (".venv", "node_modules", ".git", "__pycache__", "site-packages"):
        if bad in parts_lower:
            return False
    fname = path.name.lower()
    if fname.startswith("test_") or fname.endswith("_test.py"):
        return False
    if "sandbox" in parts_lower:
        return False
    if fname.startswith("r2_"):
        return False
    if any(tok in fname for tok in ("probe", "mock", "stub", "fake", "fixture")):
        return False
    for p in parts_lower:
        if p == "tests":
            return False
    return True


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


def _safe_pos(data: Any) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    out: Dict[str, Any] = {}
    if isinstance(data, dict):
        if "x" in data and "y" in data:
            out["x"] = data.get("x")
            out["y"] = data.get("y")
            out["source"] = "dict(x,y)"
            return out
        lp = data.get("local_position")
        if isinstance(lp, dict) and "x" in lp and "y" in lp:
            out["x"] = lp.get("x")
            out["y"] = lp.get("y")
            out["position_node"] = data.get("position")
            out["source"] = "dict(local_position)"
            return out
        pos = data.get("position")
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            out["x"] = pos.get("x")
            out["y"] = pos.get("y")
            out["source"] = "dict(position)"
            return out
        if "local_x" in data and "local_y" in data:
            out["x"] = data.get("local_x")
            out["y"] = data.get("local_y")
            out["source"] = "dict(local_x,local_y)"
            return out
        return {"raw": str(data)[:200]}
    if hasattr(data, "x") and hasattr(data, "y"):
        out["x"] = getattr(data, "x")
        out["y"] = getattr(data, "y")
        out["source"] = "obj(x,y)"
        return out
    return {"raw": repr(data)[:200]}


# ============================================================================
# STAGE A: Confirm _get_spatial_query_for_subscriber() source (same as v1)
# ============================================================================
def stage_a_provider_source() -> Dict[str, Any]:
    _print_section("STAGE A: _get_spatial_query_for_subscriber() source confirmation")
    result: Dict[str, Any] = {"stage": "A", "pass": False}

    gl_path = _BACKEND / "app" / "services" / "game_loop" / "game_loop.py"
    if not gl_path.exists():
        print(f"  [file not found: {gl_path}]")
        result["error"] = "file not found"
        return result

    src = _read_file_text(gl_path)
    lines_arr = src.split("\n")

    # Print _get_spatial_query_for_subscriber
    bounds = _find_function_bounds(src, "_get_spatial_query_for_subscriber")
    if bounds:
        s, e = bounds
        print(f"  _get_spatial_query_for_subscriber at L{s+1}..L{e}:")
        for j in range(s, e):
            print(f"  L{j+1:4d}: {lines_arr[j]}")
    else:
        print("  [function not found]")

    # Print ClaimEventSubscriber constructor context (L605–L625)
    print(f"\n  --- ClaimEventSubscriber construction (L605..L625) ---")
    for j in range(604, min(625, len(lines_arr))):
        print(f"  L{j+1:4d}: {lines_arr[j]}")

    # Print all _bus.subscribe lines involving ClaimEventSubscriber methods
    print(f"\n  --- All _bus.subscribe lines in game_loop.py ---")
    for i, line in enumerate(lines_arr, 1):
        if "_bus.subscribe" in line or "bus.subscribe" in line:
            print(f"  L{i}: {line.rstrip()}")

    result["pass"] = True
    return result


# ============================================================================
# STAGE B: PerceptualKernel.can_observe() (same as v1, confirmed)
# ============================================================================
def stage_b_perceptual_kernel() -> Dict[str, Any]:
    _print_section("STAGE B: PerceptualKernel.can_observe() — confirmed from v1")
    result: Dict[str, Any] = {"stage": "B", "pass": False}

    pk_path = _BACKEND / "app" / "models" / "npc_state.py"
    if not pk_path.exists():
        print(f"  [file not found: {pk_path}]")
        result["error"] = "file not found"
        return result

    src = _read_file_text(pk_path)
    lines_arr = src.split("\n")

    # Print can_observe method
    bounds = _find_function_bounds(src, "can_observe")
    if bounds:
        s, e = bounds
        print(f"  can_observe at L{s+1}..L{e}:")
        for j in range(s, e):
            print(f"  L{j+1:4d}: {lines_arr[j]}")
    else:
        print("  [can_observe not found]")

    # Confirm: uses event.radius, NOT HEARING_RADIUS
    print(f"\n  --- HEARING_RADIUS references in npc_state.py ---")
    for i, line in enumerate(lines_arr, 1):
        if "HEARING_RADIUS" in line:
            print(f"  L{i}: {line.rstrip()}")

    print(f"\n  SEMANTICS CONFIRMED:")
    print(f"    - can_observe uses event.radius (NOT HEARING_RADIUS)")
    print(f"    - For visibility='public': return bool(distance <= event.radius)")
    print(f"    - event.radius = 999.0 in PLAYER_INSULTS → distance 10.086m is WITHIN range")
    print(f"    - maid_lusya CAN observe if she is in listeners list")

    result["pass"] = True
    return result


# ============================================================================
# STAGE C: CORRECTED runtime verification
# ============================================================================
def stage_c_corrected_runtime() -> Dict[str, Any]:
    _print_section("STAGE C: CORRECTED runtime verification")
    result: Dict[str, Any] = {"stage": "C", "pass": False}

    try:
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d1_v2_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        bus = get_event_bus()

        # ---- C.0: Find ALL ClaimEventSubscriber instances + their registrations ----
        print("\n--- C.0: enumerate ALL ClaimEventSubscriber registrations in EventBus ---")
        all_registrations: List[Dict[str, Any]] = []
        seen_subscriber_ids: Dict[int, ClaimEventSubscriber] = {}

        for attr in ("_subscribers", "_handlers", "_callbacks", "_listeners"):
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
                        cb_name = getattr(cb, "__name__", "?")
                        sub_id = id(target_obj)
                        seen_subscriber_ids[sub_id] = target_obj
                        reg = {
                            "event_type": str(ev_type),
                            "handler_method": cb_name,
                            "subscriber_id": sub_id,
                        }
                        all_registrations.append(reg)
                        print(f"  bus.{attr}[{ev_type}] → {cb_name} (sub id={sub_id})")

        print(f"\n  Total ClaimEventSubscriber registrations: {len(all_registrations)}")
        print(f"  Distinct subscriber instances: {len(seen_subscriber_ids)}")

        if not seen_subscriber_ids:
            print("  [NO ClaimEventSubscriber found in EventBus]")
            result["error"] = "no subscriber found"
            return result

        # Pick the subscriber that handles player_insults
        player_insults_handler = None
        for reg in all_registrations:
            if "player_insult" in reg["event_type"].lower() or "player_insult" in str(reg["event_type"]).lower():
                player_insults_handler = reg
                break

        # Also check PLAYER_INSULTS event type name
        if player_insults_handler is None:
            for reg in all_registrations:
                if "insult" in reg["event_type"].lower():
                    player_insults_handler = reg
                    break

        if player_insults_handler is None:
            print("\n  [NO handler found for PLAYER_INSULTS event]")
            print("  Dumping all event types with ClaimEventSubscriber:")
            for reg in all_registrations:
                print(f"    {reg['event_type']} → {reg['handler_method']}")
            # Fallback: use the first subscriber found
            sub = list(seen_subscriber_ids.values())[0]
            print(f"\n  Fallback: using first subscriber id={id(sub)}")
        else:
            print(f"\n  >>> PLAYER_INSULTS handler identified:")
            print(f"      event_type: {player_insults_handler['event_type']}")
            print(f"      handler_method: {player_insults_handler['handler_method']}")
            print(f"      subscriber_id: {player_insults_handler['subscriber_id']}")
            sub = seen_subscriber_ids[player_insults_handler['subscriber_id']]

        # ---- C.1: DIRECTLY inspect sub._get_spatial_query (NOT via spy) ----
        print("\n--- C.1: DIRECT inspection of sub._get_spatial_query ---")
        direct_provider = getattr(sub, "_get_spatial_query", "ATTR_NOT_FOUND")
        print(f"  getattr(sub, '_get_spatial_query') = {direct_provider!r}")
        print(f"  type: {type(direct_provider).__name__}")

        if direct_provider == "ATTR_NOT_FOUND":
            print("  >>> ATTRIBUTE DOES NOT EXIST on subscriber instance")
            provider_callable_direct = False
            provider_is_none = True
        elif direct_provider is None:
            print("  >>> _get_spatial_query IS None")
            provider_callable_direct = False
            provider_is_none = True
        else:
            provider_is_none = False
            provider_callable_direct = callable(direct_provider)
            print(f"  callable: {provider_callable_direct}")
            # Describe it
            self_obj = getattr(direct_provider, "__self__", None)
            if self_obj is not None:
                print(f"  __self__: {type(self_obj).__name__} (id={id(self_obj)})")
                print(f"  __name__: {getattr(direct_provider, '__name__', '?')}")
                print(f"  __self__ is loop? {self_obj is loop}")
            else:
                print(f"  __name__: {getattr(direct_provider, '__name__', '?')}")
                if hasattr(direct_provider, "__closure__") and direct_provider.__closure__:
                    print(f"  closure cells: {len(direct_provider.__closure__)}")
                    for i, cell in enumerate(direct_provider.__closure__):
                        try:
                            val = cell.cell_contents
                            print(f"    cell[{i}]: {type(val).__name__} (id={id(val)})")
                        except ValueError:
                            print(f"    cell[{i}]: <empty>")

            # Actually CALL the provider
            if provider_callable_direct:
                print(f"\n  --- Calling provider directly ---")
                try:
                    sq = direct_provider()
                    print(f"  Result: {sq!r}")
                    print(f"  Type: {type(sq).__name__ if sq else 'None'}")
                    if sq is not None:
                        _npc_pos = getattr(sq, "_npc_positions", {}) or {}
                        print(f"  _npc_positions keys: {list(_npc_pos.keys())}")
                        print(f"  'player' in _npc_positions: {'player' in _npc_pos}")
                        print(f"  'maid_lusya' in _npc_positions: {'maid_lusya' in _npc_pos}")
                        # Try distance
                        if hasattr(sq, "distance"):
                            try:
                                d = sq.distance("player", "maid_lusya")
                                print(f"  sq.distance('player', 'maid_lusya') = {d}")
                            except Exception as e:
                                print(f"  sq.distance ERROR: {e}")
                except Exception as e:
                    print(f"  CALL ERROR: {type(e).__name__}: {e}")
                    traceback.print_exc()

        # ---- C.2: Read source of the PLAYER_INSULTS handler method ----
        print("\n--- C.2: Read source of PLAYER_INSULTS handler method ---")
        handler_method_name = player_insults_handler["handler_method"] if player_insults_handler else "on_claim_event"
        print(f"  Handler method: {handler_method_name}")

        ces_path = _BACKEND / "app" / "services" / "events" / "claim_event_subscriber.py"
        if ces_path.exists():
            ces_src = _read_file_text(ces_path)
            ces_lines = ces_src.split("\n")
            bounds = _find_function_bounds(ces_src, handler_method_name)
            if bounds:
                s, e = bounds
                print(f"  {handler_method_name} at L{s+1}..L{e}:")
                for j in range(s, e):
                    print(f"  L{j+1:4d}: {ces_lines[j]}")
            else:
                print(f"  [method {handler_method_name} not found in claim_event_subscriber.py]")
                # List all methods
                print(f"  Available methods:")
                for i, line in enumerate(ces_lines, 1):
                    stripped = line.lstrip()
                    if stripped.startswith("def "):
                        print(f"    L{i}: {stripped.rstrip()}")

        # ---- C.2b: Also read on_player_spoke if different from handler ----
        if handler_method_name != "on_player_spoke":
            print(f"\n  --- Also reading on_player_spoke (for reference) ---")
            bounds = _find_function_bounds(ces_src, "on_player_spoke")
            if bounds:
                s, e = bounds
                print(f"  on_player_spoke at L{s+1}..L{e}:")
                for j in range(s, e):
                    print(f"  L{j+1:4d}: {ces_lines[j]}")

        # ---- C.2c: Read on_claim_event too (for comparison) ----
        print(f"\n  --- Also reading on_claim_event (for comparison) ---")
        bounds = _find_function_bounds(ces_src, "on_claim_event")
        if bounds:
            s, e = bounds
            print(f"  on_claim_event at L{s+1}..L{e}:")
            for j in range(s, e):
                print(f"  L{j+1:4d}: {ces_lines[j]}")

        # ---- C.3: Attach spy to the CORRECT handler method ----
        print(f"\n--- C.3: Attach spy to {handler_method_name} + BeliefRevisionEngine ---")
        captured: Dict[str, Any] = {}
        engine = getattr(sub, "_engine", None)
        store = getattr(sub, "_store", None)

        # Spy on BeliefRevisionEngine
        engine_calls: List[Dict[str, Any]] = []
        if engine is not None:
            for method_name in ("revise", "ingest_claim", "add_claim", "ingest", "update", "consider"):
                orig_method = getattr(engine, method_name, None)
                if orig_method is None or not callable(orig_method):
                    continue

                def _make_spy(orig, name):
                    def _spy(*args, **kwargs):
                        try:
                            args_repr = []
                            for a in args:
                                try:
                                    args_repr.append(repr(a)[:300])
                                except Exception:
                                    args_repr.append("<unrepr>")
                            engine_calls.append(
                                {"method": name, "args": args_repr}
                            )
                        except Exception:
                            pass
                        return orig(*args, **kwargs)
                    return _spy
                try:
                    setattr(engine, method_name, _make_spy(orig_method, method_name))
                    print(f"  spy attached: engine.{method_name}")
                except Exception as e:
                    print(f"  [cannot spy engine.{method_name}: {e}]")

        # Spy on store
        store_calls: List[Dict[str, Any]] = []
        if store is not None:
            for method_name in ("add_record", "add_belief", "update", "store", "set_belief", "ingest"):
                orig_method = getattr(store, method_name, None)
                if orig_method is None or not callable(orig_method):
                    continue

                def _make_store_spy(orig, name):
                    def _spy(*args, **kwargs):
                        try:
                            args_repr = []
                            for a in args:
                                try:
                                    args_repr.append(repr(a)[:300])
                                except Exception:
                                    args_repr.append("<unrepr>")
                            store_calls.append({"method": name, "args": args_repr})
                        except Exception:
                            pass
                        return orig(*args, **kwargs)
                    return _spy
                try:
                    setattr(store, method_name, _make_store_spy(orig_method, method_name))
                    print(f"  spy attached: store.{method_name}")
                except Exception as e:
                    print(f"  [cannot spy store.{method_name}: {e}]")

        # Spy on the CORRECT handler method (not on_claim_event unless that's what handles PLAYER_INSULTS)
        handler_method_obj = getattr(sub, handler_method_name, None)
        if handler_method_obj is None:
            print(f"  [subscriber has no method '{handler_method_name}']")
            # Fallback to on_claim_event
            handler_method_name = "on_claim_event"
            handler_method_obj = getattr(sub, handler_method_name, None)

        orig_handler = handler_method_obj
        engine_calls_before = len(engine_calls)

        def _spy_handler(event):
            payload = getattr(event, "payload", {}) or {}
            captured["event_source"] = getattr(event, "source", "?")
            captured["event_type"] = str(getattr(event, "type", "?"))
            captured["event_visibility"] = getattr(event, "visibility", "?")
            captured["payload_action_type"] = payload.get("action_type")
            captured["payload_target_id"] = payload.get("target_id")
            captured["payload_radius"] = payload.get("radius")
            captured["has_proposition_in_payload"] = bool(payload.get("proposition"))

            # Check provider
            provider = getattr(sub, "_get_spatial_query", None)
            captured["provider_is_none"] = provider is None
            captured["provider_callable"] = provider is not None and callable(provider)

            if provider is not None and callable(provider):
                try:
                    sq = provider()
                    captured["provider_result_type"] = type(sq).__name__ if sq else "None"
                    if sq is not None:
                        _npc_pos = getattr(sq, "_npc_positions", {}) or {}
                        captured["sq_npc_positions_keys"] = list(_npc_pos.keys())
                        captured["sq_npc_positions_count"] = len(_npc_pos)
                        captured["sq_player_pos"] = _safe_pos(_npc_pos.get("player"))
                        captured["sq_lusya_pos"] = _safe_pos(_npc_pos.get("maid_lusya"))

                        # Distance
                        if hasattr(sq, "distance"):
                            try:
                                d = sq.distance("player", "maid_lusya")
                                captured["runtime_distance_player_lusya"] = d
                            except Exception as e:
                                captured["sq_distance_error"] = str(e)

                        # Manual distance
                        pp = captured.get("sq_player_pos")
                        lp = captured.get("sq_lusya_pos")
                        if pp and lp and "x" in pp and "y" in pp and "x" in lp and "y" in lp:
                            try:
                                px, py = float(pp["x"]), float(pp["y"])
                                lx, ly = float(lp["x"]), float(lp["y"])
                                captured["manual_distance"] = math.hypot(px - lx, py - ly)
                            except Exception:
                                pass

                        # can_observe
                        try:
                            from app.models.npc_state import PerceptualKernel
                            dist_val = captured.get("runtime_distance_player_lusya") or captured.get("manual_distance") or 999.0
                            captured["can_observe_maid_lusya"] = PerceptualKernel.can_observe(
                                event, dist_val, "maid_lusya", payload.get("target_id")
                            )
                        except Exception as e:
                            captured["can_observe_error"] = f"{type(e).__name__}: {e}"
                except Exception as e:
                    captured["provider_call_error"] = f"{type(e).__name__}: {e}"

            captured["engine_calls_before_handler"] = engine_calls_before

            # Call original handler
            try:
                ret = orig_handler(event)
                captured["handler_return"] = repr(ret)[:200] if ret is not None else "None"
            except Exception as e:
                captured["handler_error"] = f"{type(e).__name__}: {e}"

            # After handler
            captured["engine_calls_after_handler"] = len(engine_calls)
            captured["engine_calls_delta"] = captured["engine_calls_after_handler"] - engine_calls_before

            # Check engine calls for maid_lusya
            lusya_calls = []
            for call in engine_calls[engine_calls_before:]:
                args_str = " ".join(call.get("args", []))
                if "maid_lusya" in args_str:
                    lusya_calls.append(call)
            captured["engine_calls_for_lusya"] = lusya_calls

            # Check store for maid_lusya
            if store is not None:
                try:
                    lusya_records = store.get_all_for_agent("maid_lusya")
                    captured["epistemic_records_for_lusya_after"] = len(lusya_records)
                    captured["lusya_records_sample"] = []
                    for r in lusya_records[:3]:
                        try:
                            captured["lusya_records_sample"].append({
                                "proposition": str(getattr(r, "proposition", "?")),
                                "confidence": getattr(r, "confidence", "?"),
                                "source_id": getattr(r, "source_id", "?"),
                            })
                        except Exception:
                            captured["lusya_records_sample"].append({"repr": repr(r)[:200]})
                except Exception as e:
                    captured["epistemic_get_all_error"] = f"{type(e).__name__}: {e}"

            return ret

        setattr(sub, handler_method_name, _spy_handler)
        print(f"  spy attached: sub.{handler_method_name}")

        # ---- C.4: DO NOT clear bus — preserve subscriber registrations ----
        print(f"\n--- C.4: Preserving EventBus subscribers (NOT clearing) ---")
        print(f"  bus._handlers keys (before publish): ", end="")
        try:
            keys = list(getattr(bus, "_handlers", {}).keys())
            print(f"{len(keys)} event types")
            for k in keys[:10]:
                print(f"    {k}")
        except Exception as e:
            print(f"error: {e}")

        # ---- C.5: Publish PLAYER_INSULTS ----
        print(f"\n--- C.5: Publishing PLAYER_INSULTS ---")
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
        print(f"  event.source={evt.source}, target_id={payload['target_id']}, radius={payload['radius']}")
        print(f"  event.visibility={getattr(evt, 'visibility', '?')}")
        print(f"  event.type={getattr(evt, 'type', '?')}")

        bus.publish(evt)
        print(f"  Published.")

        # Restore original handler
        setattr(sub, handler_method_name, orig_handler)

        # ---- C.6: Print captured values ----
        print(f"\n--- C.6: Captured runtime values ---")
        if not captured:
            print("  [captured dict is EMPTY — spy did not fire]")
            print("  >>> This means the handler method was NOT called by EventBus")
            print("  >>> Possible causes:")
            print("      - EventBus.publish() does not dispatch synchronously")
            print("      - The registered handler method name differs from what we spied on")
            print("      - The event was filtered before reaching the handler")
        else:
            ordered = [
                ("event_source", "event_source"),
                ("event_type", "event_type"),
                ("event_visibility", "event_visibility"),
                ("payload_action_type", "payload_action_type"),
                ("payload_target_id", "payload_target_id"),
                ("payload_radius (event.radius)", "payload_radius"),
                ("has_proposition_in_payload", "has_proposition_in_payload"),
                ("provider_is_none", "provider_is_none"),
                ("provider_callable", "provider_callable"),
                ("provider_result_type", "provider_result_type"),
                ("provider_call_error", "provider_call_error"),
                ("sq_npc_positions_count", "sq_npc_positions_count"),
                ("sq_npc_positions_keys", "sq_npc_positions_keys"),
                ("sq_player_pos", "sq_player_pos"),
                ("sq_lusya_pos", "sq_lusya_pos"),
                ("runtime_distance_player_lusya", "runtime_distance_player_lusya"),
                ("manual_distance", "manual_distance"),
                ("can_observe_maid_lusya", "can_observe_maid_lusya"),
                ("can_observe_error", "can_observe_error"),
                ("engine_calls_delta", "engine_calls_delta"),
                ("engine_calls_for_lusya", "engine_calls_for_lusya"),
                ("epistemic_records_for_lusya_after", "epistemic_records_for_lusya_after"),
                ("lusya_records_sample", "lusya_records_sample"),
                ("handler_return", "handler_return"),
                ("handler_error", "handler_error"),
            ]
            for label, key in ordered:
                if key in captured:
                    val = captured[key]
                    if isinstance(val, str) and len(val) > 300:
                        val = val[:300] + "...[truncated]"
                    print(f"  {label}: {val}")

        # ---- C.7: All engine_calls ----
        print(f"\n--- C.7: ALL engine_calls during PLAYER_INSULTS ---")
        for i, call in enumerate(engine_calls):
            print(f"  [{i}] method={call.get('method')}")
            for arg in call.get("args", [])[:3]:
                print(f"       arg: {arg[:200]}")
        if not engine_calls:
            print("  (none — BeliefRevisionEngine was NOT called)")

        # ---- C.8: All store_calls ----
        print(f"\n--- C.8: ALL store_calls during PLAYER_INSULTS ---")
        for i, call in enumerate(store_calls):
            print(f"  [{i}] method={call.get('method')}")
            for arg in call.get("args", [])[:3]:
                print(f"       arg: {arg[:200]}")
        if not store_calls:
            print("  (none — EpistemicStore was NOT called)")

        # ---- C.9: Cleanup ----
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

        result["pass"] = True
        result["captured"] = captured
        result["direct_provider_is_none"] = provider_is_none if 'provider_is_none' in dir() else None
        result["direct_provider_callable"] = provider_callable_direct if 'provider_callable_direct' in dir() else None
        result["handler_method_name"] = handler_method_name
        result["all_registrations"] = all_registrations
        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


# ============================================================================
# STAGE D: Verdict based on ACTUAL data
# ============================================================================
def stage_d_verdict(stage_a: Dict, stage_b: Dict, stage_c: Dict) -> Dict[str, Any]:
    _print_section("STAGE D: VERDICT — based on ACTUAL runtime data")
    result: Dict[str, Any] = {"stage": "D"}

    captured = stage_c.get("captured", {})
    direct_provider_is_none = stage_c.get("direct_provider_is_none")
    direct_provider_callable = stage_c.get("direct_provider_callable")
    handler_method_name = stage_c.get("handler_method_name", "?")
    all_registrations = stage_c.get("all_registrations", [])

    print(f"\n  FACTS (from direct inspection, NOT spy):")
    print(f"    Direct _get_spatial_query is None: {direct_provider_is_none}")
    print(f"    Direct _get_spatial_query callable: {direct_provider_callable}")
    print(f"    Handler method for PLAYER_INSULTS: {handler_method_name}")
    print(f"    Total ClaimEventSubscriber registrations: {len(all_registrations)}")

    print(f"\n  FACTS (from spy, if fired):")
    print(f"    Spy fired: {bool(captured)}")
    if captured:
        print(f"    provider_is_none (runtime): {captured.get('provider_is_none')}")
        print(f"    provider_callable (runtime): {captured.get('provider_callable')}")
        print(f"    provider_result_type: {captured.get('provider_result_type')}")
        print(f"    sq_npc_positions_count: {captured.get('sq_npc_positions_count')}")
        print(f"    runtime_distance_player_lusya: {captured.get('runtime_distance_player_lusya')}")
        print(f"    can_observe_maid_lusya: {captured.get('can_observe_maid_lusya')}")
        print(f"    engine_calls_delta: {captured.get('engine_calls_delta')}")
        print(f"    epistemic_records_for_lusya_after: {captured.get('epistemic_records_for_lusya_after')}")

    # Decision tree based on ACTUAL data
    verdict: str
    rationale: str

    if direct_provider_is_none is True:
        verdict = "1. PROVIDER IS None (confirmed by direct inspection)"
        rationale = (
            "Direct getattr(sub, '_get_spatial_query') returned None. "
            "The runtime ClaimEventSubscriber instance does NOT have the provider, "
            "despite L613 passing spatial_query_provider=self._get_spatial_query_for_subscriber. "
            "Either the runtime instance is from a different constructor call, "
            "or _get_spatial_query was reset after construction."
        )
    elif direct_provider_callable is True:
        # Provider exists and is callable — check if spy fired
        if not captured:
            verdict = "4. OTHER — provider OK but spy didn't fire"
            rationale = (
                "Direct inspection shows _get_spatial_query IS callable (NOT None). "
                "Provider wiring is CORRECT. But the spy on the handler method did not fire. "
                "This means EventBus.publish(PLAYER_INSULTS) did not dispatch to the handler "
                "synchronously, OR the handler method name differs. "
                "The bug is NOT in the provider — it's in event dispatch or handler registration."
            )
        else:
            # Spy fired — check what it captured
            runtime_provider_is_none = captured.get("provider_is_none", True)
            runtime_provider_callable = captured.get("provider_callable", False)
            engine_calls_delta = captured.get("engine_calls_delta", 0)
            epistemic_records = captured.get("epistemic_records_for_lusya_after", 0)

            if runtime_provider_is_none:
                verdict = "1. PROVIDER RETURNS None at handler-call time"
                rationale = "Provider was callable during direct inspection but returned None when called during handler."
            elif engine_calls_delta == 0:
                verdict = "4. OTHER — provider OK, but BeliefRevisionEngine NOT called"
                rationale = (
                    "Provider works, but the handler method did not call BeliefRevisionEngine. "
                    "The handler's listener-gathering logic excludes maid_lusya for a different reason "
                    "(not the provider). Need to read the handler source (Stage C.2)."
                )
            elif epistemic_records == 0:
                verdict = "4. OTHER — engine called but no belief for Lusya"
                rationale = "BeliefRevisionEngine was called but maid_lusya did not receive a belief."
            else:
                verdict = "3. NOT A DEFECT — belief WAS created"
                rationale = "Provider works, can_observe returns True, belief was created. Bug is downstream."
    else:
        verdict = "4. OTHER — could not determine provider state"
        rationale = (
            "Direct inspection returned an unexpected value. "
            "Check Stage C.1 output for the actual getattr result."
        )

    print(f"\n  >>> VERDICT: {verdict}")
    print(f"  >>> RATIONALE: {rationale}")

    print(f"\n  >>> MINIMAL FIX PLAN:")
    if verdict.startswith("1."):
        print(f"    - The runtime instance lacks the provider despite L613 wiring")
        print(f"    - Search for OTHER ClaimEventSubscriber constructor calls (without provider)")
        print(f"    - OR check if _get_spatial_query is reset somewhere after construction")
    elif verdict.startswith("4.") and "spy didn't fire" in rationale:
        print(f"    - Provider is correctly wired (confirmed by direct inspection)")
        print(f"    - Investigate why EventBus.publish(PLAYER_INSULTS) doesn't dispatch to handler")
        print(f"    - Check if PLAYER_INSULTS uses async dispatch or a different bus mechanism")
    elif verdict.startswith("4.") and "BeliefRevisionEngine NOT called" in rationale:
        print(f"    - Provider works correctly")
        print(f"    - The handler method has its own listener-gathering logic")
        print(f"    - Read handler source (Stage C.2) to find why maid_lusya is excluded")
    else:
        print(f"    - Investigate downstream consumers")

    result["verdict"] = verdict
    result["rationale"] = rationale
    return result


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D1 CORRECTED PROBE v2")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("CORRECTIONS from v1:")
    print("  1. Directly inspects sub._get_spatial_query (NOT via spy)")
    print("  2. Identifies actual PLAYER_INSULTS handler via cb.__name__")
    print("  3. Reads source of the handler method")
    print("  4. Does NOT call bus.clear() — preserves subscribers")
    print("  5. Spies on the CORRECT handler method")
    print("  6. Verdict based on ACTUAL runtime data, not defaults")

    stage_a_result: Dict[str, Any] = {}
    stage_b_result: Dict[str, Any] = {}
    stage_c_result: Dict[str, Any] = {}
    stage_d_result: Dict[str, Any] = {}

    try:
        stage_a_result = stage_a_provider_source()
    except Exception as e:
        print(f"[stage A error: {e}]")
        traceback.print_exc()

    try:
        stage_b_result = stage_b_perceptual_kernel()
    except Exception as e:
        print(f"[stage B error: {e}]")
        traceback.print_exc()

    try:
        stage_c_result = stage_c_corrected_runtime()
    except Exception as e:
        print(f"[stage C error: {e}]")
        traceback.print_exc()

    try:
        stage_d_result = stage_d_verdict(stage_a_result, stage_b_result, stage_c_result)
    except Exception as e:
        print(f"[stage D error: {e}]")
        traceback.print_exc()

    print()
    print("=" * 78)
    print("FINAL SUMMARY")
    print("=" * 78)
    print(f"  Stage A pass: {stage_a_result.get('pass', False)}")
    print(f"  Stage B pass: {stage_b_result.get('pass', False)}")
    print(f"  Stage C pass: {stage_c_result.get('pass', False)}")
    print(f"  Verdict:      {stage_d_result.get('verdict', '?')}")

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

# backend/tests/sandbox/r2_flee_traversal_lifecycle_probe.py
"""
R2-FLEE-TRAVERSAL-LIFECYCLE probe.

Цель: проверить судьбу FLEE traversal ПОСЛЕ patch#1-#5.

Без изменения production-кода — только monkey-patching spies.

Гипотезы, которые нужно различить (вердикт Master):
  H1: FLEE создаёт новый traversal внутри ME.process_intents
      и он ждёт следующего тика.
  H2: FLEE не создаёт traversal — лишь отменяет incumbent.
      Старый отменён (CANCELLED), новый intent обработан, но
      движение не началось.
  H3: FLEE создаёт traversal, но он удаляется другим шагом
      pipeline (Phase 0 / Phase 5 конфликт).

Для каждой гипотезы достаточно трёх моментальных снимков
состояния maid_lusya в FLEE-tick'е:
  S1: сразу после ME.process_intents returns (traversal_post)
  S2: в конце FLEE-tick'а (после idle_tick)
  S3: в начале следующего tick'а (до idle_tick)

  H1:  S1=NEW FLEE   S2=FLEE persists   S3=FLEE persists   → position должен двинуться к exit_south
  H2:  S1=NO trav    S2=NO trav         S3=NO trav         → position не меняется
  H3:  S1=NEW FLEE   S2=NO trav (del)   S3=NO trav         → position не меняется, но S1≠S2

Дополнительно: spy на MovementEngine._process_single_intent,
interrupt_traversal и (если найден) create_traversal —
чтобы видеть точный момент изменения traversal.

Запуск (из корня backend):
  python -m tests.sandbox.r2_flee_traversal_lifecycle_probe
  # либо
  python backend/tests/sandbox/r2_flee_traversal_lifecycle_probe.py
"""
from __future__ import annotations
import os, sys, json, shutil, tempfile, traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings, BASE_DIR
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.services.npc.decision_hub import DecisionHub
from app.services.phases.movement_bridge import process_movement_intents
from app.services.spatial.movement_engine import MovementEngine
from app.services.action.commitment_arbiter import CommitmentArbiter

SPY_LOG: List[Dict[str, Any]] = []


def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))


# ----------------------------------------------------------------------------
# Loop helpers
# ----------------------------------------------------------------------------
def build_test_loop(data_dir, saves_dir):
    settings.saves_dir = str(saves_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=data_dir)
    try:
        ts = loop._get_task_scheduler()
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "_router"):
                ex._router = MagicMock()
                if hasattr(ex._router, "route"):
                    ex._router.route.return_value = "[Mock LLM]"
    except Exception:
        pass
    return loop


def cleanup_loop(loop):
    try:
        if hasattr(loop, "_task_scheduler"):
            ts = loop._task_scheduler
            if hasattr(ts, "_executor_pool"):
                try:
                    ts._executor_pool.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
    except Exception:
        pass


def init_scene(loop):
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
    return scene or {}


# ----------------------------------------------------------------------------
# Snapshot helper — полная картина состояния maid_lusya
# ----------------------------------------------------------------------------
def snapshot_maid_lusya_full(loop, label=""):
    """Полный snapshot traversal + position + commitments для maid_lusya."""
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        return {"label": label, "error": "scene None"}
    pos = scene.get("npc_positions", {}).get("maid_lusya", {})
    lp = pos.get("local_position", {}) if isinstance(pos, dict) else {}
    trav = (scene.get("active_traversals") or {}).get("maid_lusya", {})
    comm = (scene.get("active_commitments") or {}).get("maid_lusya", {})
    trav_keys = list(trav.keys()) if isinstance(trav, dict) else []
    return {
        "label": label,
        "tick": scene.get("tick"),
        "position": pos.get("position") if isinstance(pos, dict) else None,
        "x": lp.get("x") if isinstance(lp, dict) else None,
        "y": lp.get("y") if isinstance(lp, dict) else None,
        "traversal_exists": bool(trav),
        "traversal_status": trav.get("status") if isinstance(trav, dict) else None,
        "traversal_target": trav.get("target_node") if isinstance(trav, dict) else None,
        "traversal_started_tick": trav.get("started_tick") if isinstance(trav, dict) else None,
        "traversal_duration": trav.get("duration_ticks") if isinstance(trav, dict) else None,
        "traversal_intent_type": trav.get("intent_type") if isinstance(trav, dict) else None,
        "traversal_reason": trav.get("reason") if isinstance(trav, dict) else None,
        "traversal_cause": trav.get("cause") if isinstance(trav, dict) else None,
        "traversal_keys": trav_keys,
        "commitment_status": comm.get("status") if isinstance(comm, dict) else None,
    }


def snapshot_from_scene_state(scene_state, label=""):
    """То же, но из dict scene_state (для spy внутри ME)."""
    if not isinstance(scene_state, dict):
        return {"label": label, "error": "scene_state not dict"}
    pos = scene_state.get("npc_positions", {}).get("maid_lusya", {})
    lp = pos.get("local_position", {}) if isinstance(pos, dict) else {}
    trav = (scene_state.get("active_traversals") or {}).get("maid_lusya", {})
    trav_keys = list(trav.keys()) if isinstance(trav, dict) else []
    return {
        "label": label,
        "position": pos.get("position") if isinstance(pos, dict) else None,
        "x": lp.get("x") if isinstance(lp, dict) else None,
        "y": lp.get("y") if isinstance(lp, dict) else None,
        "traversal_exists": bool(trav),
        "traversal_status": trav.get("status") if isinstance(trav, dict) else None,
        "traversal_target": trav.get("target_node") if isinstance(trav, dict) else None,
        "traversal_started_tick": trav.get("started_tick") if isinstance(trav, dict) else None,
        "traversal_duration": trav.get("duration_ticks") if isinstance(trav, dict) else None,
        "traversal_intent_type": trav.get("intent_type") if isinstance(trav, dict) else None,
        "traversal_reason": trav.get("reason") if isinstance(trav, dict) else None,
        "traversal_cause": trav.get("cause") if isinstance(trav, dict) else None,
        "traversal_keys": trav_keys,
    }


# ----------------------------------------------------------------------------
# Spies
# ----------------------------------------------------------------------------
def attach_spies():
    # === Spy 1: DecisionHub.compute — FLEE detection ===
    orig_compute = DecisionHub.compute

    def _spy_compute(self_dh, *args, **kwargs):
        state_arg = args[0] if args else kwargs.get("state", None)
        npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
        result = orig_compute(self_dh, *args, **kwargs)
        if npc_id == "maid_lusya":
            dec = getattr(result, "decision", None)
            if dec is not None:
                intent = str(getattr(dec, "intent", "?"))
                target = getattr(dec, "intent_target", None)
                score = getattr(dec, "score", None)
                _stamp("DH.EXIT maid_lusya", intent=intent, target=target, score=score)
        return result

    DecisionHub.compute = _spy_compute

    # === Spy 2: SpatialTargetResolver — wrap resolve ===
    # Try multiple import paths defensively.
    resolver_class = None
    resolver_mod = None
    for mod_path, cls_name in [
        ("app.services.spatial.target_resolver", "SpatialTargetResolver"),
        ("app.services.spatial.spatial_target_resolver", "SpatialTargetResolver"),
        ("app.services.spatial.resolver", "SpatialTargetResolver"),
        ("app.services.spatial", "SpatialTargetResolver"),
    ]:
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            if hasattr(mod, cls_name):
                resolver_mod = mod
                resolver_class = getattr(mod, cls_name)
                print(f"[SPY] resolver found at {mod_path}.{cls_name}")
                break
        except Exception:
            continue

    if resolver_class is not None and hasattr(resolver_class, "resolve"):
        orig_resolve = resolver_class.resolve

        def _spy_resolve(self_r, *args, **kwargs):
            # Defensive: real call signature is
            #   resolver.resolve(target_intent, <pos2>, <pos3>, location_id=...)
            # (movement_bridge.py:69) — NOT (intent, ctx).
            # Find intent among args/kwargs defensively.
            intent = None
            if args:
                # First positional may be either intent obj OR target_intent string.
                first = args[0]
                if hasattr(first, "actor_id") or hasattr(first, "npc_id"):
                    intent = first
                elif hasattr(first, "target_intent"):
                    intent = first
            if intent is None:
                for a in args[1:]:
                    if hasattr(a, "actor_id") or hasattr(a, "npc_id"):
                        intent = a
                        break
            if intent is None:
                intent = kwargs.get("intent") or kwargs.get("target_intent")

            actor = None
            if intent is not None:
                actor = getattr(intent, "actor_id", getattr(intent, "npc_id", None))
            is_ml = (actor == "maid_lusya")

            if is_ml:
                reason = getattr(intent, "reason", "?")
                _stamp("RESOLVER.ENTER maid_lusya",
                       reason=reason,
                       intent_type=getattr(intent, "intent_type", ""),
                       target_type=str(getattr(intent, "target_type", "?")),
                       target_id=getattr(intent, "target_id", None),
                       args_count=len(args),
                       kwargs_keys=list(kwargs.keys()))
            try:
                result = orig_resolve(self_r, *args, **kwargs)
            except Exception as e:
                if is_ml:
                    _stamp("RESOLVER.EXCEPTION maid_lusya",
                           error_type=type(e).__name__, error_msg=str(e)[:200])
                raise
            if is_ml:
                status = getattr(result, "status", "?")
                anchor = (getattr(result, "anchor_node", None)
                          or getattr(result, "target_node_id", None)
                          or getattr(result, "target_node", None))
                pos = getattr(result, "position", None)
                _stamp("RESOLVER.EXIT maid_lusya",
                       status=str(status),
                       anchor_node=anchor,
                       position=str(pos) if pos is not None else None,
                       reason=str(getattr(result, "reason", ""))[:120])
            return result

        resolver_class.resolve = _spy_resolve
    else:
        print("[SPY-WARN] SpatialTargetResolver not found — RESOLVER spy skipped")

    # === Spy 3: CommitmentArbiter.enforce_for_intent ===
    orig_efi = CommitmentArbiter.enforce_for_intent

    def _spy_efi(scene_state, intent, tick):
        actor = getattr(intent, "actor_id", "?")
        if actor != "maid_lusya":
            return orig_efi(scene_state, intent, tick)
        reason = getattr(intent, "reason", "?")
        intent_type = getattr(intent, "intent_type", "")
        _at = scene_state.get("active_traversals", {}) or {}
        trav_before = _at.get("maid_lusya", {})
        _stamp("CA.enforce_for_intent:ENTER maid_lusya",
               reason=reason,
               intent_type=intent_type,
               traversal_before_status=trav_before.get("status") if isinstance(trav_before, dict) else None,
               traversal_before_target=trav_before.get("target_node") if isinstance(trav_before, dict) else None,
               traversal_before_intent_type=trav_before.get("intent_type") if isinstance(trav_before, dict) else None)
        result = orig_efi(scene_state, intent, tick)
        _at2 = scene_state.get("active_traversals", {}) or {}
        trav_after = _at2.get("maid_lusya", {})
        _stamp("CA.enforce_for_intent:EXIT maid_lusya",
               result=result,
               traversal_after_status=trav_after.get("status") if isinstance(trav_after, dict) else None,
               traversal_after_target=trav_after.get("target_node") if isinstance(trav_after, dict) else None,
               traversal_after_intent_type=trav_after.get("intent_type") if isinstance(trav_after, dict) else None)
        return result

    CommitmentArbiter.enforce_for_intent = _spy_efi

    # === Spy 4: interrupt_traversal — кто отменяет traversal? ===
    try:
        import app.domain.traversal_schema as ts_mod
        if hasattr(ts_mod, "interrupt_traversal"):
            orig_it = ts_mod.interrupt_traversal

            def _spy_it(scene_state, actor_id, *args, **kwargs):
                is_ml = (actor_id == "maid_lusya")
                if is_ml:
                    _at = (scene_state or {}).get("active_traversals", {}).get("maid_lusya", {})
                    _stamp("interrupt_traversal:ENTER maid_lusya",
                           args=[str(a)[:60] for a in args],
                           kwargs_keys=list(kwargs.keys()),
                           traversal_before_status=_at.get("status") if isinstance(_at, dict) else None,
                           traversal_before_target=_at.get("target_node") if isinstance(_at, dict) else None)
                result = orig_it(scene_state, actor_id, *args, **kwargs)
                if is_ml:
                    _at2 = (scene_state or {}).get("active_traversals", {}).get("maid_lusya", {})
                    _stamp("interrupt_traversal:EXIT maid_lusya",
                           traversal_after_status=_at2.get("status") if isinstance(_at2, dict) else None,
                           traversal_after_target=_at2.get("target_node") if isinstance(_at2, dict) else None)
                return result

            ts_mod.interrupt_traversal = _spy_it
            print("[SPY] attached interrupt_traversal")
        else:
            print("[SPY-WARN] traversal_schema.interrupt_traversal not found")
    except Exception as e:
        print(f"[SPY-WARN] interrupt_traversal spy setup failed: {e}")

    # === Spy 5: traversal creation — try multiple candidate names ===
    try:
        import app.domain.traversal_schema as ts_mod
        candidates = [
            "create_traversal", "build_traversal", "start_traversal",
            "init_traversal", "register_traversal", "propose_traversal",
            "create_traversal_dict", "build_traversal_dict",
        ]
        attached = []
        for fn_name in candidates:
            if hasattr(ts_mod, fn_name):
                orig_fn = getattr(ts_mod, fn_name)

                def _make_spy(_name, _orig):
                    def _spy(*args, **kwargs):
                        # Try to find actor_id
                        actor = None
                        if args:
                            for a in args[:3]:
                                if isinstance(a, str):
                                    actor = a
                                    break
                                if isinstance(a, dict):
                                    actor = a.get("actor_id") or a.get("npc_id")
                                    if actor:
                                        break
                        if not actor and "actor_id" in kwargs:
                            actor = kwargs["actor_id"]
                        if actor == "maid_lusya":
                            _stamp(f"{_name}:ENTER maid_lusya",
                                   args_preview=[str(a)[:80] for a in args],
                                   kwargs_keys=list(kwargs.keys()))
                        result = _orig(*args, **kwargs)
                        if actor == "maid_lusya":
                            _stamp(f"{_name}:EXIT maid_lusya",
                                   result_type=type(result).__name__,
                                   result_preview=str(result)[:200] if result is not None else None)
                        return result
                    return _spy

                setattr(ts_mod, fn_name, _make_spy(fn_name, orig_fn))
                attached.append(fn_name)
        if attached:
            print(f"[SPY] attached traversal creation spies: {attached}")
        else:
            print("[SPY-WARN] no traversal creation function found in traversal_schema")
    except Exception as e:
        print(f"[SPY-WARN] traversal creation spy setup failed: {e}")

    # === Spy 6: MovementEngine._process_single_intent (deep trace) ===
    psi_name = None
    for cand in ("_process_single_intent", "_process_intent",
                 "process_single_intent", "_handle_intent", "_process_one"):
        if hasattr(MovementEngine, cand):
            psi_name = cand
            break

    if psi_name is not None:
        orig_psi = getattr(MovementEngine, psi_name)

        def _spy_psi(self_me, intent, *args, **kwargs):
            actor = getattr(intent, "actor_id", "?")
            reason = getattr(intent, "reason", "?")
            intent_type = getattr(intent, "intent_type", "")
            is_ml = (actor == "maid_lusya")
            is_flee = (intent_type == "flee") or ("flee" in str(reason).lower())
            if is_ml:
                _stamp(f"ME.{psi_name}:ENTER maid_lusya",
                       reason=reason, intent_type=intent_type,
                       target_node_id=getattr(intent, "target_node_id", None),
                       is_flee_intent=is_flee)
            try:
                result = orig_psi(self_me, intent, *args, **kwargs)
            except Exception as e:
                if is_ml:
                    _stamp(f"ME.{psi_name}:EXCEPTION maid_lusya",
                           error_type=type(e).__name__, error_msg=str(e)[:300])
                raise
            if is_ml:
                _stamp(f"ME.{psi_name}:EXIT maid_lusya",
                       result_type=type(result).__name__,
                       result_preview=str(result)[:200] if result is not None else None,
                       is_flee_intent=is_flee)
            return result

        setattr(MovementEngine, psi_name, _spy_psi)
        print(f"[SPY] attached MovementEngine.{psi_name}")
    else:
        print("[SPY-WARN] MovementEngine._process_single_intent (or alt) NOT FOUND")

    # === Spy 6b: COMPREHENSIVE MovementEngine method trace ===
    # _process_single_intent exists but was NOT called in v1 — that means
    # ME.process_intents uses a different internal path. Wrap ALL callable
    # non-dunder methods of MovementEngine to find which one is actually used.
    SKIP_NAMES = {"process_intents", psi_name}  # already wrapped above
    wrapped_methods = []
    for name in sorted(dir(MovementEngine)):
        if name.startswith("__"):
            continue
        if name in SKIP_NAMES:
            continue
        attr = getattr(MovementEngine, name)
        if not callable(attr):
            continue
        # skip already-wrapped closures (defensive against re-entry)
        if getattr(attr, "_r2_wrapped", False):
            continue
        try:
            orig_method = attr

            def _make_wrapper(_name, _orig):
                def _wrapper(self_me, *args, **kwargs):
                    # Detect maid_lusya among args/kwargs.
                    is_ml = False
                    intent_type = ""
                    reason = ""
                    target_node_id = None
                    for a in args:
                        a_id = getattr(a, "actor_id", getattr(a, "npc_id", None))
                        if a_id == "maid_lusya":
                            is_ml = True
                            intent_type = getattr(a, "intent_type", "")
                            reason = getattr(a, "reason", "")
                            target_node_id = getattr(a, "target_node_id", None)
                            break
                    if not is_ml:
                        for v in kwargs.values():
                            a_id = getattr(v, "actor_id", getattr(v, "npc_id", None))
                            if a_id == "maid_lusya":
                                is_ml = True
                                break
                    # Also detect "maid_lusya" as a positional string arg
                    if not is_ml:
                        for a in args:
                            if isinstance(a, str) and a == "maid_lusya":
                                is_ml = True
                                break
                    if is_ml:
                        _stamp(f"ME.{_name}:CALL maid_lusya",
                               args_count=len(args),
                               kwargs_keys=list(kwargs.keys()),
                               reason=reason, intent_type=intent_type,
                               target_node_id=target_node_id)
                    return _orig(self_me, *args, **kwargs)
                _wrapper._r2_wrapped = True
                return _wrapper

            setattr(MovementEngine, name, _make_wrapper(name, orig_method))
            wrapped_methods.append(name)
        except (TypeError, AttributeError):
            continue
    if wrapped_methods:
        print(f"[SPY] wrapped {len(wrapped_methods)} MovementEngine methods: {wrapped_methods[:10]}{'...' if len(wrapped_methods) > 10 else ''}")

    # === Spy 7: MovementEngine.process_intents — S1 snapshot ===
    orig_pi = MovementEngine.process_intents

    def _spy_pi(self_me, intents, **kwargs):
        scene_state = kwargs.get("scene_state")
        has_ml = any(getattr(i, "actor_id", "") == "maid_lusya" for i in (intents or []))
        ml_intents = []
        for i in (intents or []):
            if getattr(i, "actor_id", "") == "maid_lusya":
                ml_intents.append({
                    "reason": getattr(i, "reason", "?"),
                    "intent_type": getattr(i, "intent_type", ""),
                    "target_node_id": getattr(i, "target_node_id", None),
                })
        pre_snap = snapshot_from_scene_state(scene_state, "ME.pre") if has_ml else None
        if has_ml:
            _stamp("ME.process_intents:ENTER maid_lusya",
                   ml_intents=ml_intents,
                   snapshot_pre=pre_snap)
        result = orig_pi(self_me, intents, **kwargs)
        if has_ml:
            post_snap = snapshot_from_scene_state(scene_state, "ME.post") if has_ml else None
            ml_changes = []
            for sc in (result or []):
                target_id = getattr(sc, "target", getattr(sc, "npc_id", "?"))
                if target_id == "maid_lusya":
                    ml_changes.append({
                        "field": getattr(sc, "field", "?"),
                        "value": str(getattr(sc, "value", "?"))[:120],
                    })
            pos_delta = (
                pre_snap is not None and post_snap is not None and
                (pre_snap.get("x") != post_snap.get("x")
                 or pre_snap.get("y") != post_snap.get("y"))
            )
            trav_created = (
                pre_snap is not None and post_snap is not None and
                (not pre_snap.get("traversal_exists")) and
                post_snap.get("traversal_exists")
            )
            trav_changed_status = (
                pre_snap is not None and post_snap is not None and
                pre_snap.get("traversal_status") != post_snap.get("traversal_status")
            )
            _stamp("ME.process_intents:EXIT maid_lusya",
                   ml_changes_count=len(ml_changes),
                   ml_changes=ml_changes,
                   snapshot_post=post_snap,
                   position_delta=pos_delta,
                   traversal_created=trav_created,
                   traversal_status_changed=trav_changed_status,
                   FLEE_EXECUTED=len(ml_changes) > 0)
        return result

    MovementEngine.process_intents = _spy_pi


# ----------------------------------------------------------------------------
# Insult injector
# ----------------------------------------------------------------------------
def publish_insult(target_id="maid_lusya"):
    payload = {
        "action_type": "player_insults", "target_id": target_id,
        "content": "оскорбление", "event_tick": 1, "visibility": "public",
        "radius": 999.0, "location": "tavern", "campaign_id": "Open_road",
        "raw_input": "оскорбление",
    }
    evt = EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player",
                          payload=payload, persistence_level="working")
    get_event_bus().publish(evt)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    print("\n" + "=" * 78)
    print("R2-FLEE-TRAVERSAL-LIFECYCLE probe")
    print("Goal: distinguish H1 (created+waiting) / H2 (not created) / H3 (created+deleted)")
    print("WITHOUT changing production code — monkey-patching only.")
    print("=" * 78)

    real_data_dir = Path(settings.data_dir)
    saves_dir = Path(tempfile.mkdtemp(prefix="r2_lifecycle_"))

    try:
        SPY_LOG.clear()
        try:
            get_event_bus().clear()
        except Exception:
            pass

        loop = build_test_loop(real_data_dir, saves_dir)
        init_scene(loop)
        attach_spies()

        _stamp("PRE-SCENE", **snapshot_maid_lusya_full(loop, "pre-scene"))
        publish_insult("maid_lusya")

        for tick_i in range(1, 9):
            _stamp(f"TICK_{tick_i}:START",
                   **snapshot_maid_lusya_full(loop, f"tick{tick_i}_start"))
            try:
                loop.idle_tick("Open_road")
            except Exception as e:
                _stamp(f"TICK_{tick_i}:ERROR", error=str(e)[:300])
                traceback.print_exc()
                break
            _stamp(f"TICK_{tick_i}:END",
                   **snapshot_maid_lusya_full(loop, f"tick{tick_i}_end"))

        cleanup_loop(loop)
        del loop
        import gc
        gc.collect()

        # ==================================================================
        # FORENSIC REPORT
        # ==================================================================
        print("\n" + "=" * 78)
        print("FORENSIC REPORT — R2-FLEE-TRAVERSAL-LIFECYCLE")
        print("=" * 78)

        # 1) Find ALL FLEE decisions across all ticks
        flee_decisions = []
        last_start = None
        for e in SPY_LOG:
            tag = e.get("tag", "")
            if tag.startswith("TICK_") and tag.endswith(":START"):
                try:
                    last_start = int(tag.split("_")[1].split(":")[0])
                except Exception:
                    pass
            if e.get("tag") == "DH.EXIT maid_lusya" and "FLEE" in e.get("intent", ""):
                flee_decisions.append({"tick": last_start, "event": e})

        if not flee_decisions:
            print("\n[FATAL] No FLEE decision found in any tick — probe cannot proceed.")
            return 1

        print(f"\n--- Found {len(flee_decisions)} FLEE decisions across all ticks ---")
        for fd in flee_decisions:
            print(f"  TICK {fd['tick']}: {fd['event']}")

        # 2) Process each FLEE decision
        all_verdicts = []
        for fd in flee_decisions:
            flee_tick_num = fd["tick"]
            print("\n" + "#" * 78)
            print(f"# ANALYZING FLEE in TICK {flee_tick_num}")
            print("#" * 78)

            # 3) Full timeline for FLEE tick
            print(f"\n--- TICK {flee_tick_num} FULL TIMELINE ---")
            capturing = False
            for e in SPY_LOG:
                tag = e.get("tag", "")
                if tag == f"TICK_{flee_tick_num}:START":
                    capturing = True
                if capturing:
                    print(f"  {e}")
                    if tag == f"TICK_{flee_tick_num}:END":
                        break

            # 4) Cross-tick persistence: S1/S2/S3
            next_tick = (flee_tick_num or 0) + 1
            s1_me_exit = None
            s2_tick_end = None
            s3_next_start = None
            capturing = False
            for e in SPY_LOG:
                tag = e.get("tag", "")
                if tag == f"TICK_{flee_tick_num}:START":
                    capturing = True
                if capturing and tag == "ME.process_intents:EXIT maid_lusya":
                    s1_me_exit = e
                if capturing and tag == f"TICK_{flee_tick_num}:END":
                    s2_tick_end = e
                    break
            for e in SPY_LOG:
                if e.get("tag") == f"TICK_{next_tick}:START":
                    s3_next_start = e
                    break

            print("\n" + "=" * 78)
            print(f"THREE-SNAPSHOT COMPARISON (S1 / S2 / S3) — TICK {flee_tick_num}")
            print("=" * 78)

            def _fmt_snap(snap, label):
                if not snap:
                    return f"  {label}: <missing>"
                if "snapshot_post" in snap:
                    p = snap.get("snapshot_post") or {}
                else:
                    p = snap
                return (f"  {label}: traversal_exists={p.get('traversal_exists')} "
                        f"status={p.get('traversal_status')} target={p.get('traversal_target')} "
                        f"intent_type={p.get('traversal_intent_type')} reason={p.get('traversal_reason')} "
                        f"started_tick={p.get('traversal_started_tick')} "
                        f"keys={p.get('traversal_keys')} "
                        f"pos=({p.get('x')}, {p.get('y')})")

            print(_fmt_snap(s1_me_exit, "S1 (after ME.process_intents in FLEE tick)"))
            print(_fmt_snap(s2_tick_end, "S2 (end of FLEE tick, after idle_tick)    "))
            print(_fmt_snap(s3_next_start, "S3 (start of NEXT tick, before idle_tick) "))

            # 5) Hypothesis verdict
            print("\n" + "-" * 78)
            print(f"HYPOTHESIS VERDICT — TICK {flee_tick_num}")
            print("-" * 78)

            def _extract(s1, s2, s3, key):
                vals = []
                for src in (s1, s2, s3):
                    if not src:
                        vals.append(None)
                        continue
                    p = src.get("snapshot_post") or src
                    vals.append(p.get(key))
                return vals

            s1_status, s2_status, s3_status = _extract(s1_me_exit, s2_tick_end, s3_next_start, "traversal_status")
            s1_target, s2_target, s3_target = _extract(s1_me_exit, s2_tick_end, s3_next_start, "traversal_target")
            s1_itype, s2_itype, s3_itype = _extract(s1_me_exit, s2_tick_end, s3_next_start, "traversal_intent_type")

            s1_flee_traversal = (s1_target == "tavern:exit_south")
            s2_flee_traversal = (s2_target == "tavern:exit_south")
            s3_flee_traversal = (s3_target == "tavern:exit_south")

            print(f"\nS1: target={s1_target} status={s1_status} intent_type={s1_itype}")
            print(f"S2: target={s2_target} status={s2_status} intent_type={s2_itype}")
            print(f"S3: target={s3_target} status={s3_status} intent_type={s3_itype}")

            print(f"\nS1 has FLEE traversal (target=exit_south): {s1_flee_traversal}")
            print(f"S2 has FLEE traversal (target=exit_south): {s2_flee_traversal}")
            print(f"S3 has FLEE traversal (target=exit_south): {s3_flee_traversal}")

            if not s1_me_exit:
                verdict = f"TICK {flee_tick_num}: AMBIGUOUS — ME.process_intents was NOT called for maid_lusya in FLEE tick (pipeline failed earlier)"
                print(f"\n>>> VERDICT: {verdict}")
                print(">>> Likely: resolver crashed or CA rejected before ME.process_intents.")
            elif not s1_flee_traversal:
                verdict = f"TICK {flee_tick_num}: H2 — FLEE traversal was NOT created inside ME.process_intents"
                print(f"\n>>> VERDICT: {verdict}")
                print(">>> Old incumbent traversal was cancelled (CANCELLED) by CA,")
                print(">>> but FLEE intent did NOT result in a new traversal.")
                print(">>> Position will not move toward exit_south.")
            elif s1_flee_traversal and s2_flee_traversal and s3_flee_traversal:
                verdict = f"TICK {flee_tick_num}: H1 — FLEE traversal created and persisted to next tick"
                print(f"\n>>> VERDICT: {verdict}")
                print(">>> Movement should occur in next tick(s) — check position delta below.")
            elif s1_flee_traversal and not s2_flee_traversal:
                verdict = f"TICK {flee_tick_num}: H3 — FLEE traversal created in ME but DELETED before end of tick"
                print(f"\n>>> VERDICT: {verdict}")
                print(">>> Something between ME.process_intents EXIT and end of idle_tick")
                print(">>> destroyed the FLEE traversal. Check other pipeline phases.")
            elif s1_flee_traversal and s2_flee_traversal and not s3_flee_traversal:
                verdict = f"TICK {flee_tick_num}: H3-variant — FLEE traversal survived to end of tick but was cleared at start of next"
                print(f"\n>>> VERDICT: {verdict}")
                print(">>> Check LifeEngine / schedule phase at start of next tick.")
            else:
                verdict = f"TICK {flee_tick_num}: AMBIGUOUS — see raw snapshots"
                print(f"\n>>> VERDICT: {verdict}")

            # Per-FLEE-tick position delta
            start_snap = next((e for e in SPY_LOG if e.get("tag") == f"TICK_{flee_tick_num}:START"), None)
            end_snap = next((e for e in SPY_LOG if e.get("tag") == f"TICK_{flee_tick_num}:END"), None)
            next_start = next((e for e in SPY_LOG if e.get("tag") == f"TICK_{flee_tick_num + 1}:START"), None)
            print(f"\nFLEE tick {flee_tick_num} position delta:")
            if start_snap:
                print(f"  TICK_{flee_tick_num}:START pos = ({start_snap.get('x')}, {start_snap.get('y')}) "
                      f"trav_target={start_snap.get('traversal_target')}")
            if end_snap:
                print(f"  TICK_{flee_tick_num}:END   pos = ({end_snap.get('x')}, {end_snap.get('y')}) "
                      f"trav_target={end_snap.get('traversal_target')}")
            if next_start:
                print(f"  TICK_{flee_tick_num + 1}:START pos = ({next_start.get('x')}, {next_start.get('y')}) "
                      f"trav_target={next_start.get('traversal_target')}")
            moved_within = (
                start_snap and end_snap and
                (start_snap.get("x") != end_snap.get("x")
                 or start_snap.get("y") != end_snap.get("y"))
            )
            moved_next = (
                start_snap and next_start and
                (start_snap.get("x") != next_start.get("x")
                 or start_snap.get("y") != next_start.get("y"))
            )
            print(f"  Moved within FLEE tick?         {moved_within}")
            print(f"  Moved by start of next tick?    {moved_next}")

            all_verdicts.append({
                "tick": flee_tick_num,
                "verdict": verdict,
                "s1_target": s1_target,
                "s2_target": s2_target,
                "s3_target": s3_target,
                "moved_within": moved_within,
                "moved_next": moved_next,
            })

        # 6) MovementEngine method calls — comprehensive trace
        print("\n" + "=" * 78)
        print("MovementEngine internal method calls for maid_lusya (across all ticks)")
        print("=" * 78)
        me_calls = [e for e in SPY_LOG if (e.get("tag", "").startswith("ME.") and ":CALL maid_lusya" in e.get("tag", ""))]
        print(f"\nTotal ME method calls for maid_lusya: {len(me_calls)}")
        # Group by method name
        by_method = {}
        for c in me_calls:
            tag = c.get("tag", "")
            # extract method name from "ME.<method>:CALL maid_lusya"
            method = tag.split(":CALL")[0][3:] if ":CALL" in tag else tag
            by_method.setdefault(method, []).append(c)
        for method, calls in sorted(by_method.items()):
            print(f"\n  Method: {method} ({len(calls)} calls)")
            for c in calls[:5]:
                print(f"    {c}")
            if len(calls) > 5:
                print(f"    ... and {len(calls) - 5} more")

        # 7) Final summary
        print("\n" + "=" * 78)
        print("FINAL SUMMARY FOR MASTER — all FLEE attempts")
        print("=" * 78)
        print(f"\nTotal FLEE decisions: {len(all_verdicts)}")
        print()
        print(f"{'Tick':<6}{'Verdict':<90}{'S1→S2→S3 target':<60}")
        print("-" * 156)
        for v in all_verdicts:
            s1 = v.get("s1_target") or "<missing>"
            s2 = v.get("s2_target") or "<missing>"
            s3 = v.get("s3_target") or "<missing>"
            print(f"{v['tick']:<6}{v['verdict'][:88]:<90}{s1} → {s2} → {s3}")
        print()
        # Aggregate verdict
        h1_count = sum(1 for v in all_verdicts if "H1" in v["verdict"])
        h2_count = sum(1 for v in all_verdicts if "H2" in v["verdict"])
        h3_count = sum(1 for v in all_verdicts if "H3" in v["verdict"])
        amb_count = sum(1 for v in all_verdicts if "AMBIGUOUS" in v["verdict"])
        print(f"Aggregate: H1={h1_count}  H2={h2_count}  H3={h3_count}  AMBIGUOUS={amb_count}")
        if h1_count > 0:
            print("\n>>> CONCLUSION: FLEE traversal IS created and persists."
                  "  This closes the lifecycle question.")
        elif h2_count == len(all_verdicts):
            print("\n>>> CONCLUSION: FLEE traversal NEVER created in ME."
                  "  B1.5 patch passes intent through, but ME does NOT create traversal.")
            print(">>> Hypothesis: ME._process_single_intent (or equivalent)"
                  " filters by intent_type and skips FLEE.")
        elif h3_count > 0:
            print("\n>>> CONCLUSION: FLEE traversal IS created but destroyed."
                  "  H3 — investigate post-ME pipeline phases.")

        # Resolver and CA trace summary
        print("\n" + "=" * 78)
        print("RESOLVER + CA trace summary")
        print("=" * 78)
        resolver_calls = [e for e in SPY_LOG if e.get("tag", "").startswith("RESOLVER.")]
        ca_calls = [e for e in SPY_LOG if e.get("tag", "").startswith("CA.")]
        interrupt_calls = [e for e in SPY_LOG if e.get("tag", "").startswith("interrupt_traversal")]
        build_calls = [e for e in SPY_LOG if e.get("tag", "").startswith("build_traversal_dict")]
        print(f"\nRESOLVER calls for maid_lusya: {len(resolver_calls)}")
        for c in resolver_calls:
            print(f"  {c}")
        print(f"\nCommitmentArbiter.enforce_for_intent calls for maid_lusya: {len(ca_calls)}")
        for c in ca_calls:
            print(f"  {c}")
        print(f"\ninterrupt_traversal calls for maid_lusya: {len(interrupt_calls)}")
        for c in interrupt_calls:
            print(f"  {c}")
        print(f"\nbuild_traversal_dict calls for maid_lusya: {len(build_calls)}")
        for c in build_calls:
            print(f"  {c}")

        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        try:
            shutil.rmtree(saves_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())

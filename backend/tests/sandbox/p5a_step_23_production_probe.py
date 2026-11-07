# backend/tests/sandbox/p5a_step_23_production_probe.py
"""
P5-A Step 2.3 — Production Forensic Probe.
Build real GameLoop (build_game_loop), mock only LLM router.
Direct event_bus.publish(PLAYER_INSULTS) — production channel.
idle_tick — production pipeline.
Spy wrappers — observation only, no semantic change.

A: PLAYER_INSULTS → EpistemicStore(maid_lusya)
B: idle_tick → DecisionHub → CommunicationIntent → QueuedTask → NPC_SPOKE
C: A/B control (no PLAYER_INSULTS) — сравнение
"""
from __future__ import annotations

import os, sys, json, shutil, tempfile, traceback, types, uuid, asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# === Production imports (read-only) ===
from app.core.config import settings, BASE_DIR
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_bus import get_event_bus, EventBus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate, EpistemicRecord
from app.services.npc.epistemic_store import EpistemicStore
from app.services.events.claim_event_subscriber import ClaimEventSubscriber
from app.services.npc.belief_revision_engine import BeliefRevisionEngine

# === Spy registry ===
SPY_LOG: List[Dict[str, Any]] = []

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

def wrap(obj: Any, method_name: str, tag: str) -> None:
    """Wrapper — before/after log. No semantic change (письмо №3 S350)."""
    if obj is None:
        _stamp(f"{tag}:SKIP", reason="obj is None")
        return
    if not hasattr(obj, method_name):
        _stamp(f"{tag}:SKIP", reason=f"no method {method_name}")
        return
    original = getattr(obj, method_name)
    def wrapper(*args, **kwargs):
        try:
            arg_dump = []
            if args:
                for i, a in enumerate(args[1:], 1):
                    arg_dump.append(f"arg{i}={type(a).__name__}")
            _stamp(f"{tag}:ENTER", caller_args=arg_dump, kwargs_keys=list(kwargs.keys()))
        except Exception:
            pass
        try:
            result = original(*args, **kwargs)
            try:
                _stamp(f"{tag}:EXIT", result_type=type(result).__name__,
                       result_repr=repr(result)[:200])
            except Exception:
                _stamp(f"{tag}:EXIT", result_type=type(result).__name__)
            return result
        except Exception as e:
            _stamp(f"{tag}:ERROR", error=type(e).__name__, msg=str(e)[:300])
            raise
    setattr(obj, method_name, wrapper)


# === Build production GameLoop ===
def build_test_loop() -> Tuple[Any, Path]:
    """Build real GameLoop with isolated saves + mock LLM router (conftest pattern)."""
    temp_dir = Path(tempfile.mkdtemp(prefix="p23_probe_"))
    real_data_dir = Path(settings.data_dir)
    original_saves_dir = settings.saves_dir
    original_env = settings.environment

    settings.saves_dir = str(temp_dir)
    settings.environment = "development"

    loop = build_game_loop(data_dir=real_data_dir)

    # Mock LLM router (conftest:42-46 pattern)
    try:
        ts = loop._get_task_scheduler()  # noqa: ENIGMA002
        if hasattr(ts, "_router") and ts._router is not None:
            ts._router = MagicMock()
            ts._router.route.return_value = "[Test LLM Mock]"
            _stamp("HARNESS.mock_llm", status="installed", where="task_scheduler._router")
        else:
            _stamp("HARNESS.mock_llm", status="no _router attr", where="task_scheduler")
    except Exception as e:
        _stamp("HARNESS.mock_llm", status="FAILED", error=str(e)[:200])

    return loop, temp_dir


def cleanup(loop: Any, temp_dir: Path) -> None:
    try:
        if hasattr(loop, "_task_scheduler"):
            ts = loop._task_scheduler
            if hasattr(ts, "_executor_pool"):
                try:
                    pool = ts._executor_pool
                    if pool is not None:
                        pool.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
    except Exception:
        pass
    shutil.rmtree(temp_dir, ignore_errors=True)


# === Subscribe spies AFTER loop built ===
def attach_spies(loop: Any) -> Dict[str, Any]:
    """Wrapper spies на все звенья production цепи."""
    refs: Dict[str, Any] = {}

    # 1. ClaimEventSubscriber (registered lazily in _register_epistemic_core)
    sub = getattr(loop, "_claim_event_subscriber", None)
    refs["subscriber"] = sub
    wrap(sub, "on_player_spoke", "A2.on_player_spoke")
    wrap(sub, "on_claim_event", "A3.on_claim_event")
    wrap(sub, "on_npc_spoke", "B4.on_npc_spoke")

    # 2. BeliefRevisionEngine — wrapper at class level (no handle to instance)
    try:
        orig_revise = BeliefRevisionEngine.revise
        def spy_revise(self_engine, *args, **kwargs):
            listener_id = args[0] if args else kwargs.get("listener_id", "?")
            claim = args[1] if len(args) > 1 else kwargs.get("claim", None)
            prop_summary = ""
            if claim is not None:
                p = getattr(claim, "proposition", None)
                if p is not None:
                    prop_summary = f"{p.subject_id}/{p.predicate.value}/{p.object_id}"
            _stamp("A4.belief_revision_engine.revise:ENTER",
                   listener=listener_id, prop=prop_summary,
                   speaker=getattr(claim, "speaker_id", "?"),
                   tick=getattr(claim, "tick", "?"))
            result = orig_revise(self_engine, *args, **kwargs)
            _stamp("A4.belief_revision_engine.revise:EXIT",
                   conf=getattr(result, "confidence", None),
                   source=getattr(result, "source_id", None),
                   orig_src=getattr(result, "original_source_id", None))
            return result
        BeliefRevisionEngine.revise = spy_revise  # type: ignore
        refs["engine_class_patched"] = True
    except Exception as e:
        _stamp("A4.attach", status="FAILED", error=str(e)[:200])

    # 3. EpistemicStore (instance via subscriber._store)
    if sub is not None:
        store = getattr(sub, "_store", None)
        refs["store"] = store
        wrap(store, "upsert", "A5.epistemic_store.upsert")

    # 4. TaskScheduler — execute_pending + process_tasks
    try:
        ts = loop._get_task_scheduler()  # noqa: ENIGMA002
        refs["task_scheduler"] = ts
        wrap(ts, "execute_pending", "B2.execute_pending")
        # DialogueExecutor — publish NPC_SPOKE
        if hasattr(ts, "_executor_pool"):
            try:
                pool = ts._executor_pool
                for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
                    wrap(ex, "execute", f"B4.dialogue_executor.{kind}.execute")
            except Exception as e:
                _stamp("B4.attach_executor", status="FAILED", error=str(e)[:200])
    except Exception as e:
        _stamp("B2.attach", status="FAILED", error=str(e)[:200])

    # 5. EventBus — publish spy
    bus = get_event_bus()
    orig_pub = bus.publish
    def spy_publish(evt: Any) -> None:
        et = getattr(evt, "type", "?")
        src = getattr(evt, "source", "?")
        tgt = (getattr(evt, "payload", {}) or {}).get("target_id")
        _stamp("BUS.publish", event_type=et, source=src, target_id=tgt)
        return orig_pub(evt)
    bus.publish = spy_publish  # type: ignore

    return refs


# === Track A: publish PLAYER_INSULTS + verify ===
def track_a_insult(loop: Any, target_id: str = "maid_lusya") -> Dict[str, Any]:
    _stamp("=== TRACK A: PLAYER_INSULTS ===", target=target_id)
    bus = get_event_bus()
    payload = {
        "action_type": "player_insults",
        "target_id": target_id,
        "content": "оскорбление",
        "event_tick": 1,
        "visibility": "public",
        "radius": 10.0,
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
    _stamp("A1.publish", event_id=str(evt.id), target_id=target_id)
    bus.publish(evt)
    return {"event_id": str(evt.id), "target_id": target_id}


# === Check EpistemicStore state ===
def check_belief(loop: Any, agent_id: str) -> Dict[str, Any]:
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is None:
        return {"error": "no subscriber"}
    store = getattr(sub, "_store", None)
    if store is None:
        return {"error": "no store"}
    prop = Proposition(subject_id="player", predicate=Predicate.INSULTED,
                       object_id=agent_id, polarity=True)
    rec = store.get(agent_id, prop)
    if rec is None:
        return {"agent": agent_id, "belief_present": False}
    return {
        "agent": agent_id,
        "belief_present": True,
        "confidence": getattr(rec, "confidence", None),
        "source_id": getattr(rec, "source_id", None),
        "original_source_id": getattr(rec, "original_source_id", None),
        "source_type": getattr(rec, "source_type", None),
        "first_observed_tick": getattr(rec, "first_observed_tick", None),
    }


# === Track B: idle_tick + observe ===
def track_b_idle(loop: Any, campaign_id: str = "Open_road") -> Dict[str, Any]:
    _stamp("=== TRACK B: idle_tick ===", campaign=campaign_id)
    # Snapshot pre-state
    sub = getattr(loop, "_claim_event_subscriber", None)
    pre_pending = 0
    pre_beliefs: Dict[str, Any] = {}
    if sub is not None:
        store = getattr(sub, "_store", None)
        if store is not None:
            try:
                all_recs = store.to_dict() if hasattr(store, "to_dict") else []
                pre_beliefs["total"] = len(all_recs) if isinstance(all_recs, list) else "?"
                pre_beliefs["agents"] = sorted({r.get("agent_id") for r in all_recs}) if isinstance(all_recs, list) else []
            except Exception as e:
                pre_beliefs["error"] = str(e)[:100]

    try:
        scene = loop.scene_manager.get_scene_state(campaign_id, "tavern")
        if scene is not None:
            pre_pending = len(scene.get("pending_tasks", []) or [])
            _stamp("B.pre_state", pending_tasks=pre_pending,
                   game_time=scene.get("game_time_seconds", "?"),
                   npc_count=len(scene.get("npc_positions", {}) or {}))
        else:
            _stamp("B.pre_state", scene="None")
    except Exception as e:
        _stamp("B.pre_state", error=str(e)[:200])

    # Run idle_tick
    try:
        result = loop.idle_tick(campaign_id)
        _stamp("B.idle_tick:EXIT",
               status=result.get("status", "?") if isinstance(result, dict) else type(result).__name__,
               npc_count=len(result.get("npc_positions", {})) if isinstance(result, dict) else 0)
    except Exception as e:
        _stamp("B.idle_tick:ERROR", error=type(e).__name__, msg=str(e)[:300])
        return {"error": str(e)[:200]}

    # Snapshot post-state
    post_beliefs: Dict[str, Any] = {}
    post_pending = 0
    if sub is not None:
        store = getattr(sub, "_store", None)
        if store is not None:
            try:
                all_recs = store.to_dict() if hasattr(store, "to_dict") else []
                post_beliefs["total"] = len(all_recs) if isinstance(all_recs, list) else "?"
                post_beliefs["agents"] = sorted({r.get("agent_id") for r in all_recs}) if isinstance(all_recs, list) else []
            except Exception as e:
                post_beliefs["error"] = str(e)[:100]

    try:
        scene = loop.scene_manager.get_scene_state(campaign_id, "tavern")
        if scene is not None:
            post_pending = len(scene.get("pending_tasks", []) or [])
            _stamp("B.post_state", pending_tasks=post_pending,
                   game_time=scene.get("game_time_seconds", "?"))
        else:
            _stamp("B.post_state", scene="None")
    except Exception as e:
        _stamp("B.post_state", error=str(e)[:200])

    return {
        "pre_pending": pre_pending,
        "post_pending": post_pending,
        "pre_beliefs": pre_beliefs,
        "post_beliefs": post_beliefs,
    }


# === MAIN ===
def main() -> int:
    print("\n" + "=" * 78)
    print("P5-A Step 2.3 — Production Forensic Probe")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)
    print(f"DATA_DIR={settings.data_dir}")
    print(f"BASE_DIR={BASE_DIR}")

    # Pre-flight: clear bus
    try:
        get_event_bus().clear()
    except Exception:
        pass

    loop = None
    temp_dir = None
    try:
        loop, temp_dir = build_test_loop()
        _stamp("HARNESS.built", temp_dir=str(temp_dir))

        refs = attach_spies(loop)
        _stamp("HARNESS.spies_attached",
               has_subscriber=refs.get("subscriber") is not None,
               has_store=refs.get("store") is not None,
               has_task_scheduler=refs.get("task_scheduler") is not None)

        # === TRACK A: PLAYER_INSULTS ===
        SPY_LOG.clear()
        track_a_insult(loop, target_id="maid_lusya")

        # Verify belief
        belief_a = check_belief(loop, "maid_lusya")
        _stamp("A.FINAL.belief", **belief_a)

        # === TRACK B: idle_tick ===
        SPY_LOG_b_start = len(SPY_LOG)
        b_result = track_b_idle(loop, campaign_id="Open_road")
        _stamp("B.FINAL.summary", **b_result)

        # === TRACK A persistence check ===
        # Запишем финальное состояние в scene_state, сохраним, перезагрузим
        # (commit_tick_result в idle_tick уже должен был это сделать)
        belief_a_after_idle = check_belief(loop, "maid_lusya")
        _stamp("A.PERSISTENCE.belief_after_idle", **belief_a_after_idle)

        # === REPORT ===
        print("\n" + "=" * 78)
        print("FORENSIC REPORT — Step 2.3")
        print("=" * 78)
        print(f"\nTotal SPY entries: {len(SPY_LOG)}")
        tags_seen = sorted({e["tag"] for e in SPY_LOG})
        print(f"\nAll tags:\n  " + "\n  ".join(tags_seen))
        print(f"\nTrack A belief (maid_lusya): {belief_a}")
        print(f"\nTrack A belief (after idle): {belief_a_after_idle}")
        print(f"\nTrack B summary: {b_result}")

        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        if loop is not None and temp_dir is not None:
            cleanup(loop, temp_dir)


if __name__ == "__main__":
    sys.exit(main())
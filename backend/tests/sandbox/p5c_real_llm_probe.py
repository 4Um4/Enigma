# backend/tests/sandbox/p5c_real_llm_probe.py
"""
P5-C — REAL LLM VERIFICATION.
Цель: доказать полный production-путь от PLAYER_INSULTS до NPC_SPOKE через real LLM.
Без mock. Production harness + real LlamaCppProvider (port 8181).
Wrapper spies на 10 точках наблюдения (ТЗ §6).
"""
from __future__ import annotations
import os, sys, json, shutil, sqlite3, tempfile, time, traceback, threading
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import settings, BASE_DIR
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.domain.epistemology import Proposition, Predicate
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.decision_hub import DecisionHub
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.execution.dialogue_executor import DialogueExecutor
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.llm.llama_cpp_provider import LlamaCppProvider
from app.services.phases.post_decision import run_phase_6_post_decision

SPY_LOG: List[Dict[str, Any]] = []
NPC_SPOKE_EVENTS: List[Any] = []  # captured NPC_SPOKE events

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

def _safe_repr(obj: Any, max_len: int = 300) -> str:
    try:
        s = repr(obj)
        return s[:max_len] + ("..." if len(s) > max_len else "")
    except Exception as e:
        return f"<repr error: {e}>"

# === Build production loop WITHOUT mock LLM router ===
def build_test_loop(data_dir: Path, saves_dir: Path) -> Any:
    """Production loop. NO mock — real LlamaCppProvider through TaskScheduler."""
    settings.saves_dir = str(saves_dir)
    settings.environment = "development"
    # NOT mocking LLM — using real router via initialize_router() which build_game_loop calls
    loop = build_game_loop(data_dir=data_dir)
    return loop

def cleanup_loop(loop: Any) -> None:
    try:
        if hasattr(loop, "_task_scheduler"):
            ts = loop._task_scheduler
            if hasattr(ts, "_executor_pool"):
                try: ts._executor_pool.shutdown(wait=False, cancel_futures=True)
                except Exception: pass
    except Exception: pass

def init_scene(loop: Any) -> Dict[str, Any]:
    scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
    if scene is None:
        scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
    return scene or {}

# === Spies on 10 observation points ===
def attach_spies(loop: Any) -> Dict[str, Any]:
    refs: Dict[str, Any] = {}

    # Spy point 1: DecisionHub.compute (class-level) — capture chosen intent for guard_borko
    orig_compute = DecisionHub.compute
    def _spy_compute(self_dh, *args, **kwargs):
        state_arg = args[0] if args else kwargs.get("state", None)
        npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
        if npc_id == "guard_borko":
            ep_ctx = kwargs.get("epistemic_context", None)
            _stamp("1.DH.compute:ENTER guard_borko",
                   has_epistemic_ctx=ep_ctx is not None,
                   report_prop=(ep_ctx.report_proposition.to_dict()
                                if ep_ctx and ep_ctx.report_proposition else None))
        result = orig_compute(self_dh, *args, **kwargs)
        if npc_id == "guard_borko":
            dec = getattr(result, "decision", None)
            comm = getattr(result, "communication", None)
            dec_summary = {}
            if dec is not None:
                dec_summary = {
                    "intent": str(getattr(dec, "intent", "?")),
                    "intent_target": getattr(dec, "intent_target", None),
                    "score": getattr(dec, "score", None),
                    "scores_trace_top3": sorted(getattr(dec, "scores_trace", {}).items(),
                                                key=lambda x: -x[1])[:3] if hasattr(dec, "scores_trace") else []
                }
            comm_summary = None
            if comm is not None:
                comm_summary = {
                    "speaker": getattr(comm, "speaker", "?"),
                    "intent_type": getattr(comm, "intent_type", "?"),
                    "target_id": getattr(comm, "target_id", None),
                    "topic": getattr(comm, "topic", "?")[:80] if getattr(comm, "topic", None) else None,
                    "has_proposition": getattr(comm, "proposition", None) is not None,
                    "proposition": (comm.proposition.to_dict()
                                    if getattr(comm, "proposition", None) is not None else None)
                }
            _stamp("1.DH.compute:EXIT guard_borko",
                   decision=dec_summary, communication=comm_summary)
        return result
    DecisionHub.compute = _spy_compute  # type: ignore

    # Spy point 2: CommunicationIntent creation — capture via npc_tick_pipeline (post_decision)
    orig_pd6 = run_phase_6_post_decision
    def _spy_pd6(ctx, orch):
        pre_count = len(getattr(ctx, "communication_intents", []) or [])
        comm_list = []
        for c in (getattr(ctx, "communication_intents", []) or []):
            comm_list.append({
                "speaker": getattr(c, "speaker", "?"),
                "intent_type": getattr(c, "intent_type", "?"),
                "target_id": getattr(c, "target_id", None),
                "has_proposition": getattr(c, "proposition", None) is not None,
            })
        _stamp("2.PD6.phase_6:ENTER",
               pre_communication_intents=pre_count, intents=comm_list)
        result = orig_pd6(ctx, orch)
        pending = ctx.scene_state.get("pending_tasks", []) if hasattr(ctx, "scene_state") else []
        _stamp("2.PD6.phase_6:EXIT",
               post_communication_intents=len(getattr(ctx, "communication_intents", []) or []),
               pending_tasks_count=len(pending))
        return result
    import app.services.phases.post_decision as pd_mod
    pd_mod.run_phase_6_post_decision = _spy_pd6  # type: ignore

    # Spy point 3: QueuedTask creation — wrap scene_state["pending_tasks"].append via TaskScheduler
    # We can't easily wrap list append, so we'll capture pending_tasks state after post_decision
    # (covered by 2.PD6.phase_6:EXIT)

    # Spy point 4: TaskScheduler.execute_pending
    try:
        ts = loop._get_task_scheduler()  # noqa
        refs["ts"] = ts
        orig_ep = ts.execute_pending
        def _spy_ep(scene_state, campaign_id):
            pre = len(scene_state.get("pending_tasks", []) or [])
            pre_tasks = [{"task_id": t.get("task_id"),
                          "owner_id": t.get("owner_id"),
                          "kind": t.get("kind"),
                          "payload_intent": (t.get("payload") or {}).get("intent_type")}
                         for t in (scene_state.get("pending_tasks", []) or [])]
            _stamp("4.TS.execute_pending:ENTER",
                   campaign=campaign_id, pre_pending=pre, pre_tasks=pre_tasks)
            result = orig_ep(scene_state, campaign_id)
            post = len(scene_state.get("pending_tasks", []) or [])
            _stamp("4.TS.execute_pending:EXIT", post_pending=post)
            return result
        ts.execute_pending = _spy_ep  # type: ignore

        # Spy point 5: DialogueExecutor.execute (instance wrap)
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "execute"):
                orig_exe = ex.execute
                def _make_spy(orig_exe, kind_name):
                    def _spy_exe(task):
                        req = getattr(task, "payload", None)
                        _stamp("5.DE.execute:ENTER",
                               kind=str(kind_name),
                               owner=getattr(task, "owner_id", "?"),
                               target_ids=getattr(task, "target_ids", []),
                               task_id=getattr(task, "task_id", "?"),
                               req_intent_type=getattr(req, "intent_type", "?"),
                               req_target_id=getattr(req, "target_id", "?"),
                               req_topic=getattr(req, "topic", "?")[:80] if getattr(req, "topic", None) else None,
                               req_has_proposition=getattr(req, "proposition", None) is not None)
                        results = []
                        try:
                            for art in orig_exe(task):
                                results.append(art)
                                _stamp("5.DE.execute:ARTIFACT",
                                       kind=str(kind_name),
                                       success=getattr(art, "success", "?"),
                                       result_type=getattr(art, "result_type", "?"),
                                       error_message=getattr(art, "error_message", None),
                                       data_preview=str(getattr(art, "data", {}))[:300])
                        except Exception as e:
                            _stamp("5.DE.execute:ERROR",
                                   error=type(e).__name__, msg=str(e)[:300])
                            raise
                        _stamp("5.DE.execute:EXIT",
                               kind=str(kind_name), results_count=len(results))
                        return iter(results)
                    return _spy_exe
                ex.execute = _make_spy(orig_exe, kind)  # type: ignore
    except Exception as e:
        _stamp("ATTACH.ts", error=str(e)[:200])

    # Spy point 6: LlamaCppProvider.complete (class-level wrap)
    orig_complete = LlamaCppProvider.complete
    def _spy_complete(self_prov, *args, **kwargs):
        prompt = args[0] if args else kwargs.get("prompt", "?")
        prompt_preview = str(prompt)[:300] if prompt else "?"
        _stamp("6.LLM.complete:ENTER",
               server_url=getattr(self_prov, "server_url", "?"),
               model_path=getattr(self_prov, "model_path", "?"),
               prompt_preview=prompt_preview,
               prompt_len=len(str(prompt)) if prompt else 0)
        t0 = time.time()
        try:
            result = orig_complete(self_prov, *args, **kwargs)
            latency = time.time() - t0
            _stamp("6.LLM.complete:EXIT",
                   latency_sec=round(latency, 2),
                   result_type=type(result).__name__,
                   result_preview=str(result)[:500] if result else "(empty)")
            return result
        except Exception as e:
            latency = time.time() - t0
            _stamp("6.LLM.complete:ERROR",
                   latency_sec=round(latency, 2),
                   error=type(e).__name__, msg=str(e)[:300])
            raise
    LlamaCppProvider.complete = _spy_complete  # type: ignore

    # Spy point 8: DialogueMaterializer.materialize (class-level wrap)
    orig_mat = DialogueMaterializer.materialize
    def _spy_materialize(self_mat, artifact):
        _stamp("8.DM.materialize:ENTER",
               artifact_success=getattr(artifact, "success", "?"),
               artifact_result_type=getattr(artifact, "result_type", "?"),
               artifact_data_preview=str(getattr(artifact, "data", {}))[:300])
        results = list(orig_mat(self_mat, artifact))
        _stamp("8.DM.materialize:EXIT",
               results_count=len(results),
               results_types=[type(r).__name__ for r in results])
        for r in results:
            _stamp("8.DM.materialize:RESULT",
                   type=type(r).__name__,
                   repr=_safe_repr(r, 400))
        return iter(results)
    DialogueMaterializer.materialize = _spy_materialize  # type: ignore

    # Spy point 9: EventBus.publish — capture NPC_SPOKE publications
    bus = get_event_bus()
    orig_pub = bus.publish
    def _spy_pub(evt):
        et = str(getattr(evt, "type", "?"))
        if "spoke" in et.lower():
            captured = {
                "event_type": et,
                "source": getattr(evt, "source", "?"),
                "target_id": (getattr(evt, "payload", {}) or {}).get("target_id"),
                "intent_type": (getattr(evt, "payload", {}) or {}).get("intent_type"),
                "text": (getattr(evt, "payload", {}) or {}).get("text", "")[:300] if isinstance((getattr(evt, "payload", {}) or {}).get("text"), str) else None,
                "has_proposition": "proposition" in ((getattr(evt, "payload", {}) or {})),
                "payload_keys": sorted(list((getattr(evt, "payload", {}) or {}).keys()))
            }
            NPC_SPOKE_EVENTS.append(captured)
            _stamp("9.BUS.publish:NPC_SPOKE", **captured)
        return orig_pub(evt)
    bus.publish = _spy_pub  # type: ignore
    refs["bus"] = bus

    # Spy point 10: NPC_SPOKE subscribers — wrap ClaimEventSubscriber.on_npc_spoke
    sub = getattr(loop, "_claim_event_subscriber", None)
    refs["sub"] = sub
    if sub is not None and hasattr(sub, "on_npc_spoke"):
        orig_on_npc = sub.on_npc_spoke
        def _spy_on_npc(event):
            _stamp("10.SUB.on_npc_spoke:ENTER",
                   event_type=str(getattr(event, "type", "?")),
                   source=getattr(event, "source", "?"),
                   target_id=(getattr(event, "payload", {}) or {}).get("target_id"))
            return orig_on_npc(event)
        sub.on_npc_spoke = _spy_on_npc  # type: ignore

    return refs

def publish_insult(target_id: str = "maid_lusya"):
    payload = {
        "action_type": "player_insults",
        "target_id": target_id,
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
    _stamp("0.EVENT.publish:PLAYER_INSULTS", event_id=str(evt.id), target_id=target_id)
    get_event_bus().publish(evt)

def snapshot_belief(loop: Any, agent_id: str) -> Dict[str, Any]:
    orch = getattr(loop, "_tick_orch", None)
    orch_store = getattr(orch, "_epistemic_store", None) if orch else None
    if orch_store is None:
        return {"error": "no orch store"}
    records = orch_store.get_all_for_agent(agent_id)
    return {
        "agent_id": agent_id,
        "records_count": len(records),
        "records": [{
            "agent_id": r.agent_id,
            "proposition": r.proposition.to_dict(),
            "confidence": r.confidence,
            "source_id": r.source_id,
            "source_claim_id": r.source_claim_id,
            "source_type": r.source_type,
            "original_source_id": r.original_source_id,
        } for r in records]
    }

def run_scenario(label: str, with_insult: bool, real_data_dir: Path, saves_dir: Path) -> Tuple[List[Dict[str, Any]], List[Any]]:
    print(f"\n{'#' * 78}\n# SCENARIO {label}: {'WITH' if with_insult else 'NO'} PLAYER_INSULTS\n# saves_dir={saves_dir}\n{'#' * 78}")
    SPY_LOG.clear()
    NPC_SPOKE_EVENTS.clear()
    try: get_event_bus().clear()
    except Exception: pass

    _stamp(f"{label}.STARTUP", saves_dir=str(saves_dir))
    loop = build_test_loop(real_data_dir, saves_dir)
    init_scene(loop)
    attach_spies(loop)
    _stamp(f"{label}.PRE_belief", belief=snapshot_belief(loop, "maid_lusya"))

    if with_insult:
        publish_insult("maid_lusya")
        _stamp(f"{label}.POST_INSULT_belief", belief=snapshot_belief(loop, "maid_lusya"))

    _stamp(f"{label}.IDLE_TICK_START")
    try:
        result = loop.idle_tick("Open_road")
        _stamp(f"{label}.IDLE_TICK_EXIT",
               status=result.get("status", "?") if isinstance(result, dict) else type(result).__name__)
    except Exception as e:
        _stamp(f"{label}.IDLE_TICK_ERROR", error=type(e).__name__, msg=str(e)[:400])
        traceback.print_exc()
        cleanup_loop(loop)
        return list(SPY_LOG), list(NPC_SPOKE_EVENTS)

    # Wait for async dialogue tasks (executor pool may run them async)
    _stamp(f"{label}.WAIT_ASYNC", reason="executor pool may be async")
    time.sleep(15)  # give LLM time to respond

    _stamp(f"{label}.POST_IDLE_belief", belief=snapshot_belief(loop, "maid_lusya"))
    _stamp(f"{label}.NPC_SPOKE_CAPTURED", count=len(NPC_SPOKE_EVENTS), events=list(NPC_SPOKE_EVENTS))

    cleanup_loop(loop)
    del loop
    import gc; gc.collect()
    return list(SPY_LOG), list(NPC_SPOKE_EVENTS)

def main() -> int:
    print("\n" + "=" * 78)
    print("P5-C — REAL LLM VERIFICATION")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)
    print(f"DATA_DIR={settings.data_dir}")
    print(f"llama_cpp_server_url={settings.llama_cpp_server_url}")
    print(f"llama_cpp_model_path={settings.llama_cpp_model_path}")

    # Pre-flight: verify LLM-host still alive
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"{settings.llama_cpp_server_url}/health", timeout=5) as r:
            print(f"[PRE-FLIGHT] /health OK: {r.status}, body={r.read().decode()[:200]}")
    except Exception as e:
        print(f"[PRE-FLIGHT] /health FAILED: {e}")
        print("[PRE-FLIGHT] Trying ensure_llm()...")
        try:
            from app.services.llm.runtime.client import ensure_llm
            url = ensure_llm(label="p5c_probe")
            print(f"[PRE-FLIGHT] ensure_llm returned: {url}")
            with opener.open(f"{url}/health", timeout=5) as r:
                print(f"[PRE-FLIGHT] /health OK after ensure: {r.status}")
        except Exception as e2:
            print(f"[PRE-FLIGHT] ensure_llm FAILED: {e2}")
            print("[BLOCKED] LLM-host unavailable")
            return 2

    real_data_dir = Path(settings.data_dir)
    saves_a = Path(tempfile.mkdtemp(prefix="p5c_saves_A_"))
    saves_b = Path(tempfile.mkdtemp(prefix="p5c_saves_B_"))

    try:
        spy_a, spoke_a = run_scenario("A", with_insult=True, real_data_dir=real_data_dir, saves_dir=saves_a)
        spy_b, spoke_b = run_scenario("B", with_insult=False, real_data_dir=real_data_dir, saves_dir=saves_b)

        print("\n" + "=" * 78)
        print("FORENSIC REPORT — P5-C")
        print("=" * 78)
        print("\n--- SCENARIO A (with PLAYER_INSULTS, real LLM) ---")
        print(f"SPY entries: {len(spy_a)}")
        for e in spy_a:
            print(f"  {e}")
        print(f"\nNPC_SPOKE captured (A): {len(spoke_a)}")
        for e in spoke_a:
            print(f"  {e}")

        print("\n--- SCENARIO B (control, no PLAYER_INSULTS, real LLM) ---")
        print(f"SPY entries: {len(spy_b)}")
        for e in spy_b:
            print(f"  {e}")
        print(f"\nNPC_SPOKE captured (B): {len(spoke_b)}")
        for e in spoke_b:
            print(f"  {e}")

        print("\n--- A/B COMPARISON ---")
        print(f"A: spy_entries={len(spy_a)}, npc_spoke={len(spoke_a)}")
        print(f"B: spy_entries={len(spy_b)}, npc_spoke={len(spoke_b)}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        for d in [saves_a, saves_b]:
            try: shutil.rmtree(d, ignore_errors=True)
            except Exception: pass

if __name__ == "__main__":
    sys.exit(main())
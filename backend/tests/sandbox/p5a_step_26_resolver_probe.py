# backend/tests/sandbox/p5a_step_26_resolver_probe.py
"""
P5-A Step 2.6 — Resolver Forensics.
Wrap EpistemicContextResolver.resolve + to_modifiers + DecisionHub.compute.
Цель: установить точный путь от записи в EpistemicStore до полей EpistemicContext
       и почему claim не становится threat.
"""
from __future__ import annotations
import os, sys, json, shutil, tempfile, traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple
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
from app.domain.epistemology import Proposition, Predicate, EpistemicContext
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.decision_hub import DecisionHub
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver

SPY_LOG: List[Dict[str, Any]] = []

def _stamp(tag: str, **kw: Any) -> None:
    SPY_LOG.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

def build_test_loop() -> Tuple[Any, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="p26_probe_"))
    real_data_dir = Path(settings.data_dir)
    settings.saves_dir = str(temp_dir)
    settings.environment = "development"
    loop = build_game_loop(data_dir=real_data_dir)
    try:
        ts = loop._get_task_scheduler()  # noqa
        for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
            if hasattr(ex, "_router"):
                ex._router = MagicMock()
                if hasattr(ex._router, "route"):
                    ex._router.route.return_value = "[Test LLM Mock]"
    except Exception as e:
        _stamp("HARNESS.mock_llm", status="FAILED", error=str(e)[:200])
    return loop, temp_dir

def cleanup(loop: Any, temp_dir: Path) -> None:
    try:
        if hasattr(loop, "_task_scheduler"):
            ts = loop._task_scheduler
            if hasattr(ts, "_executor_pool"):
                try: ts._executor_pool.shutdown(wait=False, cancel_futures=True)
                except Exception: pass
    except Exception: pass
    shutil.rmtree(temp_dir, ignore_errors=True)

def init_scene(loop: Any, campaign_id: str = "Open_road", location: str = "tavern") -> Dict[str, Any]:
    scene = loop.scene_manager.get_scene_state(campaign_id, location)
    if scene is None:
        scene = loop.scene_manager.initialize_scene(campaign_id, location, "12:00")
    return scene

# === Spy on EpistemicContextResolver.resolve + to_modifiers ===
def patch_resolver(loop: Any):
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is None:
        _stamp("PATCH.resolver", error="no subscriber")
        return None
    store = getattr(sub, "_store", None)
    # Resolver injected into loop._tick_orch
    orch = getattr(loop, "_tick_orch", None)
    resolver = getattr(orch, "_epistemic_context_resolver", None) if orch else None
    if resolver is None:
        # game_loop.py:608 creates resolver, but maybe stored differently
        # Try to find via attribute search
        for attr in dir(orch) if orch else []:
            if "resolver" in attr.lower():
                v = getattr(orch, attr, None)
                if isinstance(v, EpistemicContextResolver):
                    resolver = v
                    break
    if resolver is None:
        _stamp("PATCH.resolver", error="resolver not found on orchestrator")
        return None
    _stamp("PATCH.resolver", found=True, resolver_type=type(resolver).__name__,
           store_id=id(getattr(resolver, "_store", None)),
           sub_store_id=id(store))

    # Wrap resolve
    orig_resolve = resolver.resolve
    def _spy_resolve(agent_id: str):
        # PRE: what's in store for this agent
        all_recs = []
        try:
            for r in store.get_all_for_agent(agent_id):
                all_recs.append({
                    "subject": r.proposition.subject_id,
                    "predicate": r.proposition.predicate.value,
                    "object": r.proposition.object_id,
                    "polarity": r.proposition.polarity,
                    "confidence": r.confidence,
                    "source": r.source_id,
                })
        except Exception as e:
            all_recs = [{"error": str(e)[:100]}]
        _stamp(f"RES.resolve:PRE agent={agent_id}", store_records=all_recs)

        result = orig_resolve(agent_id)

        # POST: what fields are populated
        rec_summary = {
            "agent_id": result.agent_id,
            "perceived_threats": list(result.perceived_threats),
            "perceived_allies": list(result.perceived_allies),
            "perceived_violations": result.perceived_violations,
            "max_confidence": result.max_confidence,
            "trigger_proposition": (result.trigger_proposition.to_dict()
                                     if result.trigger_proposition else None),
            "claims_about_self": [p.to_dict() for p in result.claims_about_self],
            "max_self_confidence": result.max_self_confidence,
            "report_proposition": (result.report_proposition.to_dict()
                                    if result.report_proposition else None),
        }
        _stamp(f"RES.resolve:POST agent={agent_id}", context=rec_summary)
        return result
    resolver.resolve = _spy_resolve  # type: ignore

    # Wrap to_modifiers (staticmethod, but accessible via instance)
    orig_mods = resolver.to_modifiers
    def _spy_mods(context, archetype=""):
        mods = orig_mods(context, archetype)
        if context.agent_id in ("maid_lusya", "guard_borko"):
            _stamp(f"RES.to_modifiers agent={context.agent_id}",
                   archetype=archetype,
                   perceived_threats=list(context.perceived_threats),
                   claims_about_self=[p.to_dict() for p in context.claims_about_self],
                   report_proposition=(context.report_proposition.to_dict()
                                        if context.report_proposition else None),
                   modifiers=mods)
        return mods
    resolver.to_modifiers = _spy_mods  # type: ignore
    return resolver

# === Spy on DecisionHub.compute — capture full AgentAction ===
def patch_decision_hub():
    orig_compute = DecisionHub.compute
    def _spy_compute(self_dh, *args, **kwargs):
        state_arg = args[0] if args else kwargs.get("state", None)
        npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
        ep_ctx = kwargs.get("epistemic_context", None)
        epistemic_mods = kwargs.get("epistemic_modifiers", None)

        if npc_id in ("maid_lusya", "guard_borko", "merchant_goran", "blacksmith_orm"):
            _stamp(f"DH.compute:ENTER npc={npc_id}",
                   epistemic_mods=epistemic_mods,
                   has_epistemic_ctx=ep_ctx is not None,
                   trigger_prop=(ep_ctx.trigger_proposition.to_dict()
                                  if ep_ctx and ep_ctx.trigger_proposition else None),
                   report_prop=(ep_ctx.report_proposition.to_dict()
                                 if ep_ctx and ep_ctx.report_proposition else None),
                   claims_self=[p.to_dict() for p in ep_ctx.claims_about_self]
                                if ep_ctx else [])

        result = orig_compute(self_dh, *args, **kwargs)

        if npc_id in ("maid_lusya", "guard_borko", "merchant_goran", "blacksmith_orm"):
            # AgentAction has .decision (DecisionResult) and .communication (Optional[CommunicationIntent])
            dec = getattr(result, "decision", None)
            comm = getattr(result, "communication", None)
            dec_summary = {}
            if dec is not None:
                dec_summary = {
                    "intent": str(getattr(dec, "intent", "?")),
                    "intent_target": getattr(dec, "intent_target", None),
                    "score": getattr(dec, "score", None),
                    "scores_trace": dict(getattr(dec, "scores_trace", {}) or {}),
                    "narrative_fact": getattr(dec, "narrative_fact", None),
                }
            comm_summary = None
            if comm is not None:
                comm_summary = {
                    "speaker": getattr(comm, "speaker", "?"),
                    "intent_type": getattr(comm, "intent_type", "?"),
                    "target_id": getattr(comm, "target_id", None),
                    "audience": getattr(comm, "audience", "?"),
                    "topic": getattr(comm, "topic", "?")[:80] if getattr(comm, "topic", None) else None,
                    "has_proposition": getattr(comm, "proposition", None) is not None,
                }
            _stamp(f"DH.compute:EXIT npc={npc_id}",
                   decision=dec_summary,
                   communication=comm_summary)
        return result
    DecisionHub.compute = _spy_compute  # type: ignore

def attach_spies(loop: Any):
    sub = getattr(loop, "_claim_event_subscriber", None)
    if sub is not None:
        # Wrap on_claim_event for trace
        orig_oc = sub.on_claim_event
        def _spy_oc(event):
            _stamp("A3.on_claim_event:ENTER",
                   event_type=str(getattr(event, "type", "?")),
                   target_id=(getattr(event, "payload", {}) or {}).get("target_id"))
            return orig_oc(event)
        sub.on_claim_event = _spy_oc  # type: ignore

    # Wrap bus.publish for NPC_SPOKE + all events
    bus = get_event_bus()
    orig_pub = bus.publish
    def _spy_pub(evt):
        et = str(getattr(evt, "type", "?"))
        if "spoke" in et.lower() or "claim" in et.lower() or "insult" in et.lower():
            _stamp("BUS.publish",
                   event_type=et,
                   source=getattr(evt, "source", "?"),
                   target_id=(getattr(evt, "payload", {}) or {}).get("target_id"),
                   intent_type=(getattr(evt, "payload", {}) or {}).get("intent_type"))
        return orig_pub(evt)
    bus.publish = _spy_pub  # type: ignore

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
    _stamp("A1.publish", event_id=str(evt.id), target_id=target_id)
    get_event_bus().publish(evt)

def run_scenario(label: str, loop: Any, with_insult: bool):
    print(f"\n{'#' * 78}\n# SCENARIO {label}: {'WITH' if with_insult else 'NO'} PLAYER_INSULTS\n{'#' * 78}")
    SPY_LOG.clear()
    init_scene(loop, "Open_road", "tavern")
    patch_resolver(loop)
    patch_decision_hub()
    attach_spies(loop)
    _stamp(f"{label}.scene_init_done")
    if with_insult:
        publish_insult("maid_lusya")
        _stamp(f"{label}.post_insult")
    _stamp(f"{label}.idle_tick:START")
    try:
        result = loop.idle_tick("Open_road")
        _stamp(f"{label}.idle_tick:EXIT",
               status=result.get("status", "?") if isinstance(result, dict) else type(result).__name__)
    except Exception as e:
        _stamp(f"{label}.idle_tick:ERROR", error=type(e).__name__, msg=str(e)[:300])
    return list(SPY_LOG)

def main() -> int:
    print("\n" + "=" * 78)
    print("P5-A Step 2.6 — Resolver Forensics")
    print("Baseline: 72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2")
    print("=" * 78)

    try: get_event_bus().clear()
    except Exception: pass

    loop = None
    temp_dir = None
    try:
        loop, temp_dir = build_test_loop()
        _stamp("HARNESS.built", temp_dir=str(temp_dir))

        spy_a = run_scenario("A", loop, with_insult=True)
        # Rebuild loop for fresh state
        try: cleanup(loop, temp_dir)
        except Exception: pass
        loop, temp_dir = build_test_loop()
        spy_b = run_scenario("B", loop, with_insult=False)

        print("\n" + "=" * 78)
        print("FORENSIC REPORT — Step 2.6")
        print("=" * 78)
        print("\n--- SCENARIO A (with PLAYER_INSULTS) ---")
        for e in spy_a:
            print(f"  {e}")
        print("\n--- SCENARIO B (without PLAYER_INSULTS) ---")
        for e in spy_b:
            print(f"  {e}")
        return 0
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        if loop is not None and temp_dir is not None:
            try: cleanup(loop, temp_dir)
            except Exception: pass

if __name__ == "__main__":
    sys.exit(main())
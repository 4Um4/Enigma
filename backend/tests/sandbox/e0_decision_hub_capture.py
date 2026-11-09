"""path: /project/backend/tests/sandbox/e0_decision_hub_capture.py
Purpose: E0-PILOT-4 — class-level capture of DecisionHub.compute + phase 5 trace.
         Answers: is compute() called? TALK in candidates? WORLD_TICK events? Why TALK loses?
Dependencies: tests/gameplay/harness.py, app.services.llm.runtime.client, app.services.npc.decision_hub
Output: reports/experiments/e0_pilot_4/{run_log.txt, report.md, summary.json}
SAFETY: Class-level wrapper on DecisionHub.compute (reversible). Instance wrapper on _phase_5_decision (reversible).
        Both call original with same args, return original result, do not catch exceptions.
"""
import json, sys, inspect, traceback
from pathlib import Path
from datetime import datetime

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.llm.runtime.client import ensure_llm, release_lease

PAIR = ["maid_lusya", "tavern_keeper_tornin"]
N_TICKS = 5
SPEAK_RADIUS = 5.0
RUN_ID = "e0_pilot_4"
OUT = Path("reports/experiments") / RUN_ID
OUT.mkdir(parents=True, exist_ok=True)
LOG_PATH = OUT / "run_log.txt"


def safe_str(v, maxlen=80):
    try:
        s = str(v)
        return s[:maxlen] if len(s) > maxlen else s
    except Exception:
        return "<unstr>"

def safe_float(v):
    try:
        return round(float(v), 4)
    except Exception:
        return safe_str(v, 40)

def extract_dict_safe(obj, max_items=15):
    """Extract readable dict from object (dict, or object with __dict__)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): (safe_float(v) if isinstance(v, (int, float)) else safe_str(v, 50))
                for k, v in list(obj.items())[:max_items]}
    try:
        vd = vars(obj)
        if vd:
            return {str(k): (safe_float(v) if isinstance(v, (int, float)) else safe_str(v, 50))
                    for k, v in list(vd.items())[:max_items]}
    except TypeError:
        pass
    return safe_str(obj, 200)

def extract_state_brief(state):
    if state is None:
        return {"_error": "None"}
    r = {"type": type(state).__name__, "npc_id": getattr(state, "npc_id", "?")}
    r["is_alive"] = getattr(state, "is_alive", True)
    r["stress"] = getattr(state, "stress", None)
    r["will_state"] = safe_str(getattr(state, "will_state", "?"), 30)
    r["consciousness"] = getattr(state, "consciousness", None)
    dr = getattr(state, "drives_runtime", None) or getattr(state, "drives", None)
    if isinstance(dr, dict):
        r["drives_runtime"] = {k: safe_float(v) for k, v in list(dr.items())[:8]}
    elif dr is not None:
        r["drives_runtime"] = safe_str(dr, 150)
    else:
        r["drives_runtime"] = None
    # relationship_cache
    rel = getattr(state, "relationship_cache", None)
    if isinstance(rel, dict):
        r["rel_cache_count"] = len(rel)
        r["rel_cache_keys"] = list(rel.keys())[:5]
    else:
        r["rel_cache_count"] = 0
    return r

def extract_personality_brief(p):
    if p is None:
        return {"_error": "None"}
    r = {"type": type(p).__name__, "id": getattr(p, "id", "?")}
    db = getattr(p, "drives_base", None)
    if isinstance(db, dict):
        r["drives_base"] = {k: safe_float(v) for k, v in list(db.items())[:8]}
    elif db is not None:
        r["drives_base"] = safe_str(db, 150)
    pb = getattr(p, "psyche_base", None)
    if pb is not None:
        r["psyche_base"] = {
            "willpower": getattr(pb, "willpower", None),
            "breakpoint": getattr(pb, "breakpoint", None),
        }
    r["voice_profile"] = safe_str(getattr(p, "voice_profile", ""), 30)
    return r

def extract_event_brief(event):
    if event is None:
        return {"_error": "None"}
    r = {"type": type(event).__name__}
    et = getattr(event, "event_type", getattr(event, "type", None))
    r["event_type"] = safe_str(et, 40)
    r["reason"] = safe_str(getattr(event, "reason", ""), 40)
    r["actor_id"] = safe_str(getattr(event, "actor_id", ""), 20)
    r["target_id"] = safe_str(getattr(event, "target_id", ""), 20)
    r["tick"] = getattr(event, "tick", None)
    # WORLD_TICK detection
    et_str = str(et).upper() if et else ""
    r["is_world_tick"] = "WORLD_TICK" in et_str
    # All attrs
    r["all_attrs"] = extract_dict_safe(event, 10)
    return r

def extract_result_brief(result):
    if result is None:
        return {"_error": "None"}
    r = {"type": type(result).__name__}
    r["winner"] = safe_str(getattr(result, "intent", "?"), 30)
    r["score"] = safe_float(getattr(result, "score", 0))
    st = getattr(result, "scores_trace", None)
    r["scores_trace"] = extract_dict_safe(st, 20)
    # Check TALK in scores_trace
    talk_found = False
    talk_score = None
    if isinstance(r["scores_trace"], dict):
        for k, v in r["scores_trace"].items():
            if "talk" in str(k).lower():
                talk_found = True
                talk_score = v
    elif isinstance(r["scores_trace"], str):
        talk_found = "talk" in r["scores_trace"].lower()
    r["talk_in_candidates"] = talk_found
    r["talk_score"] = talk_score
    return r


# === DecisionHub class-level wrapper ===
DH_CALLS = []
DH_ORIGINAL = None

def install_dh_wrapper():
    global DH_ORIGINAL
    from app.services.npc.decision_hub import DecisionHub
    DH_ORIGINAL = DecisionHub.compute
    
    def wrapped_compute(self, *args, **kwargs):
        call_num = len(DH_CALLS) + 1
        state = args[0] if args else kwargs.get("state")
        personality = args[1] if len(args) > 1 else kwargs.get("personality")
        event = args[2] if len(args) > 2 else kwargs.get("event")
        
        entry = {
            "call_num": call_num,
            "timestamp": datetime.now().isoformat(),
            "self_type": type(self).__name__,
            "state": extract_state_brief(state),
            "personality": extract_personality_brief(personality),
            "event": extract_event_brief(event),
        }
        
        # Call original — same args, same kwargs, same self
        result = DH_ORIGINAL(self, *args, **kwargs)
        
        # Capture result — read-only
        entry["result"] = extract_result_brief(result)
        DH_CALLS.append(entry)
        
        # Return original result — unchanged
        return result
    
    DecisionHub.compute = wrapped_compute
    return DecisionHub

def restore_dh_wrapper():
    global DH_ORIGINAL
    if DH_ORIGINAL is not None:
        from app.services.npc.decision_hub import DecisionHub
        DecisionHub.compute = DH_ORIGINAL
        DH_ORIGINAL = None


# === _phase_5_decision instance wrapper ===
PHASE5_LOG = []

def install_phase5_wrapper(tick_orch):
    original = tick_orch._phase_5_decision
    
    def wrapped_phase5(*args, **kwargs):
        entry = {
            "call_num": len(PHASE5_LOG) + 1,
            "timestamp": datetime.now().isoformat(),
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()),
        }
        PHASE5_LOG.append(entry)
        try:
            result = original(*args, **kwargs)
            entry["returned"] = True
            entry["result_type"] = type(result).__name__ if result else "None"
            return result
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            raise
    
    tick_orch._phase_5_decision = wrapped_phase5
    return original

def restore_phase5_wrapper(tick_orch, original):
    if original is not None:
        tick_orch._phase_5_decision = original


def get_npc_states_via_snapshot(gl, cid):
    """Try _resolve_npcs_snapshot and _resolve_npcs_light_snapshot."""
    for method_name in ["_resolve_npcs_snapshot", "_resolve_npcs_light_snapshot"]:
        fn = getattr(gl, method_name, None)
        if fn is None:
            continue
        try:
            try:
                sig = inspect.signature(fn)
                params = list(sig.parameters.keys())
            except (ValueError, TypeError):
                params = ["?"]
            
            # Try different call signatures
            result = None
            for call_args in [(cid,), (cid, "tavern"), ()]:
                try:
                    result = fn(*call_args)
                    break
                except TypeError:
                    continue
            
            if result is None:
                continue
            
            states = {}
            if isinstance(result, dict):
                for nid in PAIR:
                    item = result.get(nid)
                    if item is not None:
                        states[nid] = item
            elif isinstance(result, list):
                for item in result:
                    nid = getattr(item, "npc_id", None)
                    if nid is None and isinstance(item, dict):
                        nid = item.get("id") or item.get("npc_id")
                    if nid in PAIR:
                        states[nid] = item
            
            return states, method_name, params
        except Exception as e:
            continue
    return {}, "none", []


def get_relationships_via_rel_store(gl, cid):
    """Read relationship data via gl._rel_store."""
    rs = getattr(gl, "_rel_store", None)
    if rs is None:
        return {"_error": "_rel_store not found"}
    result = {"type": type(rs).__name__}
    # Try get_pair or get_all_for_source
    for method in ["get_pair", "get_all_for_source", "get_relationship"]:
        fn = getattr(rs, method, None)
        if fn:
            try:
                if method == "get_pair":
                    pair_data = fn(cid, PAIR[0], PAIR[1]) if len(inspect.signature(fn).parameters) >= 3 else fn(PAIR[0], PAIR[1])
                    result[f"{method}({PAIR[0]},{PAIR[1]})"] = extract_dict_safe(pair_data)
                elif method == "get_all_for_source":
                    for nid in PAIR:
                        data = fn(cid, nid) if len(inspect.signature(fn).parameters) >= 2 else fn(nid)
                        result[f"{method}({nid})"] = extract_dict_safe(data)
            except Exception as e:
                result[f"{method}_error"] = str(e)[:80]
    return result


def main():
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = log_file
    sys.stderr = log_file
    
    print(f"[E0-PILOT-4] START {datetime.now().isoformat()}")
    url = None
    error = None
    cid = "unknown"
    npc_states_data = {}
    rel_data = {}
    dh_installed = False
    phase5_original = None
    tick_orch = None
    ticks_completed = 0
    positions_per_tick = []
    dh_sig = None
    
    try:
        print("[E0-PILOT-4] Acquiring LLM lease...")
        url = ensure_llm(label="experiment:E0-pilot4")
        print(f"[E0-PILOT-4] LLM URL: {url}")
        
        from tests.gameplay.harness import TavernGameplayHarness
        h = TavernGameplayHarness()
        h.new_game()
        raw_cid = h.campaign_id
        cid = raw_cid() if callable(raw_cid) else str(raw_cid)
        gl = h.game_loop
        print(f"[E0-PILOT-4] Campaign={cid}")
        
        # === Inspect DecisionHub.compute signature ===
        try:
            from app.services.npc.decision_hub import DecisionHub
            sig = inspect.signature(DecisionHub.compute)
            dh_sig = str(sig)
            params = list(sig.parameters.keys())
            print(f"[E0-PILOT-4] DecisionHub.compute signature: {dh_sig}")
            print(f"[E0-PILOT-4] DecisionHub.compute params: {params}")
        except Exception as e:
            print(f"[E0-PILOT-4] DecisionHub import/sig failed: {e}")
        
        # === NPCState via _resolve_npcs_snapshot ===
        npc_states_data_source = "none"
        states_result = get_npc_states_via_snapshot(gl, cid)
        if states_result[0]:
            npc_states_data_source = states_result[1]
            for nid in PAIR:
                item = states_result[0].get(nid)
                if item is not None:
                    if isinstance(item, dict):
                        npc_states_data[nid] = {
                            "source": "dict",
                            "npc_id": item.get("id") or item.get("npc_id", "?"),
                            "drives": item.get("drives") or item.get("drives_runtime"),
                            "psyche": item.get("psyche"),
                            "stress": item.get("stress"),
                            "will_state": item.get("will_state"),
                            "relationship_cache": (item.get("relationship_cache", {}) if isinstance(item.get("relationship_cache"), dict) else None),
                            "rel_cache_count": len(item.get("relationship_cache", {})) if isinstance(item.get("relationship_cache"), dict) else 0,
                        }
                    else:
                        npc_states_data[nid] = extract_state_brief(item)
                        npc_states_data[nid]["source"] = "object"
            print(f"[E0-PILOT-4] NPC states via {npc_states_data_source}: {list(npc_states_data.keys())}")
        else:
            print(f"[E0-PILOT-4] NPC states: NONE accessible via snapshot methods")
        
        # Log NPC states
        for nid in PAIR:
            ns = npc_states_data.get(nid, {})
            print(f"[E0-PILOT-4] {nid}: drives={ns.get('drives')}, psyche={ns.get('psyche')}, "
                  f"will={ns.get('will_state')}, stress={ns.get('stress')}, rel_count={ns.get('rel_cache_count')}")
        
        # === Relationships via _rel_store ===
        rel_data = get_relationships_via_rel_store(gl, cid)
        print(f"[E0-PILOT-4] rel_store: {rel_data.get('type')}")
        for k, v in rel_data.items():
            if k != "type" and not k.endswith("_error"):
                print(f"[E0-PILOT-4] rel {k}: {v}")
        
        # === Install DecisionHub class-level wrapper ===
        install_dh_wrapper()
        dh_installed = True
        print(f"[E0-PILOT-4] DecisionHub.compute wrapped (class-level, reversible)")
        
        # === Install _phase_5_decision wrapper ===
        tick_orch = getattr(gl, "_tick_orch", None)
        if tick_orch:
            phase5_original = install_phase5_wrapper(tick_orch)
            print(f"[E0-PILOT-4] _phase_5_decision wrapped (instance, reversible)")
        
        # === Run 5 ticks ===
        import math
        for n in range(1, N_TICKS + 1):
            try:
                res = gl.idle_tick(cid)
                # Read positions
                scene = gl.get_scene_state(cid, "tavern")
                if not isinstance(scene, dict):
                    scene = gl.get_scene_state(cid) if hasattr(gl, "get_scene_state") else {}
                positions = {}
                dist = None
                if isinstance(scene, dict):
                    nps = scene.get("npc_positions", {})
                    for nid in PAIR:
                        pd = nps.get(nid, {})
                        if isinstance(pd, dict):
                            lp = pd.get("local_position", {})
                            positions[nid] = {
                                "node": pd.get("position", ""),
                                "x": lp.get("x") if isinstance(lp, dict) else None,
                                "y": lp.get("y") if isinstance(lp, dict) else None,
                            }
                    try:
                        lx = positions["maid_lusya"]["x"]
                        ly = positions["maid_lusya"]["y"]
                        tx = positions["tavern_keeper_tornin"]["x"]
                        ty = positions["tavern_keeper_tornin"]["y"]
                        if all(v is not None for v in [lx, ly, tx, ty]):
                            dist = round(math.sqrt((lx-tx)**2 + (ly-ty)**2), 2)
                    except Exception:
                        pass
                status = res.get("status") if isinstance(res, dict) else str(res)[:50]
                positions_per_tick.append({"tick": n, "distance": dist, "status": status,
                                           "dh_calls_so_far": len(DH_CALLS),
                                           "phase5_calls_so_far": len(PHASE5_LOG)})
                ticks_completed = n
                in_range = "YES" if dist and dist <= SPEAK_RADIUS else "NO"
                print(f"  T{n}: status={status}, dist={dist}({in_range}), "
                      f"dh_calls={len(DH_CALLS)}, phase5_calls={len(PHASE5_LOG)}")
            except Exception as e:
                print(f"  T{n} FAILED: {type(e).__name__}: {e}")
                traceback.print_exc()
                break
        
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        # Restore wrappers
        if dh_installed:
            restore_dh_wrapper()
            print(f"[E0-PILOT-4] DecisionHub.compute restored (total calls captured: {len(DH_CALLS)})")
        if tick_orch and phase5_original is not None:
            restore_phase5_wrapper(tick_orch, phase5_original)
            print(f"[E0-PILOT-4] _phase_5_decision restored (total calls: {len(PHASE5_LOG)})")
        
        sys.stdout = old_out
        sys.stderr = old_err
        log_file.close()
        print("[E0-PILOT-4] Releasing LLM lease...")
        try: release_lease()
        except: pass
    
    # === POST-RUN ANALYSIS ===
    
    # Filter DH calls for Lusya/Tornin
    pair_calls = [c for c in DH_CALLS if c.get("state", {}).get("npc_id", "") in PAIR]
    
    # Check WORLD_TICK events
    world_tick_events = [c for c in DH_CALLS if c.get("event", {}).get("is_world_tick", False)]
    non_world_tick = [c for c in DH_CALLS if not c.get("event", {}).get("is_world_tick", False)]
    
    # Check TALK in candidates
    talk_present = [c for c in DH_CALLS if c.get("result", {}).get("talk_in_candidates", False)]
    talk_absent = [c for c in DH_CALLS if not c.get("result", {}).get("talk_in_candidates", False)]
    
    # Event types summary
    event_types = {}
    for c in DH_CALLS:
        et = c.get("event", {}).get("event_type", "?")
        event_types[et] = event_types.get(et, 0) + 1
    
    # Winners summary
    winners = {}
    for c in DH_CALLS:
        w = c.get("result", {}).get("winner", "?")
        winners[w] = winners.get(w, 0) + 1
    
    summary = {
        "run_id": RUN_ID,
        "timestamp": datetime.now().isoformat(),
        "campaign": cid,
        "ticks_completed": ticks_completed,
        "error": error,
        "dh_compute_signature": dh_sig,
        "npc_states_source": npc_states_data_source,
        "npc_states": npc_states_data,
        "rel_data": rel_data,
        "positions_per_tick": positions_per_tick,
        "dh_total_calls": len(DH_CALLS),
        "dh_pair_calls": len(pair_calls),
        "phase5_total_calls": len(PHASE5_LOG),
        "world_tick_events": len(world_tick_events),
        "non_world_tick_events": len(non_world_tick),
        "talk_present_count": len(talk_present),
        "talk_absent_count": len(talk_absent),
        "event_types": event_types,
        "winners": winners,
        "dh_calls": DH_CALLS,
        "phase5_log": PHASE5_LOG,
    }
    
    sp = OUT / "summary.json"
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    
    rp = OUT / "report.md"
    with open(rp, "w", encoding="utf-8") as f:
        f.write(f"# E0-PILOT-4 DecisionHub Runtime Capture Report\n\n")
        f.write(f"Run: {RUN_ID} | {summary['timestamp']}\n")
        f.write(f"Campaign: {cid} | Ticks: {ticks_completed}/{N_TICKS}\n\n")
        if error:
            f.write(f"**ERROR:** {error}\n\n")
        
        f.write(f"## DecisionHub.compute signature\n\n```\n{dh_sig}\n```\n\n")
        
        f.write(f"## NPC states (via {npc_states_data_source})\n\n")
        for nid in PAIR:
            ns = npc_states_data.get(nid, {})
            f.write(f"### {nid}\n")
            f.write(f"- drives: `{ns.get('drives')}`\n")
            f.write(f"- psyche: `{ns.get('psyche')}`\n")
            f.write(f"- will_state: `{ns.get('will_state')}`\n")
            f.write(f"- stress: `{ns.get('stress')}`\n")
            f.write(f"- rel_cache_count: `{ns.get('rel_cache_count')}`\n\n")
        
        f.write(f"## Relationships (via _rel_store)\n\n```json\n{json.dumps(rel_data, ensure_ascii=False, indent=2, default=str)}\n```\n\n")
        
        f.write(f"## DecisionHub calls summary\n\n")
        f.write(f"- Total compute() calls: **{len(DH_CALLS)}**\n")
        f.write(f"- Calls for Lusya/Tornin: **{len(pair_calls)}**\n")
        f.write(f"- _phase_5_decision calls: **{len(PHASE5_LOG)}**\n")
        f.write(f"- WORLD_TICK events: **{len(world_tick_events)}**\n")
        f.write(f"- Non-WORLD_TICK events: **{len(non_world_tick)}**\n")
        f.write(f"- TALK in candidates: **{len(talk_present)}**\n")
        f.write(f"- TALK absent: **{len(talk_absent)}**\n\n")
        
        f.write(f"### Event types received by DecisionHub\n\n")
        for et, count in event_types.items():
            f.write(f"- `{et}`: {count}\n")
        f.write(f"\n")
        
        f.write(f"### Winners\n\n")
        for w, count in winners.items():
            f.write(f"- `{w}`: {count}\n")
        f.write(f"\n")
        
        if DH_CALLS:
            f.write(f"## DecisionHub calls (detail)\n\n")
            for c in DH_CALLS:
                st = c.get("state", {})
                ev = c.get("event", {})
                rs = c.get("result", {})
                f.write(f"### Call #{c['call_num']}: NPC={st.get('npc_id','?')}\n")
                f.write(f"- Event: `{ev.get('event_type','?')}` reason=`{ev.get('reason','')}` is_world_tick=`{ev.get('is_world_tick')}`\n")
                f.write(f"- State: drives=`{st.get('drives_runtime')}` will=`{st.get('will_state')}` consciousness=`{st.get('consciousness')}`\n")
                f.write(f"- Personality: drives_base=`{c.get('personality',{}).get('drives_base')}`\n")
                f.write(f"- Winner: **{rs.get('winner','?')}** score={rs.get('score')}\n")
                f.write(f"- TALK in candidates: `{rs.get('talk_in_candidates')}` talk_score=`{rs.get('talk_score')}`\n")
                f.write(f"- Scores trace: `{rs.get('scores_trace')}`\n\n")
        
        if PHASE5_LOG:
            f.write(f"## _phase_5_decision calls\n\n")
            for p in PHASE5_LOG:
                f.write(f"- #{p['call_num']}: args={p['args_count']} returned={p.get('returned')} error={p.get('error','')}\n")
            f.write(f"\n")
        
        # === 7 QUESTIONS ===
        f.write(f"## Answers to 7 questions\n\n")
        
        q1 = "YES" if pair_calls else ("NO — compute() not called for pair" if len(DH_CALLS) == 0 else "NO — compute() called but not for pair NPCs")
        f.write(f"**Q1. Is DecisionHub called for Lusya and Tornin?**\n→ **{q1}**\n")
        f.write(f"   Evidence: {len(DH_CALLS)} total calls, {len(pair_calls)} for pair NPCs.\n\n")
        
        if not pair_calls:
            phase5_called = len(PHASE5_LOG) > 0
            if phase5_called:
                q2 = f"phase 5 entered ({len(PHASE5_LOG)} calls) but DecisionHub.compute NOT called — path breaks inside _phase_5_decision"
            else:
                q2 = "phase 5 NOT entered — path breaks before _phase_5_decision (in earlier phase or pipeline entry)"
            f.write(f"**Q2. Where does the path break?**\n→ **{q2}**\n\n")
        else:
            f.write(f"**Q2. (N/A — compute() is called)**\n\n")
        
        talk_any = len(talk_present) > 0
        q3 = "YES" if talk_any else ("NO" if DH_CALLS else "UNVERIFIED — compute() not called")
        f.write(f"**Q3. Is TALK among candidates?**\n→ **{q3}**\n")
        f.write(f"   Evidence: {len(talk_present)} calls with TALK, {len(talk_absent)} without.\n\n")
        
        if talk_any:
            f.write(f"**Q4. Why does TALK lose?**\n→ See scores_trace in call details above.\n\n")
        else:
            f.write(f"**Q4. (N/A — TALK not in candidates)**\n\n")
        
        if DH_CALLS and not talk_any:
            f.write(f"**Q5. At what stage is TALK excluded?**\n→ Check scores_trace: if TALK not in scores_trace keys, excluded BEFORE scoring (relevance=0 for non-WORLD_TICK events). If in keys with score=0, excluded AT scoring.\n\n")
        else:
            f.write(f"**Q5. (N/A)**\n\n")
        
        q6 = "See event_types above" if DH_CALLS else "UNVERIFIED — compute() not called"
        f.write(f"**Q6. What event type does DecisionHub receive?**\n→ **{q6}**\n")
        f.write(f"   WORLD_TICK events: {len(world_tick_events)}, Non-WORLD_TICK: {len(non_world_tick)}\n\n")
        
        if DH_CALLS:
            wt = len(world_tick_events)
            nwt = len(non_world_tick)
            if wt == 0 and nwt > 0 and not talk_any:
                q7 = "ABSENCE of WORLD_TICK is CAUSAL (not just correlation): 0 WORLD_TICK events → TALK proactive bonus (+0.4) never applies → TALK excluded or scores ~0"
            elif wt > 0 and not talk_any:
                q7 = "WORLD_TICK events present but TALK still absent — WORLD_TICK absence is NOT the cause"
            elif talk_any:
                q7 = "TALK is in candidates — WORLD_TICK question is moot"
            else:
                q7 = "UNVERIFIED — insufficient data"
        else:
            q7 = "UNVERIFIED — DecisionHub.compute not called, cannot determine"
        f.write(f"**Q7. Does WORLD_TICK absence affect result?**\n→ **{q7}**\n\n")
        
        f.write(f"## Positions and distance\n\n")
        for pt in positions_per_tick:
            f.write(f"- T{pt['tick']}: dist={pt['distance']} dh_calls={pt['dh_calls_so_far']} phase5={pt['phase5_calls_so_far']}\n")
        f.write(f"\n")
    
    # Console
    print(f"[E0-PILOT-4] DONE")
    print(f"  Artifacts: {OUT}")
    print(f"  report.md: {rp}")
    print(f"  Ticks: {ticks_completed}/{N_TICKS}")
    print(f"  DH calls: {len(DH_CALLS)} (pair: {len(pair_calls)})")
    print(f"  Phase5 calls: {len(PHASE5_LOG)}")
    print(f"  WORLD_TICK events: {len(world_tick_events)}")
    print(f"  TALK in candidates: {len(talk_present)}")
    print(f"  Winners: {winners}")
    if error:
        print(f"  ERROR: {error}")


if __name__ == "__main__":
    main()
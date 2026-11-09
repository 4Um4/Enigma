"""path: /project/backend/tests/sandbox/e0_pilot5_nonhostile.py
Purpose: E0-PILOT-5 — autonomous NPC interaction with non-hostile pair.
         Primary: Lusya <-> Orm. Fallback: Borko <-> Goran.
         10 ticks, DecisionHub capture, dialogue + LLM detection.
Dependencies: tests/gameplay/harness.py, app.services.llm.runtime.client, app.services.npc.decision_hub
Output: reports/experiments/e0_pilot_5/{run_log.txt, report.md, summary.json}
"""
import json, sys, math, inspect, traceback
from pathlib import Path
from datetime import datetime

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.llm.runtime.client import ensure_llm, release_lease

N_TICKS = 10
SPEAK_RADIUS = 5.0
HOSTILE_THRESHOLD = -30
RUN_ID = "e0_pilot_5"
OUT = Path("reports/experiments") / RUN_ID
OUT.mkdir(parents=True, exist_ok=True)
LOG_PATH = OUT / "run_log.txt"

# Candidate pairs in priority order
PAIR_CANDIDATES = [
    ("maid_lusya", "blacksmith_orm"),
    ("guard_borko", "merchant_goran"),
]


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

def extract_dict_safe(obj, max_items=20):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): (safe_float(v) if isinstance(v, (int, float)) else safe_str(v, 60))
                for k, v in list(obj.items())[:max_items]}
    try:
        vd = vars(obj)
        if vd:
            return {str(k): (safe_float(v) if isinstance(v, (int, float)) else safe_str(v, 60))
                    for k, v in list(vd.items())[:max_items]}
    except TypeError:
        pass
    return safe_str(obj, 200)


def check_pair_suitability(gl, cid, npc_a, npc_b):
    """Check trust (both directions) and distance."""
    result = {"pair": (npc_a, npc_b), "suitable": False}
    
    # Relationships via _rel_store
    rs = getattr(gl, "_rel_store", None)
    if rs:
        # A -> B
        try:
            fn = getattr(rs, "get_pair", None)
            if fn:
                try:
                    pair_data = fn(cid, npc_a, npc_b)
                except TypeError:
                    pair_data = fn(npc_a, npc_b)
                if isinstance(pair_data, dict):
                    trust_ab = pair_data.get("trust", 0)
                    fear_ab = pair_data.get("fear", 0)
                    result["trust_a_to_b"] = trust_ab
                    result["fear_a_to_b"] = fear_ab
                    result["a_to_b_hostile"] = trust_ab < HOSTILE_THRESHOLD
                else:
                    result["trust_a_to_b"] = None
            # B -> A
            try:
                pair_data_ba = fn(cid, npc_b, npc_a)
            except TypeError:
                pair_data_ba = fn(npc_b, npc_a)
            if isinstance(pair_data_ba, dict):
                trust_ba = pair_data_ba.get("trust", 0)
                fear_ba = pair_data_ba.get("fear", 0)
                result["trust_b_to_a"] = trust_ba
                result["fear_b_to_a"] = fear_ba
                result["b_to_a_hostile"] = trust_ba < HOSTILE_THRESHOLD
            else:
                result["trust_b_to_a"] = None
        except Exception as e:
            result["rel_error"] = str(e)[:100]
    
    # Positions via get_scene_state
    scene = gl.get_scene_state(cid, "tavern")
    if not isinstance(scene, dict):
        scene = gl.get_scene_state(cid) if hasattr(gl, "get_scene_state") else {}
    positions = scene.get("npc_positions", {}) if isinstance(scene, dict) else {}
    
    for nid in [npc_a, npc_b]:
        pd = positions.get(nid, {})
        if isinstance(pd, dict):
            lp = pd.get("local_position", {})
            result[f"{nid}_node"] = pd.get("position", "")
            result[f"{nid}_x"] = lp.get("x") if isinstance(lp, dict) else None
            result[f"{nid}_y"] = lp.get("y") if isinstance(lp, dict) else None
    
    # Distance
    try:
        ax = result.get(f"{npc_a}_x")
        ay = result.get(f"{npc_a}_y")
        bx = result.get(f"{npc_b}_x")
        by = result.get(f"{npc_b}_y")
        if all(v is not None for v in [ax, ay, bx, by]):
            result["distance"] = round(math.sqrt((ax-bx)**2 + (ay-by)**2), 2)
            result["in_range"] = result["distance"] <= SPEAK_RADIUS
        else:
            result["distance"] = None
            result["in_range"] = False
    except Exception:
        result["distance"] = None
        result["in_range"] = False
    
    # Hostile check
    a_hostile = result.get("a_to_b_hostile", False)
    b_hostile = result.get("b_to_a_hostile", False)
    result["any_hostile"] = a_hostile or b_hostile
    result["suitable"] = result.get("in_range", False) and not result["any_hostile"]
    
    return result


# === DecisionHub class-level wrapper (from E0-PILOT-4, proven) ===
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
        
        npc_id = getattr(state, "npc_id", "?") if state else "?"
        et = str(getattr(event, "event_type", getattr(event, "type", "?"))) if event else "?"
        reason = str(getattr(event, "reason", "")) if event else ""
        
        result = DH_ORIGINAL(self, *args, **kwargs)
        
        winner = str(getattr(result, "intent", "?"))
        score = getattr(result, "score", 0)
        st = getattr(result, "scores_trace", None)
        scores_dict = extract_dict_safe(st, 25)
        
        # Check TALK
        talk_found = False
        talk_score = None
        if isinstance(scores_dict, dict):
            for k, v in scores_dict.items():
                if "talk" in str(k).lower():
                    talk_found = True
                    talk_score = v
        
        DH_CALLS.append({
            "call_num": call_num,
            "npc_id": npc_id,
            "event_type": et[:30],
            "reason": reason[:40],
            "winner": winner,
            "score": safe_float(score),
            "scores_trace": scores_dict,
            "talk_in_candidates": talk_found,
            "talk_score": talk_score,
            "drives_base": extract_dict_safe(getattr(personality, "drives_base", None), 8) if personality else None,
        })
        return result
    
    DecisionHub.compute = wrapped_compute
    return DecisionHub

def restore_dh_wrapper():
    global DH_ORIGINAL
    if DH_ORIGINAL is not None:
        from app.services.npc.decision_hub import DecisionHub
        DecisionHub.compute = DH_ORIGINAL
        DH_ORIGINAL = None


def get_recent_dialogues(gl, cid):
    """Try to get recent dialogues via task_scheduler."""
    ts = getattr(gl, "_task_scheduler", None)
    if ts is None:
        get_ts = getattr(gl, "_get_task_scheduler", None)
        ts = get_ts() if get_ts else None
    if ts is None:
        return [], "task_scheduler not found"
    try:
        # Try get_recent_dialogues
        fn = getattr(ts, "get_recent_dialogues", None)
        if fn:
            try:
                result = fn(cid)
            except TypeError:
                result = fn()
            if result:
                return result, "get_recent_dialogues"
        return [], "get_recent_dialogues returned empty or not found"
    except Exception as e:
        return [], f"error: {e}"


def find_jsonl_logs(backend_dir):
    """Find JSONL log files."""
    jsonl_files = []
    for d in [Path("backend/logs"), Path("logs"), Path("saves"), backend_dir / "logs", backend_dir / "saves"]:
        if d.exists():
            jsonl_files.extend(d.rglob("*.jsonl"))
    return jsonl_files


def scan_jsonl_for_llm_calls(jsonl_files, since_timestamp):
    """Scan JSONL logs for LLM calls after the given timestamp."""
    llm_calls = []
    for jf in jsonl_files:
        try:
            with open(jf, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts = entry.get("timestamp", "")
                        agent = entry.get("agent", "")
                        if agent in ("llm_input", "llm_output"):
                            # Check if after run start
                            if ts and ts >= since_timestamp:
                                llm_calls.append({
                                    "file": str(jf.name),
                                    "agent": agent,
                                    "timestamp": ts[:30],
                                    "tick_id": entry.get("tick_id", "?"),
                                    "text_preview": str(entry.get("text", entry.get("response", "")))[:100],
                                })
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    return llm_calls


def main():
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = log_file
    sys.stderr = log_file
    
    print(f"[E0-PILOT-5] START {datetime.now().isoformat()}")
    url = None
    error = None
    cid = "unknown"
    selected_pair = None
    pair_check = {}
    dh_installed = False
    ticks_completed = 0
    positions_per_tick = []
    dialogues_per_tick = []
    run_start_time = datetime.now().isoformat()
    
    try:
        print("[E0-PILOT-5] Acquiring LLM lease...")
        url = ensure_llm(label="experiment:E0-pilot5")
        print(f"[E0-PILOT-5] LLM URL: {url}")
        
        from tests.gameplay.harness import TavernGameplayHarness
        h = TavernGameplayHarness()
        h.new_game()
        raw_cid = h.campaign_id
        cid = raw_cid() if callable(raw_cid) else str(raw_cid)
        gl = h.game_loop
        print(f"[E0-PILOT-5] Campaign={cid}")
        
        # === Pair selection ===
        for npc_a, npc_b in PAIR_CANDIDATES:
            check = check_pair_suitability(gl, cid, npc_a, npc_b)
            print(f"[E0-PILOT-5] Pair check {npc_a}<->{npc_b}: "
                  f"trust_a2b={check.get('trust_a_to_b')}, trust_b2a={check.get('trust_b_to_a')}, "
                  f"dist={check.get('distance')}, in_range={check.get('in_range')}, "
                  f"any_hostile={check.get('any_hostile')}, suitable={check.get('suitable')}")
            if check.get("suitable"):
                selected_pair = (npc_a, npc_b)
                pair_check = check
                break
        
        if not selected_pair:
            print("[E0-PILOT-5] NO SUITABLE PAIR FOUND — stopping")
            # Log all pair checks for reference
            for npc_a, npc_b in PAIR_CANDIDATES:
                check = check_pair_suitability(gl, cid, npc_a, npc_b)
                print(f"[E0-PILOT-5] UNSUITABLE {npc_a}<->{npc_b}: {json.dumps(check, default=str)}")
        else:
            print(f"[E0-PILOT-5] SELECTED PAIR: {selected_pair[0]} <-> {selected_pair[1]}")
            
            # === Install DecisionHub wrapper ===
            install_dh_wrapper()
            dh_installed = True
            print(f"[E0-PILOT-5] DecisionHub.compute wrapped (class-level)")
            
            # === Run 10 ticks ===
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
                        for nid in selected_pair:
                            pd = nps.get(nid, {})
                            if isinstance(pd, dict):
                                lp = pd.get("local_position", {})
                                positions[nid] = {
                                    "node": pd.get("position", ""),
                                    "x": lp.get("x") if isinstance(lp, dict) else None,
                                    "y": lp.get("y") if isinstance(lp, dict) else None,
                                }
                        try:
                            ax = positions[selected_pair[0]]["x"]
                            ay = positions[selected_pair[0]]["y"]
                            bx = positions[selected_pair[1]]["x"]
                            by = positions[selected_pair[1]]["y"]
                            if all(v is not None for v in [ax, ay, bx, by]):
                                dist = round(math.sqrt((ax-bx)**2 + (ay-by)**2), 2)
                        except Exception:
                            pass
                    
                    # Get recent dialogues
                    recent_dials, dial_source = get_recent_dialogues(gl, cid)
                    
                    status = res.get("status") if isinstance(res, dict) else str(res)[:50]
                    positions_per_tick.append({
                        "tick": n, "distance": dist, "status": status,
                        "positions": positions,
                        "dh_calls_so_far": len(DH_CALLS),
                    })
                    dialogues_per_tick.append({
                        "tick": n,
                        "recent_dialogues_count": len(recent_dials) if isinstance(recent_dials, list) else 0,
                        "recent_dialogues_source": dial_source,
                        "recent_dialogues_sample": [safe_str(d, 100) for d in (recent_dials[:3] if isinstance(recent_dials, list) else [])],
                    })
                    ticks_completed = n
                    in_range = "YES" if dist and dist <= SPEAK_RADIUS else "NO"
                    print(f"  T{n}: status={status}, dist={dist}({in_range}), "
                          f"dh={len(DH_CALLS)}, dials={len(recent_dials) if isinstance(recent_dials, list) else '?'}")
                except Exception as e:
                    print(f"  T{n} FAILED: {type(e).__name__}: {e}")
                    traceback.print_exc()
                    break
            
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        if dh_installed:
            restore_dh_wrapper()
            print(f"[E0-PILOT-5] DecisionHub.compute restored (total: {len(DH_CALLS)} calls)")
        sys.stdout = old_out
        sys.stderr = old_err
        log_file.close()
        print("[E0-PILOT-5] Releasing LLM lease...")
        try: release_lease()
        except: pass
    
    # === POST-RUN ANALYSIS ===
    
    # Find JSONL logs and scan for LLM calls
    jsonl_files = find_jsonl_logs(BACKEND)
    llm_calls = scan_jsonl_for_llm_calls(jsonl_files, run_start_time)
    
    # Filter DH calls for selected pair
    pair_calls = []
    if selected_pair:
        pair_calls = [c for c in DH_CALLS if c.get("npc_id", "") in selected_pair]
    
    # TALK analysis for pair
    pair_talk_present = [c for c in pair_calls if c.get("talk_in_candidates")]
    pair_talk_won = [c for c in pair_talk_present if "talk" in c.get("winner", "").lower()]
    
    # Winners for pair
    pair_winners = {}
    for c in pair_calls:
        w = c.get("winner", "?")
        pair_winners[w] = pair_winners.get(w, 0) + 1
    
    # All TALK winners (any NPC)
    all_talk_won = [c for c in DH_CALLS if "talk" in c.get("winner", "").lower()]
    
    # Result classification
    if not selected_pair:
        classification = "NO_SUITABLE_PAIR"
    elif not pair_calls:
        classification = "DECISIONHUB_NOT_REACHED_FOR_PAIR"
    elif not pair_talk_present:
        classification = "SOCIAL_INTENTS_AVAILABLE_BUT_TALK_NOT_CANDIDATE"
    elif pair_talk_won:
        if llm_calls or any(d.get("recent_dialogues_count", 0) > 0 for d in dialogues_per_tick):
            classification = "TALK_EXECUTED_DIALOGUE_OCCURRED"
        else:
            classification = "TALK_SELECTED_BUT_NOT_EXECUTED"
    else:
        classification = "TALK_CANDIDATE_BUT_LOSES"
    
    summary = {
        "run_id": RUN_ID,
        "timestamp": datetime.now().isoformat(),
        "campaign": cid,
        "ticks_completed": ticks_completed,
        "error": error,
        "selected_pair": list(selected_pair) if selected_pair else None,
        "pair_check": pair_check,
        "dh_total_calls": len(DH_CALLS),
        "dh_pair_calls": len(pair_calls),
        "pair_talk_present": len(pair_talk_present),
        "pair_talk_won": len(pair_talk_won),
        "all_talk_won": len(all_talk_won),
        "pair_winners": pair_winners,
        "llm_calls_count": len(llm_calls),
        "llm_calls": llm_calls[:10],
        "jsonl_files_found": [str(f.name) for f in jsonl_files],
        "positions_per_tick": positions_per_tick,
        "dialogues_per_tick": dialogues_per_tick,
        "dh_pair_calls_detail": pair_calls,
        "classification": classification,
    }
    
    sp = OUT / "summary.json"
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    
    rp = OUT / "report.md"
    with open(rp, "w", encoding="utf-8") as f:
        f.write(f"# E0-PILOT-5 Non-Hostile NPC Interaction Report\n\n")
        f.write(f"Run: {RUN_ID} | {summary['timestamp']}\n")
        f.write(f"Campaign: {cid} | Ticks: {ticks_completed}/{N_TICKS}\n\n")
        if error:
            f.write(f"**ERROR:** {error}\n\n")
        
        f.write(f"## Pair selection\n\n")
        if selected_pair:
            a, b = selected_pair
            f.write(f"**Selected: {a} <-> {b}**\n\n")
            f.write(f"| Field | Value |\n|---|---|\n")
            f.write(f"| trust {a}->{b} | {pair_check.get('trust_a_to_b')} |\n")
            f.write(f"| trust {b}->{a} | {pair_check.get('trust_b_to_a')} |\n")
            f.write(f"| fear {a}->{b} | {pair_check.get('fear_a_to_b')} |\n")
            f.write(f"| fear {b}->{a} | {pair_check.get('fear_b_to_a')} |\n")
            f.write(f"| distance | {pair_check.get('distance')} |\n")
            f.write(f"| in_range (<= {SPEAK_RADIUS}) | {pair_check.get('in_range')} |\n")
            f.write(f"| any_hostile | {pair_check.get('any_hostile')} |\n\n")
        else:
            f.write(f"**NO SUITABLE PAIR FOUND**\n\n")
        
        f.write(f"## Result classification\n\n")
        f.write(f"**{classification}**\n\n")
        
        f.write(f"## DecisionHub summary\n\n")
        f.write(f"- Total compute() calls: {len(DH_CALLS)}\n")
        f.write(f"- Pair calls: {len(pair_calls)}\n")
        f.write(f"- TALK in candidates (pair): {len(pair_talk_present)}\n")
        f.write(f"- TALK won (pair): {len(pair_talk_won)}\n")
        f.write(f"- TALK won (all NPC): {len(all_talk_won)}\n\n")
        
        f.write(f"### Pair winners\n\n")
        for w, count in pair_winners.items():
            f.write(f"- `{w}`: {count}\n")
        f.write(f"\n")
        
        if pair_calls:
            f.write(f"## DecisionHub calls for pair (detail)\n\n")
            for c in pair_calls:
                f.write(f"### Call #{c['call_num']}: {c['npc_id']}\n")
                f.write(f"- Event: `{c['event_type']}` reason=`{c['reason']}`\n")
                f.write(f"- Winner: **{c['winner']}** score={c['score']}\n")
                f.write(f"- TALK in candidates: `{c['talk_in_candidates']}` talk_score=`{c['talk_score']}`\n")
                f.write(f"- drives_base: `{c['drives_base']}`\n")
                st = c.get('scores_trace', {})
                if isinstance(st, dict):
                    # Show top 5 scores sorted
                    sorted_scores = sorted(st.items(), key=lambda x: float(x[1]) if isinstance(x[1], (int, float)) else -999, reverse=True)
                    f.write(f"- Top 5 scores: {sorted_scores[:5]}\n")
                f.write(f"\n")
        
        f.write(f"## Dialogue detection\n\n")
        f.write(f"### Recent dialogues per tick\n\n")
        for d in dialogues_per_tick:
            f.write(f"- T{d['tick']}: count={d['recent_dialogues_count']} source=`{d['recent_dialogues_source']}`\n")
            for s in d.get('recent_dialogues_sample', []):
                f.write(f"  - {s}\n")
        f.write(f"\n")
        
        f.write(f"### LLM calls (from JSONL log)\n\n")
        f.write(f"Total LLM calls during run: **{len(llm_calls)}**\n\n")
        for lc in llm_calls[:10]:
            f.write(f"- [{lc['agent']}] tick={lc['tick_id']} ts={lc['timestamp']} text={lc['text_preview']}\n")
        f.write(f"\n")
        
        f.write(f"## Positions and distance\n\n")
        f.write(f"| Tick | {selected_pair[0] if selected_pair else 'A'} pos | {selected_pair[1] if selected_pair else 'B'} pos | Dist | In range? |\n")
        f.write(f"|------|-------|--------|------|------|\n")
        for pt in positions_per_tick:
            if selected_pair:
                a_pos = pt.get("positions", {}).get(selected_pair[0], {})
                b_pos = pt.get("positions", {}).get(selected_pair[1], {})
                f.write(f"| {pt['tick']} | {a_pos.get('node','?')}({a_pos.get('x')},{a_pos.get('y')}) | "
                        f"{b_pos.get('node','?')}({b_pos.get('x')},{b_pos.get('y')}) | "
                        f"{pt['distance']} | {'YES' if pt['distance'] and pt['distance'] <= SPEAK_RADIUS else 'NO'} |\n")
        f.write(f"\n")
        
        f.write(f"## Classification criteria (per TZ §4)\n\n")
        if classification == "NO_SUITABLE_PAIR":
            f.write(f"- No suitable non-hostile pair found within speak radius.\n")
        elif classification == "SOCIAL_INTENTS_AVAILABLE_BUT_TALK_NOT_CANDIDATE":
            f.write(f"- Social intents available but TALK not in candidates for pair.\n")
        elif classification == "TALK_CANDIDATE_BUT_LOSES":
            f.write(f"- TALK is in candidates but loses to other intents.\n")
        elif classification == "TALK_SELECTED_BUT_NOT_EXECUTED":
            f.write(f"- TALK won DecisionHub but no dialogue/LLM call detected.\n")
        elif classification == "TALK_EXECUTED_DIALOGUE_OCCURRED":
            f.write(f"- TALK won AND dialogue/LLM call detected.\n")
        f.write(f"\n")
    
    # Console
    print(f"[E0-PILOT-5] DONE")
    print(f"  Artifacts: {OUT}")
    print(f"  Pair: {selected_pair}")
    print(f"  Ticks: {ticks_completed}/{N_TICKS}")
    print(f"  DH calls: {len(DH_CALLS)} (pair: {len(pair_calls)})")
    print(f"  TALK in candidates (pair): {len(pair_talk_present)}")
    print(f"  TALK won (pair): {len(pair_talk_won)}")
    print(f"  LLM calls: {len(llm_calls)}")
    print(f"  Classification: {classification}")
    if error:
        print(f"  ERROR: {error}")


if __name__ == "__main__":
    main()
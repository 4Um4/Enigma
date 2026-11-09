"""path: /project/backend/tests/sandbox/e0_decision_probe.py
Purpose: E0-PILOT-3 — diagnose why Lusya/Tornin don't choose TALK.
         5 ticks. Capture runtime psychology + DecisionHub results.
Dependencies: tests/gameplay/harness.py, app.services.llm.runtime.client
Output: reports/experiments/e0_decision_probe/{run_log.txt, report.md, summary.json}
Does NOT modify production code. DecisionHub wrapper is runner-level only:
  - calls original compute() with same args
  - returns original result unchanged
  - only side effect: logs the result for analysis
  - restored after run
"""
import json, sys, math, re, traceback
from pathlib import Path
from datetime import datetime

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.llm.runtime.client import ensure_llm, release_lease

PAIR = ["maid_lusya", "tavern_keeper_tornin"]
N_TICKS = 5
SPEAK_RADIUS = 5.0
RUN_ID = "e0_decision_probe"
OUT = Path("reports/experiments") / RUN_ID
OUT.mkdir(parents=True, exist_ok=True)
LOG_PATH = OUT / "run_log.txt"


def find_attr(obj, names):
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v, n
    return None, None


def extract_npc_state(state):
    if state is None:
        return {"_error": "state is None"}
    r = {}
    r["npc_id"] = getattr(state, "npc_id", "?")
    r["is_alive"] = getattr(state, "is_alive", True)
    r["life_status"] = str(getattr(state, "life_status", "ALIVE"))
    r["stress"] = getattr(state, "stress", None)
    r["consciousness"] = getattr(state, "consciousness", None)
    r["will_state"] = str(getattr(state, "will_state", "?"))

    drives = getattr(state, "drives_runtime", None) or getattr(state, "drives", None)
    if isinstance(drives, dict):
        r["drives"] = {k: round(float(v), 3) if isinstance(v, (int, float)) else str(v)[:50]
                       for k, v in list(drives.items())[:10]}
    elif drives is not None:
        r["drives"] = str(drives)[:200]
    else:
        r["drives"] = None

    psyche = getattr(state, "psyche", None)
    if isinstance(psyche, dict):
        r["psyche"] = {k: v for k, v in list(psyche.items())[:10]}
    elif psyche is not None:
        r["psyche"] = {
            "willpower": getattr(psyche, "willpower", None),
            "breakpoint": getattr(psyche, "breakpoint", None),
            "loyalty_true": getattr(psyche, "loyalty_true", getattr(psyche, "loyalty_base", None)),
        }
    else:
        r["psyche"] = None

    rel = getattr(state, "relationship_cache", None)
    if isinstance(rel, dict):
        r["relationship_cache_count"] = len(rel)
        r["relationship_cache"] = {
            target: {k: (round(float(v), 2) if isinstance(v, (int, float)) else str(v)[:30])
                     for k, v in list(d.items())[:6]} if isinstance(d, dict) else str(d)[:80]
            for target, d in list(rel.items())[:5]
        }
    elif rel is not None:
        r["relationship_cache"] = str(rel)[:200]
        r["relationship_cache_count"] = 0
    else:
        r["relationship_cache"] = None
        r["relationship_cache_count"] = 0

    r["emotion"] = str(getattr(state, "emotion", getattr(state, "emotion_tag", "")))[:50]
    r["affective_load"] = getattr(state, "affective_load", None)

    # Activity / schedule
    r["activity_state"] = str(getattr(state, "activity_state", getattr(state, "current_activity", "?")))[:50]

    return r


def get_positions_and_distance(scene):
    if not isinstance(scene, dict):
        return {}, None
    positions = scene.get("npc_positions", {})
    result = {}
    for nid in PAIR:
        pd = positions.get(nid, {})
        if isinstance(pd, dict):
            lp = pd.get("local_position", {})
            result[nid] = {
                "node": pd.get("position", ""),
                "location": pd.get("location_id", ""),
                "x": lp.get("x") if isinstance(lp, dict) else None,
                "y": lp.get("y") if isinstance(lp, dict) else None,
            }
        else:
            result[nid] = {"raw": str(pd)[:50]}
    dist = None
    try:
        lx = result["maid_lusya"].get("x")
        ly = result["maid_lusya"].get("y")
        tx = result["tavern_keeper_tornin"].get("x")
        ty = result["tavern_keeper_tornin"].get("y")
        if all(v is not None for v in [lx, ly, tx, ty]):
            dist = round(math.sqrt((lx - tx)**2 + (ly - ty)**2), 2)
    except Exception:
        pass
    return result, dist


class DecisionHubCapture:
    """Runner-level wrapper. Calls original compute with same args, returns original result.
    Only side effect: logs the result. Does NOT modify args, result, order, or exceptions."""
    def __init__(self, original_compute):
        self.original = original_compute
        self.results = []
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        state = args[0] if args else kwargs.get("state")
        npc_id = getattr(state, "npc_id", "?") if state else "?"
        event = args[2] if len(args) > 2 else kwargs.get("event")
        event_type = str(getattr(event, "event_type", getattr(event, "type", "?"))) if event else "?"
        event_reason = str(getattr(event, "reason", "")) if event else ""
        # Call original — same args, same kwargs
        result = self.original(*args, **kwargs)
        # Capture — read-only, does not modify result
        winner = str(getattr(result, "intent", "?"))
        score = getattr(result, "score", 0)
        st = getattr(result, "scores_trace", None)
        entry = {
            "call_num": self.call_count,
            "npc_id": npc_id,
            "event_type": event_type[:30],
            "event_reason": event_reason[:40],
            "winner": winner,
            "score": round(float(score), 4) if isinstance(score, (int, float)) else score,
            "scores_trace": self._extract_scores(st),
        }
        self.results.append(entry)
        # Return original result — unchanged
        return result

    def _extract_scores(self, trace):
        if trace is None:
            return None
        try:
            if isinstance(trace, dict):
                return {str(k): (round(float(v), 4) if isinstance(v, (int, float)) else str(v)[:40])
                        for k, v in list(trace.items())[:15]}
            elif isinstance(trace, list):
                return [str(x)[:80] for x in trace[:15]]
            else:
                return str(trace)[:200]
        except Exception:
            return str(trace)[:150]


def parse_log_for_decision_traces(log_text):
    """Parse [TRACE][DECISION_SCORE] and [DIAG_COMPONENTS] from run_log.txt"""
    traces = []
    for m in re.finditer(r'\[TRACE\]\[DECISION_SCORE\]\s*npc=(\S+)\s+winner=(\S+)\s+top3=(\[.*?\])', log_text):
        traces.append({"source": "TRACE_DECISION_SCORE", "npc": m.group(1),
                       "winner": m.group(2), "top3": m.group(3)[:200]})
    for m in re.finditer(r'\[DIAG_COMPONENTS\]\s*npc=(\S+)\s+intent=(\S+)\s+base=([\d.]+)\s*comps=(\{.*?\})', log_text):
        traces.append({"source": "DIAG_COMPONENTS", "npc": m.group(1),
                       "intent": m.group(2), "base": float(m.group(3)),
                       "comps": m.group(4)[:300]})
    return traces


def main():
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = log_file
    sys.stderr = log_file

    print(f"[E0-DECISION-PROBE] START {datetime.now().isoformat()}")
    url = None
    error = None
    cid = "unknown"
    npc_initial = {}
    npc_final = {}
    positions_per_tick = []
    dh_capture = None
    dh = None
    dh_location = "not found"
    dh_restored = False
    ticks_completed = 0
    engine_found = False
    tick_orch = None

    try:
        print("[E0-DECISION-PROBE] Acquiring LLM lease...")
        url = ensure_llm(label="experiment:E0-probe")
        print(f"[E0-DECISION-PROBE] LLM URL: {url}")

        from tests.gameplay.harness import TavernGameplayHarness
        h = TavernGameplayHarness()
        h.new_game()
        raw_cid = h.campaign_id
        cid = raw_cid() if callable(raw_cid) else str(raw_cid)
        gl = h.game_loop
        print(f"[E0-DECISION-PROBE] Campaign={cid}")

        # === Explore GameLoop ===
        gl_attrs = [a for a in dir(gl) if not a.startswith("__")]
        print(f"[E0-DECISION-PROBE] GameLoop attrs: {gl_attrs[:40]}")

        # === Access LifeEngine + NPCState ===
        get_le = getattr(gl, "_get_life_engine", None)
        engine = get_le() if get_le else None
        if engine is None:
            tick_orch = getattr(gl, "_tick_orch", None)
            if tick_orch:
                engine = getattr(tick_orch, "_life_engine", None) or getattr(tick_orch, "life_engine", None)

        if engine:
            engine_found = True
            print(f"[E0-DECISION-PROBE] LifeEngine: {type(engine).__name__}")
            npc_states = engine.get_npc_states(cid)
            print(f"[E0-DECISION-PROBE] npc_states type: {type(npc_states).__name__}, "
                  f"len={len(npc_states) if hasattr(npc_states, '__len__') else '?'}")
            for nid in PAIR:
                state = None
                if isinstance(npc_states, dict):
                    state = npc_states.get(nid)
                elif isinstance(npc_states, list):
                    state = next((s for s in npc_states if getattr(s, "npc_id", "") == nid), None)
                npc_initial[nid] = extract_npc_state(state)
                ns = npc_initial[nid]
                print(f"[E0-DECISION-PROBE] {nid}: drives={ns.get('drives')}, "
                      f"psyche={ns.get('psyche')}, will={ns.get('will_state')}, "
                      f"stress={ns.get('stress')}, rel_count={ns.get('relationship_cache_count')}")
        else:
            print("[E0-DECISION-PROBE] WARNING: LifeEngine not found")

        # === Initial positions + distance ===
        scene = gl.get_scene_state(cid, "tavern")
        if not isinstance(scene, dict):
            # Try without location
            scene = gl.get_scene_state(cid) if hasattr(gl, "get_scene_state") else {}
        positions, dist = get_positions_and_distance(scene)
        positions_per_tick.append({"tick": 0, "positions": positions, "distance": dist})
        print(f"[E0-DECISION-PROBE] Initial: Lusya={positions.get('maid_lusya')}, "
              f"Tornin={positions.get('tavern_keeper_tornin')}, dist={dist}")

        # === Find DecisionHub ===
        tick_orch = tick_orch or getattr(gl, "_tick_orch", None)
        if tick_orch:
            print(f"[E0-DECISION-PROBE] TickOrch: {type(tick_orch).__name__}")
            to_attrs = [a for a in dir(tick_orch) if not a.startswith("__")]
            to_interesting = [a for a in to_attrs if any(k in a.lower() for k in
                ["decision", "npc", "pipeline", "hub", "compute", "phase"])]
            print(f"[E0-DECISION-PROBE] TickOrch attrs (filtered): {to_interesting[:20]}")

            dh, dh_name = find_attr(tick_orch, ["_decision_hub", "decision_hub", "_dh"])
            if dh:
                dh_location = f"tick_orch.{dh_name}"
            else:
                pipeline, pnome = find_attr(tick_orch, ["_npc_pipeline", "npc_pipeline", "_pipeline"])
                if pipeline:
                    print(f"[E0-DECISION-PROBE] Pipeline: {type(pipeline).__name__} (attr={pnome})")
                    p_attrs = [a for a in dir(pipeline) if not a.startswith("__")]
                    p_interesting = [a for a in p_attrs if any(k in a.lower() for k in
                        ["decision", "hub", "dh", "compute"])]
                    print(f"[E0-DECISION-PROBE] Pipeline attrs (filtered): {p_interesting[:15]}")
                    dh, dh_name = find_attr(pipeline, ["_decision_hub", "decision_hub", "_dh"])
                    if dh:
                        dh_location = f"tick_orch.{pnome}.{dh_name}"
        else:
            print("[E0-DECISION-PROBE] WARNING: _tick_orch not found")

        # === Wrap DecisionHub (runner-level, reversible) ===
        if dh:
            print(f"[E0-DECISION-PROBE] DecisionHub found at {dh_location}: {type(dh).__name__}")
            dh_capture = DecisionHubCapture(dh.compute)
            dh.compute = dh_capture
            print("[E0-DECISION-PROBE] DecisionHub.compute wrapped (reversible)")
        else:
            print(f"[E0-DECISION-PROBE] DecisionHub NOT FOUND at {dh_location}")
            print("[E0-DECISION-PROBE] Will rely on [TRACE][DECISION_SCORE] in log")

        # === Run 5 ticks ===
        for n in range(1, N_TICKS + 1):
            try:
                res = gl.idle_tick(cid)
                scene = gl.get_scene_state(cid, "tavern")
                if not isinstance(scene, dict):
                    scene = gl.get_scene_state(cid) if hasattr(gl, "get_scene_state") else {}
                positions, dist = get_positions_and_distance(scene)
                status = res.get("status") if isinstance(res, dict) else str(res)[:50]
                positions_per_tick.append({
                    "tick": n, "positions": positions, "distance": dist,
                    "status": status,
                    "dh_calls_so_far": dh_capture.call_count if dh_capture else None,
                })
                ticks_completed = n
                in_range = "YES" if dist and dist <= SPEAK_RADIUS else "NO"
                print(f"  T{n}: status={status}, dist={dist} (in_range={in_range}), "
                      f"dh_calls={dh_capture.call_count if dh_capture else 'N/A'}")
            except Exception as e:
                print(f"  T{n} FAILED: {type(e).__name__}: {e}")
                traceback.print_exc()
                break

        # === Final NPC states ===
        if engine:
            npc_states = engine.get_npc_states(cid)
            for nid in PAIR:
                state = None
                if isinstance(npc_states, dict):
                    state = npc_states.get(nid)
                elif isinstance(npc_states, list):
                    state = next((s for s in npc_states if getattr(s, "npc_id", "") == nid), None)
                npc_final[nid] = extract_npc_state(state)

        # === Restore DecisionHub ===
        if dh and dh_capture:
            dh.compute = dh_capture.original
            dh_restored = True
            print(f"[E0-DECISION-PROBE] DecisionHub.compute restored (total_calls={dh_capture.call_count})")

    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        log_file.close()
        print("[E0-DECISION-PROBE] Releasing LLM lease...")
        try: release_lease()
        except: pass

    # === POST-RUN ANALYSIS ===
    log_text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    log_traces = parse_log_for_decision_traces(log_text)

    # Check TALK in candidates
    talk_in_wrapper = False
    talk_in_log = False
    talk_scores = []
    if dh_capture:
        for r in dh_capture.results:
            st = r.get("scores_trace")
            if isinstance(st, dict):
                for k, v in st.items():
                    if "talk" in str(k).lower():
                        talk_in_wrapper = True
                        talk_scores.append({"call": r["call_num"], "npc": r["npc_id"],
                                            "event": r["event_reason"], "talk_score": v,
                                            "winner": r["winner"]})
    for t in log_traces:
        blob = json.dumps(t, ensure_ascii=False)
        if "talk" in blob.lower():
            talk_in_log = True

    # TALK status
    if not dh_capture and not log_traces:
        talk_status = "UNVERIFIED — no DecisionHub data (neither wrapper nor log traces)"
    elif dh_capture and dh_capture.call_count == 0:
        talk_status = "BEFORE_SCORING — DecisionHub.compute never called (NPCs filtered before phase 5)"
    elif talk_in_wrapper or talk_in_log:
        talk_status = "AT_SCORING — TALK appeared in candidates (check if it won or lost)"
    else:
        talk_status = "BEFORE_SCORING — TALK not in candidates (filtered or relevance=0 for movement events)"

    # Proximity
    lost_proximity = any(pt.get("distance") and pt["distance"] > SPEAK_RADIUS for pt in positions_per_tick[1:])

    summary = {
        "run_id": RUN_ID,
        "timestamp": datetime.now().isoformat(),
        "campaign": cid,
        "ticks_completed": ticks_completed,
        "ticks_requested": N_TICKS,
        "error": error,
        "engine_found": engine_found,
        "npc_initial": npc_initial,
        "npc_final": npc_final,
        "positions_per_tick": positions_per_tick,
        "speak_radius": SPEAK_RADIUS,
        "lost_proximity": lost_proximity,
        "decision_hub": {
            "found": dh is not None,
            "location": dh_location,
            "wrapped": dh_capture is not None,
            "restored": dh_restored,
            "call_count": dh_capture.call_count if dh_capture else 0,
            "results": dh_capture.results if dh_capture else [],
        },
        "log_decision_traces": log_traces,
        "talk_analysis": {
            "talk_in_wrapper": talk_in_wrapper,
            "talk_in_log": talk_in_log,
            "talk_scores": talk_scores,
            "talk_status": talk_status,
        },
    }

    sp = OUT / "summary.json"
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    rp = OUT / "report.md"
    with open(rp, "w", encoding="utf-8") as f:
        f.write(f"# E0-PILOT-3 Decision Probe Report\n\n")
        f.write(f"Run: {RUN_ID} | {summary['timestamp']}\n")
        f.write(f"Campaign: {cid} | Ticks: {ticks_completed}/{N_TICKS}\n\n")
        if error:
            f.write(f"**ERROR:** {error}\n\n")

        f.write(f"## 1. Runtime NPC psychology (initial)\n\n")
        for nid in PAIR:
            ns = npc_initial.get(nid, {})
            f.write(f"### {nid}\n")
            f.write(f"- drives: `{ns.get('drives')}`\n")
            f.write(f"- psyche: `{ns.get('psyche')}`\n")
            f.write(f"- will_state: `{ns.get('will_state')}`\n")
            f.write(f"- stress: `{ns.get('stress')}`\n")
            f.write(f"- consciousness: `{ns.get('consciousness')}`\n")
            f.write(f"- emotion: `{ns.get('emotion')}`\n")
            f.write(f"- affective_load: `{ns.get('affective_load')}`\n")
            f.write(f"- relationship_cache_count: `{ns.get('relationship_cache_count')}`\n")
            f.write(f"- relationship_cache: `{ns.get('relationship_cache')}`\n")
            f.write(f"- activity_state: `{ns.get('activity_state')}`\n\n")

        f.write(f"## 2. Positions and distance\n\n")
        f.write(f"| Tick | Lusya | Tornin | Dist | In range (<= {SPEAK_RADIUS})? |\n")
        f.write(f"|------|-------|--------|------|------|\n")
        for pt in positions_per_tick:
            lus = pt["positions"].get("maid_lusya", {})
            tor = pt["positions"].get("tavern_keeper_tornin", {})
            d = pt["distance"]
            f.write(f"| {pt['tick']} | {lus.get('node','?')}({lus.get('x')},{lus.get('y')}) | "
                    f"{tor.get('node','?')}({tor.get('x')},{tor.get('y')}) | "
                    f"{d} | {'YES' if d and d <= SPEAK_RADIUS else 'NO'} |\n")
        f.write(f"\nLost proximity during run: **{lost_proximity}**\n\n")

        f.write(f"## 3. DecisionHub\n\n")
        f.write(f"- Found: `{dh is not None}`\n")
        f.write(f"- Location: `{dh_location}`\n")
        f.write(f"- Wrapped (runner-level): `{dh_capture is not None}`\n")
        f.write(f"- Restored: `{dh_restored}`\n")
        f.write(f"- compute() call count: `{dh_capture.call_count if dh_capture else 0}`\n\n")

        if dh_capture and dh_capture.results:
            f.write(f"### DecisionHub calls (wrapper capture)\n\n")
            f.write(f"| # | NPC | Event type | Reason | Winner | Score | Scores trace |\n")
            f.write(f"|---|-----|-----------|--------|--------|-------|-------------|\n")
            for r in dh_capture.results:
                f.write(f"| {r['call_num']} | {r['npc_id']} | {r['event_type']} | {r['event_reason']} | "
                        f"**{r['winner']}** | {r['score']} | `{r['scores_trace']}` |\n")
            f.write(f"\n")

        if log_traces:
            f.write(f"### Log traces ([TRACE][DECISION_SCORE] / [DIAG_COMPONENTS])\n\n")
            for t in log_traces[:15]:
                f.write(f"- `{t}`\n")
            f.write(f"\n")
        else:
            f.write(f"### Log traces: **NONE found** — [TRACE][DECISION_SCORE] not printed (gated or DecisionHub not reached)\n\n")

        f.write(f"## 4. TALK analysis\n\n")
        f.write(f"- TALK in wrapper candidates: `{talk_in_wrapper}`\n")
        f.write(f"- TALK in log traces: `{talk_in_log}`\n")
        f.write(f"- TALK scores: `{talk_scores}`\n")
        f.write(f"- **TALK status: {talk_status}**\n\n")

        f.write(f"## 5. Verdict per conclusion\n\n")
        v_runtime = "VERIFIED" if any(ns.get("drives") for ns in npc_initial.values()) else "UNVERIFIED"
        v_dh_reached = "VERIFIED" if (dh_capture and dh_capture.call_count > 0) else ("UNVERIFIED" if not dh_capture else "PARTIALLY VERIFIED")
        v_talk_candidate = "VERIFIED" if (talk_in_wrapper or talk_in_log) else ("UNVERIFIED" if not dh_capture else "PARTIALLY VERIFIED")
        v_talk_blocked = "VERIFIED" if talk_status.startswith("BEFORE") else "NOT_APPLICABLE"
        v_proximity = "VERIFIED" if lost_proximity else ("PARTIALLY VERIFIED" if positions_per_tick else "UNVERIFIED")

        f.write(f"| Conclusion | Status |\n|---|---|\n")
        f.write(f"| Runtime psychology data exists (drives, psyche) | {v_runtime} |\n")
        f.write(f"| Execution reaches DecisionHub.compute | {v_dh_reached} |\n")
        f.write(f"| TALK appears among candidates | {v_talk_candidate} |\n")
        f.write(f"| TALK blocked before scoring | {v_talk_blocked} |\n")
        f.write(f"| NPCs lose proximity (> {SPEAK_RADIUS}m) | {v_proximity} |\n\n")

        f.write(f"## 6. NPC final state (after {ticks_completed} ticks)\n\n")
        for nid in PAIR:
            ns = npc_final.get(nid, {})
            f.write(f"### {nid}\n")
            f.write(f"- drives: `{ns.get('drives')}`\n")
            f.write(f"- will_state: `{ns.get('will_state')}`\n")
            f.write(f"- stress: `{ns.get('stress')}`\n")
            f.write(f"- relationship_cache_count: `{ns.get('relationship_cache_count')}`\n\n")

    # Console summary
    print(f"[E0-DECISION-PROBE] DONE")
    print(f"  Artifacts: {OUT}")
    print(f"  report.md: {rp}")
    print(f"  Ticks: {ticks_completed}/{N_TICKS}")
    print(f"  DecisionHub: found={dh is not None}, calls={dh_capture.call_count if dh_capture else 0}")
    print(f"  TALK status: {talk_status}")
    print(f"  Lost proximity: {lost_proximity}")
    if error:
        print(f"  ERROR: {error}")


if __name__ == "__main__":
    main()
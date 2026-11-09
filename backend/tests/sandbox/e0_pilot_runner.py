"""path: /project/backend/tests/sandbox/e0_pilot_runner.py
Purpose: E0-PILOT-1 v2 - autonomous 30-tick Lusya <-> Tornin, semantic coherence focus.
Dependencies: tests/gameplay/harness.py, app.services.llm.runtime.client
Output: reports/experiments/e0_pilot_1/{run_log.txt, summary.json, chain_report.md}
"""
import json, sys, re, traceback
from pathlib import Path
from datetime import datetime

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.llm.runtime.client import ensure_llm, release_lease

PAIR = ["maid_lusya", "tavern_keeper_tornin"]
N_TICKS = 30
RUN_ID = "e0_pilot_1"
OUT = Path("reports/experiments") / RUN_ID
OUT.mkdir(parents=True, exist_ok=True)
LOG_PATH = OUT / "run_log.txt"


class EventCapture:
    def __init__(self):
        self.npc_spoke = []
        self.comm_claims = []
        self.all_events = []
    def on_event(self, event):
        try:
            etype = str(getattr(event, "event_type", "") or getattr(event, "type", "") or "")
            payload = getattr(event, "payload", {}) or {}
            if not isinstance(payload, dict):
                payload = {"_raw": str(payload)[:200]}
            actor = str(getattr(event, "actor_id", "") or payload.get("actor_id", payload.get("speaker_id", "")))
            target = str(getattr(event, "target_id", "") or payload.get("target_id", payload.get("listener_id", "")))
            tick = getattr(event, "tick", 0) or payload.get("tick", 0)
            rec = {"event_type": etype, "actor": actor, "target": target, "tick": tick}
            self.all_events.append(rec)
            eu = etype.upper()
            if "NPC_SPOKE" in eu:
                rec["text"] = str(payload.get("text", ""))[:400]
                rec["intent"] = str(payload.get("intent", payload.get("intent_type", "")))
                self.npc_spoke.append(rec)
            elif "COMMUNICATION_CLAIM" in eu or "COMM_CLAIM" in eu:
                rec["proposition"] = payload.get("proposition", {})
                self.comm_claims.append(rec)
        except Exception as e:
            self.all_events.append({"_error": str(e)})


def find_attr(obj, names):
    for n in names:
        v = getattr(obj, n, None)
        if v is not None:
            return v, n
    return None, None


def read_scene(gl, cid):
    ssm, _ = find_attr(gl, ["_scene_state_manager", "scene_state_manager", "_scene_mgr"])
    if not ssm:
        return {"_error": "no ssm"}
    try:
        scene = ssm.get_scene_state(cid, "tavern")
        if not isinstance(scene, dict):
            return {"_error": f"scene is {type(scene).__name__}"}
        return {
            "tick": scene.get("tick", 0),
            "game_time_seconds": scene.get("game_time_seconds", 0),
            "npc_positions": {k: (v.get("position","") if isinstance(v,dict) else str(v))
                              for k,v in scene.get("npc_positions",{}).items()},
            "pending_tasks": [{"speaker": str(t.get("request",{}).get("speaker_id","")),
                               "target": str(t.get("request",{}).get("target_id","")),
                               "prepared_prompt": str(t.get("request",{}).get("prepared_prompt",""))[:200]}
                              for t in scene.get("pending_tasks",[]) if isinstance(t, dict)],
        }
    except Exception as e:
        return {"_error": str(e)}


def read_epistemic(gl, cid, npcs):
    ep, attr = find_attr(gl, ["_epistemic_store", "epistemic_store", "_epistemic"])
    result = {"_source": "none", "_npcs": {}}
    if ep:
        result["_source"] = f"game_loop.{attr}"
        for nid in npcs:
            try:
                recs = ep.get_all_for_agent(nid)
                result["_npcs"][nid] = {
                    "_count": len(recs),
                    "_top3": [{"prop": str(r.proposition), "conf": r.confidence,
                               "source": r.source_id, "stype": getattr(r,"source_type","")}
                              for r in sorted(recs, key=lambda x: x.confidence, reverse=True)[:3]]
                }
            except Exception as e:
                result["_npcs"][nid] = {"_error": str(e)}
    else:
        ssm, _ = find_attr(gl, ["_scene_state_manager", "scene_state_manager"])
        if ssm:
            try:
                scene = ssm.get_scene_state(cid, "tavern")
                recs = scene.get("epistemic_records", [])
                result["_source"] = "scene_state[epistemic_records]"
                result["_count"] = len(recs) if isinstance(recs, list) else 0
            except Exception as e:
                result["_error"] = str(e)
    return result


def read_cognition(gl, npcs):
    resolver, attr = find_attr(gl, ["_cognition_resolver", "cognition_resolver",
                                    "_cognition_context_resolver", "_cog_resolver"])
    diag = {"resolver_found": resolver is not None}
    if not resolver:
        diag["note"] = "CognitionContextResolver not on game_loop"
        return diag
    diag["resolver_attr"] = attr
    ep = getattr(resolver, "_epistemic_store", None)
    diag["epistemic_store_wired"] = ep is not None
    diag["epistemic_store_type"] = type(ep).__name__ if ep else "NoneType"
    for nid in npcs:
        try:
            block = resolver.resolve_block(nid, partner_id="player")
            diag[f"resolve_block_{nid}"] = {
                "empty": len(block) == 0,
                "length": len(block),
                "has_beliefs": len(block) > 80,
                "preview": block[:300],
            }
        except Exception as e:
            diag[f"resolve_block_{nid}"] = {"_error": str(e)}
    return diag


def analyze_semantic_coherence(spoke_records):
    """For each NPC_SPOKE, find interlocutor's previous replica; compute lexical overlap."""
    sorted_sp = sorted(spoke_records, key=lambda s: s.get("tick", 0))
    results = []
    for i, sp in enumerate(sorted_sp):
        speaker = sp.get("actor", "")
        target = sp.get("target", "")
        tick = sp.get("tick", 0)
        text = sp.get("text", "")
        entry = {
            "tick": tick, "speaker": speaker, "target": target,
            "text_preview": text[:200],
        }
        # Find target's most recent replica to speaker before this one
        prev = None
        for j in range(i - 1, -1, -1):
            p = sorted_sp[j]
            if p.get("actor", "") == target and p.get("target", "") == speaker:
                prev = p
                break
        if not prev:
            entry["classification"] = "monologue"
            entry["note"] = "no prior replica from target"
            entry["lexical_overlap"] = 0
            results.append(entry)
            continue
        prev_text = prev.get("text", "")
        entry["prev_tick"] = prev.get("tick", 0)
        entry["prev_text_preview"] = prev_text[:200]
        # Lexical overlap: words >= 4 chars (content words proxy, avoids stop-word issue)
        prev_content = {w for w in re.findall(r'[\w\u0400-\u04ff]+', prev_text.lower()) if len(w) >= 4}
        curr_content = {w for w in re.findall(r'[\w\u0400-\u04ff]+', text.lower()) if len(w) >= 4}
        overlap = prev_content & curr_content
        entry["lexical_overlap"] = len(overlap)
        entry["overlap_words"] = list(overlap)[:10]
        if len(overlap) >= 3:
            entry["classification"] = "linked"
        elif len(overlap) >= 1:
            entry["classification"] = "weak"
        else:
            entry["classification"] = "no_link"
        results.append(entry)
    return results


def parse_decision_traces(log_text):
    """Parse [TRACE][DECISION_SCORE] lines from run_log.txt"""
    traces = []
    pattern = r'\[TRACE\]\[DECISION_SCORE\]\s*npc=(\S+)\s+winner=(\S+)\s+top3=(\[.*?\])'
    for m in re.finditer(pattern, log_text):
        npc, winner, top3 = m.groups()
        traces.append({"npc": npc, "winner": winner, "top3": top3[:200]})
    # Also try [DIAG_COMPONENTS]
    diag_pattern = r'\[DIAG_COMPONENTS\]\s*npc=(\S+)\s+intent=(\S+)\s+base=([\d.]+)'
    for m in re.finditer(diag_pattern, log_text):
        npc, intent, base = m.groups()
        traces.append({"npc": npc, "intent": intent, "base": float(base), "_source": "DIAG_COMPONENTS"})
    return traces


def main():
    # Redirect ALL stdout/stderr to run_log.txt
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = log_file
    sys.stderr = log_file

    print(f"[E0-PILOT-1 v2] START {datetime.now().isoformat()}")
    print(f"[E0-PILOT-1 v2] Output: {OUT}")

    url = None
    cap = EventCapture()
    ticks = []
    snap_start = {}
    snap_end = {}
    cog = {}
    error = None

    try:
        print("[E0-PILOT-1 v2] Acquiring LLM lease...")
        url = ensure_llm(label="experiment:E0")
        print(f"[E0-PILOT-1 v2] LLM URL: {url}")

        from tests.gameplay.harness import TavernGameplayHarness
        h = TavernGameplayHarness()
        h.new_game()

        # campaign_id: attribute OR method (harness sets it as attr after new_game)
        raw_cid = h.campaign_id
        cid = raw_cid() if callable(raw_cid) else str(raw_cid)
        gl = h.game_loop
        print(f"[E0-PILOT-1 v2] Campaign={cid}, GameLoop={type(gl).__name__}")

        # Explore attrs
        gl_attrs = [a for a in dir(gl) if not a.startswith("__")]
        interesting = [a for a in gl_attrs if any(k in a.lower() for k in
            ["epistemic","scene","event","memory","cogn","npc","dialogue","tick"])]
        print(f"[E0-PILOT-1 v2] GameLoop attrs: {interesting[:25]}")

        # Subscribe to events
        eb, eb_attr = find_attr(gl, ["_event_bus", "event_bus", "_event_bus_instance", "_bus"])
        if eb:
            for et in ["NPC_SPOKE", "COMMUNICATION_CLAIM", "npc_spoke", "comm_claim"]:
                try: eb.subscribe(et, cap.on_event)
                except: pass
            print(f"[E0-PILOT-1 v2] EventBus: attr={eb_attr}, npc_spoke_cap={len(cap.npc_spoke)}")
        else:
            print("[E0-PILOT-1 v2] WARNING: EventBus not found")

        # Initial snapshot
        snap_start = {"scene": read_scene(gl, cid), "epistemic": read_epistemic(gl, cid, PAIR)}
        print(f"[E0-PILOT-1 v2] Initial: tick={snap_start['scene'].get('tick')}, "
              f"game_time={snap_start['scene'].get('game_time_seconds')}")
        for nid in PAIR:
            ec = snap_start['epistemic'].get('_npcs', {}).get(nid, {})
            print(f"[E0-PILOT-1 v2] {nid} initial beliefs: {ec.get('_count', '?')}")

        # Run ticks
        for n in range(1, N_TICKS + 1):
            try:
                res = gl.idle_tick(cid)
                scene = read_scene(gl, cid)
                ep = read_epistemic(gl, cid, PAIR)
                tick_tick = scene.get("tick", n)
                spoke_this = [s for s in cap.npc_spoke if s.get("tick") == tick_tick]
                claims_this = [c for c in cap.comm_claims if c.get("tick") == tick_tick]
                # Per-NPC epistemic count
                ep_counts = {}
                for nid in PAIR:
                    ec = ep.get("_npcs", {}).get(nid, {})
                    ep_counts[nid] = ec.get("_count", -1)
                ticks.append({
                    "n": n,
                    "status": res.get("status") if isinstance(res, dict) else str(res)[:50],
                    "scene_tick": scene.get("tick"),
                    "game_time": scene.get("game_time_seconds"),
                    "npc_positions": {k: v for k, v in scene.get("npc_positions", {}).items()
                                      if k in PAIR or k == "player"},
                    "pending_tasks": scene.get("pending_tasks", []),
                    "epistemic_counts": ep_counts,
                    "spoke_this_tick": spoke_this,
                    "claims_this_tick": claims_this,
                })
                print(f"  T{n}: status={ticks[-1]['status']}, "
                      f"game_time={scene.get('game_time_seconds')}, "
                      f"spoke={len(spoke_this)}, claims={len(claims_this)}, "
                      f"ep={ep_counts}")
            except Exception as e:
                print(f"  T{n} FAILED: {type(e).__name__}: {e}")
                traceback.print_exc()
                ticks.append({"n": n, "error": str(e)})
                break

        snap_end = {"scene": read_scene(gl, cid), "epistemic": read_epistemic(gl, cid, PAIR)}
        cog = read_cognition(gl, PAIR)

    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        log_file.close()
        print("[E0-PILOT-1 v2] Releasing LLM lease...")
        try: release_lease()
        except: pass

    # Post-run analysis (console + files restored)
    # Parse decision traces from log
    log_text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    decision_traces = parse_decision_traces(log_text)

    # Semantic coherence
    coherence = analyze_semantic_coherence(cap.npc_spoke)
    coh_counts = {"linked": 0, "weak": 0, "no_link": 0, "monologue": 0}
    for c in coherence:
        coh_counts[c["classification"]] = coh_counts.get(c["classification"], 0) + 1

    # Per-NPC epistemic trajectory
    ep_trajectory = {nid: [] for nid in PAIR}
    for t in ticks:
        ec = t.get("epistemic_counts", {})
        for nid in PAIR:
            ep_trajectory[nid].append({"tick": t.get("n"), "count": ec.get(nid, -1)})

    # Per-NPC decision winners (from parsed traces)
    per_npc_winners = {nid: [] for nid in PAIR}
    for dt in decision_traces:
        npc = dt.get("npc", "")
        if npc in PAIR:
            per_npc_winners[npc].append(dt.get("winner", dt.get("intent", "")))

    summary = {
        "run_id": RUN_ID, "timestamp": datetime.now().isoformat(),
        "campaign": cid if 'cid' in dir() else "unknown",
        "n_ticks_completed": len([t for t in ticks if "error" not in t]),
        "n_ticks_failed": len([t for t in ticks if "error" in t]),
        "pair": PAIR, "llm_url": url,
        "error": error,
        "game_time": {
            "start": snap_start.get("scene", {}).get("game_time_seconds"),
            "end": snap_end.get("scene", {}).get("game_time_seconds"),
        },
        "event_counts": {
            "npc_spoke": len(cap.npc_spoke),
            "comm_claims": len(cap.comm_claims),
            "all_events": len(cap.all_events),
        },
        "semantic_coherence_counts": coh_counts,
        "cognition_diagnostic": cog,
        "per_npc_epistemic_trajectory": ep_trajectory,
        "per_npc_decision_winners": per_npc_winners,
        "npc_spoke_records": cap.npc_spoke,
        "comm_claim_records": cap.comm_claims,
        "coherence_analysis": coherence,
        "decision_traces_sample": decision_traces[:20],
        "ticks": ticks,
    }

    sp = OUT / "summary.json"
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    cp = OUT / "chain_report.md"
    with open(cp, "w", encoding="utf-8") as f:
        f.write(f"# E0-PILOT-1 v2 Chain Report\n\nRun: {RUN_ID} | {summary['timestamp']}\n")
        f.write(f"Campaign: {summary['campaign']} | Ticks: {summary['n_ticks_completed']}/{N_TICKS}\n")
        if error:
            f.write(f"**ERROR:** {error}\n")
        f.write(f"\n## Counts\n\n- NPC_SPOKE: {len(cap.npc_spoke)}\n")
        f.write(f"- COMMUNICATION_CLAIM: {len(cap.comm_claims)}\n")
        f.write(f"- Game time: {summary['game_time']['start']} -> {summary['game_time']['end']}\n\n")
        f.write(f"## Semantic coherence (does each replica depend on the previous?)\n\n")
        f.write(f"- linked (>=3 content words overlap): {coh_counts['linked']}\n")
        f.write(f"- weak (1-2 words): {coh_counts['weak']}\n")
        f.write(f"- no_link (0 overlap): {coh_counts['no_link']}\n")
        f.write(f"- monologue (no prior from target): {coh_counts['monologue']}\n\n")
        f.write(f"### Per-replica analysis\n\n")
        for c in coherence:
            f.write(f"- T{c['tick']} {c['speaker']}->{c['target']}: **{c['classification']}** "
                    f"(overlap={c.get('lexical_overlap',0)}, words={c.get('overlap_words',[])})\n")
            f.write(f"  text: {c.get('text_preview','')[:120]}\n")
            if 'prev_text_preview' in c:
                f.write(f"  prev: {c.get('prev_text_preview','')[:120]}\n")
        f.write(f"\n## Per-NPC cognitive position\n\n")
        for nid in PAIR:
            f.write(f"### {nid}\n")
            f.write(f"- EpistemicStore trajectory: {ep_trajectory[nid]}\n")
            winners = per_npc_winners.get(nid, [])
            f.write(f"- DecisionHub winners ({len(winners)} traces): {winners[:15]}\n\n")
        f.write(f"## CognitionContextResolver\n\n```json\n{json.dumps(cog, ensure_ascii=False, indent=2, default=str)}\n```\n\n")
        f.write(f"## NPC_SPOKE records\n\n")
        for i, s in enumerate(cap.npc_spoke):
            f.write(f"### {i+1}. T{s.get('tick')} {s.get('actor')}->{s.get('target')} [{s.get('intent')}]\n")
            f.write(f"   text: {s.get('text', '')[:250]}\n\n")
        f.write(f"## COMMUNICATION_CLAIM records\n\n")
        for i, c in enumerate(cap.comm_claims):
            f.write(f"### {i+1}. T{c.get('tick')} {c.get('actor')}->{c.get('target')}\n")
            f.write(f"   proposition: {c.get('proposition')}\n\n")

    # CONSOLE OUTPUT (minimal)
    print(f"[E0-PILOT-1 v2] DONE")
    print(f"  Artifacts: {OUT}")
    print(f"  run_log.txt: {LOG_PATH} (raw stdout, includes CCH_SEED noise)")
    print(f"  summary.json: {sp}")
    print(f"  chain_report.md: {cp}")
    print(f"  NPC_SPOKE: {len(cap.npc_spoke)} | COMM_CLAIM: {len(cap.comm_claims)}")
    print(f"  Semantic coherence: linked={coh_counts['linked']}, weak={coh_counts['weak']}, "
          f"no_link={coh_counts['no_link']}, monologue={coh_counts['monologue']}")
    print(f"  Cognition: resolver_found={cog.get('resolver_found')}, "
          f"epistemic_wired={cog.get('epistemic_store_wired')}")
    if error:
        print(f"  ERROR: {error}")


if __name__ == "__main__":
    main()
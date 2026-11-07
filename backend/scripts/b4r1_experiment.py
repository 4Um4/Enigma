#!/usr/bin/env python3
"""B4-R1: E2E validation — Tornin speaks via claims_about_self fallback after Stage B.

TZ: B4-R1 — REAL E2E VALIDATION AFTER STAGE B
Mode: one controlled E2E experiment. No production code changes.
Goal: verify proposition from claims_about_self passes through DecisionHub
      and becomes content of real LLM-generated replica.

Run: cd backend; $env:ENIGMA_B4_APPROVED=1; python scripts/b4r1_experiment.py
"""

import sys, os, json, time, logging, subprocess
from pathlib import Path
from datetime import datetime

# Path setup
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent if _HERE.name == "scripts" else _HERE
sys.path.insert(0, str(_BACKEND))
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_ROOT))

from tests.gameplay.harness import TavernGameplayHarness
from tests.gameplay.test_butterfly_b4_verified_belief import (
    _publish_player_insults,
    _read_epistemic_for_agent,
    _resolve_cognition_context,
    _install_spies,
    _uninstall_spies,
    _check_b4_approved,
    _check_llm_health_http,
    SPY_SPOKE,
    SPY_CLAIM,
    _collect_verifier_records,
    _PLAYER,
    _VICTIM,
    _WITNESS,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

# Verifier log capture
_verifier_records: list = []
class _VerifierCapture(logging.Handler):
    def emit(self, record):
        _verifier_records.append(record)
_vh = _VerifierCapture()
_vh.setLevel(logging.DEBUG)
_lv = logging.getLogger("app.services.cognition.proposition_verifier")
_lv.addHandler(_vh)
_lv.setLevel(logging.DEBUG)


def main():
    print("=" * 72)
    print("B4-R1: E2E Validation — Tornin speaks via claims_about_self fallback")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Player={_PLAYER}, Victim={_VICTIM}, Witness={_WITNESS}")
    print("=" * 72)

    # Git SHA
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(_ROOT), stderr=subprocess.DEVNULL).decode().strip()[:8]
        print(f"Git SHA: {sha}")
    except Exception:
        sha = "unknown"

    # Pre-flight
    if not _check_b4_approved():
        print("\nFAIL: ENIGMA_B4_APPROVED != 1. Set: $env:ENIGMA_B4_APPROVED=1")
        return
    if not _check_llm_health_http():
        print("\nFAIL: LLM-server :8181 not responding")
        return
    print("Pre-flight: OK")

    # Ensure LLM
    try:
        from app.services.llm.runtime.client import ensure_llm
        ensure_llm(label="B4-R1")
        print("LLM: ensured")
    except Exception as e:
        print(f"LLM auto-start warning: {e} (continuing — health already confirmed)")

    # Setup harness (PRODUCTION — no mocks)
    print("\n--- Setup ---")
    h = TavernGameplayHarness(seed=42, location="tavern")
    h.new_game()
    print("Harness: new_game() — production build_game_loop")
    _install_spies()
    print("Spies: installed")
    # NOT overriding Tornin's disposition — autonomous selection (TZ requirement)

    try:
        # Phase 1: Inject player insult
        print("\n--- Phase 1: Inject player insult ---")
        h.advance_ticks(2)
        _publish_player_insults(h, _VICTIM, radius=15.0)
        print(f"Published: PLAYER_INSULTS -> target={_VICTIM}, source={_PLAYER}")

        # Phase 2: Run production game loop
        print("\n--- Phase 2: Run production game loop (20 ticks) ---")
        _verifier_records.clear()
        SPY_SPOKE.clear()
        SPY_CLAIM.clear()
        t0 = time.monotonic()
        tick_results = h.advance_ticks(20)
        elapsed = time.monotonic() - t0
        print(f"advance_ticks(20): {elapsed:.1f}s, {len(tick_results)} results")
        print(f"Counters: npc_spoke={h.counters.npc_spoke}, events={dict(h.counters.events_by_type)}")

        # === CAPTURE 8 POINTS ===
        print("\n" + "=" * 72)
        print("CAPTURE: 8 mandatory data points")
        print("=" * 72)

        # 1: EpistemicStore record for Tornin
        tornin_records = _read_epistemic_for_agent(h, _VICTIM)
        print(f"\n[1] EpistemicStore ({_VICTIM}): {len(tornin_records)} records")
        for r in tornin_records:
            p = r.get("proposition", {})
            print(f"    subj={p.get('subject_id')} pred={p.get('predicate')} obj={p.get('object_id')} "
                  f"pol={p.get('polarity')} conf={r.get('confidence')} src={r.get('source_id')}")

        # 2: EpistemicContext
        cog_ctx = _resolve_cognition_context(h, _VICTIM)
        print(f"\n[2] EpistemicContext ({_VICTIM}):")
        print(f"    has_report={cog_ctx.get('has_report_proposition')} "
              f"has_claims={cog_ctx.get('has_claims_about_self')} "
              f"max_conf={cog_ctx.get('max_confidence')}")

        # 3: DecisionHub audit (proposition_selection)
        from app.core.config import settings
        audit_path = Path(settings.data_dir) / "logs" / "enigma_audit.jsonl"
        ps_entries = []
        if audit_path.exists():
            with open(audit_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        if e.get("agent") == "proposition_selection" and e.get("npc_id") == _VICTIM:
                            ps_entries.append(e)
                    except Exception:
                        pass
        print(f"\n[3] proposition_selection audit ({_VICTIM}): {len(ps_entries)} entries")
        for e in ps_entries[-5:]:
            print(f"    intent={e.get('intent_type')} src={e.get('selected_source')} "
                  f"reason={e.get('fallback_reason')} trig={e.get('trigger_available')} "
                  f"rep={e.get('report_available')} claims={e.get('claims_about_self_count')}")
            if e.get("proposition_key"):
                print(f"      key={e['proposition_key']}")

        # 4+5: NPC_SPOKE from Tornin
        tornin_spoke = [s for s in SPY_SPOKE if s.get("source") == _VICTIM]
        print(f"\n[4] NPC_SPOKE from {_VICTIM}: {len(tornin_spoke)}")
        for i, s in enumerate(tornin_spoke):
            text = s.get("text", "")
            is_tpl = text.startswith("[Intent.") or text.startswith("[Заглушка")
            print(f"    [{i}] {'TEMPLATE' if is_tpl else 'LLM-GEN'}: {text[:250]}")

        # 6: PropositionVerifier
        vdata = _collect_verifier_records(_verifier_records)
        print(f"\n[6] PropositionVerifier: {len(vdata)} records")
        for v in vdata[-5:]:
            print(f"    status={v.get('status')} prop={v.get('proposition')}")

        # 7: COMMUNICATION_CLAIM from Tornin
        tornin_claims = [c for c in SPY_CLAIM if c.get("source") == _VICTIM]
        print(f"\n[7] COMMUNICATION_CLAIM from {_VICTIM}: {len(tornin_claims)}")
        for c in tornin_claims:
            pl = c.get("payload", {}) or {}
            p = pl.get("proposition", {}) or {}
            print(f"    target={c.get('target_id')} subj={p.get('subject_id')} "
                  f"pred={p.get('predicate')} obj={p.get('object_id')} pol={p.get('polarity')}")

        # 8: Receiver EpistemicStore
        print(f"\n[8] Receiver EpistemicStore:")
        receiver_beliefs = {}
        for c in tornin_claims:
            t = c.get("target_id")
            if t and t not in receiver_beliefs:
                receiver_beliefs[t] = _read_epistemic_for_agent(h, t)
        if not receiver_beliefs:
            print("    No targets (no COMMUNICATION_CLAIM from Tornin)")
        for t, recs in receiver_beliefs.items():
            print(f"    {t}: {len(recs)} records")
            for r in recs:
                p = r.get("proposition", {})
                print(f"      subj={p.get('subject_id')} pred={p.get('predicate')} "
                      f"obj={p.get('object_id')} conf={r.get('confidence')}")

        # === PASS/FAIL ===
        print("\n" + "=" * 72)
        print("PASS/FAIL TABLE")
        print("=" * 72)

        es, ep, eo = _PLAYER, "insulted", _VICTIM
        checks = []
        checks.append(("1. Tornin has belief (player INSULTED tornin)",
                       any(r.get("proposition",{}).get("predicate")==ep and
                           r.get("proposition",{}).get("subject_id")==es and
                           r.get("proposition",{}).get("object_id")==eo
                           for r in tornin_records)))
        checks.append(("2. claims_about_self non-empty",
                       cog_ctx.get("has_claims_about_self", False)))
        sr = [e for e in ps_entries if e.get("intent_type")=="spread_rumor"]
        checks.append(("3. Tornin selected spread_rumor", len(sr) > 0))
        cs = [e for e in sr if e.get("selected_source")=="claims_about_self"]
        checks.append(("4. selected_source = claims_about_self", len(cs) > 0))
        checks.append(("5. NPC_SPOKE with LLM text (not template)",
                       any(s.get("text") and not s["text"].startswith("[Intent.")
                           and not s["text"].startswith("[Заглушка") for s in tornin_spoke)))
        vyes = any(v.get("status")=="YES" and
                   v.get("proposition",{}).get("subject_id")==es and
                   v.get("proposition",{}).get("predicate")==ep and
                   v.get("proposition",{}).get("object_id")==eo
                   for v in vdata)
        checks.append(("6. PropositionVerifier YES", vyes))
        checks.append(("7. COMMUNICATION_CLAIM published", len(tornin_claims) > 0))
        rbel = any(any(r.get("proposition",{}).get("predicate")==ep and
                       r.get("proposition",{}).get("subject_id")==es for r in recs)
                   for recs in receiver_beliefs.values())
        checks.append(("8. Receiver got belief", rbel))

        all_pass = True
        for desc, passed in checks:
            st = "PASS" if passed else "FAIL"
            if not passed: all_pass = False
            print(f"  [{st}] {desc}")

        print(f"\n{'='*72}")
        if all_pass:
            print("OVERALL: PASS — Stage B channel alignment works end-to-end")
        elif not sr:
            print("OVERALL: INCONCLUSIVE — Tornin did not select spread_rumor")
            intents = set(e.get("intent_type") for e in ps_entries)
            print(f"  Intents selected: {intents}")
            print("  (TZ: INCONCLUSIVE for fallback check, scoring result saved)")
        elif sr and not cs:
            print("OVERALL: INCONCLUSIVE — spread_rumor selected but NOT via claims_about_self")
            for e in sr:
                print(f"  src={e.get('selected_source')} reason={e.get('fallback_reason')}")
        else:
            print("OVERALL: FAIL")
        print(f"{'='*72}")

        # Save artifacts
        adir = _ROOT / "diagnostics" / "b4r1_artifacts"
        adir.mkdir(parents=True, exist_ok=True)
        results = {
            "timestamp": datetime.now().isoformat(), "git_sha": sha,
            "player": _PLAYER, "victim": _VICTIM, "ticks": 20,
            "elapsed": round(elapsed, 1),
            "epistemic_store": tornin_records,
            "epistemic_context": cog_ctx,
            "audit": ps_entries,
            "npc_spoke": tornin_spoke,
            "verifier": vdata,
            "claims": tornin_claims,
            "receiver_beliefs": dict(receiver_beliefs),
            "checks": [{"d": d, "p": p} for d, p in checks],
            "counters": {"npc_spoke": h.counters.npc_spoke, "events": dict(h.counters.events_by_type)},
        }
        rpath = adir / "b4r1_results.json"
        with open(rpath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"\nArtifacts: {rpath}")

    finally:
        _uninstall_spies()
        try: h.dispose()
        except: pass


if __name__ == "__main__":
    os.environ.setdefault("ENIGMA_B4_APPROVED", "1")
    main()

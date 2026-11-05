"""S415 A/B v8 — USL-2 ACTION → WORLD STATE.

Chain: BIOGRAPHY → MEMORY → DECISION → ACTION → WORLD STATE.

A (bio enabled):    maid_lusya with Chronicle biography
B (control):        maid_lusya without Chronicle (4 monkeypatches), legacy static preserved

Stimulus: player_action("угрожаю служанке") → THREATEN → reactive path

Hooks:
  - NpcTickPipeline.run → capture movement_intents + decisions (npc_deltas)
  - MovementEngine.process_intents → capture SceneChange list

USL-2 criteria:
  A: intent=flee + movement_intents>0 + Δdist>0
  B: intent=idle/observe + movement_intents=0 + Δdist≈0
"""
from __future__ import annotations

import json
import math
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

NPC_ID = "maid_lusya"
PLAYER_ID = "player"
STIMULUS_TEXT = "я угрожаю служанке Люсе"
POST_STIMULUS_TICKS = 3

ARTIFACTS = ROOT / "artifacts" / "s415" / "ab_v8"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def euclidean(a: dict, b: dict) -> float:
    ax, ay = (a or {}).get("x", 0), (a or {}).get("y", 0)
    bx, by = (b or {}).get("x", 0), (b or {}).get("y", 0)
    return math.hypot(ax - bx, ay - by)


# ═══ Capture ════════════════════════════════════════════════════════════════

class Capture:
    def __init__(self):
        self.decisions = []
        self.movement_intents = []
        self.scene_changes = []

    def reset(self):
        self.decisions.clear()
        self.movement_intents.clear()
        self.scene_changes.clear()


CAPTURE = Capture()


def install_hooks():
    from app.services.npc.npc_tick_pipeline import NpcTickPipeline
    from app.services.spatial.movement_engine import MovementEngine

    orig_run = NpcTickPipeline.run

    @staticmethod
    def hooked_run(state, drf_ctx=None, rng_factory=None):
        mutation = orig_run(state, drf_ctx, rng_factory)
        try:
            for delta in (mutation.npc_deltas or []):
                npc_id = getattr(delta, "npc_id", "?")
                intent = getattr(delta, "intent", None)
                intent_val = intent.value if hasattr(intent, "value") else str(intent or "none")
                target = getattr(delta, "target", None)
                CAPTURE.decisions.append({
                    "tick": state.tick_id,
                    "npc_id": npc_id,
                    "intent": intent_val,
                    "target": target,
                })
            for mi in (mutation.movement_intents or []):
                actor = getattr(mi, "actor_id", "?")
                reason = getattr(mi, "reason", "?")
                gtype = type(mi).__name__
                CAPTURE.movement_intents.append({
                    "tick": state.tick_id,
                    "npc_id": actor,
                    "goal_type": gtype,
                    "reason": reason,
                })
        except Exception as e:
            print(f"[HOOK WARN] run capture: {e}")
        return mutation

    NpcTickPipeline.run = hooked_run

    orig_process = MovementEngine.process_intents

    def hooked_process(self, intents, *args, **kwargs):
        changes = orig_process(self, intents, *args, **kwargs)
        try:
            for sc in (changes or []):
                target = getattr(sc, "target", None) or getattr(sc, "npc_id", "?")
                field = getattr(sc, "field", "?")
                new_val = getattr(sc, "new_value", None)
                CAPTURE.scene_changes.append({
                    "target": target,
                    "field": field,
                    "new_value": str(new_val)[:120] if new_val else None,
                })
        except Exception as e:
            print(f"[HOOK WARN] process_intents capture: {e}")
        return changes

    MovementEngine.process_intents = hooked_process
    print("[HOOKS] Installed: NpcTickPipeline.run + MovementEngine.process_intents")


# ═══ Control monkeypatches ══════════════════════════════════════════════════

@contextmanager
def chronicle_seeder_disabled():
    from app.services.chronicle import chronicle_seeder

    orig_mem = chronicle_seeder.build_seed_memories
    orig_rel = chronicle_seeder.build_seed_relationships
    orig_imp = chronicle_seeder.build_seed_imprints
    orig_bel = chronicle_seeder.build_seed_beliefs

    chronicle_seeder.build_seed_memories = lambda npc_id, doc: ()
    chronicle_seeder.build_seed_relationships = lambda npc_id, doc: {}
    chronicle_seeder.build_seed_imprints = lambda doc: []
    chronicle_seeder.build_seed_beliefs = lambda doc: {}

    print("[CONTROL] Chronicle seeder DISABLED (4 monkeypatches)")
    try:
        yield
    finally:
        chronicle_seeder.build_seed_memories = orig_mem
        chronicle_seeder.build_seed_relationships = orig_rel
        chronicle_seeder.build_seed_imprints = orig_imp
        chronicle_seeder.build_seed_beliefs = orig_bel
        print("[CONTROL] Chronicle seeder RESTORED")


# ═══ Variant runner ═════════════════════════════════════════════════════════

def run_variant(label: str, disable_bio: bool) -> dict:
    from tests.gameplay.harness import TavernGameplayHarness

    print(f"\n{'═' * 60}")
    print(f"  VARIANT {label} — biography={'DISABLED (control)' if disable_bio else 'ENABLED'}")
    print(f"{'═' * 60}")

    CAPTURE.reset()
    harness = None

    try:
        if disable_bio:
            with chronicle_seeder_disabled():
                harness = TavernGameplayHarness(seed=42)
                harness.new_game()
        else:
            harness = TavernGameplayHarness(seed=42)
            harness.new_game()

        print(f"[{label}] new_game OK (campaign={harness.campaign_id})")

        # ── BEFORE: positions ──
        scene_before = harness.get_scene() or {}
        npc_pos_before = scene_before.get("npc_positions", {})

        lusya_before = npc_pos_before.get(NPC_ID, {})
        player_before = npc_pos_before.get(PLAYER_ID, {})

        lusya_pos_b = lusya_before.get("local_position", {})
        player_pos_b = player_before.get("local_position", {})

        dist_before = euclidean(lusya_pos_b, player_pos_b)

        # ── BEFORE: cognitive state ──
        npc_before = harness.inspect_npc(NPC_ID) or {}
        ncache = npc_before.get("narrative_cache", [])
        rcache = npc_before.get("relationship_cache", {})
        imprints = npc_before.get("affective_imprints", [])

        print(f"[{label}] BEFORE:")
        print(f"  lusya.pos  = {lusya_pos_b}")
        print(f"  player.pos = {player_pos_b}")
        print(f"  dist(lusya,player) = {dist_before:.2f}")
        print(f"  narrative_cache = {len(ncache) if ncache else 0}")
        print(f"  relationship_targets = {list((rcache or {}).keys())}")
        print(f"  affective_imprints = {len(imprints) if imprints else 0}")

        # ── STIMULUS ──
        print(f"[{label}] STIMULUS: player_action('{STIMULUS_TEXT}')")
        try:
            result = harness.player_action(STIMULUS_TEXT)
            print(f"[{label}] player_action OK ({type(result).__name__})")
        except Exception as e:
            print(f"[{label}] player_action ERROR: {type(e).__name__}: {e}")

        # ── POST-STIMULUS ticks ──
        print(f"[{label}] advance_ticks({POST_STIMULUS_TICKS})...")
        try:
            harness.advance_ticks(POST_STIMULUS_TICKS)
        except Exception as e:
            print(f"[{label}] advance_ticks ERROR: {type(e).__name__}: {e}")

        # ── AFTER: positions ──
        scene_after = harness.get_scene() or {}
        npc_pos_after = scene_after.get("npc_positions", {})

        lusya_after = npc_pos_after.get(NPC_ID, {})
        player_after = npc_pos_after.get(PLAYER_ID, {})

        lusya_pos_a = lusya_after.get("local_position", {})
        player_pos_a = player_after.get("local_position", {})

        dist_after = euclidean(lusya_pos_a, player_pos_a)
        delta_dist = dist_after - dist_before

        print(f"[{label}] AFTER:")
        print(f"  lusya.pos  = {lusya_pos_a}")
        print(f"  player.pos = {player_pos_a}")
        print(f"  dist(lusya,player) = {dist_after:.2f}")
        print(f"  Δdistance = {delta_dist:.2f}")

        # ── Captured metrics (maid_lusya only) ──
        l_decisions = [d for d in CAPTURE.decisions if d["npc_id"] == NPC_ID]
        l_movement = [m for m in CAPTURE.movement_intents if m["npc_id"] == NPC_ID]
        l_changes = [sc for sc in CAPTURE.scene_changes if sc["target"] == NPC_ID]

        print(f"[{label}] CAPTURED (maid_lusya only):")
        print(f"  decisions: {len(l_decisions)}")
        for d in l_decisions:
            print(f"    tick={d['tick']} intent={d['intent']} target={d['target']}")
        print(f"  movement_intents: {len(l_movement)}")
        for m in l_movement:
            print(f"    tick={m['tick']} type={m['goal_type']} reason={m['reason']}")
        print(f"  scene_changes: {len(l_changes)}")
        for sc in l_changes:
            print(f"    field={sc['field']} new_value={sc['new_value']}")

        return {
            "label": label,
            "bio_disabled": disable_bio,
            "cognitive": {
                "narrative_cache_count": len(ncache) if ncache else 0,
                "relationship_cache_targets": list((rcache or {}).keys()),
                "affective_imprints_count": len(imprints) if imprints else 0,
            },
            "positions": {
                "lusya_before": lusya_pos_b,
                "lusya_after": lusya_pos_a,
                "player_before": player_pos_b,
                "player_after": player_pos_a,
                "dist_before": dist_before,
                "dist_after": dist_after,
                "delta_dist": delta_dist,
            },
            "decisions": l_decisions,
            "movement_intents": l_movement,
            "scene_changes": l_changes,
        }

    finally:
        if harness:
            try:
                harness.dispose()
            except Exception:
                pass
            print(f"[{label}] harness disposed.")


# ═══ Main ═══════════════════════════════════════════════════════════════════

def main() -> int:
    print(f"\n[S415] A/B v8 — USL-2 ACTION → WORLD STATE — {ts()}")
    print(f"[S415] NPC: {NPC_ID}")
    print(f"[S415] Stimulus: player_action('{STIMULUS_TEXT}')")
    print(f"[S415] Post-stimulus ticks: {POST_STIMULUS_TICKS}")

    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    print(f"[S415] commit: {commit_sha}")

    install_hooks()

    result_A = run_variant("A", disable_bio=False)
    result_B = run_variant("B", disable_bio=True)

    # ── Comparison ──
    print(f"\n{'═' * 60}")
    print("  A/B v8 COMPARISON")
    print(f"{'═' * 60}")

    print(f"\n{'Metric':<40} {'A (bio)':<25} {'B (control)':<25}")
    print("─" * 90)

    print(f"{'narrative_cache_count':<40} {result_A['cognitive']['narrative_cache_count']:<25} {result_B['cognitive']['narrative_cache_count']:<25}")
    print(f"{'relationship_cache_targets':<40} {str(result_A['cognitive']['relationship_cache_targets']):<25} {str(result_B['cognitive']['relationship_cache_targets']):<25}")
    print(f"{'affective_imprints_count':<40} {result_A['cognitive']['affective_imprints_count']:<25} {result_B['cognitive']['affective_imprints_count']:<25}")

    A_intents = [d["intent"] for d in result_A["decisions"]]
    B_intents = [d["intent"] for d in result_B["decisions"]]
    print(f"{'decisions count':<40} {len(result_A['decisions']):<25} {len(result_B['decisions']):<25}")
    print(f"{'intents':<40} {str(A_intents):<25} {str(B_intents):<25}")
    print(f"{'movement_intents count':<40} {len(result_A['movement_intents']):<25} {len(result_B['movement_intents']):<25}")
    print(f"{'scene_changes count':<40} {len(result_A['scene_changes']):<25} {len(result_B['scene_changes']):<25}")
    print(f"{'dist(lusya,player) before':<40} {result_A['positions']['dist_before']:<25.2f} {result_B['positions']['dist_before']:<25.2f}")
    print(f"{'dist(lusya,player) after':<40} {result_A['positions']['dist_after']:<25.2f} {result_B['positions']['dist_after']:<25.2f}")
    print(f"{'Δdistance':<40} {result_A['positions']['delta_dist']:<25.2f} {result_B['positions']['delta_dist']:<25.2f}")

    # ── USL-2 verdict ──
    print(f"\n{'═' * 60}")
    print("  USL-2 VERDICT")
    print(f"{'═' * 60}")

    A_flee = any(d["intent"] == "flee" for d in result_A["decisions"])
    A_move = len(result_A["movement_intents"]) > 0
    A_change = len(result_A["scene_changes"]) > 0
    A_moved = abs(result_A["positions"]["delta_dist"]) > 0.01

    B_flee = any(d["intent"] == "flee" for d in result_B["decisions"])
    B_move = len(result_B["movement_intents"]) > 0
    B_moved = abs(result_B["positions"]["delta_dist"]) > 0.01

    print(f"  A (bio):     flee={A_flee}  movement={A_move}  sceneChange={A_change}  moved={A_moved}")
    print(f"  B (control): flee={B_flee}  movement={B_move}  moved={B_moved}")

    if A_flee and A_move and A_moved and not B_moved:
        verdict = "✅ USL-2 PROVEN — full chain BIO→MEM→DEC→ACT→WORLD"
    elif A_flee and A_move and A_change and not A_moved:
        verdict = "⚠️ PARTIAL — DEC→ACT proven, ACT→WORLD broken (SceneChange not applied to positions)"
    elif A_flee and A_move and not A_change:
        verdict = "⚠️ PARTIAL — DEC→ACT (movement_intents) proven, MovementEngine produced no SceneChange"
    elif A_flee and not A_move:
        verdict = "⚠️ PARTIAL — DEC proven (flee), ACT not generated (movement_intents empty)"
    elif not A_flee:
        verdict = "❌ OPEN — biography did not produce flee. Check stimulus/memory modifiers."
    else:
        verdict = "❌ OPEN — see metrics"

    print(f"\n  VERDICT: {verdict}")

    # ── Save artifacts ──
    report = {
        "timestamp": ts(),
        "commit_sha": commit_sha,
        "npc_id": NPC_ID,
        "stimulus": STIMULUS_TEXT,
        "post_stimulus_ticks": POST_STIMULUS_TICKS,
        "variant_A": result_A,
        "variant_B": result_B,
        "verdict": verdict,
    }
    report_path = ARTIFACTS / "ab_v8_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[S415] Report: {report_path}")

    return 0 if "PROVEN" in verdict else 1


if __name__ == "__main__":
    sys.exit(main())

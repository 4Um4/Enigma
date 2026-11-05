"""S415.1 Verify v2: narrative_cache loads after fix + idle_tick."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tests.gameplay.harness import TavernGameplayHarness

print("[VERIFY] Initializing TavernGameplayHarness...")
harness = TavernGameplayHarness(seed=42)
try:
    harness.new_game()
    print(f"[VERIFY] new_game OK (campaign={harness.campaign_id})")

    # Pre-tick snapshot — may be empty (lazy loading)
    npc_pre = harness.inspect_npc("maid_lusya")
    print(f"[VERIFY] PRE-TICK: maid_lusya found = {npc_pre is not None}")
    if npc_pre:
        ncache_pre = npc_pre.get("narrative_cache", [])
        print(f"[VERIFY] PRE-TICK: narrative_cache = {len(ncache_pre) if ncache_pre else 0}")

    # Force cache population via idle_tick (no player action, no stimulus)
    print(f"[VERIFY] Running 1 idle_tick to populate cache...")
    try:
        harness.game_loop.idle_tick(harness.campaign_id)
        harness.counters.ticks += 1
        print(f"[VERIFY] idle_tick OK")
    except Exception as e:
        print(f"[VERIFY] idle_tick ERROR: {type(e).__name__}: {e}")

    # Post-tick snapshot
    npc = harness.inspect_npc("maid_lusya")
    print(f"\n[VERIFY] POST-TICK: maid_lusya found = {npc is not None}")
    if npc is None:
        print("[VERIFY] FAIL: maid_lusya not found even after idle_tick")
        sys.exit(1)

    ncache = npc.get("narrative_cache", [])
    rcache = npc.get("relationship_cache", {})
    psyche = npc.get("psyche", {})
    beliefs = psyche.get("beliefs", {})
    imprints = npc.get("affective_imprints", [])

    print(f"\n[VERIFY] maid_lusya state AFTER idle_tick:")
    print(f"  narrative_cache count: {len(ncache) if ncache else 0}")
    print(f"  relationship_cache targets: {list((rcache or {}).keys())}")
    print(f"  psyche.beliefs count: {len(beliefs) if isinstance(beliefs, (dict, list)) else 0}")
    print(f"  affective_imprints count: {len(imprints) if imprints else 0}")

    if ncache:
        print(f"\n[VERIFY] narrative_cache samples:")
        for i, m in enumerate(ncache[:5]):
            print(f"  [{i}] target_id={m.get('target_id')}, summary={str(m.get('summary',''))[:80]}")

    if rcache:
        print(f"\n[VERIFY] relationship_cache details:")
        for tgt, vals in list((rcache or {}).items())[:5]:
            print(f"  {tgt}: trust={vals.get('trust')}, chronicle_origin={vals.get('chronicle_origin')}")

    # Verdict
    print(f"\n[VERIFY] VERDICT:")
    if len(ncache if ncache else []) > 0:
        print(f"  ✅ narrative_cache populated ({len(ncache)} entries)")
    else:
        print(f"  ❌ narrative_cache STILL empty — fix did not work")

    if len(rcache if rcache else {}) > 0:
        print(f"  ✅ relationship_cache populated ({len(rcache)} targets)")
    else:
        print(f"  ❌ relationship_cache STILL empty")

    # Also check other NPCs to ensure fix works for all
    print(f"\n[VERIFY] All NPCs narrative_cache:")
    for _n in harness.game_loop._resolve_npcs_snapshot(harness.campaign_id) or []:
        _id = _n.get("id") or _n.get("npc_id", "?")
        _nc = _n.get("narrative_cache", [])
        print(f"  {_id}: narrative_cache={len(_nc) if _nc else 0}")

finally:
    harness.dispose()
    print("\n[VERIFY] harness disposed.")

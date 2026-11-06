"""P5-A Step 2.1: REAL LLM RUMOR PROPAGATION DIAGNOSTIC.

Сквозная трассировка одного события PLAYER_INSULTS через все звенья.

Проверяемые звенья (PASS/FAIL/NOT CALLED):
  1. PLAYER_INSULTS published
  2. ClaimEventSubscriber.on_player_spoke — создаёт Proposition(player, INSULTED, victim)?
  3. EpistemicStore(maid_lusya) — belief after PLAYER_INSULTS?
  4. DecisionHub — выбирает ли Люся spread_rumor?
  5. NPC_SPOKE from maid_lusya — есть ли с intent=spread_rumor?
  6. Proposition в NPC_SPOKE payload?
  7. COMMUNICATION_CLAIM published?
  8. EpistemicStore(tavern_keeper_tornin) — belief after rumor?
"""
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tests.gameplay.harness import TavernGameplayHarness


def main():
    print("=" * 70)
    print("P5-A Step 2.1: Rumor Propagation Diagnostic")
    print("=" * 70)

    # Spy data
    _events = defaultdict(list)
    _npc_spoke = []
    _comm_claim = []
    _player_insults = []

    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    _bus = get_event_bus()

    def _spy_all(event):
        _et = getattr(event, "type", "?")
        _src = getattr(event, "source", "?")
        _pl = getattr(event, "payload", {}) or {}
        _events[_et].append({"source": _src, "payload_keys": list(_pl.keys())[:10], "target_id": _pl.get("target_id", ""), "intent_type": _pl.get("intent_type", "")})

    def _spy_npc_spoke(event):
        _src = getattr(event, "source", "?")
        _pl = getattr(event, "payload", {}) or {}
        _npc_spoke.append({
            "source": _src,
            "target_id": _pl.get("target_id", ""),
            "intent_type": _pl.get("intent_type", ""),
            "text": str(_pl.get("text", ""))[:80],
            "has_proposition": bool(_pl.get("proposition")),
        })

    def _spy_comm_claim(event):
        _src = getattr(event, "source", "?")
        _pl = getattr(event, "payload", {}) or {}
        _comm_claim.append({
            "source": _src,
            "proposition": str(_pl.get("proposition", ""))[:80],
        })

    _bus.subscribe(EventType.NPC_SPOKE, _spy_npc_spoke)
    _bus.subscribe(EventType.COMMUNICATION_CLAIM, _spy_comm_claim)

    # Setup
    print("\n[SETUP] Creating harness...")
    _h = TavernGameplayHarness(seed=42, location="tavern")
    _h.new_game()

    # Pre-flight: check EpistemicStore before insult
    _tick_orch = getattr(_h.game_loop, "_tick_orch", None)
    _store = getattr(_tick_orch, "_epistemic_store", None)
    _sched = _h.game_loop._get_task_scheduler()
    _mm = getattr(_sched, "_memory_manager", None)

    def _get_beliefs(npc_id):
        if not _store:
            return []
        return _store.get_all_for_agent(npc_id)

    print(f"\n[PRE-FLIGHT] EpistemicStore: {_store is not None}")
    _lusya_pre = _get_beliefs("maid_lusya")
    _tornin_pre = _get_beliefs("tavern_keeper_tornin")
    print(f"  maid_lusya beliefs (pre): {len(_lusya_pre)}")
    print(f"  tavern_keeper_tornin beliefs (pre): {len(_tornin_pre)}")

    # Step 1: Publish PLAYER_INSULTS
    print("\n[STEP 1] Publishing PLAYER_INSULTS...")
    from app.domain.events import EventDTO
    _bus.publish(EventDTO.create(
        event_type=EventType.PLAYER_INSULTS.value,
        source="player",
        payload={
            "target_id": "tavern_keeper_tornin",
            "text": "Ты дурак и позорище!",
            "action_type": "player_insults",
        },
        visibility="public",
        radius=10.0,
        persistence_level="session",
    ))
    print("  PLAYER_INSULTS published (target=tavern_keeper_tornin)")

    # Step 2: Check beliefs immediately after publish
    _lusya_after_pub = _get_beliefs("maid_lusya")
    _tornin_after_pub = _get_beliefs("tavern_keeper_tornin")
    print("\n[STEP 2] Beliefs immediately after publish:")
    print(f"  maid_lusya: {len(_lusya_after_pub)} (was {len(_lusya_pre)})")
    print(f"  tavern_keeper_tornin: {len(_tornin_after_pub)} (was {len(_tornin_pre)})")
    if _lusya_after_pub:
        for r in _lusya_after_pub[:3]:
            print(f"    maid_lusya: prop={r.proposition.predicate.value}({r.proposition.subject_id}->{r.proposition.object_id}) conf={r.confidence:.2f}")

    # Step 3: Run 3 idle ticks
    print("\n[STEP 3] Running 3 idle ticks...")
    _t0 = time.monotonic()
    _h.advance_ticks(3)
    _t1 = time.monotonic()
    print(f"  3 ticks done in {_t1 - _t0:.1f}s")

    # Step 4: Check beliefs after ticks
    _lusya_after_ticks = _get_beliefs("maid_lusya")
    _tornin_after_ticks = _get_beliefs("tavern_keeper_tornin")
    print("\n[STEP 4] Beliefs after 3 ticks:")
    print(f"  maid_lusya: {len(_lusya_after_ticks)} (was {len(_lusya_pre)})")
    print(f"  tavern_keeper_tornin: {len(_tornin_after_ticks)} (was {len(_tornin_pre)})")
    if _tornin_after_ticks:
        for r in _tornin_after_ticks[:3]:
            print(f"    tornin: prop={r.proposition.predicate.value}({r.proposition.subject_id}->{r.proposition.object_id}) conf={r.confidence:.2f}")

    # Step 5: Analyze NPC_SPOKE events
    print(f"\n[STEP 5] NPC_SPOKE events: {len(_npc_spoke)}")
    _lusya_speeches = [s for s in _npc_spoke if s["source"] == "maid_lusya"]
    _tornin_speeches = [s for s in _npc_spoke if s["source"] == "tavern_keeper_tornin"]
    print(f"  maid_lusya speeches: {len(_lusya_speeches)}")
    for s in _lusya_speeches:
        print(f"    intent={s['intent_type']!r} target={s['target_id']!r} has_prop={s['has_proposition']} text={s['text']!r}")
    print(f"  tavern_keeper_tornin speeches: {len(_tornin_speeches)}")

    # Step 6: COMMUNICATION_CLAIM events
    print(f"\n[STEP 6] COMMUNICATION_CLAIM events: {len(_comm_claim)}")
    for c in _comm_claim[:5]:
        print(f"    source={c['source']!r} prop={c['proposition']!r}")

    # Step 7: Verdict per link
    print(f"\n{'=' * 70}")
    print("VERDICT PER LINK")
    print(f"{'=' * 70}")

    _links = []
    # Link 1: PLAYER_INSULTS → EpistemicStore(maid_lusya)
    _l1 = len(_lusya_after_ticks) > len(_lusya_pre)
    _links.append(("1. PLAYER_INSULTS → EpistemicStore(maid_lusya)", "PASS" if _l1 else "FAIL"))

    # Link 2: maid_lusya → spread_rumor intent
    _has_spread = any(s["intent_type"] == "spread_rumor" for s in _lusya_speeches)
    _links.append(("2. maid_lusya chooses spread_rumor", "PASS" if _has_spread else "FAIL"))

    # Link 3: spread_rumor → NPC_SPOKE with proposition
    _has_prop = any(s["has_proposition"] for s in _lusya_speeches)
    _links.append(("3. NPC_SPOKE has proposition", "PASS" if _has_prop else "FAIL"))

    # Link 4: COMMUNICATION_CLAIM published
    _links.append(("4. COMMUNICATION_CLAIM published", "PASS" if len(_comm_claim) > 0 else "FAIL"))

    # Link 5: EpistemicStore(tornin) has belief
    _l5 = len(_tornin_after_ticks) > len(_tornin_pre)
    _links.append(("5. EpistemicStore(tornin) has belief", "PASS" if _l5 else "FAIL"))

    for name, status in _links:
        _marker = "✅" if status == "PASS" else "❌"
        print(f"  {_marker} {name}: {status}")

    _all_pass = all(s == "PASS" for _, s in _links)
    print(f"\n{'=' * 70}")
    print(f"OVERALL: {'ALL PASS — rumor propagation works' if _all_pass else 'CHAIN BROKEN — see FAIL links above'}")
    print(f"{'=' * 70}")

    _h.dispose()

if __name__ == "__main__":
    main()
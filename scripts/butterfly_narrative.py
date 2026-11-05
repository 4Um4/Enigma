"""
Butterfly narrative — full scenario with REAL LLM (production setup).

Runs through TavernGameplayHarness:
1. Player insults Tornin (PLAYER_INSULTS)
2. Lusya hears and forms belief (EpistemicStore)
3. Lusya decides to spread_rumor (canonical disposition=1.3, NO override)
4. NPC_SPOKE events captured (actual LLM dialogue)
5. Tornin EpistemicStore shows what he knows (source=Lusya)
6. Cognition block shows what LLM receives

NO test fixtures: no router=None, no _SyncPool, no override_disposition.
"""
import os, sys
os.environ["WORK_ENABLED"] = "1"
# sys.path not needed — run from backend/

from tests.gameplay.harness import TavernGameplayHarness
from app.domain.events import EventDTO
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from uuid import uuid4

SPY_SPOKE = []
SPY_CLAIM = []

def _spy_npc_spoke(event):
    _pl = getattr(event, "payload", {}) or {}
    SPY_SPOKE.append({
        "source": getattr(event, "source", "?"),
        "target_id": _pl.get("target_id"),
        "intent_type": _pl.get("intent_type"),
        "has_prop": bool(_pl.get("proposition")),
        "text": _pl.get("text", _pl.get("content", _pl.get("dialogue_text", ""))),
        "payload_keys": list(_pl.keys()),
        "raw_payload": dict(_pl),
    })

def _spy_comm_claim(event):
    _pl = getattr(event, "payload", {}) or {}
    _prop = _pl.get("proposition") or {}
    SPY_CLAIM.append({
        "source": getattr(event, "source", "?"),
        "target_id": _pl.get("target_id"),
        "predicate": _prop.get("predicate"),
        "subject_id": _prop.get("subject_id"),
        "object_id": _prop.get("object_id"),
    })

print("=" * 70)
print("BUTTERFLY NARRATIVE — REAL LLM (production setup, no fixtures)")
print("=" * 70)

h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()

_bus = get_event_bus()
_bus.subscribe(EventType.NPC_SPOKE, _spy_npc_spoke)
_bus.subscribe(EventType.COMMUNICATION_CLAIM, _spy_comm_claim)
print("[SETUP] Harness created — REAL LLM, no router=None, no sync pool")
print(f"[SETUP] Campaign: {h.campaign_id}")

print("\n[WARMUP] 2 ticks...")
h.advance_ticks(2)

print("\n[INJECT] PLAYER_INSULTS: player insulted tavern_keeper_tornin")
_event = EventDTO(
    id=uuid4(),
    type=EventType.PLAYER_INSULTS.value,
    source="player",
    timestamp=0.0,
    payload={"target_id": "tavern_keeper_tornin", "action_type": "player_insults", "intent_type": "insult"},
    visibility="public",
    radius=15.0,
    persistence_level="session",
)
_bus.publish(_event)

print("\n[RUN] 12 ticks — waiting for NPC reactions (real LLM, async TaskScheduler)...")
h.advance_ticks(12)

print("\n" + "=" * 70)
print("NPC SPEECH (what NPCs actually said):")
print("=" * 70)
print(f"NPC_SPOKE events: {len(SPY_SPOKE)}")
for i, s in enumerate(SPY_SPOKE):
    print(f"\n--- Speech #{i+1} ---")
    print(f"  Speaker: {s['source']}")
    print(f"  Target:  {s['target_id']}")
    print(f"  Intent:  {s['intent_type']}")
    print(f"  Has proposition: {s['has_prop']}")
    print(f"  Payload keys: {s['payload_keys']}")
    if s['text']:
        print(f'  SPEECH: "{s["text"]}"')
    else:
        print(f"  SPEECH: (no text field — full payload: {s['raw_payload']})")

print(f"\n{'=' * 70}")
print("COMMUNICATION_CLAIM events: {len(SPY_CLAIM)}")
for i, c in enumerate(SPY_CLAIM):
    print(f"  #{i+1}: {c['source']} tells {c['target_id']}: {c['subject_id']} {c['predicate']} {c['object_id']}")

print(f"\n{'=' * 70}")
print("EPISTEMIC STORE (what each NPC knows):")
print("=" * 70)
_store = getattr(h.game_loop._tick_orch, "_epistemic_store", None)
if _store:
    for r in _store.to_dict():
        _p = r.get("proposition", {})
        _pol = _p.get("polarity", True)
        print(f"\n  Agent: {r.get('agent_id')}")
        print(f"    Belief: {_p.get('subject_id')} {_p.get('predicate')} {_p.get('object_id')}")
        print(f"    Polarity: {_pol} ({'утверждение' if _pol else 'опровержение'})")
        print(f"    Confidence: {r.get('confidence', 0.0):.2f}")
        print(f"    Source: {r.get('source_id', '?')} (type: {r.get('source_type', '?')})")
        print(f"    Original source: {r.get('original_source_id', '?')}")
        print(f"    Tick: first={r.get('first_observed_tick')}, last={r.get('last_updated_tick')}")
else:
    print("  (EpistemicStore not found)")

print(f"\n{'=' * 70}")
print("RECENT DIALOGUES (from TaskScheduler):")
print("=" * 70)
try:
    _sched = h.game_loop._get_task_scheduler()
    _recent = _sched.get_recent_dialogues(0.0)
    if _recent:
        for d in _recent:
            print(f"  {d}")
    else:
        print("  (no recent dialogues)")
except Exception as e:
    print(f"  (error: {e})")

h.dispose()
print(f"\n{'=' * 70}")
print("END")
print("=" * 70)
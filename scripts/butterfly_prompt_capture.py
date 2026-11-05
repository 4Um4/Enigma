"""Butterfly narrative — prompt capture (LLM down, showing cognition block)."""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ["WORK_ENABLED"] = "1"

import types
from uuid import uuid4
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.events import EventDTO
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType

SPY_SPOKE = []

def _spy(event):
    _pl = getattr(event, "payload", {}) or {}
    SPY_SPOKE.append({
        "source": getattr(event, "source", "?"),
        "target": _pl.get("target_id"),
        "intent": _pl.get("intent_type"),
        "text": _pl.get("text", _pl.get("content", "")),
        "keys": list(_pl.keys()),
    })

print("=" * 70)
print("BUTTERFLY — COGNITION BLOCK CAPTURE")
print("(LLM down — showing what NPC WOULD receive in prompt)")
print("=" * 70)

h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()

# router=None + sync pool (LLM-free, stub text — but cognition block IS built)
from app.domain.execution import TaskKind
_sched = getattr(h.game_loop, "_task_scheduler", None) or h.game_loop._get_task_scheduler()
_executors = getattr(_sched, "_executors", None) or {}
_dlg = _executors.get(TaskKind.DIALOGUE)
if _dlg is not None and hasattr(_dlg, "_router"):
    _dlg._router = None
    print("[WIRING] router=None (LLM down — stub text, cognition block built)")
_sched._executor_pool = type("SP", (), {
    "submit": lambda self, fn, *a, **kw: (fn(*a, **kw), types.SimpleNamespace(result=lambda: None))[1],
    "shutdown": lambda self, wait=True: None,
})()

_bus = get_event_bus()
_bus.subscribe(EventType.NPC_SPOKE, _spy)

print("\n[WARMUP] 2 ticks...")
h.advance_ticks(2)

print("\n[INJECT] PLAYER_INSULTS: player -> tavern_keeper_tornin")
_bus.publish(EventDTO(
    id=uuid4(), type=EventType.PLAYER_INSULTS.value, source="player", timestamp=0.0,
    payload={"target_id": "tavern_keeper_tornin", "action_type": "player_insults", "intent_type": "insult"},
    visibility="public", radius=15.0, persistence_level="session",
))

print("\n[RUN] 8 ticks...")
h.advance_ticks(8)

# NPC speech
print("\n" + "=" * 70)
print("NPC_SPOKE: %d events" % len(SPY_SPOKE))
for i, s in enumerate(SPY_SPOKE):
    print("\n  #%d: %s -> %s (intent=%s)" % (i+1, s["source"], s["target"], s["intent"]))
    print("     keys: %s" % s["keys"])
    if s["text"]:
        print('     text: "%s"' % s["text"])

# EpistemicStore
print("\n" + "=" * 70)
print("EPISTEMIC STORE (what each NPC knows):")
_store = getattr(h.game_loop._tick_orch, "_epistemic_store", None)
if _store:
    for r in _store.to_dict():
        _p = r.get("proposition", {})
        print("\n  %s: %s %s %s" % (r.get("agent_id"), _p.get("subject_id"), _p.get("predicate"), _p.get("object_id")))
        print("    polarity=%s, conf=%.2f" % (_p.get("polarity", True), r.get("confidence", 0)))
        print("    source=%s, type=%s" % (r.get("source_id", "?"), r.get("source_type", "?")))
        print("    original=%s" % r.get("original_source_id", "?"))
else:
    print("  (not found)")

# Cognition block for Tornin
print("\n" + "=" * 70)
print("TORNIK COGNITION BLOCK (what LLM would receive):")
print("=" * 70)
from app.services.npc.cognition_context import CognitionContextResolver
_mm = h.game_loop.memory_manager
if _store and _mm:
    try:
        _cog = CognitionContextResolver(
            _mm,
            epistemic_store=_store,
            context_provider=lambda nid: {"name": nid, "description": ""},
        )
        _block = _cog.resolve_block("tavern_keeper_tornin", "player")
        if _block:
            print(_block)
        else:
            print("(empty cognition block)")
    except Exception as e:
        print("(error: %s)" % e)

# Contradictions for Tornin
print("\n" + "=" * 70)
print("TORNIK CONTRADICTIONS:")
from app.services.execution.dialogue_executor import DialogueExecutor
de = DialogueExecutor(epistemic_store=_store)
contr = de._format_contradictions("tavern_keeper_tornin", h.campaign_id)
print(contr if contr else "(no contradictions)")

# Causal context for Tornin
print("\n" + "=" * 70)
print("TORNIK CAUSAL CONTEXT:")
_npc_states = h.game_loop._resolve_npcs_snapshot(h.campaign_id) or []
_tornin = next((n for n in _npc_states if n.get("npc_id") == "tavern_keeper_tornin" or n.get("id") == "tavern_keeper_tornin"), None)
if _tornin:
    _ledger = _tornin.get("causal_ledger", [])
    if _ledger:
        print(de._format_causal_context(_ledger))
    else:
        print("(no causal_ledger entries)")
else:
    print("(Tornin not found)")

h.dispose()
print("\n" + "=" * 70)
print("END")
print("=" * 70)
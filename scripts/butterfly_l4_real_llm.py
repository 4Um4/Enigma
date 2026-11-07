"""L4: Real LLM butterfly narrative — NPC speaks to NPC via LLM."""
import os, sys, time, atexit, types
from pathlib import Path

_BACKEND = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

os.environ["WORK_ENABLED"] = "1"

# === START LLM (Host broker SDK, Этап 4.1.11) ===
print("=== STARTING LLM (Host broker SDK) ===")
from app.services.llm.runtime.client import ensure_llm
_llm_ok = True
try:
    ensure_llm(label="butterfly_l4")
except Exception as e:
    print(f"[LLM] start failed: {e}")
    _llm_ok = False

# Wait for health (diagnostic)
print("[LLM] Waiting for health (max 60s)...")
import urllib.request
_llm_alive = False
for _i in range(12):
    time.sleep(5)
    try:
        req = urllib.request.urlopen("http://localhost:8181/health", timeout=3)
        print(f"[LLM] ALIVE (status {req.status})")
        _llm_alive = True
        break
    except Exception:
        print(f"[LLM] Waiting... ({(_i+1)*5}s)")
        continue

if not _llm_alive:
    print("[LLM] NOT ALIVE after 60s — aborting")
    sys.exit(1)

# === BUTTERFLY SCENARIO ===
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.events import EventDTO
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from uuid import uuid4

SPY_SPOKE = []
SPY_CLAIM = []

def _spy_spoke(event):
    _pl = getattr(event, "payload", {}) or {}
    SPY_SPOKE.append({
        "source": getattr(event, "source", "?"),
        "target": _pl.get("target_id"),
        "intent": _pl.get("intent_type"),
        "text": _pl.get("text", _pl.get("content", "")),
        "has_prop": bool(_pl.get("proposition")),
        "topic": _pl.get("topic", ""),
        "exposure": _pl.get("exposure", ""),
    })

def _spy_claim(event):
    _pl = getattr(event, "payload", {}) or {}
    _prop = _pl.get("proposition") or {}
    SPY_CLAIM.append({
        "source": getattr(event, "source", "?"),
        "target": _pl.get("target_id"),
        "predicate": _prop.get("predicate"),
        "subject": _prop.get("subject_id"),
        "object": _prop.get("object_id"),
    })

print("\n" + "=" * 70)
print("BUTTERFLY L4 — REAL LLM NARRATIVE")
print("=" * 70)

h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()

# === SPATIAL FIX: move Lusya close to Tornin ===
print("\n[SPATIAL] Moving maid_lusya close to tavern_keeper_tornin...")
_scene = h.get_scene_fresh()
if _scene:
    _pos = _scene.get("npc_positions", {})
    _tornin = _pos.get("tavern_keeper_tornin", {})
    _lusya = _pos.get("maid_lusya", {})
    _tornin_pos = _tornin.get("local_position", {})
    print(f"  Tornin position: {_tornin_pos}")
    print(f"  Lusya position: {_lusya.get('local_position', {})}")

    # Move Lusya to Tornin's position (slightly offset)
    if _tornin_pos:
        _new_pos = {"x": _tornin_pos.get("x", 5.0), "y": _tornin_pos.get("y", 5.0)}
        # Update in tick_scenes (production path)
        _tick_scenes = getattr(h.game_loop.scene_manager, "_tick_scenes", {})
        for _loc, _sc in _tick_scenes.items():
            if isinstance(_sc, dict):
                _npc_pos = _sc.get("npc_positions", {})
                if "maid_lusya" in _npc_pos:
                    _npc_pos["maid_lusya"]["local_position"] = _new_pos
                    print(f"  Lusya moved to {_new_pos} in {_loc}")
else:
    print("  [WARN] Could not get scene for spatial fix")

# === Install spies ===
_bus = get_event_bus()
_bus.subscribe(EventType.NPC_SPOKE, _spy_spoke)
_bus.subscribe(EventType.COMMUNICATION_CLAIM, _spy_claim)

# === DON'T set router=None — use REAL LLM ===
print("[SETUP] REAL LLM (no router=None, no sync pool, no override)")

# === Warmup ===
print("\n[WARMUP] 2 ticks...")
h.advance_ticks(2)

# === Inject PLAYER_INSULTS ===
print("\n[INJECT] PLAYER_INSULTS: player -> tavern_keeper_tornin")
_bus.publish(EventDTO(
    id=uuid4(), type=EventType.PLAYER_INSULTS.value, source="player", timestamp=0.0,
    payload={"target_id": "tavern_keeper_tornin", "action_type": "player_insults", "intent_type": "insult"},
    visibility="public", radius=15.0, persistence_level="session",
))

# === Run ticks — REAL LLM, async TaskScheduler ===
print("\n[RUN] 10 ticks (real LLM, async — may take ~30-60s)...")
h.advance_ticks(10)

# === RESULTS ===
print("\n" + "=" * 70)
print("NPC SPEECH (real LLM-generated):")
print("=" * 70)
print(f"NPC_SPOKE events: {len(SPY_SPOKE)}")
for i, s in enumerate(SPY_SPOKE):
    print(f"\n--- Speech #{i+1} ---")
    print(f"  Speaker: {s['source']}")
    print(f"  Target:  {s['target']}")
    print(f"  Intent:  {s['intent']}")
    print(f"  Topic:   {s['topic']}")
    print(f"  Has proposition: {s['has_prop']}")
    if s['text']:
        print(f'  SPEECH: "{s["text"]}"')
    else:
        print(f"  SPEECH: (empty)")

print(f"\n{'=' * 70}")
print(f"COMMUNICATION_CLAIM events: {len(SPY_CLAIM)}")
for i, c in enumerate(SPY_CLAIM):
    print(f"  #{i+1}: {c['source']} -> {c['target']}: {c['subject']} {c['predicate']} {c['object']}")

print(f"\n{'=' * 70}")
print("EPISTEMIC STORE (what each NPC knows):")
_store = getattr(h.game_loop._tick_orch, "_epistemic_store", None)
if _store:
    for r in _store.to_dict():
        _p = r.get("proposition", {})
        _pol = _p.get("polarity", True)
        print(f"\n  Agent: {r.get('agent_id')}")
        print(f"    Belief: {_p.get('subject_id')} {_p.get('predicate')} {_p.get('object_id')}")
        print(f"    Polarity: {_pol}")
        print(f"    Confidence: {r.get('confidence', 0.0):.2f}")
        print(f"    Source: {r.get('source_id', '?')} (type: {r.get('source_type', '?')})")
        print(f"    Original source: {r.get('original_source_id', '?')}")
else:
    print("  (not found)")

print(f"\n{'=' * 70}")
print("TORNIK COGNITION BLOCK (what LLM received):")
from app.services.npc.cognition_context import CognitionContextResolver
_mm = h.game_loop.memory_manager
if _store and _mm:
    try:
        _cog = CognitionContextResolver(_mm, epistemic_store=_store, context_provider=lambda nid: {"name": nid})
        _block = _cog.resolve_block("tavern_keeper_tornin", "player")
        print(_block if _block else "(empty)")
    except Exception as e:
        print(f"(error: {e})")

print(f"\n{'=' * 70}")
print("TORNIK CONTRADICTIONS:")
from app.services.execution.dialogue_executor import DialogueExecutor
de = DialogueExecutor(epistemic_store=_store)
contr = de._format_contradictions("tavern_keeper_tornin", h.campaign_id)
print(contr if contr else "(no contradictions)")

print(f"\n{'=' * 70}")
print("TORNIK CAUSAL CONTEXT:")
_npc_states = h.game_loop._resolve_npcs_snapshot(h.campaign_id) or []
_tornin = next((n for n in _npc_states if n.get("npc_id") == "tavern_keeper_tornin" or n.get("id") == "tavern_keeper_tornin"), None)
if _tornin:
    _ledger = _tornin.get("causal_ledger", [])
    if _ledger:
        print(de._format_causal_context(_ledger))
    else:
        print("(no causal entries)")
else:
    print("(Tornin not found)")

h.dispose()
print(f"\n{'=' * 70}")
print("END")
print("=" * 70)
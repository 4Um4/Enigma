import sys, json, tempfile, shutil, traceback
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.core.config import settings
from app.services.game_loop_builder import build_game_loop
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.domain.events import EventDTO
from app.services.npc.decision_hub import DecisionHub
from app.services.phases.movement_bridge import process_movement_intents
from app.services.spatial.movement_engine import MovementEngine
from app.services.spatial.spatial_target_resolver import SpatialTargetResolver

SPY = []
def stamp(tag, **kw):
    SPY.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

# Spy on SpatialTargetResolver.resolve
orig_resolve = SpatialTargetResolver.resolve
def spy_resolve(self_res, target_intent, **kw):
    actor = kw.get("actor_id", "?")
    reason = getattr(target_intent, "reason", "?") if target_intent else "?"
    target_type = getattr(target_intent, "target_type", "?") if target_intent else "?"
    target_id = getattr(target_intent, "target_id", "?") if target_intent else "?"
    confidence = getattr(target_intent, "confidence", "?") if target_intent else "?"
    
    if actor == "maid_lusya":
        stamp("RESOLVER.ENTER",
              actor=actor, reason=reason, target_type=str(target_type),
              target_id=target_id, confidence=confidence)
    
    result = orig_resolve(self_res, target_intent, **kw)
    
    if actor == "maid_lusya":
        status = getattr(result, "resolution_status", "?")
        mode = getattr(result, "resolution_mode", "?")
        reason_out = getattr(result, "resolution_reason", "?")
        anchor = getattr(result, "anchor_node_id", "?")
        pos = getattr(result, "position", "?")
        stamp("RESOLVER.EXIT",
              actor=actor, status=str(status), mode=str(mode),
              reason=reason_out, anchor_node=anchor, position=str(pos)[:100])
    return result
SpatialTargetResolver.resolve = spy_resolve

# Spy on DecisionHub
orig_compute = DecisionHub.compute
def spy_compute(self_dh, *args, **kwargs):
    state_arg = args[0] if args else kwargs.get("state", None)
    npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
    result = orig_compute(self_dh, *args, **kwargs)
    if npc_id == "maid_lusya":
        dec = getattr(result, "decision", None)
        if dec:
            stamp("DH.EXIT", intent=str(getattr(dec, "intent", "?")),
                  target=getattr(dec, "intent_target", None),
                  score=getattr(dec, "score", None))
    return result
DecisionHub.compute = spy_compute

# Spy on MovementEngine
orig_pi = MovementEngine.process_intents
def spy_pi(self_me, intents, **kwargs):
    scene = kwargs.get("scene_state", {})
    ml_intents = []
    for i in (intents or []):
        if getattr(i, "actor_id", "") == "maid_lusya":
            ml_intents.append({
                "reason": getattr(i, "reason", "?"),
                "intent_type": getattr(i, "intent_type", ""),
                "target_node_id": getattr(i, "target_node_id", ""),
                "has_target_intent": getattr(i, "target_intent", None) is not None,
            })
    trav = (scene.get("active_traversals") or {}).get("maid_lusya", {})
    if ml_intents:
        stamp("ME.ENTER",
              ml_intents=ml_intents,
              has_traversal=bool(trav),
              trav_status=trav.get("status") if isinstance(trav, dict) else None)
    result = orig_pi(self_me, intents, **kwargs)
    if ml_intents:
        ml_changes = [sc for sc in (result or []) if getattr(sc, "target", getattr(sc, "npc_id", "?")) == "maid_lusya"]
        stamp("ME.EXIT", ml_changes=len(ml_changes), EXECUTED=len(ml_changes) > 0)
    return result
MovementEngine.process_intents = spy_pi

settings.saves_dir = str(Path(tempfile.mkdtemp(prefix="r2_flee_")))
settings.environment = "development"
loop = build_game_loop(data_dir=Path(settings.data_dir))
scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
if scene is None:
    scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
ts = loop._get_task_scheduler()
for k, ex in (getattr(ts, "_executors", {}) or {}).items():
    if hasattr(ex, "_router"):
        ex._router = MagicMock()
        ex._router.route.return_value = "[Mock]"

payload = {"action_type": "player_insults", "target_id": "maid_lusya", "content": "x",
           "event_tick": 1, "visibility": "public", "radius": 999.0, "location": "tavern",
           "campaign_id": "Open_road", "raw_input": "x"}
get_event_bus().publish(EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player",
                          payload=payload, persistence_level="working"))

for tick_i in range(1, 8):
    print(f"--- TICK {tick_i} ---")
    try:
        loop.idle_tick("Open_road")
    except Exception as e:
        print(f"TICK ERROR: {type(e).__name__}: {e}")
        break

print("FLEE RESOLVER PROBE DONE")
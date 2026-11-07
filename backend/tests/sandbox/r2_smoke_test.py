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
from app.services.spatial.movement_engine import MovementEngine

SPY = []
def stamp(tag, **kw):
    SPY.append({"tag": tag, **kw})
    print(f"[SPY] {tag}: " + json.dumps(kw, ensure_ascii=False, default=str))

orig_pi = MovementEngine.process_intents
def spy_pi(self_me, intents, **kwargs):
    scene = kwargs.get("scene_state", {})
    ml_types = [getattr(i, "intent_type", "") for i in (intents or []) if getattr(i, "actor_id", "") == "maid_lusya"]
    trav = (scene.get("active_traversals") or {}).get("maid_lusya", {})
    if ml_types:
        stamp("ME.ENTER", ml_types=ml_types, has_traversal=bool(trav),
              trav_status=trav.get("status") if isinstance(trav, dict) else None)
    result = orig_pi(self_me, intents, **kwargs)
    if ml_types:
        ml_changes = [sc for sc in (result or []) if getattr(sc, "target", getattr(sc, "npc_id", "?")) == "maid_lusya"]
        stamp("ME.EXIT", ml_changes=len(ml_changes), EXECUTED=len(ml_changes) > 0)
    return result
MovementEngine.process_intents = spy_pi

orig_compute = DecisionHub.compute
def spy_compute(self_dh, *args, **kwargs):
    state_arg = args[0] if args else kwargs.get("state", None)
    npc_id = getattr(state_arg, "npc_id", "?") if state_arg is not None else "?"
    result = orig_compute(self_dh, *args, **kwargs)
    if npc_id == "maid_lusya":
        dec = getattr(result, "decision", None)
        if dec:
            stamp("DH.EXIT", intent=str(getattr(dec, "intent", "?")), score=getattr(dec, "score", None))
    return result
DecisionHub.compute = spy_compute

settings.saves_dir = str(Path(tempfile.mkdtemp(prefix="r2_smoke_")))
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

for tick_i in range(1, 6):
    print(f"--- TICK {tick_i} ---")
    try:
        loop.idle_tick("Open_road")
    except Exception as e:
        print(f"TICK ERROR: {type(e).__name__}: {e}")
        break

print("SMOKE TEST DONE")
# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, "backend")
os.environ.setdefault("D8P_ENABLED", "1")

def log(msg):
    print(msg, flush=True)

log("STEP 1: initialize_router")
from app.services.llm.router import initialize_router
initialize_router()
log("STEP 1 done")

log("STEP 2: import harness")
from tests.gameplay.harness import TavernGameplayHarness
log("STEP 2 done")

log("STEP 3: create harness")
h = TavernGameplayHarness(seed=42, location="tavern")
log("STEP 3 done")

log("STEP 4: new_game")
h.new_game()
log("STEP 4 done")

log("STEP 5: install_llm_free")
from app.domain.execution import TaskKind
from app.services.cognition.proposition_verifier import PassthroughVerifier
from app.services.execution.dialogue_materializer import DialogueMaterializer
sched = h.game_loop._get_task_scheduler()
executors = getattr(sched, "_executors", None) or {}
dlg_executor = executors.get(TaskKind.DIALOGUE)
if dlg_executor is not None:
    dlg_executor._router = None
sched._executor_pool = type("_SyncPool", (), {
    "submit": lambda self, fn, *a, **kw: fn(*a, **kw),
    "shutdown": lambda self: None,
})()
sched._materializers["dialogue_line"] = DialogueMaterializer(
    proposition_verifier=PassthroughVerifier()
)
log("STEP 5 done")

log("STEP 6: publish insults")
from app.domain.events import EventDTO
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
bus = get_event_bus()
bus.publish(EventDTO.create(
    event_type=EventType.PLAYER_INSULTS.value,
    source="player",
    payload={"target_id": "tavern_keeper_tornin", "text": "Ты дурак!", "action_type": "player_insults"},
    visibility="public", radius=10.0, persistence_level="session",
))
log("STEP 6 done")

log("STEP 7: advance_ticks(5)")
h.advance_ticks(5)
log("STEP 7 done")

log("STEP 8: check belief")
tick_orch = getattr(h.game_loop, "_tick_orch", None)
store = getattr(tick_orch, "_epistemic_store", None) if tick_orch else None
beliefs = store.get_all_for_agent("tavern_keeper_tornin") if store else []
has_belief = any(
    r.proposition.predicate.value == "insulted"
    and r.proposition.subject_id == "player"
    for r in beliefs
)
log(f"STEP 8 done: belief_present={has_belief} records={len(beliefs)}")

if has_belief:
    belief = [r for r in beliefs if r.proposition.predicate.value == "insulted" and r.proposition.subject_id == "player"][0]
    log(f"  source_id={belief.source_id}")
    log(f"  original_source_id={belief.original_source_id}")
    log(f"  confidence={belief.confidence}")

log("STEP 9: cognition block")
from app.services.npc.cognition_context import CognitionContextResolver
mm = getattr(sched, "_memory_manager", None)
resolver = CognitionContextResolver(memory_manager=mm, epistemic_store=store)
cog_block = resolver.resolve_block("tavern_keeper_tornin", "player")
log(f"STEP 9 done: cog_block_head={cog_block[:200]!r}")

log("STEP 10: restore real router")
from app.services.llm.router import get_router
dlg_executor._router = get_router()
log("STEP 10 done")

log("STEP 11: spy on Tornin speeches")
tornin_speeches = []
def spy(event):
    if getattr(event, "source", "") == "tavern_keeper_tornin":
        pl = getattr(event, "payload", {}) or {}
        tornin_speeches.append({
            "text": pl.get("text", ""),
            "intent_type": pl.get("intent_type", ""),
            "tone": pl.get("tone", ""),
        })
bus.subscribe(EventType.NPC_SPOKE, spy)
log("STEP 11 done")

log("STEP 12: player_action (real LLM)")
t0 = time.monotonic()
try:
    resp = h.player_action("Торнин, привет, как дела?")
    t1 = time.monotonic()
    log(f"STEP 12 done: completed in {t1-t0:.1f}s")
except Exception as e:
    t1 = time.monotonic()
    log(f"STEP 12 FAILED in {t1-t0:.1f}s: {e}")

log("STEP 13: results")
log(f"belief_present={has_belief}")
log(f"cognition_block={cog_block[:300]!r}")
log(f"tornin_speeches={len(tornin_speeches)}")
for i, s in enumerate(tornin_speeches):
    log(f"[TORNIN {i}] text={s['text'][:200]!r} intent={s['intent_type']} tone={s['tone']}")
if not tornin_speeches:
    log("[NO TORNIN SPEECH]")

h.dispose()
log("DONE")

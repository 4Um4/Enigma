# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, "backend")
os.environ.setdefault("D8P_ENABLED", "1")

def log(msg):
    print(msg, flush=True)

log("INIT: router")
from app.services.llm.router import initialize_router
initialize_router()

log("INIT: harness")
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
from app.services.cognition.proposition_verifier import PassthroughVerifier
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.npc.cognition_context import CognitionContextResolver
from app.domain.events import EventDTO

log("INIT: create harness")
h = TavernGameplayHarness(seed=42, location="tavern")
log("INIT: new_game")
h.new_game()
log("INIT done")

# Phase 1: LLM-free rumor propagation
log("PHASE1: install LLM-free")
sched = h.game_loop._get_task_scheduler()
dlg_executor = sched._executors.get(TaskKind.DIALOGUE)
if dlg_executor is not None:
    dlg_executor._router = None
sched._executor_pool = type("P", (), {"submit": lambda s,f,*a,**k: f(*a,**k), "shutdown": lambda s: None})()
sched._materializers["dialogue_line"] = DialogueMaterializer(proposition_verifier=PassthroughVerifier())

log("PHASE1: publish insults")
bus = get_event_bus()
bus.publish(EventDTO.create(
    event_type=EventType.PLAYER_INSULTS.value,
    source="player",
    payload={"target_id": "tavern_keeper_tornin", "text": "Ты дурак!", "action_type": "player_insults"},
    visibility="public", radius=10.0, persistence_level="session",
))

log("PHASE1: advance_ticks(5)")
t0 = time.monotonic()
h.advance_ticks(5)
log(f"PHASE1 done: ticks={time.monotonic()-t0:.1f}s")

# Check belief
tick_orch = getattr(h.game_loop, "_tick_orch", None)
store = getattr(tick_orch, "_epistemic_store", None)
beliefs = store.get_all_for_agent("tavern_keeper_tornin") if store else []
has_belief = any(r.proposition.predicate.value == "insulted" and r.proposition.subject_id == "player" for r in beliefs)
log(f"BELIEF: present={has_belief} records={len(beliefs)}")
if has_belief:
    b = [r for r in beliefs if r.proposition.predicate.value == "insulted" and r.proposition.subject_id == "player"][0]
    log(f"  source={b.source_id} orig={b.original_source_id} conf={b.confidence}")

# Cognition block
mm = getattr(sched, "_memory_manager", None)
resolver = CognitionContextResolver(memory_manager=mm, epistemic_store=store)
cog = resolver.resolve_block("tavern_keeper_tornin", "player")
log(f"COGNITION: {cog[:300]}")

# Phase 2: restore real router
log("PHASE2: restore router")
from app.services.llm.router import get_router
dlg_executor._router = get_router()

# Spy on Tornin speeches
speeches = []
def spy(event):
    if getattr(event, "source", "") == "tavern_keeper_tornin":
        pl = getattr(event, "payload", {}) or {}
        speeches.append({"text": pl.get("text", ""), "intent": pl.get("intent_type", ""), "tone": pl.get("tone", "")})
bus.subscribe(EventType.NPC_SPOKE, spy)

# Player talks to Tornin
log("PHASE2: player_action")
t0 = time.monotonic()
try:
    resp = h.player_action("Торнин, привет, как дела?")
    log(f"PHASE2 done: {time.monotonic()-t0:.1f}s")
except Exception as e:
    log(f"PHASE2 FAILED: {time.monotonic()-t0:.1f}s {e}")

# Results
log(f"RESULTS: belief={has_belief} speeches={len(speeches)}")
for i, s in enumerate(speeches):
    log(f"[TORNIN {i}] text={s['text'][:200]}")
    log(f"  intent={s['intent']} tone={s['tone']}")
if not speeches:
    log("[NO TORNIN SPEECH]")

h.dispose()
log("DONE")

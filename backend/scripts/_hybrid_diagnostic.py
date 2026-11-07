# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, "backend")
os.environ.setdefault("D8P_ENABLED", "1")

from app.services.llm.router import initialize_router
initialize_router()

from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
from app.services.cognition.proposition_verifier import PassthroughVerifier
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.npc.cognition_context import CognitionContextResolver
from app.domain.events import EventDTO

def publish_insults(harness, victim):
    bus = get_event_bus()
    bus.publish(EventDTO.create(
        event_type=EventType.PLAYER_INSULTS.value,
        source="player",
        payload={"target_id": victim, "text": "Ты дурак!", "action_type": "player_insults"},
        visibility="public", radius=10.0, persistence_level="session",
    ))

def install_llm_free(harness):
    """LLM-free setup for rumor propagation phase."""
    sched = getattr(harness.game_loop, "_task_scheduler", None)
    if sched is None:
        sched = harness.game_loop._get_task_scheduler()
    executors = getattr(sched, "_executors", None) or {}
    dlg_executor = executors.get(TaskKind.DIALOGUE)
    if dlg_executor is not None and hasattr(dlg_executor, "_router"):
        dlg_executor._router = None
    sched._executor_pool = type("_SyncPool", (), {
        "submit": lambda self, fn, *a, **kw: fn(*a, **kw),
        "shutdown": lambda self: None,
    })()
    sched._materializers["dialogue_line"] = DialogueMaterializer(
        proposition_verifier=PassthroughVerifier()
    )
    print("[HYBRID] Phase 1: LLM-free rumor propagation")

def restore_real_router(harness):
    """Restore real router for Tornin's LLM dialogue."""
    sched = getattr(harness.game_loop, "_task_scheduler", None)
    if sched is None:
        sched = harness.game_loop._get_task_scheduler()
    executors = getattr(sched, "_executors", None) or {}
    dlg_executor = executors.get(TaskKind.DIALOGUE)
    if dlg_executor is not None:
        from app.services.llm.router import get_router
        dlg_executor._router = get_router()
        print("[HYBRID] Phase 2: Real router restored for Tornin dialogue")

def get_store(harness):
    tick_orch = getattr(harness.game_loop, "_tick_orch", None)
    return getattr(tick_orch, "_epistemic_store", None) if tick_orch else None

def get_cognition(harness):
    store = get_store(harness)
    if not store:
        return ""
    sched = harness.game_loop._get_task_scheduler()
    mm = getattr(sched, "_memory_manager", None)
    resolver = CognitionContextResolver(memory_manager=mm, epistemic_store=store)
    return resolver.resolve_block("tavern_keeper_tornin", "player")

def capture_tornin_speeches(harness):
    speeches = []
    def spy(event):
        if getattr(event, "source", "") == "tavern_keeper_tornin":
            pl = getattr(event, "payload", {}) or {}
            speeches.append({
                "text": pl.get("text", ""),
                "intent_type": pl.get("intent_type", ""),
                "tone": pl.get("tone", ""),
            })
    bus = get_event_bus()
    bus.subscribe(EventType.NPC_SPOKE, spy)
    return speeches

# ========== HYBRID DIAGNOSTIC ==========
print("=" * 60)
print("HYBRID DIAGNOSTIC: LLM-free rumor → real LLM Tornin dialogue")
print("=" * 60)

h = TavernGameplayHarness(seed=42, location="tavern")
h.new_game()

# Phase 1: LLM-free rumor propagation
install_llm_free(h)
publish_insults(h, "tavern_keeper_tornin")
print("  PLAYER_INSULTS published")
h.advance_ticks(5)
print("  advance_ticks(5) done")

# Verify belief
store = get_store(h)
beliefs = store.get_all_for_agent("tavern_keeper_tornin") if store else []
has_belief = any(
    r.proposition.predicate.value == "insulted"
    and r.proposition.subject_id == "player"
    for r in beliefs
)
print(f"  belief_present={has_belief} (records={len(beliefs)})")

if has_belief:
    belief = [r for r in beliefs if r.proposition.predicate.value == "insulted" and r.proposition.subject_id == "player"][0]
    print(f"  source_id={belief.source_id}")
    print(f"  original_source_id={belief.original_source_id}")
    print(f"  confidence={belief.confidence}")

cog_block = get_cognition(h)
print(f"  cognition_block_head={cog_block[:200]!r}")

# Phase 2: Restore real router
restore_real_router(h)

# Spy on Tornin speeches
tornin_speeches = capture_tornin_speeches(h)

# Player talks to Tornin with real LLM
print("\n[HYBRID] Phase 2: Real LLM dialogue — player talks to Tornin")
t0 = time.monotonic()
try:
    resp = h.player_action("Торнин, привет, как дела?")
    t1 = time.monotonic()
    print(f"  player_action completed in {t1-t0:.1f}s")
except Exception as e:
    t1 = time.monotonic()
    print(f"  player_action FAILED in {t1-t0:.1f}s: {e}")

# Results
print(f"\n{'='*60}")
print("HYBRID RESULTS")
print(f"{'='*60}")
print(f"belief_present={has_belief}")
print(f"cognition_block={cog_block[:300]!r}")
print(f"tornin_speeches={len(tornin_speeches)}")

for i, s in enumerate(tornin_speeches):
    print(f"\n[TORNIN {i}]")
    print(f"  text={s['text'][:200]!r}")
    print(f"  intent={s['intent_type']}")
    print(f"  tone={s['tone']}")

if not tornin_speeches:
    print("  [NO TORNIN SPEECH] — NPC_SPOKE from tornin not captured")
    print("  Check: DM may have generated narrative without NPC_SPOKE event")

h.dispose()

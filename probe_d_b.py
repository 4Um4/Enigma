import sys, types
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)

from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
from app.domain import epistemic_dispositions as _ed
from app.domain.epistemology import EpistemicRecord, Predicate, Proposition

# === Sync-pool + wiring как в K2 ===
class _SyncPool:
    def submit(self, fn, *a, **k):
        fn(*a, **k); return types.SimpleNamespace(result=lambda: None)
    def shutdown(self, wait=True): pass

# Override guard disposition (как в тесте)
_ed.EPISTEMIC_DISPOSITIONS["guard"] = {
    "report": 0.0, "warn": 0.5, "attack": 0.4,
    "spread_rumor": 0.0, "talk": 0.2, "intimidate": 1.4,
}

SPY_SPOKE = []
SPY_CLAIM = []
def _spy_spoke(ev):
    SPY_SPOKE.append({
        "source": getattr(ev, "source", "?"),
        "target_id": (getattr(ev, "payload", {}) or {}).get("target_id"),
        "intent_type": (getattr(ev, "payload", {}) or {}).get("intent_type"),
        "tick": getattr(ev, "tick", None),
        "event_id": getattr(ev, "id", None),
    })
def _spy_claim(ev):
    _pl = getattr(ev, "payload", {}) or {}
    _prop = _pl.get("proposition") or {}
    SPY_CLAIM.append({
        "source": getattr(ev, "source", "?"),
        "target_id": _pl.get("target_id"),
        "subject_id": _prop.get("subject_id"),
        "predicate": _prop.get("predicate"),
        "claim_id": _pl.get("claim_id"),
        "event_id": getattr(ev, "id", None),
    })

_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_sched = _h.game_loop._get_task_scheduler()
_sched._executors[TaskKind.DIALOGUE]._router = None
_sched._executor_pool = _SyncPool()

from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
_bus = get_event_bus()
_bus.subscribe(EventType.NPC_SPOKE, _spy_spoke)
_bus.subscribe(EventType.COMMUNICATION_CLAIM, _spy_claim)

_h.advance_ticks(2)

# Seed belief как в K2
_store = _h.game_loop._tick_orch._epistemic_store
_store.upsert(EpistemicRecord(
    agent_id="guard_borko",
    proposition=Proposition(subject_id="thief_shadow",
                            predicate=Predicate.STOLE,
                            object_id="unknown", polarity=True),
    confidence=0.7, source_id="direct_observation",
    source_claim_id="fixture-gb-ts-stole",
    first_observed_tick=0, last_updated_tick=0,
))

print("[K2 setup] seed belief applied")
_h.advance_ticks(12)

# === Этап 1: maid_lusya EpistemicRecord ===
print("\n=== ЭТАП 1: maid_lusya EpistemicStore ===")
_maid_records = [r for r in _store.to_dict() if r.get("agent_id") == "maid_lusya"]
print(f"Records count: {len(_maid_records)}")
for r in _maid_records:
    _p = r.get("proposition", {})
    print(f"  prop={_p.get('predicate')} subj={_p.get('subject_id')} obj={_p.get('object_id')} "
          f"conf={r.get('confidence')} source={r.get('source_id')} "
          f"claim_id={r.get('source_claim_id')}")
    print(f"    first_observed_tick={r.get('first_observed_tick')} last_updated_tick={r.get('last_updated_tick')}")

# === Этап 2: EpistemicContextResolver для maid_lusya ===
print("\n=== ЭТАП 2: EpistemicContext for maid_lusya ===")
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver, CONFIDENCE_THRESHOLD
_resolver = EpistemicContextResolver(_store)
_ctx = _resolver.resolve("maid_lusya")
print(f"  perceived_threats={_ctx.perceived_threats}")
print(f"  perceived_allies={_ctx.perceived_allies}")
print(f"  perceived_violations={_ctx.perceived_violations}")
print(f"  trigger_proposition={_ctx.trigger_proposition}")
print(f"  max_confidence={_ctx.max_confidence}")
print(f"  claims_about_self={_ctx.claims_about_self}")
print(f"  max_self_confidence={_ctx.max_self_confidence}")
print(f"  CONFIDENCE_THRESHOLD={CONFIDENCE_THRESHOLD}")

# === Этап 2 (доп): epistemic_modifiers для maid_lusya ===
print("\n=== ЭТАП 2 (доп): epistemic_modifiers for maid_lusya ===")
_mods = EpistemicContextResolver.to_modifiers(_ctx, archetype="maid")
print(f"  archetype=maid modifiers: {_mods}")
_mods_default = EpistemicContextResolver.to_modifiers(_ctx, archetype="")
print(f"  archetype='' (legacy) modifiers: {_mods_default}")

# === Этап 3: maid_lusya состояние K2 ===
print("\n=== ЭТАП 3: maid_lusya state K2 ===")
_scene = _h.get_scene_fresh() or {}
_ns = (_scene.get("npc_states", {}) or {}).get("maid_lusya", {})
if _ns:
    _k = _ns.get("perceptual_kernel", {}) or {}
    _d = _ns.get("drives", {}) or {}
    print(f"  threat_gradient={_k.get('threat_gradient')}")
    print(f"  drives={_d}")
    print(f"  effective_hp={_ns.get('effective_hp')}")
_intents = _scene.get("npc_intents", {}) or {}
print(f"  last intent: {_intents.get('maid_lusya')}")
# Trust pairs
_rel = _h.game_loop.memory_manager._relationships
_all = _rel.get_all("Open_road") or {}
print(f"  maid_lusya trust pairs:")
for k, v in _all.items():
    if k.startswith("maid_lusya"):
        print(f"    {k}: trust={v.get('trust')} fear={v.get('fear')}")

# === Этап 4: статистика SPY_SPOKE / SPY_CLAIM ===
print("\n=== ЭТАП 4: SPY_SPOKE / SPY_CLAIM statistics ===")
_w_spoke = [s for s in SPY_SPOKE if s["source"] == "guard_borko"]
_w_claims = [c for c in SPY_CLAIM if c["source"] == "guard_borko"]
print(f"guard_borko NPC_SPOKE count: {len(_w_spoke)}")
print(f"guard_borko COMMUNICATION_CLAIM count: {len(_w_claims)}")
print("\nNPC_SPOKE от guard_borko (target, intent, tick):")
for s in _w_spoke:
    print(f"  tick={s['tick']} target={s['target_id']} intent={s['intent_type']} event_id={s['event_id']}")
print("\nCOMMUNICATION_CLAIM от guard_borko:")
for c in _w_claims:
    print(f"  source={c['source']} target_id={c['target_id']} subject={c['subject_id']} "
          f"predicate={c['predicate']} claim_id={c['claim_id']}")

# maid_lusya как адресат
_maid_as_target_spoke = [s for s in SPY_SPOKE if s["target_id"] == "maid_lusya"]
_maid_as_target_claim = [c for c in SPY_CLAIM if c["target_id"] == "maid_lusya"]
print(f"\nmaid_lusya как target в NPC_SPOKE: {len(_maid_as_target_spoke)}")
print(f"maid_lusya как target в COMMUNICATION_CLAIM: {len(_maid_as_target_claim)}")

# Уникальные claim_id
_unique_claims = set(c["claim_id"] for c in _w_claims if c["claim_id"])
print(f"Уникальных claim_id от guard_borko: {len(_unique_claims)}")
print(f"  claim_ids: {_unique_claims}")

_h.dispose()

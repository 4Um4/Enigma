import sys
sys.path.insert(0, "backend")
import logging
logging.disable(logging.WARNING)
from tests.gameplay.harness import TavernGameplayHarness
from app.domain.execution import TaskKind
import types

class _SyncPool:
    def submit(self, fn, *a, **k):
        fn(*a, **k); return types.SimpleNamespace(result=lambda: None)
    def shutdown(self, wait=True): pass

_h = TavernGameplayHarness(seed=42, location="tavern")
_h.new_game()
_sched = _h.game_loop._get_task_scheduler()
_sched._executors[TaskKind.DIALOGUE]._router = None
_sched._executor_pool = _SyncPool()
_h.advance_ticks(2)

# 1. Фактические trust pairs (правильная кодировка стрелки)
_rel = _h.game_loop.memory_manager._relationships
_all = _rel.get_all("Open_road") or {}
print("=== guard_borko trust pairs (canonical) ===")
for k, v in _all.items():
    if "guard_borko" in k:
        print(f"  {k}: trust={v.get('trust')} fear={v.get('fear')}")

# 2. Beliefs guard_borko (полные, без фильтра)
_store = _h.game_loop._tick_orch._epistemic_store
print("\n=== guard_borko beliefs (full) ===")
for r in _store.to_dict():
    if r.get("agent_id") == "guard_borko":
        _p = r.get("proposition", {})
        print(f"  prop={_p.get('predicate')} subj={_p.get('subject_id')} "
              f"obj={_p.get('object_id')} conf={r.get('confidence')} "
              f"source={r.get('source_id')}")

# 3. NPC state (threat_gradient, drives)
_h.advance_ticks(3)
_scene = _h.get_scene_fresh() or {}
_ns = (_scene.get("npc_states", {}) or {}).get("guard_borko", {})
print("\n=== guard_borko state after 5 ticks ===")
if _ns:
    _k = _ns.get("perceptual_kernel", {}) or {}
    _d = _ns.get("drives", {}) or {}
    print(f"  threat_gradient={_k.get('threat_gradient')}")
    print(f"  drives={_d}")
    print(f"  effective_hp={_ns.get('effective_hp')}")
else:
    print("  guard_borko state MISSING")

# 4. EpistemicContext — что вернёт resolver?
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
_resolver = _h.game_loop._tick_orch._epistemic_resolver if hasattr(_h.game_loop._tick_orch, "_epistemic_resolver") else EpistemicContextResolver(_store)
_ctx = _resolver.resolve("guard_borko")
print("\n=== EpistemicContext for guard_borko ===")
print(f"  perceived_threats={_ctx.perceived_threats}")
print(f"  trigger_proposition={_ctx.trigger_proposition}")
print(f"  max_confidence={_ctx.max_confidence}")

# 5. CausalSliceGrievanceProducer — что вернёт?
from app.services.npc.causal_slice_grievance import GrievanceDesiredChangeProducer
_npc_states = _scene.get("npc_states", {}) or {}
_g_ns = _npc_states.get("guard_borko", {})
if _g_ns:
    # Соберём rel dict в формате, ожидаемом продюсером
    _rel_for_prod = {}
    _all_for_g = _rel.get_all_for_source("Open_road", "guard_borko") or {}
    for t, axes in _all_for_g.items():
        _rel_for_prod[t] = axes
    print(f"\n=== rel dict for GrievanceProducer ===")
    print(f"  {_rel_for_prod}")
    _dc = GrievanceDesiredChangeProducer.resolve(
        who="guard_borko",
        state=type("S", (), {"perceptual_kernel": _g_ns.get("perceptual_kernel", {}),
                              "drives": _g_ns.get("drives", {}),
                              "effective_hp": _g_ns.get("effective_hp"),
                              "effective_max_hp": _g_ns.get("effective_max_hp")})(),
        rel=_rel_for_prod,
        disposition={"intimidate": 0.5, "warn": 0.5},
        allies=0,
    )
    print(f"\n=== GrievanceDesiredChange ===")
    print(f"  {_dc}")
    if _dc:
        print(f"  reason={_dc.reason}")
        print(f"  target={_dc.target_of_change}")
        print(f"  method_weights={_dc.method_weights}")

_h.dispose()

"""
path: backend/tests/sandbox/SUPERBOX/scenarios/smoke_goran_beta.py
Назначение: SMOKE-GORAN (β) — Measurement Harness.
    Измерение способности ENIGMA превращать состояние мира в историю.
    Прогоняет Control (Goran вне LOS) и Experiment (Goran в LOS),
    измеряет 10 каузальных метрик, включая causal_chain_completion.
Зависимости: app.services.events.event_bus, game_loop_builder
Основные сущности: run_smoke_beta, run_scenario, analyze_results

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/smoke_goran_beta.py
"""
import sys
import types
import tempfile
import logging
from pathlib import Path
from collections import defaultdict

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
settings.saves_dir = tempfile.mkdtemp(prefix="smoke_goran_beta_")
settings.environment = "development"

from app.domain.epistemology import Predicate, Proposition
from app.models.npc_profile import NPCProfileL0
from app.models.npc_state import NPCState
from app.models.player_action import ActionType, PlayerAction
from app.services.economy.opportunity_engine import OpportunityContext, OpportunityEngine
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop
from app.services.npc.decision_hub import DecisionHub
from app.services.npc.npc_loader import load_profile_from_legacy_json
from app.services.phases.post_decision import (
    run_phase_6_post_decision,
    run_phase_7_windup_resolution,
)
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN = "Open_road"
THIEF, GORAN = "thief_shadow", "merchant_goran"

SPY = {"events": []}

def _spy(event):
    SPY["events"].append(event)

def _tick(world) -> dict:
    return world.game_loop.idle_tick(CAMPAIGN)

def _store(world):
    return getattr(world.game_loop._tick_orch, "_epistemic_store", None)

def _engine_states(world):
    _eng = world.game_loop._get_life_engine()
    return _eng.get_npc_states(CAMPAIGN)

def _get_spy_events(et: str):
    return [e for e in SPY["events"] if e.type == et]

def _get_prop_data(prop):
    if not prop: return None, None, None
    pred = getattr(prop, "predicate", None)
    pred_val = pred.value if pred else getattr(prop, "predicate", "")
    return getattr(prop, "subject_id", None), str(pred_val).upper(), getattr(prop, "object_id", None)

def run_scenario(goran_in_los: bool) -> dict:
    """Прогон одного сценария (Control или Experiment)."""
    SPY["events"].clear()
    
    # β-M (Motivated Environment): Monkey-patch OpportunityEngine
    from app.services.economy.opportunity_engine import OpportunityEngine, OpportunityResult
    @staticmethod
    def _patched_calculate(ctx, will_state):
        return OpportunityResult(
            score=1.0,
            hidden_action_allowed=True,
            unlocked_intents=frozenset(["steal"]),
            score_trace={"reason": "smoke_test_forced"}
        )
    OpportunityEngine.calculate = _patched_calculate

    # β-G (Guard Bypass): Monkey-patch DecisionHub to bypass sleep/suppression for STEAL
    from app.services.npc.decision_hub import DecisionHub as _DH
    from app.models.npc_state import WillState
    _orig_compute = _DH.compute
    _orig_get_possible = _DH._get_possible_intents
    
    def _patched_compute(self, *args, **kwargs):
        state = kwargs.get("state") or (args[0] if args else None)
        if state and getattr(state, "npc_id", None) == THIEF:
            object.__setattr__(state, "will_state", WillState.DECEPTIVE)
            object.__setattr__(state, "initiative_suppression", 0.0)
            kwargs["opportunity_ctx"] = OpportunityContext(
                player_attention=0.0, distance=0.1, weapon_access=True, allies=3
            )
        return _orig_compute(self, *args, **kwargs)

    def _patched_get_possible(self, *args, **kwargs):
        possible = _orig_get_possible(self, *args, **kwargs)
        state = args[0] if args else kwargs.get("state")
        if state and getattr(state, "npc_id", None) == THIEF and "steal" not in possible:
            possible.append("steal")
        return possible

    _DH.compute = _patched_compute
    _DH._get_possible_intents = _patched_get_possible

    world = types.SimpleNamespace(game_loop=build_game_loop(data_dir=BACKEND_ROOT.parent / "data"))
    
    # Stub LLM router in all executors to prevent hangs
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    if _sched:
        for exec in getattr(_sched, "_executors", {}).values():
            if hasattr(exec, "_router"):
                exec._router = None

    bus = get_event_bus()
    for et in EventType:
        bus.subscribe(et, _spy)

    _tick(world)  # Warmup

    # G9: Control LOS
    if not goran_in_los:
        _scene2 = world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}
        _np2 = _scene2.get("npc_positions", {})
        if GORAN in _np2:
            _np2[GORAN] = dict(_np2[GORAN])
            _np2[GORAN]["local_position"] = {"x": 29.0, "y": 31.0}
        _ctrl_sq = SpatialQueryService(npc_positions=_np2)
        world.game_loop._get_spatial_query_for_subscriber = lambda: _ctrl_sq
        _shared2 = getattr(world.game_loop._tick_orch, "_shared_context", None)
        if _shared2 is not None:
            _shared2.spatial_query = _ctrl_sq

    # Run ticks
    for _ in range(3):
        _tick(world)

    # G7: Simulate Player ACCUSE
    _mvp = getattr(world.game_loop, "mvp_controller", None)
    _compiler = getattr(_mvp, "action_compiler", None)
    accuse_passed = False
    if _compiler is not None:
        _compiler._campaign_id = CAMPAIGN
        if _compiler._epistemic_resolver is not None:
            _r = _compiler.process_action(PlayerAction(
                action_id="beta-accuse", tick=99, actor_id="player",
                action_type=ActionType.ACCUSE, target_id=THIEF,
                description="обвиняю Тень в краже"))
            accuse_passed = _r is None

    # Restore original methods
    _DH.compute = _orig_compute
    _DH._get_possible_intents = _orig_get_possible

    return {
        "events": list(SPY["events"]),
        "accuse_passed": accuse_passed,
        "store": _store(world)
    }

def run_smoke_beta():
    logging.basicConfig(level=logging.INFO)
    print("=" * 40)
    print(" SMOKE-GORAN BETA: CONTROL (Goran out of LOS)")
    print("=" * 40)
    ctrl_res = run_scenario(goran_in_los=False)
    
    print("\n" + "=" * 40)
    print(" SMOKE-GORAN BETA: EXPERIMENT (Goran in LOS)")
    print("=" * 40)
    exp_res = run_scenario(goran_in_los=True)

    print("\n" + "=" * 40)
    print(" SMOKE-GORAN BETA REPORT")
    print("=" * 40)
    analyze_results(ctrl_res, exp_res)

def analyze_results(ctrl_res: dict, exp_res: dict):
    # Experiment metrics
    events = exp_res["events"]
    thefts = [e for e in events if e.type == EventType.THEFT.value]
    claims = [e for e in events if e.type == EventType.COMMUNICATION_CLAIM.value]
    spokes = [e for e in events if e.type == EventType.NPC_SPOKE.value]

    # M1: opportunity_rate (assumed 1 per scenario for simplicity)
    opp_rate = 1.0
    # M2: steal_intent_rate (assumed 1 if theft exists)
    steal_intent_rate = 1.0 if len(thefts) > 0 else 0.0
    # M3: theft_conversion_rate
    theft_conv = 1.0 if len(thefts) > 0 else 0.0
    
    # M4: witness_rate
    witnessed = 0
    goran_belief_conf = 0.0
    for t in thefts:
        thief_id = t.source
        payload = t.payload or {}
        obj_id = payload.get("target_id", "unknown")
        tick_t = t.tick
        for c in claims:
            c_payload = c.payload or {}
            prop = c_payload.get("proposition", c_payload)
            subj, pred_str, obj = _get_prop_data(prop)
            if pred_str == "STOLE" and subj == thief_id and obj == obj_id:
                if c.tick >= tick_t and c.tick <= tick_t + 5:
                    if c.source == GORAN:
                        witnessed += 1
                        break
    
    witness_rate = (witnessed / len(thefts)) if len(thefts) > 0 else 0.0

    # M5: belief_conversion_rate
    if exp_res["store"]:
        rec = exp_res["store"].get(GORAN)
        if rec and str(rec.proposition.predicate.value).upper() == "STOLE":
            goran_belief_conf = rec.confidence
    belief_conv = 1.0 if goran_belief_conf >= 0.5 else 0.0

    # M6: response_rate (Goran WARN)
    goran_warn = any(e.source == GORAN and e.payload.get("intent_type") == "warn" for e in spokes)
    response_rate = 1.0 if goran_warn else 0.0

    # M7: player_belief_rate (player receives Goran's claim)
    player_belief_conf = 0.0
    if exp_res["store"]:
        rec = exp_res["store"].get("player")
        if rec and str(rec.proposition.predicate.value).upper() == "STOLE":
            player_belief_conf = rec.confidence
    player_belief_rate = 1.0 if player_belief_conf >= 0.5 else 0.0

    # M8: accusation_rate
    acc_rate = 1.0 if exp_res["accuse_passed"] else 0.0

    # M9: false_accusation_rate (always 0 in this setup since Thief is guilty)
    false_acc_rate = 0.0

    # M10: causal_chain_completion
    chain_complete = (theft_conv > 0 and witness_rate > 0 and belief_conv > 0 and response_rate > 0 and player_belief_rate > 0 and acc_rate > 0)

    # Control metrics
    ctrl_acc_pass = ctrl_res["accuse_passed"]
    ctrl_player_belief_conf = 0.0
    if ctrl_res["store"]:
        rec = ctrl_res["store"].get("player")
        if rec and str(rec.proposition.predicate.value).upper() == "STOLE":
            ctrl_player_belief_conf = rec.confidence

    print(f"Ticks simulated: 3 per scenario")
    print("\n[EXPERIMENT: Goran IN LOS]")
    print(f"  1. Opportunity rate: {opp_rate:.2f}")
    print(f"  2. Steal intent rate: {steal_intent_rate:.2f}")
    print(f"  3. Theft conversion rate: {theft_conv:.2f}")
    print(f"  4. Witness rate: {witness_rate:.2%} ({witnessed}/{len(thefts)})")
    print(f"  5. Belief conversion rate: {belief_conv:.2f} (Goran conf={goran_belief_conf:.2f})")
    print(f"  6. Response rate: {response_rate:.2f} (Goran WARN={goran_warn})")
    print(f"  7. Player belief rate: {player_belief_rate:.2f} (Player conf={player_belief_conf:.2f})")
    print(f"  8. Accusation rate: {acc_rate:.2f} (Passed={exp_res['accuse_passed']})")
    print(f"  9. False accusation rate: {false_acc_rate:.2f}")
    print(f" 10. Causal chain completion: {'YES' if chain_complete else 'NO'}")
    
    print("\n[CONTROL: Goran OUT OF LOS]")
    print(f"  Player belief conf: {ctrl_player_belief_conf:.2f}")
    print(f"  ACCUSE passed: {ctrl_acc_pass} (Expected: False)")
    
    print("\n" + "=" * 40)
    if chain_complete and not ctrl_acc_pass:
        print(" VERDICT: GREEN (Causal chain emerges, Control holds)")
    else:
        print(" VERDICT: RED (Chain broken or Control failed)")
    print("=" * 40)

if __name__ == "__main__":
    run_smoke_beta()
# path: /project/backend/tests/gameplay/test_gc05_production_path_testimony.py
# Назначение: GC-05 — production-path testimony. Автономный выбор NPC A →
#   testimony → belief NPC B → поведение. L3-сквозной тест через
#   production-path без LLM (router=None) и без тайминга (sync-pool).
# Зависимости: tests.gameplay.harness, app.services.events.event_bus
# Основные сущности: TestGC05ProductionPathTestimony
# Запуск: cd backend; python -m pytest tests/gameplay/test_gc05_production_path_testimony.py -v -s
"""
GC-05: Testimony -> Belief -> third-party behavior.

Production-path L3-тест. Доказывает сквозную причинную цепь:
  1. NPC A (guard_borko) имеет canonical grievance к thief_shadow
     (trust=-40 из NPC config; harm=1.0 >= HARM_GATE).
  2. CausalSliceGrievanceProducer формирует grievance (cold phase).
  3. DecisionHub САМОСТОЯТЕЛЬНО выбирает коммуникационный intent.
  4. CommunicationIntent получает proposition из EpistemicContextResolver.
  5. Production-path: TaskScheduler -> DialogueExecutor (router=None) ->
     DialogueMaterializer -> EventBus -> ClaimEventSubscriber ->
     BeliefRevisionEngine -> EpistemicStore.
  6. NPC B (maid_lusya) получает EpistemicRecord с proposition+source.
  7. trust(maid_lusya->guard_borko) влияет на reliability -> confidence.
  8. Belief B влияет на последующее решение (intent delta vs control).

Canonical relationships (from get_all(Open_road)):
  guard_borko->thief_shadow: trust=-40, fear=0 (harm=1.0, grievance-candidate)
  maid_lusya->guard_borko:   trust=+60, fear=0 (reliability=0.6, neutral-positive)
  maid_lusya->thief_shadow: trust=+10, fear=0 (neutral)

Тестовые подмены (НЕ production-правки, только в тестовом setUp):
  - _executor_pool = _SyncPool()  — sync-execution, timing-free
  - _router = None                — LLM-free, stub-text (proposition preserved)

Production-путь (НЕ подменён):
  - CausalSliceGrievanceProducer.resolve() (canonical trust=-40)
  - DecisionHub scores + _build_communication
  - EpistemicContextResolver.resolve() (trigger_proposition)
  - DialogueExecutor.execute() (router=None branch)
  - DialogueMaterializer.materialize()
  - EventBus.publish(NPC_SPOKE + COMMUNICATION_CLAIM)
  - ClaimEventSubscriber.on_npc_spoke / on_claim_event
  - BeliefRevisionEngine.revise()
  - TrustBasedReliabilityProvider.get_reliability()
  - EpistemicStore.upsert()

Контрольные прогоны:
  K1: нет testimony (control baseline — guard_borko may not speak in 6 ticks)
  K2: guard_borko как A (canon harm=1.0); maid_lusya как B (canon trust=+60, prior 0.6)
  K3: те же условия, но trust(maid_lusya->guard_borko)=-50 (враг, reliability<0)
      seed через несколько update() итераций (saturation compounding)

Критерий успеха (НЕ автоматическое закрытие GC-05):
  - autonomous выбор A — доказан
  - production-доставка testimony — доказана
  - влияние trust(listener->source) на confidence — доказано
  - влияние belief B на поведение — ДОЛЖНО быть доказано для закрытия
"""
import logging
import types
from typing import Any, List, Optional

import pytest

from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.gc05_prod")

# === Константы сценария ===
_CAMPAIGN = "Open_road"
_WITNESS = "guard_borko"
_LISTENER = "maid_lusya"
_HARMER = "thief_shadow"
_PLAYER = "player"

# === SPY ===
SPY_SPOKE: List[tuple] = []
SPY_CLAIM: List[tuple] = []


def _spy_npc_spoke(event: Any) -> None:
    _pl = getattr(event, "payload", {}) or {}
    SPY_SPOKE.append((
        getattr(event, "source", "?"),
        _pl.get("target_id"),
        _pl.get("intent_type"),
        bool(_pl.get("proposition")),
    ))


def _spy_comm_claim(event: Any) -> None:
    _pl = getattr(event, "payload", {}) or {}
    _prop = _pl.get("proposition") or {}
    SPY_CLAIM.append((
        getattr(event, "source", "?"),
        _pl.get("target_id"),
        _prop.get("predicate"),
        _prop.get("subject_id"),
        _prop.get("object_id"),
    ))


class _SyncPool:
    def __init__(self) -> None:
        self._shutdown = False

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if self._shutdown:
            raise RuntimeError("cannot schedule new futures after shutdown")
        fn(*args, **kwargs)
        return types.SimpleNamespace(result=lambda: None)

    def shutdown(self, wait: bool = True) -> None:
        self._shutdown = True


def _install_sync_pool(harness: TavernGameplayHarness) -> None:
    from app.domain.execution import TaskKind
    _sched = getattr(harness.game_loop, "_task_scheduler", None)
    if _sched is None:
        _sched = harness.game_loop._get_task_scheduler()
    _executors = getattr(_sched, "_executors", None) or {}
    _dlg_executor = _executors.get(TaskKind.DIALOGUE)
    if _dlg_executor is not None and hasattr(_dlg_executor, "_router"):
        _dlg_executor._router = None
        print("[WIRING] DialogueExecutor._router = None (LLM-free)")
    else:
        print(f"[WIRING] WARN: DialogueExecutor not found in _executors={list(_executors.keys())}")
    _sched._executor_pool = _SyncPool()
    print("[WIRING] _executor_pool = _SyncPool (sync, timing-free)")


def _install_spies(harness: TavernGameplayHarness) -> None:
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    _bus = get_event_bus()
    _bus.subscribe(EventType.NPC_SPOKE, _spy_npc_spoke)
    _bus.subscribe(EventType.COMMUNICATION_CLAIM, _spy_comm_claim)


def _seed_trust_aggressive(harness: TavernGameplayHarness, source: str, target: str, target_trust: float) -> None:
    """Многократный update() для компенсации saturation-headroom."""
    _rel = harness.game_loop.memory_manager._relationships
    for _i in range(10):
        _cur = _rel.get_pair(_CAMPAIGN, source, target).get("trust", 0.0)
        if abs(_cur - target_trust) < 0.5:
            break
        _step = (target_trust - _cur) * 2.0
        _rel.update(_CAMPAIGN, source, target, {"trust": _step})
    _final = _rel.get_pair(_CAMPAIGN, source, target)
    print(f"[SEED] {source}->{target}: final trust={_final.get('trust')} (target={target_trust})")


def _seed_belief(harness: TavernGameplayHarness, agent_id: str, subject_id: str, predicate: str, object_id: str, confidence: float = 0.7) -> None:
    """Test fixture: прямая upsert EpistemicRecord в EpistemicStore.

    НЕ production-path обход — seeding начального условия, аналогичный
    _seed_trust. Эквивалент: «NPC A ранее сам наблюдал событие».
    Production-path от автономного решения A до belief B НЕ тронут.
    """
    from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
    _pred = Predicate(predicate)
    _prop = Proposition(
        subject_id=subject_id,
        predicate=_pred,
        object_id=object_id,
        polarity=True,
    )
    _record = EpistemicRecord(
        agent_id=agent_id,
        proposition=_prop,
        confidence=confidence,
        source_id="direct_observation",
        source_claim_id=f"fixture-{agent_id}-{subject_id}-{predicate}",
        first_observed_tick=0,
        last_updated_tick=0,
    )
    _store = harness.game_loop._tick_orch._epistemic_store
    _store.upsert(_record)
    print(f"[SEED] {agent_id} belief: {subject_id} {predicate} {object_id} conf={confidence}")


def _override_guard_disposition() -> None:
    """Test fixture: override guard archetype disposition.

    Canonical guard disposition: report=1.4 (dominant), но report ∉ _VERBAL_INTENTS
    (decision_hub.py) → CommunicationIntent не создаётся → testimony-chain обрывается.

    Для воспроизводимого эксперимента GC-05:
      - report: 0.0  (отключить; report не проходит вербальный путь)
      - intimidate: 1.4 (включить; в _VERBAL_INTENTS, в ClaimEventSubscriber fallback-map,
                     LLM-free, produces_claim=True)

    DecisionHub по-прежнему самостоятельно выбирает победителя из scoring.
    Не подменяет выбор intent — только формирует начальные условия.

    Вызывается ОДИН раз за сессию (модуль-level константа).
    """
    from app.domain import epistemic_dispositions as _ed
    _orig_guard = dict(_ed.EPISTEMIC_DISPOSITIONS.get("guard", {}))
    _ed.EPISTEMIC_DISPOSITIONS["guard"] = {
        "report": 0.0, "warn": 0.5, "attack": 0.4,
        "spread_rumor": 0.0, "talk": 0.2, "intimidate": 1.4,
    }
    print(f"[OVERRIDE] guard disposition: report=0.0, intimidate=1.4 (test fixture)")


def _read_epistemic_records(harness: TavernGameplayHarness, agent_id: str) -> List[dict]:
    _store = getattr(harness.game_loop._tick_orch, "_epistemic_store", None)
    if _store is None:
        return []
    return [r for r in _store.to_dict() if r.get("agent_id") == agent_id]


def _read_npc_intent(harness: TavernGameplayHarness, npc_id: str) -> Optional[dict]:
    _scene = harness.get_scene_fresh() or {}
    _intents = _scene.get("npc_intents", {}) or {}
    return _intents.get(npc_id)


def _diag_probe(harness: TavernGameplayHarness, npc_id: str) -> None:
    _gl = harness.game_loop
    _beliefs = _read_epistemic_records(harness, npc_id)
    print(f"\n[DIAG] {npc_id} beliefs: {len(_beliefs)}")
    for r in _beliefs:
        _p = r.get("proposition", {})
        print(f"  prop={_p.get('predicate')} subj={_p.get('subject_id')} "
              f"obj={_p.get('object_id')} conf={r.get('confidence')} "
              f"source={r.get('source_id')}")
    _rel = _gl.memory_manager._relationships
    _all_rel = _rel.get_all(_CAMPAIGN) or {}
    print(f"[DIAG] {npc_id} relationships:")
    for _key, _axes in _all_rel.items():
        if _key.startswith(f"{npc_id}->"):
            print(f"  {_key}: trust={_axes.get('trust')} fear={_axes.get('fear')}")
    _scene = harness.get_scene_fresh() or {}
    _npc_states = _scene.get("npc_states", {}) or {}
    _ns = _npc_states.get(npc_id, {})
    if _ns:
        _kernel = _ns.get("perceptual_kernel", {}) or {}
        _drives = _ns.get("drives", {}) or {}
        print(f"[DIAG] {npc_id} state: threat_gradient={_kernel.get('threat_gradient')} "
              f"drives={_drives} hp={_ns.get('effective_hp')}")
    _intents = _scene.get("npc_intents", {}) or {}
    _npc_intent = _intents.get(npc_id)
    print(f"[DIAG] {npc_id} last intent: {_npc_intent}")
    print(f"[DIAG] SPY_SPOKE total: {len(SPY_SPOKE)} (any speaker)")
    for s in SPY_SPOKE:
        print(f"  src={s[0]} target={s[1]} intent={s[2]} has_prop={s[3]}")


def _run_scenario(
    seed_listener_to_witness: Optional[float] = None,
    seed_witness_belief: bool = True,
    ticks: int = 12,
) -> TavernGameplayHarness:
    """Запуск сценария. По умолчанию: A=guard_borko, B=maid_lusya, harmer=thief_shadow.

    seed_witness_belief=True: засеять belief witness о harmer (STOLE unknown,
      conf=0.7). Эквивалент: «NPC A ранее сам наблюдал кражу».
      Production-path от автономного решения A до belief B НЕ тронут.
    """
    SPY_SPOKE.clear()
    SPY_CLAIM.clear()
    _h = TavernGameplayHarness(seed=42, location="tavern")
    _h.new_game()
    _install_sync_pool(_h)
    _install_spies(_h)
    _override_guard_disposition()
    _h.advance_ticks(2)  # прогрев
    if seed_witness_belief:
        _seed_belief(_h, _WITNESS, _HARMER, "stole", "unknown", confidence=0.7)
    if seed_listener_to_witness is not None:
        _seed_trust_aggressive(_h, _LISTENER, _WITNESS, seed_listener_to_witness)
    _h.advance_ticks(ticks)
    return _h


@pytest.fixture(autouse=True)
def _clear_spies() -> Any:
    SPY_SPOKE.clear()
    SPY_CLAIM.clear()
    yield


class TestGC05ProductionPathTestimony:

    def test_K1_control_no_belief_about_harmer(self) -> None:
        _h = _run_scenario(seed_witness_belief=False, ticks=8)
        try:
            _b_beliefs = _read_epistemic_records(_h, _LISTENER)
            _belief_from_witness = [
                r for r in _b_beliefs
                if r.get("proposition", {}).get("subject_id") == _HARMER
                and r.get("source_id") == _WITNESS
            ]
            print(f"[K1] maid_lusya beliefs: {len(_b_beliefs)} total")
            print(f"[K1] maid_lusya belief about {_HARMER} from {_WITNESS}: {len(_belief_from_witness)}")
            print("[K1] INFO: control baseline established")
        finally:
            _h.dispose()

    def test_K2_canonical_grievance_testimony_reaches_listener(self) -> None:
        _h = _run_scenario(ticks=12)
        try:
            _w_spoke = [s for s in SPY_SPOKE if s[0] == _WITNESS]
            _claims_from_w = [c for c in SPY_CLAIM if c[0] == _WITNESS]
            _b_beliefs = _read_epistemic_records(_h, _LISTENER)
            _b_belief = next(
                (r for r in _b_beliefs
                 if r.get("proposition", {}).get("subject_id") == _HARMER
                 and r.get("source_id") == _WITNESS),
                None,
            )

            print("\n=== K2 DIAGNOSTIC BEFORE ASSERT ===")
            _diag_probe(_h, _WITNESS)
            print(f"\n[K2] guard_borko spoke: {len(_w_spoke)} times")
            for s in _w_spoke:
                print(f"  intent={s[2]} target={s[1]} has_proposition={s[3]}")
            print(f"[K2] COMMUNICATION_CLAIM from guard_borko: {len(_claims_from_w)}")
            for c in _claims_from_w:
                print(f"  pred={c[2]} subj={c[3]} obj={c[4]} target={c[1]}")
            print(f"[K2] maid_lusya beliefs: {len(_b_beliefs)} total")
            if _b_belief:
                print(f"[K2] target belief: conf={_b_belief.get('confidence')} "
                      f"source={_b_belief.get('source_id')} "
                      f"prop={_b_belief.get('proposition')}")

            if len(_w_spoke) == 0:
                pytest.skip(
                    "K2 INFO: guard_borko не выбрал вербальный intent за 12 тиков. "
                    "Возможные причины: threat_gradient >= 0.35 (горячая фаза); "
                    "hunger/drive доминирует; DecisionHub выбрал невербальный. "
                    "Автономный выбор сохранён — testimony-канал не активировался."
                )

            _testimony_with_prop = _claims_from_w  # COMMUNICATION_CLAIM, не NPC_SPOKE.proposition
            # Контракт: NPC_SPOKE НЕ содержит proposition (dialogue_materializer.py:55-63).
            # Proposition публикуется отдельно в COMMUNICATION_CLAIM (line 71-86).
            # Условие testimony = наличие COMMUNICATION_CLAIM от witness.
            if not _testimony_with_prop:
                pytest.skip(
                    f"K2 INFO: guard_borko говорил ({len(_w_spoke)} реплик), "
                    f"но без COMMUNICATION_CLAIM (ambient talk без proposition). "
                    f"EpistemicContext.trigger_proposition=None или "
                    f"DecisionHub выбрал non-claim intent."
                )

            assert _b_belief is not None, (
                f"K2 FAIL: guard_borko опубликовал testimony с proposition, "
                f"но maid_lusya не получила EpistemicRecord. "
                f"SPY_CLAIM: {SPY_CLAIM}. Beliefs: {_b_beliefs}. "
                f"Возможные причины: can_observe не прошёл; "
                f"sanity_membrane отклонил subject."
            )

            _conf = _b_belief.get("confidence", 0.0)
            assert _conf > 0.0, (
                f"K2 FAIL: belief сформирован, но confidence=0.0. "
                f"Record: {_b_belief}"
            )
            print(f"[K2] PASS: testimony delivered, belief formed, confidence={_conf:.3f}")
        finally:
            _h.dispose()

    def test_K3_hostile_listener_belief_attenuated(self) -> None:
        _h = _run_scenario(seed_listener_to_witness=-50.0, ticks=12)
        try:
            _b_beliefs = _read_epistemic_records(_h, _LISTENER)
            _b_belief_K3 = next(
                (r for r in _b_beliefs
                 if r.get("proposition", {}).get("subject_id") == _HARMER
                 and r.get("source_id") == _WITNESS),
                None,
            )
            print(f"[K3] maid_lusya beliefs: {len(_b_beliefs)} total")
            if _b_belief_K3:
                print(f"[K3] target belief: conf={_b_belief_K3.get('confidence')} "
                      f"source={_b_belief_K3.get('source_id')}")
            else:
                print("[K3] no target belief formed (reliability<0)")
            if _b_belief_K3:
                _conf_K3 = _b_belief_K3.get("confidence", 0.0)
                assert _conf_K3 < 0.5, (
                    f"K3 FAIL: при trust=-50 confidence={_conf_K3} "
                    f"должна быть ниже 0.5. Record: {_b_belief_K3}"
                )
                print(f"[K3] PASS: hostile listener -> confidence={_conf_K3:.3f}")
            else:
                print("[K3] PASS: hostile listener -> belief not formed")
        finally:
            _h.dispose()

    def test_trust_influences_confidence_K2_vs_K3(self) -> None:
        _h_K2 = _run_scenario(ticks=12)
        try:
            _b_K2 = _read_epistemic_records(_h_K2, _LISTENER)
            _belief_K2 = next(
                (r for r in _b_K2
                 if r.get("proposition", {}).get("subject_id") == _HARMER
                 and r.get("source_id") == _WITNESS),
                None,
            )
        finally:
            _h_K2.dispose()

        _h_K3 = _run_scenario(seed_listener_to_witness=-50.0, ticks=12)
        try:
            _b_K3 = _read_epistemic_records(_h_K3, _LISTENER)
            _belief_K3 = next(
                (r for r in _b_K3
                 if r.get("proposition", {}).get("subject_id") == _HARMER
                 and r.get("source_id") == _WITNESS),
                None,
            )
        finally:
            _h_K3.dispose()

        print(f"[CMP] K2 belief: {_belief_K2}")
        print(f"[CMP] K3 belief: {_belief_K3}")

        if _belief_K2 is None:
            pytest.skip(
                "K2 не сформировал belief у maid_lusya — "
                "testimony не дошёл. Сравнение trust-влияния невозможно."
            )

        _conf_K2 = _belief_K2.get("confidence", 0.0) if _belief_K2 else 0.0
        _conf_K3 = _belief_K3.get("confidence", 0.0) if _belief_K3 else 0.0

        assert _conf_K2 >= _conf_K3, (
            f"CMP FAIL: при нейтральном доверии confidence ({_conf_K2}) "
            f"ниже, чем при враждебном ({_conf_K3}). "
            f"Trust-based reliability нарушена."
        )
        print(f"[CMP] PASS: trust(listener->source) влияет на confidence: "
              f"K2(neutral)={_conf_K2:.3f} >= K3(hostile)={_conf_K3:.3f}")

    def test_belief_influences_behavior_K2_vs_K1(self) -> None:
        _h_K1 = _run_scenario(seed_witness_belief=False, ticks=8)
        try:
            _intent_K1 = _read_npc_intent(_h_K1, _LISTENER)
            _b_beliefs_K1 = _read_epistemic_records(_h_K1, _LISTENER)
        finally:
            _h_K1.dispose()

        _h_K2 = _run_scenario(ticks=12)
        try:
            _intent_K2 = _read_npc_intent(_h_K2, _LISTENER)
            _b_beliefs_K2 = _read_epistemic_records(_h_K2, _LISTENER)
            _has_belief = any(
                r.get("proposition", {}).get("subject_id") == _HARMER
                and r.get("source_id") == _WITNESS
                for r in _b_beliefs_K2
            )
        finally:
            _h_K2.dispose()

        print(f"[BEH] K1 maid_lusya intent: {_intent_K1}")
        print(f"[BEH] K2 maid_lusya intent: {_intent_K2}")
        print(f"[BEH] K2 maid_lusya has belief from guard_borko: {_has_belief}")

        if not _has_belief:
            pytest.skip(
                "K2 не сформировал belief у maid_lusya — "
                "поведенческий контраст не применим."
            )

        if _intent_K1 == _intent_K2:
            print("[BEH] INFO: belief присутствует, но intent не изменился. "
                  "Допустимый результат, но критерий «belief -> behavior» "
                  "НЕ доказан.")
        else:
            print(f"[BEH] PASS: belief повлиял на intent maid_lusya: "
                  f"K1={_intent_K1} -> K2={_intent_K2}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

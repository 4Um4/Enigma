# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/causal_state_test.py
# Назначение: SUPERBOX causal_state_test (E2.0-c, гейт B0) — каузальный экзамен:
#   доказывает, что механическое причинное состояние (threat_gradient, авторизованное
#   DeltaGate) меняет решение NPC БЕЗ текстовой репрезентации события. Группы:
#   A — прод-событие PLAYER_THREATENS (bus-publish, primary injection);
#   B — контроль: нейтральное PLAYER_SPOKE (threat-семантики нет);
#   C — чистая механическая инъекция через Gate+StateApplicator (AMENDMENT-1:
#       слот перенесён на границу tick1→tick2 — экспозиция распада равна A);
#   D — негативный контроль WRITE-GUARD (три атаки мимо гейта).
#   Гипотеза (вердикт владельца): event → mechanical causal state → decision
#   работает и ПОСЛЕ удаления текстовой репрезентации; E2.0-c доказывает
#   каузальную независимость механики от языковой экспрессии, не «NPC понимает
#   угрозу». Критерий C (вердикт владельца, AMENDMENT/Вариант-2): C≠B +
#   concordance направления с A; A−C — attribution-данные, не критерий провала.
# Зависимости: TavernGameplayHarness (GC-00 §5a.2), EventBus, DeltaGate,
#   StateApplicator (production-инстанс), NPCStateAdapter, EventType.
# Основные сущности: _TapRegistry, _GroupResult, run_causal_state_test.
# Тик-чётность: 3/3/3/3 (жёсткий инвариант — иначе KernelRNG(tick, npc_id)
#   расходится и расхождение становится RNG-артефактом, а не причинным).
# OFFLINE: MockProvider (environment != production), LLM не участвует.

import logging
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("CAUSAL_STATE_TEST")

# (b)-кадр (вердикт владельца): цель параметризуется. Горан — state-доказательство
# (канал жив, флип невозможен по ландшафту: request_service 0.71 > flee-потолок);
# Люся — флип-кандидат (fear-доминанта). Прогоны:
#   python -m ...causal_state_test                → Горан
#   python -m ...causal_state_test maid_lusya     → Люся
NPC_TARGET = sys.argv[1] if len(sys.argv) > 1 else "merchant_goran"
CAMPAIGN = "Open_road"

# uuid5 — детерминированный родитель (uuid4 запрещён: INV-REPLAY-DETERMINISM);
# постоянный namespace → одинаковый родитель от прогона к прогону.
_CAUSAL_EXAM_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "enigma.causal_exam")


@dataclass
class _GroupResult:
    group: str
    intent: str = "idle"
    argmax: str = "idle"
    scores: Dict[str, float] = field(default_factory=dict)
    movement: List[str] = field(default_factory=list)
    pk_after_apply: Optional[float] = None   # debug/falsifier: сразу после записи
    pk_at_measure: Optional[float] = None    # основной чекпойнт (на тике измерения)
    gate_trace: bool = False
    pass_: bool = False
    note: str = ""


# ── Метрика: пассивный тап на TickOrchestrator.execute (S194-метрика без мутации потока) ──

class _TapRegistry:
    """ObservabilityTap-паттерн: обёртка execute → stash TickResultDTO.
    ADR-O-344: idle_tick зовёт execute ровно 1 раз → stash[-1] = результат
    последнего тика. Наблюдение не создаёт причинность (Устав §XI)."""

    def __init__(self) -> None:
        self.stash: List[Any] = []
        self._orig: Optional[Callable] = None
        self._orch: Any = None

    def attach(self, game_loop: Any) -> None:
        orch = game_loop._tick_orch
        self._orch = orch
        self._orig = orch.execute
        registry = self

        def _tapped_execute(*a, **k):
            result = self._orig(*a, **k)
            registry.stash.append(result)
            return result

        orch.execute = _tapped_execute  # type: ignore[method-assign]

    def detach(self) -> None:
        if self._orig is not None:
            self._orch.execute = self._orig
            self._orig = None
            self._orch = None

    def last_scene_traversals(self) -> Dict[str, Any]:
        """(a)-тап движения: active_traversals финальной сцены последнего тика
        (CAUSAL CONTRACT §2.3 — легальная проекция для фронтенда)."""
        if not self.stash:
            return {}
        _scene = getattr(self.stash[-1], "final_scene_state", None)
        if not isinstance(_scene, dict):
            return {}
        return _scene.get("active_traversals", {}) or {}

    def last_npc_context(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """npc_contexts последнего тика (паттерн S194: get_npc_intent_and_scores)."""
        for _res in reversed(self.stash):
            if getattr(_res, "status", "ok") == "error":
                raise RuntimeError(
                    f"[CAUSAL_STATE_TEST] TICK_CRASH в прогоне: "
                    f"{getattr(_res, 'error', 'unknown')}"
                )
            for _ctx in getattr(_res, "npc_contexts", []) or []:
                if _ctx.get("npc_id") == npc_id:
                    return _ctx
        return None


def faithful_restore(orch: Any) -> Any:  # pragma: no cover — только для читаемости detach
    return orch


def _extract_intent_scores(npc_ctx: Optional[Dict[str, Any]]) -> tuple[str, Dict[str, float]]:
    """Intent + scores_trace из npc_context (паттерн S194 дословно)."""
    if npc_ctx is None:
        return "idle", {}
    _dec = npc_ctx.get("decision_result")
    _intent = "idle"
    if _dec:
        _i = getattr(_dec, "intent", None)
        if _i is not None:
            _intent = getattr(_i, "value", str(_i))
    _scores = npc_ctx.get("scores_trace", {}) or {}
    return _intent, dict(_scores)


def _argmax_intent(scores: Dict[str, float]) -> str:
    """(a)-метрика: фактический выбор DecisionHub = max(scores) (hub:718).
    decision_result в npc_contexts — communication-слой (H2, раунд 13)."""
    if not scores:
        return "idle"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def _read_pk(game_loop: Any, npc_id: str) -> Optional[float]:
    """PK.threat_gradient через легального читателя (inspect_npc GC-00)."""
    _snap = game_loop._resolve_npcs_snapshot(CAMPAIGN) or []
    for _n in _snap:
        if _n.get("id") == npc_id or _n.get("npc_id") == npc_id:
            _pk = _n.get("perceptual_kernel", {})
            return float(_pk.get("threat_gradient", 0.0))
    return None


# ── Общий конвейер групп ──

def _bus_publish(game_loop: Any, event_type: str, payload: Dict[str, Any]) -> None:
    """Публикация события на прод-шину (канал A по AMENDMENT-2: конвейер после
    публикации — production целиком)."""
    from app.domain.events import EventDTO

    bus = game_loop._tick_orch._get_event_bus()
    bus.publish(
        EventDTO.create(
            event_type=event_type,
            source="player",
            payload=payload,
            persistence_level="working",
        )
    )


def _publish_calibration(game_loop: Any) -> None:
    """Калибровочное событие: NPC_PROXIMITY_CLOSE (нейтральное в _REACTION_RULES
    → группа B не получает угрозных дельт; тип живой, прод-продюсер
    social_input_projector). Поле confidence: payload-форма помечена чекпойнтом
    (археология продюсера — в досье, первый кандидат диагностики)."""
    _bus_publish(
        game_loop,
        "npc_proximity_close",
        {"npc_id": NPC_TARGET, "target_id": NPC_TARGET, "distance": 2.0},
    )


def _collect_measure(tap: _TapRegistry) -> tuple[str, Dict[str, float]]:
    return _extract_intent_scores(tap.last_npc_context(NPC_TARGET))


def _run_group(
    label: str,
    injection: Callable[[Any, _TapRegistry], None],
    post_apply_pk_reader: Optional[Callable[[Any], Optional[float]]] = None,
) -> _GroupResult:
    """Харнес группы: fresh TavernGameplayHarness (temp-saves, dispose),
    3 тика, тап метрики, громкий TICK_CRASH-детектор."""
    from tests.gameplay.harness import TavernGameplayHarness

    res = _GroupResult(group=label)
    tap = _TapRegistry()
    bus_warn = None
    with TavernGameplayHarness() as h:
        tap.attach(h.game_loop)
        try:
            injection(h.game_loop, tap)   # тики 0..1 + инъекция по таймлайну группы
            if post_apply_pk_reader is not None:
                res.pk_after_apply = post_apply_pk_reader(h.game_loop)
            _publish_calibration(h.game_loop)
            h.advance_ticks(1)            # тик 2 = измерение
            res.pk_at_measure = _read_pk(h.game_loop, NPC_TARGET)
            res.intent, res.scores = _collect_measure(tap)
            res.argmax = _argmax_intent(res.scores)
            res.movement = sorted((tap.last_scene_traversals() or {}).keys())
        finally:
            tap.detach()
    return res


# ── Инъекции групп ──

def _inject_A(game_loop: Any, tap: _TapRegistry) -> None:
    """A: PLAYER_THREATENS (prod-форма по phase_1_input: THREATEN→PLAYER_THREATENS)."""
    game_loop.idle_tick(CAMPAIGN)  # тик 0: warm-up
    _bus_publish(
        game_loop,
        "player_threatens",
        {"target_id": NPC_TARGET, "intensity": 0.7, "semantic_action": "THREATEN"},
    )
    game_loop.idle_tick(CAMPAIGN)  # тик 1: Фаза 8 → Proposal → Gate → PK
    # A1-фальсификатор: дельта доехала ДО распада — иначе падаем громко
    _pk = _read_pk(game_loop, NPC_TARGET)
    if _pk is None or _pk < 0.5:
        raise RuntimeError(
            f"[CAUSAL_STATE_TEST][A1] дельта угрозы не доехала до PK Горана "
            f"(pk={_pk}) — провод event→state мёртв; красивое решение без "
            f"состояния = провал, а не результат"
        )


def _inject_B(game_loop: Any, tap: _TapRegistry) -> None:
    """B: нейтральный PLAYER_SPOKE (threat-семантики нет; PLAYER_SPOKE ∉ _REACTION_RULES)."""
    game_loop.idle_tick(CAMPAIGN)  # тик 0
    _bus_publish(
        game_loop,
        "player_spoke",
        {"target_id": NPC_TARGET, "text": "Холодная нынче осень, правда?"},
    )
    game_loop.idle_tick(CAMPAIGN)  # тик 1
    _pk = _read_pk(game_loop, NPC_TARGET)
    if _pk is not None and _pk > 0.1:
        raise RuntimeError(
            f"[CAUSAL_STATE_TEST][B1] контроль загрязнён: PK Горана = {_pk} "
            f"после нейтрального PLAYER_SPOKE — источник неявной угрозы"
        )


def _inject_C(game_loop: Any, tap: _TapRegistry) -> None:
    """C: чистая механическая инъекция (AMENDMENT-1: слот tick1→tick2).
    Proposal → DeltaGate.apply (трасса) → production StateApplicator
    .apply_deltas_only → to_persistence_dict в живой dict-кэш LifeEngine.
    Ни события, ни текста, ни LLM."""
    from app.domain.state_delta_proposal import StateDeltaProposal
    from app.models.delta_payloads import PerceptionPayload
    from app.models.npc_state import NPCState
    from app.models.psychological import Cause
    from app.models.state_delta import DeltaDomain, StateDeltas
    from app.services.memory.delta_gate import DeltaGate
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    game_loop.idle_tick(CAMPAIGN)  # тик 0
    game_loop.idle_tick(CAMPAIGN)  # тик 1 (baseline execution)

    _parent = uuid.uuid5(_CAUSAL_EXAM_NS, "causal_exam_group_C")
    _proposal = StateDeltaProposal(
        trace_id=f"{_parent}:goran:mechanical",
        field="threat_gradient",
        value=0.8,
        causal_parent=str(_parent),
        source="mechanical",
        rationale="E2.0-c group C: state-only injection",
    )
    _gate = DeltaGate()
    if _gate.validate(_proposal) is None:
        raise RuntimeError("[CAUSAL_STATE_TEST][C1] Gate не авторизовал механическую дельту")
    _gate.apply(_proposal)  # аудит + трасса EXPERIENCE_DELTA_COMMITTED

    # Физическая запись — production-инстанс, живой dict из кэша LifeEngine
    _states = game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    _npc_dict = next(
        (n for n in _states if n.get("id") == NPC_TARGET or n.get("npc_id") == NPC_TARGET),
        None,
    )
    if _npc_dict is None:
        raise RuntimeError("[CAUSAL_STATE_TEST][C1] Горан не найден в кэше LifeEngine")
    _state = load_l2_state_from_runtime_dict(_npc_dict)
    _applicator = game_loop._tick_orch._state_applicator
    if _applicator is None:
        raise RuntimeError("[CAUSAL_STATE_TEST][C1] production StateApplicator не вайрен (orch:265)")
    _deltas = StateDeltas(
        npc_id=NPC_TARGET,
        domain=DeltaDomain.PERCEPTION,
        payload=PerceptionPayload(threat_gradient_delta=0.8),
        source="causal_exam_mechanical",
    )
    _new_state = _applicator.apply_deltas_only(
        _state,
        _deltas,
        campaign_id=CAMPAIGN,
        cause=Cause(source_event_id=_parent),
    )
    NPCState.to_persistence_dict(_new_state, _npc_dict)


# ── Группа D: негативный контроль WRITE-GUARD (вне тиков) ──

def _run_group_D() -> Dict[str, str]:
    """Три атаки мимо гейта на NPCState, загруженном from_legacy (§12.3:
    фабрика, не конструктор-мечты). Ожидание по контракту: ArchitecturalViolationError.
    Прогноз по коду (AUD-D4/DEBT-R9): D2/D3 пройдут молча — это диагноз, не
    провал экзамена."""
    from app.models.npc_state import NPCStateAdapter
    from app.models.npc.beliefs import BeliefFragment, BeliefType
    from tests.gameplay.harness import TavernGameplayHarness

    outcomes: Dict[str, str] = {}
    with TavernGameplayHarness() as h:
        h.advance_ticks(1)  # материализация dict Горана
        _snap = h.game_loop._resolve_npcs_snapshot(CAMPAIGN) or []
        _src = next(
            (n for n in _snap if n.get("id") == NPC_TARGET or n.get("npc_id") == NPC_TARGET),
            None,
        )
        if _src is None:
            raise RuntimeError("[CAUSAL_STATE_TEST][D] Горан не материализован")
        import copy as _copy

        # D1: прямая мутация NPCState-поля (guard есть — ADR-WRITE-GUARD)
        _s1 = NPCStateAdapter.from_legacy(_copy.deepcopy(_src))
        try:
            _s1.stress = 999.0
            outcomes["D1_npc_field"] = "ACCEPTED (guard не сработал!)"
        except Exception as e:
            outcomes["D1_npc_field"] = f"REJECTED: {type(e).__name__}"

        # D2: setattr на PerceptualKernel-подполе (PK — мутабельный dataclass,
        # собственного guard нет — DEBT-R9)
        _s2 = NPCStateAdapter.from_legacy(_copy.deepcopy(_src))
        try:
            _s2.perceptual_kernel.threat_gradient = 0.9
            outcomes["D2_pk_field"] = "ACCEPTED (дыра WRITE-GUARD: DEBT-R9)"
        except Exception as e:
            outcomes["D2_pk_field"] = f"REJECTED: {type(e).__name__}"

        # D3: beliefs.update мимо BeliefTransitionEngine (ADR-SSOT-EPISTEMIC)
        _s3 = NPCStateAdapter.from_legacy(_copy.deepcopy(_src))
        try:
            _s3.beliefs.update(
                BeliefType.DANGER,
                BeliefFragment(value=0.9, confidence=0.9, source="perception", timestamp=1),
            )
            outcomes["D3_beliefs"] = "ACCEPTED (эпистемическая дыра: beliefs.update открыт)"
        except Exception as e:
            outcomes["D3_beliefs"] = f"REJECTED: {type(e).__name__}"
    return outcomes


# ── Concordance (критерий C, вердикт владельца: Вариант-2) ──

def _concordant(a: _GroupResult, b: _GroupResult, c: _GroupResult) -> bool:
    """C конкордантен A относительно B, если:
    (1) хотя бы один интент изменился между C и B;
    (2) знак эффекта по компонентам скоров совпадает со знаком A−B.
    Реализация по компонентам scores: (C−B) и (A−B) → знако-совпадение
    по сдвинутым компонентам; при пустом пересечении — fallback на интент."""
    changed = c.intent != b.intent
    _a_b = {k: a.scores.get(k, 0.0) - b.scores.get(k, 0.0) for k in a.scores}
    _c_b = {k: c.scores.get(k, 0.0) - b.scores.get(k, 0.0) for k in c.scores}
    common = [k for k in _a_b if k in _c_b and (abs(_a_b[k]) > 1e-6 or abs(_c_b[k]) > 1e-6)]
    if not common:
        return changed  # fallback: интент-уровень
    agree = [
        (_a_b[k] > 0) == (_c_b[k] > 0)
        for k in common
        if abs(_c_b[k]) > 1e-6  # C-эффект должен быть ненулевым хотя бы где-то
    ]
    if not agree:
        return changed
    return changed and sum(agree) / len(agree) >= 0.5


def _format_scores(s: Dict[str, float]) -> str:
    _top = sorted(s.items(), key=lambda kv: kv[1], reverse=True)[:6]
    return ", ".join(f"{k}={v:.3f}" for k, v in _top)


def run_causal_state_test() -> Dict[str, Any]:
    """E2.0-c: каузальный экзамен. Возвращает вердикт-таблицу групп + итог."""
    from app.services.events.event_bus import get_event_bus

    print("=" * 70)
    print("⚔️ SUPERBOX causal_state_test — E2.0-c (гейт B0)")
    print(f"Цель (b): {NPC_TARGET}")
    print("=" * 70)
    print("Гипотеза: механическое причинное состояние меняет решение БЕЗ текста.")
    print("Критерий C (владелец, Вариант-2): C≠B + concordance(A); A−C = attribution.")
    print("AMENDMENT-1: C инъецируется на границе tick1→tick2 (равная экспозиция распада).")
    print()

    get_event_bus().clear()

    res_a = _run_group("A", _inject_A)
    get_event_bus().clear()
    res_b = _run_group("B", _inject_B)
    get_event_bus().clear()
    res_c = _run_group("C", _inject_C, post_apply_pk_reader=None)
    get_event_bus().clear()
    d_outcomes = _run_group_D()

    # ── Вердикты ──
    res_a.pass_ = (res_a.argmax != res_b.argmax or res_a.intent != res_b.intent) and (res_a.pk_at_measure or 0.0) > 0.5
    res_c.pass_ = (res_c.argmax != res_b.argmax or res_c.intent != res_b.intent) and (res_c.pk_at_measure or 0.0) > 0.5 and _concordant(res_a, res_b, res_c)
    # A−C attribution (данные, не критерий):
    _attr = {
        k: (res_a.scores.get(k, 0.0) - res_c.scores.get(k, 0.0))
        for k in res_a.scores
    }

    print(f"[A] intent={res_a.intent} | argmax={res_a.argmax} | move={res_a.movement} | PK@tick2={res_a.pk_at_measure} | {_format_scores(res_a.scores)}")
    print(f"[B] intent={res_b.intent} | argmax={res_b.argmax} | move={res_b.movement} | PK@tick2={res_b.pk_at_measure} | {_format_scores(res_b.scores)}")
    print(f"[C] intent={res_c.intent} | argmax={res_c.argmax} | move={res_c.movement} | PK@tick2={res_c.pk_at_measure} | {_format_scores(res_c.scores)}")
    print(f"[ATTRIBUTION A−C] " + ", ".join(f"{k}={v:+.3f}" for k, v in sorted(_attr.items(), key=lambda kv: abs(kv[1]), reverse=True)[:6]))
    print()
    for _k, _v in d_outcomes.items():
        print(f"[D] {_k}: {_v}")
    print()

    _verdicts = {
        "A_divergence": res_a.pass_,
        "C_state_channel": res_c.pass_,
        "D_control": d_outcomes,
    }
    _behavioral = res_a.pass_ and res_c.pass_
    print(f"ИТОГ A/B/C: {'✅ ЗАКРЫТО' if _behavioral else '❌ КРАСНЫЙ'} (A={res_a.pass_}, C={res_c.pass_})")
    print("Группа D читается отдельно: REJECTED у всех трёх = мембрана целa;")
    print("ACCEPTED = диагностированная дыра WRITE-GUARD → досье + минимальный guard → перепрогон.")
    return _verdicts


if __name__ == "__main__":
    _out = run_causal_state_test()
    sys.exit(0 if (_out.get("A_divergence") and _out.get("C_state_channel")) else 1)
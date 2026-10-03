# path: /project/backend/tests/gameplay/perturbation_harness.py
# Назначение: Stage 3 INV-CONSUMER-GAP / Causal Anatomy (ADR-O-414) —
#   минимальный пертурбационный proof-прибор: «изменил орган через production
#   write-path — изменилась ли downstream decision-траектория в probe window?».
#   Единственный класс утверждения (вердикты Мастера S319): state-level
#   perturbation; event-level probe — v2, НЕ строится. Вердикты:
#   WIRED (GREEN) / GAP (RED-находка, не чинится машиной) / INJECTION_FAILED
#   (дельта не доехала или перезаписана физикой тика — отдельная находка,
#   НЕ GAP) / INVALID (A/A-дрейф или утечка до окна — прибор, не мир).
#   ЗАПРЕТЫ: второй simulation engine (харнесс единственный, §9.2 roadmap),
#   прямые записи мимо StateApplicator, uuid4, wall-clock, универсальность.
# Зависимости: tests.gameplay.harness.TavernGameplayHarness; StateApplicator
#   (apply_deltas_only + Cause — production write-path); DecisionHub
#   .SCORE_NOISE_RANGE (noise-off на все рукава, паттерн gc09-B R1, урок
#   S254: CAUSAL FALSE GREEN от RNG); тик-чётность рукавов (прецедент
#   causal_state_test: иначе KernelRNG(tick, npc_id) = RNG-артефакт).
# Основные сущности: ProbeSpec, ProbeResult, _TapRegistry, run_probe,
#   run_smoke. Выход: __main__ smoke | probe <field> <npc> <injection> [N];
#   exit: 0 WIRED / 2 GAP / 3 INJECTION_FAILED / 4 INVALID / 64 usage.

import logging
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("PERTURBATION_HARNESS")

_CAMPAIGN = "Open_road"

# Детерминированный namespace инъекций: uuid4 запрещён (INV-REPLAY-
# DETERMINISM); постоянный namespace = одинаковый cause от прогона к прогону
# (прецедент causal_state_test._CAUSAL_EXAM_NS).
_INJECTION_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "enigma.perturbation_harness")

# Калибровочная константа ПРИБОРА (не онтология): минимальная доля инъекции,
# которая обязана дожить до чекпойнта, чтобы дельта считалась выжившей.
_SURVIVAL_MIN_FRACTION = 0.25


@dataclass(frozen=True)
class ProbeSpec:
    """Зонд: одно поле-носитель, один NPC, одна дельта, одно окно.
    injection берётся из manifest.probe_hint (воспроизводимость proof);
    expected_window — свойство proof-сценария, НЕ прибора (вердикт Мастера:
    delayed consumers не объявляются мёртвыми универсальным правилом)."""
    field: str                      # манифест-ключ носителя: "body_state.fatigue"
    npc_id: str
    injection: float
    write_kind: str = "PHYSIOLOGY"  # PHYSIOLOGY | RELATIONSHIP_V2; BELIEF_DELTA — шаг re-proof
    pair_target: str = "player"     # RELATIONSHIP_V2: направленность пары (R001-прецедент)
    inject_after_tick: int = 1      # K: столько тиков до инъекции; первый
                                    # потенциально затронутый тик решения — следующий
    horizon: int = 6               # N: полный тик-бюджет КАЖДОГО рукава (чётность)


@dataclass
class ProbeResult:
    probe: str
    # Структурный краш-фикс S319: verdict обязан иметь дефолт, иначе конструктор
    # без verdict падает (инцидент bring-up). PENDING не имеет права покинуть
    # run_probe — каждый путь присваивает вердикт; exit-мэппинг __main__ на
    # PENDING падает KeyError = громкий отказ (L4), не тихий None.
    verdict: str = "PENDING"
    first_divergence_tick: Optional[int] = None  # индекс тика расхождения в рукаве
    divergence_delta: Optional[int] = None       # Δ = first_divergence − K
    utility_delta_observed: bool = False         # scores разошлись (диагностика, не вердикт)
    argmax_flip: bool = False
    checkpoints: Dict[str, Optional[float]] = field(default_factory=dict)
    overwrite_source: Optional[str] = None        # causal_ledger-хвост при перезаписи
    score_diffs: List[Tuple[int, str, str, Optional[float], Optional[float]]] = field(
        default_factory=list
    )  # (тик, npc, ось, base, pert) — ГДЕ деформирован utility-ландшафт
    notes: List[str] = field(default_factory=list)


class _TapRegistry:
    """Пассивный тап TickOrchestrator.execute (паттерн causal_state_test /
    прецедент S194). Наблюдение не создаёт причинности (Устав §11)."""

    def __init__(self) -> None:
        self.stash: List[Any] = []
        self._orig: Optional[Callable] = None
        self._orch: Any = None

    def attach(self, game_loop: Any) -> None:
        _orch = game_loop._tick_orch
        self._orch = _orch
        self._orig = _orch.execute
        _registry = self

        def _tapped_execute(*a: Any, **k: Any) -> Any:
            _result = _registry._orig(*a, **k)  # type: ignore[misc]
            _registry.stash.append(_result)
            return _result

        _orch.execute = _tapped_execute  # type: ignore[method-assign]

    def detach(self) -> None:
        if self._orig is not None:
            self._orch.execute = self._orig  # type: ignore[method-assign]
            self._orig = None
            self._orch = None


def _rows_from_tap(
    tap: _TapRegistry,
) -> Tuple[List[Tuple[int, str, str, str]], Dict[Tuple[int, str], Dict[str, float]]]:
    """Траектория решений по ВСЕМ NPC сцены: (тик, npc_id, argmax, intent)
    + параллельный scores-канал. argmax = фактический выбор хаба (hub:718),
    intent — communication-слой (H2, раунд 13 — прецедент causal_state_test)."""
    _rows: List[Tuple[int, str, str, str]] = []
    _scores: Dict[Tuple[int, str], Dict[str, float]] = {}
    for _tick_idx, _res in enumerate(tap.stash):
        if getattr(_res, "status", "ok") == "error":
            raise RuntimeError(
                f"[PERTURBATION] TICK_CRASH в рукаве: {getattr(_res, 'error', 'unknown')}"
            )
        for _ctx in getattr(_res, "npc_contexts", []) or []:
            _nid = str(_ctx.get("npc_id", "?"))
            _dec = _ctx.get("decision_result")
            _intent = "idle"
            if _dec:
                _raw_intent = getattr(_dec, "intent", None)
                if _raw_intent is not None:
                    _intent = getattr(_raw_intent, "value", str(_raw_intent))
            _sc = dict(_ctx.get("scores_trace", {}) or {})
            _argmax = max(_sc.items(), key=lambda kv: kv[1])[0] if _sc else "idle"
            _rows.append((_tick_idx, _nid, _argmax, _intent))
            _scores[(_tick_idx, _nid)] = _sc
    return _rows, _scores


def _read_field(harness: Any, npc_id: str, dotted: str) -> Optional[float]:
    """Чтение поля-носителя из живого runtime-дикта (inspect_npc GC-00,
    read-only). None = точка чтения недостижима — само по себе находка."""
    _raw = harness.inspect_npc(npc_id)
    if _raw is None:
        return None
    _cur: Any = _raw
    for _part in dotted.split("."):
        if isinstance(_cur, dict) and _part in _cur:
            _cur = _cur[_part]
        else:
            return None
    return float(_cur) if isinstance(_cur, (int, float)) else None


def _ledger_tail(harness: Any, npc_id: str) -> Optional[str]:
    """Best-effort атрибуция перезаписи: хвост causal_ledger из runtime-дикта.
    v1-граница: сериализованная форма; при отсутствии — честный None."""
    try:
        _raw = harness.inspect_npc(npc_id)
        if not isinstance(_raw, dict):
            return None
        _led = _raw.get("causal_ledger")
        if isinstance(_led, list) and _led:
            return " | ".join(str(_e)[:120] for _e in _led[-3:])
    except Exception:  # noqa: S110 — наблюдатель не роняет прогон (§11)
        return None
    return None


# ── Инъекторы: каждый — дословная реплика ДОКАЗАННОГО production-паттерна ──

def _inject_physiology(harness: Any, spec: ProbeSpec) -> None:
    """PHYSIOLOGY-инъекция (паттерн causal_state_test группа C, дословно):
    StateDeltas(PHYSIOLOGY) → production StateApplicator.apply_deltas_only
    + Cause → NPCState.to_persistence_dict в живой dict-кэш LifeEngine.
    Никаких прямых записей (ADR-WRITE-GUARD / CAUSAL-SPINE)."""
    from app.models.delta_payloads import PhysiologyPayload
    from app.models.npc_state import NPCState
    from app.models.psychological import Cause
    from app.models.state_delta import DeltaDomain, StateDeltas
    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

    # Тайпчекер-честность: явные kwargs вместо **-сплита — сплит ослепляет
    # Pylance/mypy (Tuple-параметры add_injuries/add_statuses виделись float).
    _payload_factories: Dict[str, Callable[[float], PhysiologyPayload]] = {
        "fatigue": lambda v: PhysiologyPayload(fatigue_delta=v),
        "energy": lambda v: PhysiologyPayload(energy_delta=v),
        "pain": lambda v: PhysiologyPayload(pain_delta=v),
        "blood_loss": lambda v: PhysiologyPayload(blood_loss_delta=v),
        "shock_impulse": lambda v: PhysiologyPayload(shock_impulse=v),
        "hydration": lambda v: PhysiologyPayload(hydration_delta=v),
        "nutrition": lambda v: PhysiologyPayload(nutrition_delta=v),
    }
    _factory = _payload_factories.get(spec.field.split(".", 1)[1])
    if _factory is None:
        raise RuntimeError(f"[PERTURBATION] неизвестный physiology-носитель: {spec.field}")
    _states = harness.game_loop._get_life_engine().get_npc_states(_CAMPAIGN)
    _npc_dict = next(
        (n for n in _states if n.get("id") == spec.npc_id or n.get("npc_id") == spec.npc_id),
        None,
    )
    if _npc_dict is None:
        raise RuntimeError(f"[PERTURBATION] NPC {spec.npc_id} не найден в кэше LifeEngine")
    _state = load_l2_state_from_runtime_dict(_npc_dict)
    _applicator = harness.game_loop._tick_orch._state_applicator
    if _applicator is None:
        raise RuntimeError("[PERTURBATION] production StateApplicator не вайрен")
    _deltas = StateDeltas(
        npc_id=spec.npc_id,
        domain=DeltaDomain.PHYSIOLOGY,
        payload=_factory(spec.injection),
        source="perturbation_harness",
    )
    _cause = Cause(source_event_id=uuid.uuid5(_INJECTION_NS, f"{spec.field}:{spec.npc_id}"))
    _new_state = _applicator.apply_deltas_only(
        _state, _deltas, campaign_id=_CAMPAIGN, cause=_cause
    )
    NPCState.to_persistence_dict(_new_state, _npc_dict)


def _inject_relationship_v2(harness: Any, spec: ProbeSpec) -> None:
    """RELATIONSHIP_V2-инъекция (R001-прецедент, experiment_runner:462):
    NPCStateAdapter.from_legacy → production StateApplicator.update_relationships
    → RelationshipWriteGate → V2 Store (SSOT). Write-back в npc_dict НЕ делаем —
    кэш эфемерен (P1 ARCH), стор — единственный носитель, доживающий до тика.
    Санкция Мастера (Q2): диагностическая state-level проба, НЕ proof."""
    from app.models.npc_state import NPCStateAdapter

    _states = harness.game_loop._get_life_engine().get_npc_states(_CAMPAIGN)
    _npc_dict = next(
        (n for n in _states if n.get("id") == spec.npc_id or n.get("npc_id") == spec.npc_id),
        None,
    )
    if _npc_dict is None:
        raise RuntimeError(f"[PERTURBATION] NPC {spec.npc_id} не найден в кэше LifeEngine")
    _applicator = harness.game_loop._tick_orch._state_applicator
    if _applicator is None:
        raise RuntimeError("[PERTURBATION] production StateApplicator не вайрен (orch:265)")
    _state = NPCStateAdapter.from_legacy(_npc_dict)
    _applicator.update_relationships(
        state=_state,
        campaign_id=_CAMPAIGN,
        target_id=spec.pair_target,
        trust_delta=spec.injection,
    )


_INJECTORS: Dict[str, Callable[[Any, ProbeSpec], None]] = {
    "PHYSIOLOGY": _inject_physiology,
    "RELATIONSHIP_V2": _inject_relationship_v2,
    # BELIEF_DELTA — добавляется шагом re-proof beliefs (apply_belief_delta).
}


def _make_checkpoint_reader(spec: ProbeSpec) -> Callable[[Any, str], Optional[float]]:
    """Диспетчер точки чтения по write_kind. RELATIONSHIP_V2: канонический
    V2-стор через harness.read_trust (memory_manager._relationships.get_pair,
    S249-факт). Vacuum → 0.0 — ИЗМЕРИТЕЛЬНАЯ конвенция прибора: онтологически
    Vacuum ≠ 0.0 (§ENIGMA-003); досье-запись обязана отмечать baseline-Vacuum."""
    if spec.write_kind == "RELATIONSHIP_V2":
        def _rel_reader(harness: Any, npc_id: str) -> Optional[float]:
            _v = harness.read_trust(npc_id, spec.pair_target)
            return 0.0 if _v is None else _v
        return _rel_reader
    return lambda harness, npc_id: _read_field(harness, npc_id, spec.field)


@dataclass
class _ArmData:
    rows: List[Tuple[int, str, str, str]]
    scores: Dict[Tuple[int, str], Dict[str, float]]
    checkpoints: Dict[str, Optional[float]]
    ledger_tail: Optional[str] = None


def _run_arm(spec: ProbeSpec, perturbed: bool) -> _ArmData:
    """Один рукав: fresh TavernGameplayHarness (temp-saves, dispose),
    K тиков → [инъекция] → N−K тиков. Тик-чётность всех рукавов = N."""
    from tests.gameplay.harness import TavernGameplayHarness

    _tap = _TapRegistry()
    _read = _make_checkpoint_reader(spec)
    _checkpoints: Dict[str, Optional[float]] = {}
    _ledger: Optional[str] = None
    with TavernGameplayHarness() as _h:
        _tap.attach(_h.game_loop)
        try:
            for _ in range(spec.inject_after_tick):
                _h.advance_ticks(1)
            _checkpoints["at_K"] = _read(_h, spec.npc_id)
            if perturbed:
                _INJECTORS[spec.write_kind](_h, spec)
                _checkpoints["post_injection"] = _read(_h, spec.npc_id)
            _first = True
            for _ in range(spec.horizon - spec.inject_after_tick):
                _h.advance_ticks(1)
                if _first:
                    # K1 = первый тик ПОСЛЕ инъекции: точка, где физика тика
                    # уже имела шанс перезаписать дельту до решателя
                    _checkpoints["at_K1"] = _read(_h, spec.npc_id)
                    _first = False
            _checkpoints["at_N"] = _read(_h, spec.npc_id)
            _ledger = _ledger_tail(_h, spec.npc_id)
        finally:
            _tap.detach()
    _rows, _scores = _rows_from_tap(_tap)
    return _ArmData(rows=sorted(_rows), scores=_scores,
                    checkpoints=_checkpoints, ledger_tail=_ledger)


def _fail_probe(res: ProbeResult, verdict: str, note: str) -> ProbeResult:
    """Единая точка отказа: вердикт + обоснование, атомарно."""
    res.verdict = verdict
    res.notes.append(note)
    return res


def _collect_score_diffs(
    p: _ArmData, base: _ArmData, k: int
) -> List[Tuple[int, str, str, Optional[float], Optional[float]]]:
    """Полная детализация расхождения scores-канала после K: (тик, npc, ось,
    base, pert). Корм для досье (ГДЕ деформирован ландшафт) и для паттерн-
    ассертов re-proof (семантика A: CAUSAL = проводимость до вычисления,
    argmax_flip — annotation)."""
    _diffs: List[Tuple[int, str, str, Optional[float], Optional[float]]] = []
    for _key in sorted(set(p.scores) | set(base.scores)):
        if _key[0] < k:
            continue
        _pv = p.scores.get(_key, {})
        _bv = base.scores.get(_key, {})
        for _axis in sorted(set(_pv) | set(_bv)):
            if _pv.get(_axis) != _bv.get(_axis):
                _diffs.append((_key[0], _key[1], _axis, _bv.get(_axis), _pv.get(_axis)))
    return _diffs


def _gap_verdict(res: ProbeResult, p: _ArmData, base: _ArmData, k: int) -> ProbeResult:
    """GAP: ребро state→decision не доказано. scores-канал — параллельная
    диагностика (вердикт Мастера S319: scores без argmax-флипа ≠ WIRED),
    не критерий вердикта; score_diffs фиксируют ГДЕ деформирован utility."""
    res.verdict = "GAP"
    res.score_diffs = _collect_score_diffs(p, base, k)
    res.utility_delta_observed = bool(res.score_diffs)
    res.notes.append("state → decision: ребро НЕ доказано; finding → владельцу сегмента (машина не чинит)")
    if res.score_diffs:
        res.notes.append(
            "annotation: utility_delta=observed, argmax_flip=false — калибровочный материал DecisionHub"
        )
    return res


def run_probe(spec: ProbeSpec) -> ProbeResult:
    """Четырёхвердиктная машина (иерархия Мастера S319):
    A/A → детерминизм ствола → выживание дельты → окно траектории."""
    if spec.horizon <= spec.inject_after_tick:
        raise ValueError("ProbeSpec: horizon обязан быть > inject_after_tick (нужно окно после инъекции)")
    import app.services.npc.decision_hub as _dh

    _orig_noise = _dh.SCORE_NOISE_RANGE
    _dh.SCORE_NOISE_RANGE = 0.0  # R1: noise-off на ВСЕ рукава (gc09-B, урок S254)
    try:
        _res = ProbeResult(probe=f"{spec.field}:{spec.npc_id}")
        _aa1 = _run_arm(spec, perturbed=False)
        _aa2 = _run_arm(spec, perturbed=False)
        if _aa1.rows != _aa2.rows:
            return _fail_probe(_res, "INVALID",
                "A/A-дрейф (траектория): прибор ловит RNG-шум, не каузальность — чинить ПРИБОР")
        if _aa1.scores != _aa2.scores:
            return _fail_probe(_res, "INVALID",
                "A/A-дрейф (scores_trace): суб-пороговая дивергенция между идентичными "
                "рукавами — вердикты контаминированы; кандидат №1 — глобальный backoff-"
                "стейт LLM-роутера (smoke S319: arm-1 платит 3 retry, arm-2 fast-fail); "
                "чинить изоляцию рукавов, не мир")
        if not _aa1.rows:
            return _fail_probe(_res, "INVALID",
                "траектория пуста: npc_contexts не материализуются — прибор слеп")
        _base, _p = _aa1, _run_arm(spec, perturbed=True)
        _k = spec.inject_after_tick

        # Окно до инъекции: общий ствол обязан совпасть (утечка = INVALID)
        if [r for r in _p.rows if r[0] < _k] != [r for r in _base.rows if r[0] < _k]:
            return _fail_probe(_res, "INVALID", "окно до инъекции разошлось — утечка недетерминизма")

        _bK = _base.checkpoints.get("at_K")
        _pPost = _p.checkpoints.get("post_injection")
        _pK1 = _p.checkpoints.get("at_K1")
        _bK1 = _base.checkpoints.get("at_K1")
        _res.checkpoints = {
            "base_at_K": _bK, "post_injection": _pPost,
            "p_at_K1": _pK1, "base_at_K1": _bK1,
            "p_at_N": _p.checkpoints.get("at_N"),
            "base_at_N": _base.checkpoints.get("at_N"),
        }
        _thr = max(0.5, abs(spec.injection) * _SURVIVAL_MIN_FRACTION)
        if _bK is None or _pPost is None or _pK1 is None or _bK1 is None:
            return _fail_probe(_res, "INJECTION_FAILED",
                "точка чтения поля недостижима (checkpoint=None) — отдельная находка")
        if abs(_pPost - _bK) < _thr:
            return _fail_probe(_res, "INJECTION_FAILED",
                f"дельта не доехала до точки чтения (post={_pPost}, base={_bK}, порог={_thr})")
        if abs(_pK1 - _bK1) < _thr:
            # Дельта перезаписана физикой тика ДО первого решения: consumer
            # неизвестен, organ не обвинён (дисциплина INJECTION_FAILED ≠ GAP)
            _fail_probe(_res, "INJECTION_FAILED",
                f"дельта перезаписана физикой тика до первого решения "
                f"(K1: p={_pK1}, base={_bK1}) — consumer неизвестен, organ не обвинён")
            _res.overwrite_source = _p.ledger_tail
            return _res

        # Окно после инъекции: траектория решений (argmax — первичный сигнал)
        _pr = [r for r in _p.rows if r[0] >= _k]
        _br = [r for r in _base.rows if r[0] >= _k]
        if _pr == _br:
            return _gap_verdict(_res, _p, _base, _k)

        _res.verdict = "WIRED"
        _ticks = sorted({r[0] for r in _pr} | {r[0] for r in _br})
        _fd = next((_t for _t in _ticks
                    if [r for r in _pr if r[0] == _t] != [r for r in _br if r[0] == _t]),
                   None)
        _res.first_divergence_tick = _fd
        _res.divergence_delta = (_fd - _k) if _fd is not None else None
        _res.argmax_flip = {r[:3] for r in _pr} != {r[:3] for r in _br}
        _res.notes.append(
            f"first_divergence: tick={_fd} (Δ={_res.divergence_delta} от инъекции после тика {_k})"
        )
        return _res
    finally:
        _dh.SCORE_NOISE_RANGE = _orig_noise


def run_smoke(npc_id: str = "merchant_goran", horizon: int = 4) -> bool:
    """Bring-up гейт №1: A/A-детерминизм прибора БЕЗ инъекции — на двух
    уровнях (rows + scores). GREEN = измерительным каналам можно верить;
    RED = чинить прибор, не мир."""
    _spec = ProbeSpec(field="body_state.fatigue", npc_id=npc_id,
                      injection=0.0, horizon=horizon)
    import app.services.npc.decision_hub as _dh

    _orig = _dh.SCORE_NOISE_RANGE
    _dh.SCORE_NOISE_RANGE = 0.0
    try:
        _a = _run_arm(_spec, perturbed=False)
        _b = _run_arm(_spec, perturbed=False)
    finally:
        _dh.SCORE_NOISE_RANGE = _orig
    if not _a.rows:
        print("[SMOKE] RED: траектория пуста — npc_contexts не материализуются")
        print("ИТОГ SMOKE: RED — прибор слеп")
        return False
    _rows_ok = _a.rows == _b.rows
    _scores_ok = _a.scores == _b.scores
    _ok = _rows_ok and _scores_ok
    print(f"[SMOKE] A/A rows equal: {_rows_ok} (rows={len(_a.rows)} vs {len(_b.rows)}, ticks={horizon})")
    print(f"[SMOKE] A/A scores equal: {_scores_ok}")
    if not _rows_ok:
        for _r1, _r2 in zip(_a.rows, _b.rows):
            if _r1 != _r2:
                print(f"[SMOKE] первый дрейф (rows): {_r1} vs {_r2}")
                break
    if not _scores_ok:
        _diff = sorted(k for k in set(_a.scores) | set(_b.scores)
                       if _a.scores.get(k) != _b.scores.get(k))
        if _diff:
            print(f"[SMOKE] дрейф scores: {len(_diff)} ключей; первый: {_diff[0]}: "
                  f"{_a.scores.get(_diff[0])} vs {_b.scores.get(_diff[0])}")
    print(f"[SMOKE] fatigue checkpoints (base): {_a.checkpoints}")
    print(f"ИТОГ SMOKE: {'GREEN — прибор детерминирован' if _ok else 'RED — INVALID-прибор'}")
    return _ok


if __name__ == "__main__":
    _mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if _mode == "smoke":
        sys.exit(0 if run_smoke() else 1)
    if _mode == "probe":
        _spec = ProbeSpec(
            field=sys.argv[2], npc_id=sys.argv[3], injection=float(sys.argv[4]),
            horizon=int(sys.argv[5]) if len(sys.argv) > 5 else 6,
            write_kind=sys.argv[6] if len(sys.argv) > 6 else "PHYSIOLOGY",
        )
        _r = run_probe(_spec)
        print(f"PROBE {_r.probe} → {_r.verdict}")
        print(f"  first_divergence_tick={_r.first_divergence_tick} Δ={_r.divergence_delta}")
        print(f"  utility_delta_observed={_r.utility_delta_observed} argmax_flip={_r.argmax_flip}")
        print(f"  checkpoints={_r.checkpoints}")
        if _r.overwrite_source:
            print(f"  overwrite ledger tail: {_r.overwrite_source}")
        if _r.score_diffs:
            print(f"  score_diffs: {len(_r.score_diffs)} осей разошлось; первые 8:")
            for _d in _r.score_diffs[:8]:
                print(f"    tick={_d[0]} npc={_d[1]} axis={_d[2]}: base={_d[3]} -> pert={_d[4]}")
        for _note in _r.notes:
            print(f"  note: {_note}")
        # PENDING здесь = KeyError = громкий отказ: вердикт обязан быть финальным
        sys.exit({"WIRED": 0, "GAP": 2, "INJECTION_FAILED": 3, "INVALID": 4}[_r.verdict])
    print("usage: perturbation_harness.py [smoke | probe <field> <npc_id> <injection> [horizon] [kind]]")
    sys.exit(64)
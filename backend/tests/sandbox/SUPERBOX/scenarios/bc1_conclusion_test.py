# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/bc1_conclusion_test.py
# Назначение: SUPERBOX bc1_conclusion_test (BC-1/ADR-O-381) — приёмка слоя
#   EXPERIENCE→CONCLUSION на GC-00-харнесе. Группы:
#   A — прод-путь: PLAYER_THREATENS → (E2.0-b) DeltaGate → EXPERIENCE_DELTA_COMMITTED
#       → коллектор → Фаза 9: ConclusionEngine → ConclusionGate → ConclusionStore
#       → CONCLUSION_FORMED. Метрика = содержимое ConclusionStore + события-трассы
#       (НЕ intent — урок H2/S243).
#   B — NO-VACUUM (инвариант владельца, вербатим): «BC-1 не имеет права создавать
#       conclusion из отсутствия нового опыта» — тройной контроль: без новых
#       EXPERIENCE_DELTA → 0 CONCLUSION_FORMED → 0 записей → коллектор пуст.
#   C — state-канал без события (AMENDMENT-1-паритет, слот tick1→tick2):
#       ConclusionProposal → ConclusionGate.apply (авторизованный вход) → store;
#       concordance с A (идентичность вывода + близость confidence).
#   D — WRITE-GUARD: store.apply мимо ConclusionGate → ArchitecturalViolationError
#       (D в цензус НЕ вносится — замок экзамена, урок S243).
#   E — рестарт round-trip: to_dict → from_dict → записи идентичны (S193/009).
#   OFF — dormant (INV-BC1-NOOP): флаг снят → слой молчит, ключа в сцене нет.
# Зависимости: TavernGameplayHarness (GC-00 §5a.2), EventBus, BC-1-слои.
# Основные сущности: _TapRegistry, _GroupResult, run_bc1_conclusion_test.
# Тик-чётность: 3/3/3/3 (A/B/C; D/E/OFF — слой-уровень, RNG-независимы).
# OFFLINE: MockProvider (environment != production), LLM не участвует.

"""
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.bc1_conclusion_test; cd ..
"""

import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("BC1_CONCLUSION_TEST")

# Слой ON на время сценария (группы A-E); OFF-группа снимает и восстанавливает.
# Флаг читается живьём (bc1_enabled) и в init-ensure TickOrchestrator —
# потому ставится ДО построения харнессов.
os.environ["BC1_ENABLED"] = "1"

# Цель параметризуется (прецедент (b)-кадра). Люся — fear-доминанта
# (лучшая чувствительность к threat-правилу); любой NPC-адресат валиден.
NPC_TARGET = sys.argv[1] if len(sys.argv) > 1 else "maid_lusya"
CAMPAIGN = "Open_road"

# uuid5 — детерминированный родитель (uuid4 запрещён: INV-REPLAY-DETERMINISM).
_BC1_EXAM_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "enigma.bc1_exam")


@dataclass
class _GroupResult:
    group: str
    record: Optional[Dict[str, Any]] = None
    store_size: int = 0
    formed_events: int = 0
    collector_residual: int = -1
    pk_at_measure: Optional[float] = None
    store_data: List[Dict[str, Any]] = field(default_factory=list)
    pass_: bool = False


# ── Тап (ObservabilityTap-паттерн, дословно из causal_state_test) ──

class _TapRegistry:
    """Обёртка execute → stash TickResultDTO. Наблюдение не создаёт
    причинность (Устав §XI)."""

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

    def _check_crash(self) -> None:
        for _res in reversed(self.stash):
            if getattr(_res, "status", "ok") == "error":
                raise RuntimeError(
                    f"[BC1_CONCLUSION_TEST] TICK_CRASH в прогоне: "
                    f"{getattr(_res, 'error', 'unknown')}"
                )

    def last_scene(self) -> Dict[str, Any]:
        self._check_crash()
        if not self.stash:
            return {}
        _scene = getattr(self.stash[-1], "final_scene_state", None)
        if not isinstance(_scene, dict):
            return {}
        return _scene


# ── Хелперы (дословно из causal_state_test) ──

def _bus_publish(game_loop: Any, event_type: str, payload: Dict[str, Any]) -> None:
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
    _bus_publish(
        game_loop,
        "npc_proximity_close",
        {"npc_id": NPC_TARGET, "target_id": NPC_TARGET, "distance": 2.0},
    )


def _read_pk(game_loop: Any, npc_id: str) -> Optional[float]:
    _snap = game_loop._resolve_npcs_snapshot(CAMPAIGN) or []
    for _n in _snap:
        if _n.get("id") == npc_id or _n.get("npc_id") == npc_id:
            _pk = _n.get("perceptual_kernel", {})
            return float(_pk.get("threat_gradient", 0.0))
    return None


def _predicate() -> Any:
    from app.domain.conclusions import ConclusionPredicate

    return ConclusionPredicate.IS_DANGEROUS


def _store_of(game_loop: Any) -> Any:
    return getattr(game_loop._tick_orch, "_conclusion_store", None)


def _record_as_dict(record: Any) -> Dict[str, Any]:
    return {
        "owner_id": record.owner_id,
        "subject": record.subject,
        "predicate": record.predicate.value,
        "object": record.object,
        "confidence": record.confidence,
        "evidence": list(record.evidence),
        "trace_id": record.trace_id,
        "causal_parent": record.causal_parent,
        "source": record.source,
        "formed_tick": record.formed_tick,
    }


# ── Общий конвейер групп (методология causal_state_test: clear ВНЕ группы,
#    ДО построения харнесса — подписки харнесса и коллектора выживают) ──

def _run_group_bc1(
    label: str,
    injection: Callable[[Any, _TapRegistry, _GroupResult], None],
) -> _GroupResult:
    from app.services.events.event_types import EventType
    from tests.gameplay.harness import TavernGameplayHarness

    res = _GroupResult(group=label)
    tap = _TapRegistry()
    formed: List[Any] = []

    with TavernGameplayHarness() as h:
        tap.attach(h.game_loop)
        bus = h.game_loop._tick_orch._get_event_bus()
        bus.subscribe(EventType.CONCLUSION_FORMED, lambda ev: formed.append(ev))
        try:
            injection(h.game_loop, tap, res)
            _publish_calibration(h.game_loop)
            h.advance_ticks(1)  # тик 2 = измерение
            tap._check_crash()
            res.pk_at_measure = _read_pk(h.game_loop, NPC_TARGET)
            store = _store_of(h.game_loop)
            if store is None:
                raise RuntimeError(
                    f"[BC1_CONCLUSION_TEST][{label}] BC-1 store не wired (ON-группа)"
                )
            res.store_size = len(store)
            rec = store.get(NPC_TARGET, "player", _predicate())
            if rec is not None:
                res.record = _record_as_dict(rec)
            res.store_data = store.to_dict()
            orch = h.game_loop._tick_orch
            res.collector_residual = len(
                getattr(orch, "_conclusion_collector", []) or []
            )
            res.formed_events = len(formed)
        finally:
            tap.detach()
    return res


# ── Инъекции групп ──

def _inject_A(game_loop: Any, tap: _TapRegistry, res: _GroupResult) -> None:
    """A: прод-путь. Threat-событие → тик 1: Фаза 8 (reaction S115:
    DeltaGate.apply → EXPERIENCE_DELTA_COMMITTED → коллектор) → Фаза 9
    (engine → gate → store → CONCLUSION_FORMED)."""
    game_loop.idle_tick(CAMPAIGN)  # тик 0: warm-up
    _bus_publish(
        game_loop,
        "player_threatens",
        {"target_id": NPC_TARGET, "intensity": 0.7, "semantic_action": "THREATEN"},
    )
    game_loop.idle_tick(CAMPAIGN)  # тик 1: event → state → conclusion
    # A1-фальсификатор (логика causal_state_test): дельта доехала ДО PK —
    # иначе провод event→state мёртв, и вывод не мог родиться.
    _pk = _read_pk(game_loop, NPC_TARGET)
    if _pk is None or _pk < 0.5:
        raise RuntimeError(
            f"[BC1_CONCLUSION_TEST][A1] дельта угрозы не доехала до PK "
            f"({NPC_TARGET}: pk={_pk}) — провод event→state мёртв"
        )
    # A2-фальсификатор: conclusion существует уже после тика обработки.
    store = _store_of(game_loop)
    if store is None or store.get(NPC_TARGET, "player", _predicate()) is None:
        raise RuntimeError(
            "[BC1_CONCLUSION_TEST][A2] conclusion НЕ сформирован после тика "
            "обработки — канал EXPERIENCE_DELTA→CONCLUSION мёртв "
            "(коллектор / Фаза 9 / gate)"
        )


def _inject_B(game_loop: Any, tap: _TapRegistry, res: _GroupResult) -> None:
    """B: NO-VACUUM. Нейтральный PLAYER_SPOKE (threat-семантики нет)
    → ноль EXPERIENCE_DELTA → ноль выводов."""
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
            f"[BC1_CONCLUSION_TEST][B1] контроль загрязнён: PK = {_pk} "
            f"после нейтрального PLAYER_SPOKE — источник неявной угрозы"
        )
    store = _store_of(game_loop)
    if store is not None and len(store) > 0:
        raise RuntimeError(
            f"[BC1_CONCLUSION_TEST][B2] NO-VACUUM НАРУШЕН: {len(store)} "
            f"conclusion(s) без нового опыта — генератор «выводов из состояния»"
        )


def _inject_C(game_loop: Any, tap: _TapRegistry, res: _GroupResult) -> None:
    """C: state-канал без события (слот tick1→tick2, AMENDMENT-1-паритет).
    Proposal → orchestrator-гейт → store. Ни события, ни текста, ни LLM."""
    from app.domain.conclusions import ConclusionPredicate, ConclusionProposal

    game_loop.idle_tick(CAMPAIGN)  # тик 0
    game_loop.idle_tick(CAMPAIGN)  # тик 1 (baseline execution)

    _parent = uuid.uuid5(_BC1_EXAM_NS, "bc1_group_C")
    _proposal = ConclusionProposal(
        owner_id=NPC_TARGET,
        subject="player",
        predicate=ConclusionPredicate.IS_DANGEROUS,
        object="",
        confidence=0.8,
        evidence=(str(_parent),),
        trace_id=f"{_parent}:{NPC_TARGET}:mechanical",
        causal_parent=str(_parent),
        source="direct_experience",
        rationale="BC-1 group C: state-only injection",
    )
    gate = getattr(game_loop._tick_orch, "_conclusion_gate", None)
    store = _store_of(game_loop)
    if gate is None or store is None:
        raise RuntimeError("[BC1_CONCLUSION_TEST][C1] BC-1 слои не wired (gate/store)")
    if not gate.apply(_proposal, consumer_dispatch=store.apply):
        raise RuntimeError(
            "[BC1_CONCLUSION_TEST][C1] gate не принял механический proposal"
        )


# ── Группа D: WRITE-GUARD (слой-уровень; харнесс не нужен — guard
#    проверяет caller, не мир; D в цензус НЕ вносится — замок) ──

def _run_group_D() -> Dict[str, str]:
    from app.domain.conclusions import ConclusionPredicate, ConclusionProposal
    from app.services.npc.conclusion_store import ConclusionStore

    _parent = uuid.uuid5(_BC1_EXAM_NS, "bc1_group_D")
    _proposal = ConclusionProposal(
        owner_id=NPC_TARGET,
        subject="player",
        predicate=ConclusionPredicate.IS_DANGEROUS,
        object="",
        confidence=0.9,
        evidence=(str(_parent),),
        trace_id=f"{_parent}:{NPC_TARGET}:bypass",
        causal_parent=str(_parent),
    )
    store = ConclusionStore()
    try:
        store.apply(_proposal, 0.9)
        return {"D_store_bypass": "ACCEPTED (guard не сработал!)"}
    except Exception as e:
        return {"D_store_bypass": f"REJECTED: {type(e).__name__}"}


# ── Группа E: рестарт round-trip (данные группы A; прецедент SUPERBOX-009) ──

def _run_group_E(a_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    from app.domain.conclusions import ConclusionPredicate
    from app.services.npc.conclusion_store import ConclusionStore

    restored = ConclusionStore.from_dict(a_data)
    rec = restored.get(NPC_TARGET, "player", ConclusionPredicate.IS_DANGEROUS)
    if rec is None:
        return {"ok": False, "note": "запись потеряна после рестарта"}
    src = next((d for d in a_data if d.get("owner_id") == NPC_TARGET), None)
    ok = (
        src is not None
        and rec.confidence == src.get("confidence")
        and tuple(rec.evidence) == tuple(src.get("evidence", ()))
        and rec.predicate.value == src.get("predicate")
    )
    return {
        "ok": ok,
        "note": f"conf={rec.confidence}, evidence={list(rec.evidence)}",
    }


# ── Группа OFF: dormant (INV-BC1-NOOP) ──

def _run_group_OFF() -> Dict[str, Any]:
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    os.environ.pop("BC1_ENABLED", None)
    out: Dict[str, Any] = {"events": 0, "store_attr": "?", "scene_key": "?"}
    formed: List[Any] = []
    try:
        from tests.gameplay.harness import TavernGameplayHarness

        tap = _TapRegistry()
        get_event_bus().clear()  # ДО построения харнесса (протокол групп)
        with TavernGameplayHarness() as h:
            tap.attach(h.game_loop)
            bus = h.game_loop._tick_orch._get_event_bus()
            bus.subscribe(
                EventType.CONCLUSION_FORMED, lambda ev: formed.append(ev)
            )
            try:
                h.game_loop.idle_tick(CAMPAIGN)  # тик 0
                _bus_publish(
                    h.game_loop,
                    "player_threatens",
                    {
                        "target_id": NPC_TARGET,
                        "intensity": 0.7,
                        "semantic_action": "THREATEN",
                    },
                )
                h.game_loop.idle_tick(CAMPAIGN)  # тик 1: E2.0-b жив, BC-1 молчит
                tap._check_crash()
                scene = tap.last_scene()
                out["events"] = len(formed)
                out["store_attr"] = (
                    "None"
                    if getattr(h.game_loop._tick_orch, "_conclusion_store", None)
                    is None
                    else "WIRED(!)"
                )
                out["scene_key"] = (
                    "absent" if "conclusions" not in scene else "PRESENT(!)"
                )
            finally:
                tap.detach()
    finally:
        os.environ["BC1_ENABLED"] = "1"
    return out


# ── Оркестрация + вердикты ──

def run_bc1_conclusion_test() -> Dict[str, Any]:
    from app.services.events.event_bus import get_event_bus

    print("=" * 70)
    print("🧠 SUPERBOX bc1_conclusion_test — BC-1 (ADR-O-381, dormant ON)")
    print(f"Цель: {NPC_TARGET}")
    print("=" * 70)
    print("Гипотеза: значимый опыт порождает вывод (триплет) без текста/LLM.")
    print("Инвариант владельца: NO-VACUUM — без нового опыта выводов нет.")
    print()

    get_event_bus().clear()
    res_a = _run_group_bc1("A", _inject_A)
    get_event_bus().clear()
    res_b = _run_group_bc1("B", _inject_B)
    get_event_bus().clear()
    res_c = _run_group_bc1("C", _inject_C)
    get_event_bus().clear()
    d_outcome = _run_group_D()
    e_outcome = _run_group_E(res_a.store_data)
    off_outcome = _run_group_OFF()

    # ── Вердикты ──
    res_a.pass_ = (
        res_a.record is not None
        and res_a.record.get("confidence", 0.0) >= 0.5
        and len(res_a.record.get("evidence", [])) > 0
        and res_a.formed_events >= 1
    )
    res_b.pass_ = (
        res_b.formed_events == 0
        and res_b.store_size == 0
        and res_b.collector_residual == 0
    )
    _conf_a = (res_a.record or {}).get("confidence")
    _conf_c = (res_c.record or {}).get("confidence")
    res_c.pass_ = (
        res_c.record is not None
        and res_c.record.get("owner_id") == NPC_TARGET
        and res_c.record.get("subject") == "player"
        and _conf_a is not None
        and _conf_c is not None
        and abs(_conf_a - _conf_c) <= 0.05
        and res_c.formed_events >= 1
    )
    _d_pass = d_outcome["D_store_bypass"].startswith("REJECTED")
    _e_pass = bool(e_outcome.get("ok"))
    _off_pass = (
        off_outcome.get("events") == 0
        and off_outcome.get("store_attr") == "None"
        and off_outcome.get("scene_key") == "absent"
    )

    for _r in (res_a, res_b, res_c):
        _rec = _r.record
        _rec_s = (
            "owner={owner_id} subject={subject} pred={predicate} "
            "conf={confidence} evidence={evidence}".format(**_rec)
            if _rec
            else "—"
        )
        print(
            f"[{_r.group}] pass={_r.pass_} | record: {_rec_s} | "
            f"store={_r.store_size} | CONCLUSION_FORMED={_r.formed_events} | "
            f"collector_resid={_r.collector_residual} | PK@tick2={_r.pk_at_measure}"
        )
    print(f"[D] {d_outcome['D_store_bypass']}")
    print(
        f"[E] restart round-trip: {'✅' if _e_pass else '❌'} "
        f"{e_outcome.get('note')}"
    )
    print(
        f"[OFF] dormant: events={off_outcome['events']}, "
        f"store={off_outcome['store_attr']}, "
        f"scene_key={off_outcome['scene_key']}"
    )
    print()

    _all = (
        res_a.pass_
        and res_b.pass_
        and res_c.pass_
        and _d_pass
        and _e_pass
        and _off_pass
    )
    print(
        f"ИТОГ BC-1: {'✅ ЗАКРЫТО' if _all else '❌ КРАСНЫЙ'} "
        f"(A={res_a.pass_}, B={res_b.pass_}, C={res_c.pass_}, "
        f"D={_d_pass}, E={_e_pass}, OFF={_off_pass})"
    )
    print("Метрика: ConclusionStore-контент + трассы CONCLUSION_FORMED (не intent).")
    return {
        "A_experience_to_conclusion": res_a.pass_,
        "B_no_vacuum": res_b.pass_,
        "C_state_channel": res_c.pass_,
        "D_guard": d_outcome,
        "E_roundtrip": _e_pass,
        "OFF_dormant": _off_pass,
    }


if __name__ == "__main__":
    _out = run_bc1_conclusion_test()
    _ok = (
        _out.get("A_experience_to_conclusion")
        and _out.get("B_no_vacuum")
        and _out.get("C_state_channel")
        and _out.get("E_roundtrip")
        and _out.get("OFF_dormant")
        and str(_out.get("D_guard", {}).get("D_store_bypass", "")).startswith(
            "REJECTED"
        )
    )
    sys.exit(0 if _ok else 1)
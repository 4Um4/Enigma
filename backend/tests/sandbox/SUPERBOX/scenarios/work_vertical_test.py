"""
SUPERBOX-WORK (S256, ADR-O-391): Vertical Slice «Заказ и расчёт».

ЖЕЛЕЗНЫЕ УСЛОВИЯ:
  1. Инъекция ТОЛЬКО входа: thirst=0.9 (факт тела Горана) + экономический
     факт мира (у таверны есть эль: stock_for_sale). Desire, Intent.TRADE,
     ORDER, SERVE, settlement — рождаются production-конвейером.
  2. DecisionHub не тронут: TRADE выбирается существующим compute.
  3. Settlement — только терминалом SERVE; мутации — только SSOT
     (INV-WORK-PERSIST; deepcopy-ловушка S-143 закрыта конструктивно).
  4. OFF (WORK_ENABLED) = no causal footprint: ни заказа, ни SERVE,
     ни economic writes, ни WORK-outcome (абляция, не «NPC не работает»).

Цепь:
  W1 ORDER born (goran→tornin, ale) → SERVE → ale/gold перешли,
     COMPLETED, outcome обоим, income записан
  W2 CRITICAL: следующий тик видит изменившийся мир (SSOT переживает
     тик; повторный settle = no-op)
  W3 ATOMIC FAILURE: stock=0 → FAILED, before==after, success=False
  W4 OFF: профили deep-equal, work_orders нет, SERVE нет, trade-outcome нет
  W5 повторяемость: второй заказ → второй расчёт (механизм, не сценарий)

Открытый пункт (честная фиксация, прецедент eat): CONSEQUENCE_REACHES_MEMORY —
исходы на шине доказаны; проводка в память NPC — LIFE INTEGRATION (R4).
Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/work_vertical_test.py
"""
import os
import sys
import tempfile
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings

# Изоляция saves ДО импорта сервисов (IPT-паттерн; урок H5 из ADR-O-378)
settings.saves_dir = tempfile.mkdtemp(prefix="work_slice_")

# Флаги контура: пара EAT + WORK (call-time читатели)
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
os.environ["WORK_ENABLED"] = "1"

from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
GORAN = "merchant_goran"
TORNIN = "tavern_keeper_tornin"
MAX_TICKS = 60
PRICE = 0.01

SPY = {"events": []}
INTENT_TALLY = {}
GORAN_POS = []


def _spy(event):
    SPY["events"].append(event)


def _tick(world):
    return world.game_loop.idle_tick(CAMPAIGN)


def _states_map(world):
    _st = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    if isinstance(_st, list):
        return {n.get("npc_id", n.get("id")): n for n in _st}
    return _st or {}


def _scene(world):
    return world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}


def _orders(world):
    _o = _scene(world).get("work_orders")
    return _o if isinstance(_o, dict) else {}


def _tally_tasks(world):
    """[P6-DIAG] пассивный зонд: какие интенты материализовались в задачи."""
    _pt = _scene(world).get("pending_tasks")
    if isinstance(_pt, list):
        for _t in _pt:
            _k = (
                str(_t.get("owner_id", "")),
                str((_t.get("payload") or {}).get("intent_type", "")),
            )
            INTENT_TALLY[_k] = INTENT_TALLY.get(_k, 0) + 1


def _profiles(world):
    return world.game_loop._svc.get_or_create_economic_profiles(CAMPAIGN)


def _quiet():
    import logging

    logging.basicConfig(level=logging.WARNING)
    for _name in (
        "app.services.llm.router",
        "app.services.llm.provider_manager",
        "app.services.llm.llama_cpp_provider",
        "app.services.game_loop.task_scheduler",
        "app.services.execution.dialogue_queue",
        "app.services.memory",
        "app.services.npc.npc_tick_pipeline",
    ):
        logging.getLogger(_name).setLevel(logging.CRITICAL)
    logging.getLogger().setLevel(logging.CRITICAL)


def _feq(a, b):
    return abs(float(a) - float(b)) < 1e-9


def _thirst(world, who=GORAN, val=0.9):
    _t = _states_map(world).get(who) or {}
    _t.setdefault("needs", {})["thirst"] = val


def _seed(world):
    """Вход мира: экономический факт (эль в таверне) + гость у стойки."""
    _p = _profiles(world)
    _tp = _p.get(TORNIN)
    _gp = _p.get(GORAN)
    if _tp is None or _gp is None:
        print(f"[SEED] ❌ профили не найдены; есть: {sorted(_p.keys())}")
        return False
    _tp.stock_for_sale["ale"] = 5.0
    _st = _states_map(world)
    _g, _t = _st.get(GORAN) or {}, _st.get(TORNIN) or {}
    if _g and _t and _t.get("position"):
        _g["position"] = _t.get("position")
    return True


def _eco(world):
    _p = _profiles(world)

    def _snap(nid):
        _x = _p.get(nid)
        if _x is None:
            return None
        return (
            round(float(_x.gold), 4),
            {k: round(float(v), 4) for k, v in _x.goods.items()},
            {k: round(float(v), 4) for k, v in _x.stock_for_sale.items()},
        )

    return {nid: _snap(nid) for nid in (GORAN, TORNIN)}


def _collect_serve(world, seen):
    _a = (_states_map(world).get(TORNIN) or {}).get("activity_state")
    if isinstance(_a, dict) and str(_a.get("activity_type")) == "serve":
        seen.append(dict(_a))


def _work_outcomes():
    return [
        e
        for e in SPY["events"]
        if str(getattr(e, "type", "")) == "activity_outcome"
        and (getattr(e, "payload", {}) or {}).get("order_id")
    ]


def main() -> int:
    _quiet()
    print("=" * 64)
    print("SUPERBOX-WORK: Vertical Slice «Заказ и расчёт» (S256, ADR-O-391)")
    print("=" * 64)
    ok = True

    # ── E0: живой мир + LLM-стаб + шпион ─────────────────────────────
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _executor = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _executor is not None and hasattr(_executor, "_router"):
        _executor._router = None
        print("[E0] DialogueExecutor → stub-режим (LLM выключена для теста)")
    _bus = world.game_loop._tick_orch._get_event_bus()
    _bus.subscribe(EventType.ACTIVITY_OUTCOME, _spy)
    _tick(world)  # инициализация сцены

    if not _seed(world):
        return 1
    _before = _eco(world)
    _thirst(world)

    _serve_seen = []
    for _ in range(MAX_TICKS):
        _tick(world)
        _tally_tasks(world)
        _collect_serve(world, _serve_seen)
        GORAN_POS.append(
            str((_states_map(world).get(GORAN) or {}).get("position", "") or "")
        )
        if any(o.get("status") == "completed" for o in _orders(world).values()):
            break

    _orders_f = _orders(world)
    _after = _eco(world)
    _des = (_states_map(world).get(GORAN) or {}).get("desires") or []
    print(f"[P6-DIAG] интенты→задачи: {dict(sorted(INTENT_TALLY.items()))}")
    print(f"[POS-DIAG] позиции Горана: {sorted(set(GORAN_POS))}")
    print(
        f"[W1-DIAG] desires(goran)="
        f"{[(d.get('subject_class'), d.get('urgency')) for d in _des]}; "
        f"orders={list(_orders_f.keys())}; serve_ticks={len(_serve_seen)}"
    )

    # ── W1: сделка ───────────────────────────────────────────────────
    _o = next(
        (o for o in _orders_f.values() if o.get("status") == "completed"), None
    )
    w1 = (
        _o is not None
        and _o.get("actor_id") == GORAN
        and _o.get("target_id") == TORNIN
        and (_o.get("goods") or {}).get("ale", 0) == 1
        and bool(_serve_seen)
        and str(_serve_seen[0].get("desire_id", "")).startswith("order:")
    )
    print(f"[W1] ORDER→SERVE→COMPLETED (goran→tornin, ale) — {'✅' if w1 else '❌'}")
    ok = ok and w1

    w1e = (
        _o is not None
        and _feq(_after[GORAN][0], _before[GORAN][0] - PRICE)
        and _feq(_after[TORNIN][0], _before[TORNIN][0] + PRICE)
        and _feq(_after[TORNIN][2].get("ale", 0.0), 5.0 - 1)
        and _feq(_after[GORAN][1].get("ale", 0.0), _before[GORAN][1].get("ale", 0.0) + 1)
    )
    print(
        f"[W1-E] ale: tornin {_before[TORNIN][2].get('ale')}→{_after[TORNIN][2].get('ale')}, "
        f"goran +ale; gold: goran {_before[GORAN][0]}→{_after[GORAN][0]}, "
        f"tornin {_before[TORNIN][0]}→{_after[TORNIN][0]} — {'✅' if w1e else '❌'}"
    )
    ok = ok and w1e

    _src_ok = {
        str(getattr(e, "source", ""))
        for e in _work_outcomes()
        if (getattr(e, "payload", {}) or {}).get("success") is True
    }
    w1o = GORAN in _src_ok and TORNIN in _src_ok
    print(
        f"[W1-O] ACTIVITY_OUTCOME обоим (sources={sorted(_src_ok)}) — "
        f"{'✅' if w1o else '❌'}"
    )
    ok = ok and w1o

    _inc = world.game_loop._svc.economy_tracker.get_daily_income(TORNIN)
    print(
        f"[W1-INC] daily_income({TORNIN})={_inc} — "
        f"{'✅' if _feq(_inc, PRICE) else '⚠️ (день мог перевернуться; замок — юнит)'}"
    )

    # ── W2 CRITICAL: переживает следующий тик ────────────────────────
    _tick(world)
    _tick(world)
    _after2 = _eco(world)
    _o2 = _orders(world).get(_o.get("order_id")) if _o else None
    w2 = (
        _after2[GORAN] == _after[GORAN]
        and _after2[TORNIN] == _after[TORNIN]
        and _o2 is not None
        and _o2.get("status") == "completed"
    )
    print(
        f"[W2] CRITICAL — тик N+2 читает изменившийся SSOT "
        f"(ale={_after2[GORAN][1].get('ale')}, gold_t={_after2[TORNIN][0]}, "
        f"повторного settle нет) — {'✅' if w2 else '❌'}"
    )
    ok = ok and w2

    # ── W5: повторяемость (механизм, не сценарий) ─────────────────────
    _thirst(world)
    for _ in range(MAX_TICKS):
        _tick(world)
        if (
            sum(1 for o in _orders(world).values() if o.get("status") == "completed")
            >= 2
        ):
            break
    _after5 = _eco(world)
    w5 = (
        sum(1 for o in _orders(world).values() if o.get("status") == "completed") >= 2
        and _feq(_after5[TORNIN][2].get("ale", 0.0), 5.0 - 2)
        and _feq(_after5[GORAN][1].get("ale", 0.0), _before[GORAN][1].get("ale", 0.0) + 2)
        and _feq(_after5[TORNIN][0], _before[TORNIN][0] + 2 * PRICE)
    )
    print(
        f"[W5] второй заказ исполнен (ale_tornin={_after5[TORNIN][2].get('ale')}, "
        f"gold_tornin={_after5[TORNIN][0]}) — {'✅' if w5 else '❌'}"
    )
    ok = ok and w5

    # ── W3: атомарный провал ──────────────────────────────────────────
    _tp = _profiles(world).get(TORNIN)
    _tp.stock_for_sale["ale"] = 0.0
    _before3 = _eco(world)
    _thirst(world)
    for _ in range(MAX_TICKS):
        _tick(world)
        if any(
            str(o.get("fail_reason", "")).startswith("no_stock")
            for o in _orders(world).values()
        ):
            break
    _after3 = _eco(world)
    _failed = [
        o
        for o in _orders(world).values()
        if o.get("status") == "failed"
        and str(o.get("fail_reason", "")).startswith("no_stock")
    ]
    w3 = (
        bool(_failed)
        and _after3[GORAN] == _before3[GORAN]
        and _after3[TORNIN] == _before3[TORNIN]
        and any(
            (getattr(e, "payload", {}) or {}).get("success") is False
            for e in _work_outcomes()
            if (getattr(e, "payload", {}) or {}).get("order_id")
            == (_failed[0].get("order_id") if _failed else None)
        )
    )
    print(
        f"[W3] stock=0 → FAILED no_stock:ale, before==after, success=False — "
        f"{'✅' if w3 else '❌'}"
    )
    ok = ok and w3

    # ── W4: OFF = no causal footprint (абляция) ──────────────────────
    SPY["events"].clear()
    os.environ["WORK_ENABLED"] = ""
    settings.saves_dir = tempfile.mkdtemp(prefix="work_slice_ctrl_")
    from app.services.npc.life_engine import reset_life_engine

    reset_life_engine()
    world2 = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _tick(world2)
    _p2 = _profiles(world2)
    if _p2.get(TORNIN) is None or _p2.get(GORAN) is None:
        print("[W4] ❌ профили control-мира не найдены")
        return 1
    _p2[TORNIN].stock_for_sale["ale"] = 5.0
    _st2 = _states_map(world2)
    (_st2.get(GORAN) or {}).setdefault("needs", {})["thirst"] = 0.9
    _g2, _t2 = _st2.get(GORAN) or {}, _st2.get(TORNIN) or {}
    if _g2 and _t2 and _t2.get("position"):
        _g2["position"] = _t2.get("position")
    _before4 = _eco(world2)
    _serve4 = 0
    for _ in range(30):
        _tick(world2)
        _a = (_states_map(world2).get(TORNIN) or {}).get("activity_state")
        if isinstance(_a, dict) and str(_a.get("activity_type")) == "serve":
            _serve4 += 1
    _after4 = _eco(world2)
    w4 = (
        _before4[GORAN] == _after4[GORAN]
        and _before4[TORNIN] == _after4[TORNIN]
        and not _orders(world2)
        and _serve4 == 0
        and not _work_outcomes()
    )
    print(
        f"[W4] OFF: профили deep-equal, work_orders нет, SERVE нет "
        f"({_serve4}), trade-outcome нет — {'✅' if w4 else '❌'} "
        f"(OFF выключает исполнение вертикали, не DecisionHub)"
    )
    ok = ok and w4

    print("=" * 64)
    print(
        "🎉 СРЕЗ WORK ДОКАЗАН: выбор → заказ → деятельность → обмен → "
        "изменённый мир → исход обоим → следующий тик видит след. "
        "OFF — нем."
        if ok
        else "❌ ТЕСТ С ОШИБКАМИ — см. блок выше"
    )
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
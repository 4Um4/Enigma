"""
path: /project/backend/tests/test_work_orders.py
Назначение: ADR-O-391 (WORK, S256) — юнит-замок контура заказов:
    рождение ORDER, материализация SERVE, атомарный settlement,
    идемпотентность терминала (L-W6), FAILED без мутаций (L-W3),
    OFF = no-op (L-W5).
"""
from types import SimpleNamespace

from app.domain.activity import ActivityState, ActivityStep, ActivityType, StepKind
from app.models.economy import EconomicProfile, TransactionStatus
from app.services.economy.work_orders import (
    create_order_from_trade_intent,
    fail_order,
    run_work_orders_pass,
    settle_order,
    work_enabled,
)
from app.services.npc.activity_catalog import _SPEC_BY_TYPE, ACTIVITY_CATALOG

GORAN = "merchant_goran"
TORNIN = "tavern_keeper_tornin"


def _profile(npc_id, gold=10.0, goods=None, stock=None):
    return EconomicProfile(
        npc_id=npc_id,
        gold=gold,
        goods=goods or {},
        stock_for_sale=stock or {},
        income_sources={},
        expense_categories={},
        base_needs=[],
    )


class _Bus:
    def __init__(self):
        self.events = []

    def publish(self, e):
        self.events.append(e)


def _ctx(profiles, npcs=None, scene=None, tracker=None, tick=5):
    _inc = []
    svc = SimpleNamespace(
        get_or_create_economic_profiles=lambda cid: profiles,
        economy_tracker=tracker
        or SimpleNamespace(record_income=lambda nid, amt: _inc.append((nid, amt))),
    )
    return SimpleNamespace(
        npc_services=svc,
        campaign_id="t",
        all_npcs_raw=npcs or [],
        scene_state=scene if scene is not None else {},
        tick_number=tick,
    )


def _orch(bus):
    return SimpleNamespace(_get_event_bus=lambda: bus)


def _accepted_order(monkeypatch, profiles, npcs=None):
    monkeypatch.setenv("WORK_ENABLED", "1")
    ctx = _ctx(profiles, npcs=npcs)
    oid = create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN)
    assert oid
    ctx.scene_state["work_orders"][oid]["status"] = TransactionStatus.ACCEPTED.value
    return ctx, oid


# ── Реестр и домен ────────────────────────────────────────────────────


def test_work_enabled_env(monkeypatch):
    monkeypatch.delenv("WORK_ENABLED", raising=False)
    assert work_enabled() is False
    monkeypatch.setenv("WORK_ENABLED", "1")
    assert work_enabled() is True


def test_serve_registered_in_catalog():
    assert ActivityType.SERVE in _SPEC_BY_TYPE
    assert ACTIVITY_CATALOG["service"].activity_type is ActivityType.SERVE


def test_serve_state_roundtrip():
    _s = ActivityState(
        activity_id=ActivityState.build_id(TORNIN, ActivityType.SERVE, 3),
        activity_type=ActivityType.SERVE,
        desire_id="order:wo_1",
        target_ref="wo_1",
        steps=(
            ActivityStep(
                step_kind=StepKind.BODY_ACTION, action_type="SERVE", duration_ticks=2
            ),
        ),
        started_tick=3,
    )
    assert ActivityState.from_dict(_s.to_dict()) == _s


# ── create_order ──────────────────────────────────────────────────────


def test_create_order_off_noop(monkeypatch):
    monkeypatch.delenv("WORK_ENABLED", raising=False)
    ctx = _ctx(
        {GORAN: _profile(GORAN), TORNIN: _profile(TORNIN, stock={"ale": 5.0})}
    )
    assert create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN) is None
    assert "work_orders" not in ctx.scene_state  # OFF не создаёт даже ключ


def test_create_order_born(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN),
        TORNIN: _profile(TORNIN, stock={"ale": 5.0}),
    }
    npcs = [
        {
            "npc_id": GORAN,
            "desires": [
                {"desire_id": "d:ale", "subject_class": "ale", "urgency": 0.9}
            ],
        }
    ]
    ctx = _ctx(profiles, npcs=npcs)
    oid = create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN)
    assert oid == "wo_5_merchant_goran_tavern_keeper_tornin_ale"
    o = ctx.scene_state["work_orders"][oid]
    assert o["status"] == TransactionStatus.PROPOSED.value
    assert o["goods"] == {"ale": 1.0}
    assert o["payment"] == 0.01
    assert o["buyer_desire_id"] == "d:ale"
    # рождение заказа не мутирует экономику
    assert profiles[TORNIN].stock_for_sale["ale"] == 5.0
    assert profiles[GORAN].gold == 10.0


def test_create_order_guards(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN),
        TORNIN: _profile(TORNIN, stock={}),
    }
    ctx = _ctx(profiles)
    # пустой сток — предмет не назван
    assert create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN) is None
    # адресат "all" — неучастник
    profiles[TORNIN].stock_for_sale["ale"] = 5.0
    assert create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref="all") is None


# ── work-pass ─────────────────────────────────────────────────────────


def test_work_pass_materializes_serve(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN),
        TORNIN: _profile(TORNIN, stock={"ale": 5.0}),
    }
    ctx = _ctx(profiles)
    oid = create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN)
    tornin = {"npc_id": TORNIN, "body_state": {"hp": 100}}
    ctx.all_npcs_raw = [tornin]
    run_work_orders_pass(ctx, _orch(_Bus()))
    a = tornin["activity_state"]
    assert a["activity_type"] == "serve"
    assert a["desire_id"] == f"order:{oid}"
    assert a["target_ref"] == oid
    assert ctx.scene_state["work_orders"][oid]["status"] == (
        TransactionStatus.ACCEPTED.value
    )


def test_work_pass_busy_seller_waits(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN),
        TORNIN: _profile(TORNIN, stock={"ale": 5.0}),
    }
    ctx = _ctx(profiles)
    oid = create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN)
    tornin = {
        "npc_id": TORNIN,
        "body_state": {"hp": 100},
        "activity_state": {"activity_type": "eat"},
    }
    ctx.all_npcs_raw = [tornin]
    run_work_orders_pass(ctx, _orch(_Bus()))
    assert tornin["activity_state"]["activity_type"] == "eat"  # не перетёрт
    assert ctx.scene_state["work_orders"][oid]["status"] == (
        TransactionStatus.PROPOSED.value
    )


def test_work_pass_off_noop(monkeypatch):
    monkeypatch.delenv("WORK_ENABLED", raising=False)
    ctx = _ctx({})
    ctx.scene_state["work_orders"] = {
        "wo_1": {"status": "proposed", "target_id": TORNIN}
    }
    tornin = {"npc_id": TORNIN, "body_state": {"hp": 100}}
    ctx.all_npcs_raw = [tornin]
    run_work_orders_pass(ctx, _orch(_Bus()))
    assert "activity_state" not in tornin


# ── settlement ────────────────────────────────────────────────────────


def test_settle_success_atomic(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    _inc = []
    tracker = SimpleNamespace(record_income=lambda nid, amt: _inc.append((nid, amt)))
    profiles = {
        GORAN: _profile(GORAN, gold=10.0),
        TORNIN: _profile(TORNIN, gold=10.0, stock={"ale": 5.0}),
    }
    ctx, oid = _accepted_order(monkeypatch, profiles)
    ctx.npc_services.economy_tracker = tracker
    bus = _Bus()
    settle_order(ctx, _orch(bus), seller_id=TORNIN, order_id=oid)

    assert profiles[TORNIN].stock_for_sale["ale"] == 4.0
    assert profiles[GORAN].goods["ale"] == 1.0
    assert profiles[GORAN].gold == 9.99
    assert profiles[TORNIN].gold == 10.01
    assert ctx.scene_state["work_orders"][oid]["status"] == (
        TransactionStatus.COMPLETED.value
    )
    assert _inc == [(TORNIN, 0.01)]
    _sources = {getattr(e, "source", "") for e in bus.events}
    assert _sources == {GORAN, TORNIN}
    assert all(
        (getattr(e, "payload", {}) or {}).get("success") is True for e in bus.events
    )


def test_settle_idempotent(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN, gold=10.0),
        TORNIN: _profile(TORNIN, gold=10.0, stock={"ale": 5.0}),
    }
    ctx, oid = _accepted_order(monkeypatch, profiles)
    settle_order(ctx, _orch(_Bus()), seller_id=TORNIN, order_id=oid)
    settle_order(ctx, _orch(_Bus()), seller_id=TORNIN, order_id=oid)  # L-W6
    assert profiles[TORNIN].stock_for_sale["ale"] == 4.0
    assert profiles[GORAN].gold == 9.99  # двойного списания нет


def test_settle_no_stock_failed(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN, gold=10.0),
        TORNIN: _profile(TORNIN, gold=10.0, stock={"ale": 0.0}),
    }
    ctx, oid = _accepted_order(monkeypatch, profiles)
    _before = (profiles[GORAN].gold, dict(profiles[GORAN].goods),
               profiles[TORNIN].gold, dict(profiles[TORNIN].stock_for_sale))
    bus = _Bus()
    settle_order(ctx, _orch(bus), seller_id=TORNIN, order_id=oid)
    assert ctx.scene_state["work_orders"][oid]["status"] == (
        TransactionStatus.FAILED.value
    )
    assert ctx.scene_state["work_orders"][oid]["fail_reason"] == "no_stock:ale"
    assert (profiles[GORAN].gold, dict(profiles[GORAN].goods),
            profiles[TORNIN].gold, dict(profiles[TORNIN].stock_for_sale)) == _before
    assert bus.events and all(
        (getattr(e, "payload", {}) or {}).get("success") is False for e in bus.events
    )


def test_settle_no_gold_failed(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN, gold=0.0),
        TORNIN: _profile(TORNIN, gold=10.0, stock={"ale": 5.0}),
    }
    ctx, oid = _accepted_order(monkeypatch, profiles)
    settle_order(ctx, _orch(_Bus()), seller_id=TORNIN, order_id=oid)
    o = ctx.scene_state["work_orders"][oid]
    assert o["status"] == TransactionStatus.FAILED.value
    assert o["fail_reason"] == "no_gold"
    assert profiles[TORNIN].stock_for_sale["ale"] == 5.0  # мир не изменился
    assert profiles[GORAN].goods == {}


def test_fail_order_no_mutations(monkeypatch):
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN, gold=10.0),
        TORNIN: _profile(TORNIN, gold=10.0, stock={"ale": 5.0}),
    }
    ctx, oid = _accepted_order(monkeypatch, profiles)
    fail_order(ctx, order_id=oid, reason="timeout")
    assert ctx.scene_state["work_orders"][oid]["status"] == (
        TransactionStatus.FAILED.value
    )
    assert profiles[TORNIN].stock_for_sale["ale"] == 5.0
    assert profiles[GORAN].gold == 10.0


def test_create_order_routes_to_seller(monkeypatch):
    """M2b-фикс: социальный адресат (orm) без товара → ордер маршрутизируется
    к продавцу предмета (tornin); детерминизм выбора."""
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN),
        "blacksmith_orm": _profile("blacksmith_orm", stock={}),
        TORNIN: _profile(TORNIN, stock={"ale": 5.0}),
    }
    npcs = [
        {
            "npc_id": GORAN,
            "desires": [
                {"desire_id": "d:ale", "subject_class": "ale", "urgency": 0.9}
            ],
        }
    ]
    ctx = _ctx(profiles, npcs=npcs)
    oid = create_order_from_trade_intent(
        ctx, speaker=GORAN, seller_ref="blacksmith_orm"
    )
    assert oid == "wo_5_merchant_goran_tavern_keeper_tornin_ale"
    o = ctx.scene_state["work_orders"][oid]
    assert o["target_id"] == TORNIN
    assert o["goods"] == {"ale": 1.0}


def test_create_order_dedup_open(monkeypatch):
    """Один открытый заказ на покупателя: живой PROPOSED гасит новые рождения."""
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN),
        TORNIN: _profile(TORNIN, stock={"ale": 5.0}),
    }
    ctx = _ctx(profiles)
    assert create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN)
    assert (
        create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN) is None
    )


def test_settle_satisfies_buyer_pressure(monkeypatch):
    """Терминал обмена гасит давление покупателя (EAT-прецедент)."""
    monkeypatch.setenv("WORK_ENABLED", "1")
    profiles = {
        GORAN: _profile(GORAN, gold=10.0),
        TORNIN: _profile(TORNIN, gold=10.0, stock={"ale": 5.0}),
    }
    goran = {
        "npc_id": GORAN,
        "needs": {"thirst": 0.9},
        "desires": [
            {
                "desire_id": "d:ale",
                "subject_class": "ale",
                "urgency": 0.9,
                "last_fulfilled_tick": -1,
            }
        ],
    }
    ctx = _ctx(profiles, npcs=[goran])
    oid = create_order_from_trade_intent(ctx, speaker=GORAN, seller_ref=TORNIN)
    ctx.scene_state["work_orders"][oid]["status"] = TransactionStatus.ACCEPTED.value
    settle_order(ctx, _orch(_Bus()), seller_id=TORNIN, order_id=oid)
    assert goran["needs"]["thirst"] == 0.0
    assert goran["desires"][0]["last_fulfilled_tick"] == 5
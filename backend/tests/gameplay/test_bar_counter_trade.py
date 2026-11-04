# path: /project/backend/tests/gameplay/test_bar_counter_trade.py
# Назначение: Priority 2 — барная стойка: player + NPC через один торговый путь.
#   create_order → Transaction PROPOSED → settle_order → atomic exchange.
#   Проверки: создание заказа, дедуп, недостаток денег, нет товара,
#   двойное списание, NPC через тот же механизм.
# Зависимости: tests.gameplay.harness, app.services.economy.work_orders
# Запуск: cd backend; python -m pytest tests/gameplay/test_bar_counter_trade.py -v -s

"""
Priority 2: Bar counter trade — player + NPC use same mechanism.

Tests the shared create_order → settle_order path:
  1. Player orders ale → Transaction PROPOSED created
  2. NPC orders ale → same create_order function
  3. Insufficient funds → settle FAILED (no_gold)
  4. No stock → settle FAILED (no_stock)
  5. Dedup: one open order per buyer
  6. No double charge: second settle = no-op (L-W6)

Production-path: create_order + settle_order (work_orders.py).
Test fixtures: WORK_ENABLED=1, seeded stock_for_sale, SimpleNamespace ctx.
"""
import os
from types import SimpleNamespace
from typing import Any

import pytest

from tests.gameplay.harness import TavernGameplayHarness

_CAMPAIGN = "Open_road"
_PLAYER = "player"
_SELLER = "tavern_keeper_tornin"
_NPC_BUYER = "maid_lusya"
_GOOD = "ale"


@pytest.fixture(autouse=True)
def _work_enabled_env():
    """WORK_ENABLED=1 для всех тестов; restore после."""
    os.environ["WORK_ENABLED"] = "1"
    yield
    os.environ.pop("WORK_ENABLED", None)


def _setup_harness() -> TavernGameplayHarness:
    """Harness с WORK_ENABLED + seeded stock_for_sale на продавце."""
    h = TavernGameplayHarness(seed=42, location="tavern")
    h.new_game()
    profiles = h.game_loop._svc.get_or_create_economic_profiles(h.campaign_id)
    # Seed stock: продавец имеет ale для продажи
    profiles[_SELLER].stock_for_sale[_GOOD] = 10.0
    return h


def _make_ctx(h: TavernGameplayHarness, tick: int = 1) -> SimpleNamespace:
    """Construct ctx for create_order/settle_order."""
    _scene = h.get_scene_fresh() or {}
    return SimpleNamespace(
        scene_state=_scene,
        tick_number=tick,
        campaign_id=h.campaign_id,
        npc_services=h.game_loop._svc,
        all_npcs_raw=h.game_loop._resolve_npcs_snapshot(h.campaign_id) or [],
    )


class TestBarCounterTrade:
    """Priority 2: player + NPC use same trade mechanism."""

    def test_player_order_creates_transaction(self) -> None:
        """Player orders ale → Transaction PROPOSED created."""
        from app.services.economy.work_orders import create_order

        h = _setup_harness()
        try:
            ctx = _make_ctx(h)
            order_id = create_order(
                ctx, buyer=_PLAYER, good=_GOOD, orchestrator=h.game_loop._tick_orch
            )
            print(f"[CHECK] order_id={order_id}")
            assert order_id is not None, "create_order returned None"

            orders = ctx.scene_state.get("work_orders", {})
            _o = orders[order_id]
            print(f"[CHECK] order: {_o}")
            assert _o["status"] == "proposed"
            assert _o["actor_id"] == _PLAYER
            assert _o["target_id"] == _SELLER
            assert _o["goods"] == {_GOOD: 1.0}
            assert _o["payment"] > 0.0
            print(f"[OK] Transaction PROPOSED: actor={_o['actor_id']} target={_o['target_id']} payment={_o['payment']}")
        finally:
            h.dispose()

    def test_npc_order_same_mechanism(self) -> None:
        """NPC uses same create_order function — same mechanism."""
        from app.services.economy.work_orders import create_order

        h = _setup_harness()
        try:
            ctx = _make_ctx(h)
            order_id = create_order(
                ctx, buyer=_NPC_BUYER, good=_GOOD, orchestrator=h.game_loop._tick_orch
            )
            print(f"[CHECK] NPC order_id={order_id}")
            assert order_id is not None, "create_order returned None for NPC"

            orders = ctx.scene_state.get("work_orders", {})
            _o = orders[order_id]
            assert _o["actor_id"] == _NPC_BUYER
            assert _o["target_id"] == _SELLER
            print(f"[OK] NPC same mechanism: actor={_o['actor_id']} good={_o['goods']}")
        finally:
            h.dispose()

    def test_dedup_one_open_order(self) -> None:
        """Dedup: second create_order returns None (one open order per buyer)."""
        from app.services.economy.work_orders import create_order

        h = _setup_harness()
        try:
            ctx = _make_ctx(h)
            order1 = create_order(
                ctx, buyer=_PLAYER, good=_GOOD, orchestrator=h.game_loop._tick_orch
            )
            assert order1 is not None, "first create_order failed"

            order2 = create_order(
                ctx, buyer=_PLAYER, good=_GOOD, orchestrator=h.game_loop._tick_orch
            )
            print(f"[CHECK] order1={order1}, order2={order2}")
            assert order2 is None, "dedup failed — second order created"
            print("[OK] Dedup: second create_order returned None")
        finally:
            h.dispose()

    def test_insufficient_funds_failed(self) -> None:
        """Insufficient funds → settle FAILED (no_gold)."""
        from app.services.economy.work_orders import create_order, settle_order

        h = _setup_harness()
        try:
            profiles = h.game_loop._svc.get_or_create_economic_profiles(h.campaign_id)
            profiles[_PLAYER].gold = 0.0  # no money
            print("[SEED] player gold=0.0")

            ctx = _make_ctx(h)
            order_id = create_order(
                ctx, buyer=_PLAYER, good=_GOOD, orchestrator=h.game_loop._tick_orch
            )
            assert order_id is not None

            # Bypass SERVE: manually set ACCEPTED
            orders = ctx.scene_state.get("work_orders", {})
            orders[order_id]["status"] = "accepted"

            settle_order(ctx, h.game_loop._tick_orch, seller_id=_SELLER, order_id=order_id)

            _o = orders[order_id]
            print(f"[CHECK] order after settle: status={_o['status']} fail_reason={_o.get('fail_reason')}")
            assert _o["status"] == "failed", f"expected failed, got {_o['status']}"
            assert "no_gold" in _o.get("fail_reason", ""), f"expected no_gold, got {_o.get('fail_reason')}"
            print("[OK] Insufficient funds → FAILED (no_gold)")
        finally:
            h.dispose()

    def test_no_stock_failed(self) -> None:
        """No stock → settle FAILED (no_stock)."""
        from app.services.economy.work_orders import create_order, settle_order

        h = _setup_harness()
        try:
            profiles = h.game_loop._svc.get_or_create_economic_profiles(h.campaign_id)
            profiles[_SELLER].stock_for_sale[_GOOD] = 0.0  # no stock
            print("[SEED] seller stock=0.0")

            ctx = _make_ctx(h)
            order_id = create_order(
                ctx, buyer=_PLAYER, good=_GOOD, orchestrator=h.game_loop._tick_orch
            )
            assert order_id is not None

            orders = ctx.scene_state.get("work_orders", {})
            orders[order_id]["status"] = "accepted"

            settle_order(ctx, h.game_loop._tick_orch, seller_id=_SELLER, order_id=order_id)

            _o = orders[order_id]
            print(f"[CHECK] order after settle: status={_o['status']} fail_reason={_o.get('fail_reason')}")
            assert _o["status"] == "failed", f"expected failed, got {_o['status']}"
            assert "no_stock" in _o.get("fail_reason", ""), f"expected no_stock, got {_o.get('fail_reason')}"
            print("[OK] No stock → FAILED (no_stock)")
        finally:
            h.dispose()

    def test_no_double_charge(self) -> None:
        """No double charge: second settle = no-op (L-W6)."""
        from app.services.economy.work_orders import create_order, settle_order

        h = _setup_harness()
        try:
            profiles = h.game_loop._svc.get_or_create_economic_profiles(h.campaign_id)
            initial_gold = profiles[_PLAYER].gold
            initial_stock = profiles[_SELLER].stock_for_sale[_GOOD]
            print(f"[SEED] player gold={initial_gold}, seller stock={initial_stock}")

            ctx = _make_ctx(h)
            order_id = create_order(
                ctx, buyer=_PLAYER, good=_GOOD, orchestrator=h.game_loop._tick_orch
            )
            assert order_id is not None

            orders = ctx.scene_state.get("work_orders", {})
            orders[order_id]["status"] = "accepted"

            # First settle
            settle_order(ctx, h.game_loop._tick_orch, seller_id=_SELLER, order_id=order_id)
            gold_after_first = profiles[_PLAYER].gold
            stock_after_first = profiles[_SELLER].stock_for_sale[_GOOD]
            print(f"[CHECK] after 1st settle: gold={gold_after_first} stock={stock_after_first}")
            assert gold_after_first < initial_gold, "gold not deducted on 1st settle"
            assert stock_after_first < initial_stock, "stock not deducted on 1st settle"
            assert orders[order_id]["status"] == "completed"

            # Second settle (should be no-op)
            settle_order(ctx, h.game_loop._tick_orch, seller_id=_SELLER, order_id=order_id)
            gold_after_second = profiles[_PLAYER].gold
            stock_after_second = profiles[_SELLER].stock_for_sale[_GOOD]
            print(f"[CHECK] after 2nd settle: gold={gold_after_second} stock={stock_after_second}")
            assert gold_after_second == gold_after_first, "double charge on 2nd settle!"
            assert stock_after_second == stock_after_first, "double stock deduction on 2nd settle!"
            print("[OK] No double charge: 2nd settle = no-op (L-W6)")
        finally:
            h.dispose()
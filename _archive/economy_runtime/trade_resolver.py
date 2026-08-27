"""
backend/app/services/economy/trade_resolver.py
Связка между DecisionHub (intent) и TransactionEngine (сделки).

NPC хочет TRADE → TradeResolver определяет что/у кого → TransactionEngine.execute_sale

Назначение: Превращать решения NPC в реальные экономические действия
Зависимости: app.models.economy, app.services.economy.transaction_engine
Основные сущности: TradeResolver
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from app.core.constants import GOODS_PRICES
from app.models.economy import EconomicProfile, NeedType
from app.services.economy.transaction_engine import TransactionEngine




@dataclass
class TradeResult:
    """Результат попытки торговли."""

    buyer_id: str
    seller_id: str
    goods: Dict[str, float]
    price: float
    success: bool
    reason: str = ""


class TradeResolver:
    """
    Определяет что NPC хочет купить/продать и находит партнёров.

    Логика:
    - Если у NPC urgent need по FOOD → пытается купить еду
    - Ищет продавца с нужным товаром в той же локации
    - Рассчитывает цену на основе GOODS_PRICES + наценка продавца
    - Вызывает TransactionEngine.execute_sale
    """

    def __init__(self, tx_engine: TransactionEngine) -> None:
        self.tx_engine = tx_engine

    def resolve_tick(
        self,
        profiles: Dict[str, EconomicProfile],
        trade_intents: Dict[str, float],  # npc_id → score
        location: str = "",
    ) -> List[TradeResult]:
        """
        Обрабатывает все TRADE интенты за тик.

        Args:
            profiles: Все экономические профили
            trade_intents: NPC с intent=TRADE и их score
            location: Локация (для ограничения поиска партнёров)

        Returns:
            Список результатов сделок
        """
        results: List[TradeResult] = []

        # Сортируем по score — самые отчаянные торгуют первыми
        sorted_buyers = sorted(trade_intents.items(), key=lambda x: -x[1])

        for buyer_id, score in sorted_buyers:
            buyer = profiles.get(buyer_id)
            if not buyer:
                continue

            # Определяем что нужно купить (на основе потребностей)
            needed_good = self._determine_needed_good(buyer)
            if not needed_good:
                continue

            # Сколько нужно
            needed_amount = self._calculate_needed_amount(buyer, needed_good)

            # Ищем продавца
            seller_id = self._find_seller(
                profiles, buyer_id, needed_good, needed_amount
            )
            if not seller_id:
                continue

            seller = profiles[seller_id]

            # P8: Корректируем объём закупки, если у продавца меньше, чем нужно
            available_stock = seller.stock_for_sale.get(needed_good, 0.0)
            if available_stock < needed_amount:
                needed_amount = max(1.0, available_stock)

            # Рассчитываем цену
            price = self._calculate_price(needed_good, needed_amount, seller)

            # Проверяем аффордабилити перед вызовом движка
            if not buyer.can_afford(price):
                results.append(
                    TradeResult(
                        buyer_id=buyer_id,
                        seller_id=seller_id,
                        goods={needed_good: needed_amount},
                        price=price,
                        success=False,
                        reason=f"не может позволить {price}G (есть {buyer.gold}G)",
                    )
                )
                continue

            # Выполняем сделку
            tx = self.tx_engine.execute_sale(
                buyer=buyer,
                seller=seller,
                goods={needed_good: needed_amount},
                price=price,
                reason=f"{buyer_id} покупает {needed_good} у {seller_id}",
                tick=0,
            )

            success = tx.status.value == "completed"
            results.append(
                TradeResult(
                    buyer_id=buyer_id,
                    seller_id=seller_id,
                    goods={needed_good: needed_amount},
                    price=price,
                    success=success,
                    reason=tx.reason if not success else "",
                )
            )

        # Второй проход: NPC с срочными потребностями покупают, даже если intent ≠ trade
        # DecisionHub может дать «разговор» при голоде — но голодный купит еду
        already_traded = set(trade_intents.keys())
        for npc_id, profile in profiles.items():
            if npc_id in already_traded:
                continue
            needed_good = self._determine_needed_good(profile)
            if not needed_good:
                continue
            needed_amount = self._calculate_needed_amount(profile, needed_good)
            seller_id = self._find_seller(profiles, npc_id, needed_good, needed_amount)
            if not seller_id:
                continue
            seller = profiles[seller_id]
            
            # P8: Корректируем объём закупки, если у продавца меньше, чем нужно
            available_stock = seller.stock_for_sale.get(needed_good, 0.0)
            if available_stock < needed_amount:
                needed_amount = max(1.0, available_stock)
                
            price = self._calculate_price(needed_good, needed_amount, seller)
            if not profile.can_afford(price):
                continue
            tx = self.tx_engine.execute_sale(
                buyer=profile,
                seller=seller,
                goods={needed_good: needed_amount},
                price=price,
                reason=f"{npc_id} покупает {needed_good} у {seller_id} (потребность)",
                tick=0,
            )
            success = tx.status.value == "completed"
            results.append(
                TradeResult(
                    buyer_id=npc_id,
                    seller_id=seller_id,
                    goods={needed_good: needed_amount},
                    price=price,
                    success=success,
                    reason=tx.reason if not success else "",
                )
            )

        return results

    def _determine_needed_good(self, profile: EconomicProfile) -> Optional[str]:
        """Определяет какой товар NPC хочет купить на основе потребностей."""
        # Проверяем срочные потребности
        urgent_needs = profile.get_urgent_needs(threshold=0.6)

        for need in urgent_needs:
            if need.need_type == NeedType.FOOD:
                # Покупать только если запасы низкие (< 3 порции)
                if profile.goods.get("food", 0.0) < 3.0:
                    return "food"

        return None

    def _calculate_needed_amount(self, profile: EconomicProfile, good: str) -> float:
        """Сколько единиц товара купить."""
        # Покупаем до 3 единиц за раз (на день)
        current = profile.goods.get(good, 0.0)
        return min(3.0, max(1.0, 3.0 - current))

    def _find_seller(
        self,
        profiles: Dict[str, EconomicProfile],
        buyer_id: str,
        good: str,
        amount: float,
    ) -> Optional[str]:
        """Ищет продавца с нужным товаром."""
        best_seller: Optional[str] = None
        best_price = float("inf")

        for npc_id, profile in profiles.items():
            if npc_id == buyer_id:
                continue
            # Ищем только у тех, у кого есть товар НА ПРОДАЖУ
            if not profile.has_stock(good, 1.0): # P8: Хоть 1 единица
                continue

            # Выбираем самого дешёвого
            base_price = GOODS_PRICES.get(good, 0.1)
            price = base_price * amount
            if price < best_price:
                best_price = price
                best_seller = npc_id

        return best_seller

    def _find_seller(
        self,
        profiles: Dict[str, EconomicProfile],
        buyer_id: str,
        good: str,
        amount: float,
    ) -> Optional[str]:
        """Ищет продавца с нужным товаром."""
        best_seller: Optional[str] = None
        best_price = float("inf")

        for npc_id, profile in profiles.items():
            if npc_id == buyer_id:
                continue
            # Ищем только у тех, у кого есть товар НА ПРОДАЖУ
            if not profile.has_stock(good, amount):
                continue

            # Выбираем самого дешёвого
            base_price = GOODS_PRICES.get(good, 0.1)
            price = base_price * amount
            if price < best_price:
                best_price = price
                best_seller = npc_id

        return best_seller

    def _calculate_price(
        self,
        good: str,
        amount: float,
        seller: EconomicProfile,
    ) -> float:
        """Рассчитывает финальную цену с наценкой продавца."""
        base_price = GOODS_PRICES.get(good, 0.1)

        # Наценка продавца на основе wealth_level (богатые продают дороже)
        markup = 1.0 + seller.wealth_level * 0.3  # 0-30% наценка

        return round(base_price * amount * markup, 2)

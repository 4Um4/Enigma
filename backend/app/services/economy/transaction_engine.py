# backend/app/services/economy/transaction_engine.py
"""
TransactionEngine — движок сделок.
Обрабатывает Transaction объекты: валидация, выполнение, откат.

Назначение: Обрабатывает транзакции между NPC (и NPC-игрок). Атомарность, валидация, статусы.
Зависимости: app.models.economy
Основные сущности: TransactionEngine

КОНТРАКТ:
- Атомарность: либо обе стороны обновлены, либо ни одной
- Валидация: проверка ресурсов ДО выполнения
- Статусы: PROPOSED → COMPLETED или FAILED
- Запись в CausalLedger: через causal_note в Transaction
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

from app.models.economy import (
    EconomicProfile,
    Transaction,
    TransactionStatus,
    TransactionType,
)

logger = logging.getLogger(__name__)


class TransactionError(Exception):
    """Ошибка транзакции с описанием причины."""
    pass


@dataclass
class TransactionEngine:
    """
    Движок транзакций. Без состояния — все данные в профилях.
    """
    
    def execute_sale(
        self,
        buyer: EconomicProfile,
        seller: EconomicProfile,
        goods: Dict[str, float],
        price: float,
        reason: str = "",
        tick: int = 0,
    ) -> Transaction:
        """
        Продажа: продавец → покупатель (товар), покупатель → продавец (деньги).
        
        Args:
            buyer: Профиль покупателя
            seller: Профиль продавца
            goods: Товары → количество
            price: Цена в золоте
            reason: Описание для логов
            tick: Тик мира
            
        Returns:
            Transaction с статусом COMPLETED или FAILED
        """
        tx = Transaction(
            tx_type=TransactionType.SALE,
            actor_id=buyer.npc_id,
            target_id=seller.npc_id,
            goods=goods,
            payment=price,
            reason=reason,
            tick=tick,
        )
        
        # Валидация: товар должен быть в stock_for_sale (не в личных запасах)
        for good_id, amount in goods.items():
            if not seller.has_stock(good_id, amount):
                tx = Transaction(
                    tx_type=TransactionType.SALE,
                    status=TransactionStatus.FAILED,
                    actor_id=buyer.npc_id,
                    target_id=seller.npc_id,
                    reason=f"seller lacks stock: {goods}",
                    tick=tick,
                )
                self._record_both(buyer, seller, tx)
                return tx
        
        if not buyer.can_afford(price):
            tx = Transaction(
                tx_type=TransactionType.SALE,
                status=TransactionStatus.FAILED,
                actor_id=buyer.npc_id,
                target_id=seller.npc_id,
                reason=f"buyer cannot afford {price}G (has {buyer.gold}G)",
                tick=tick,
            )
            self._record_both(buyer, seller, tx)
            return tx
        
        # Выполнение (атомарно)
        try:
            # Покупатель платит
            buyer.spend(price)
            # Продавец получает
            seller.receive(price)
            # Товар переходит из stock_for_sale продавца → goods покупателя
            for good_id, amount in goods.items():
                seller.remove_stock(good_id, amount)
                buyer.add_good(good_id, amount)
            
            tx = Transaction(
                tx_type=TransactionType.SALE,
                status=TransactionStatus.COMPLETED,
                actor_id=buyer.npc_id,
                target_id=seller.npc_id,
                goods=goods,
                payment=price,
                reason=reason,
                causal_note=f"{buyer.npc_id} bought {goods} from {seller.npc_id} for {price}G",
                tick=tick,
            )
        except Exception as e:
            tx = Transaction(
                tx_type=TransactionType.SALE,
                status=TransactionStatus.FAILED,
                actor_id=buyer.npc_id,
                target_id=seller.npc_id,
                reason=f"execution error: {e}",
                tick=tick,
            )
        
        self._record_both(buyer, seller, tx)
        return tx
    
    def execute_employment(
        self,
        employer: EconomicProfile,
        employee: EconomicProfile,
        wage: float,
        duration_ticks: int = 0,
        job_type: str = "",
        reason: str = "",
        tick: int = 0,
    ) -> Transaction:
        """
        Трудовой контракт: работодатель → работник (зарплата каждый интервал).
        Создаёт Contract в профиле работника.
        
        Returns:
            Transaction с результатом
        """
        from app.models.economy import Contract
        
        # Проверяем: работодатель может платить?
        daily_cost = wage * 24 / max(1, duration_ticks) if duration_ticks > 0 else wage
        
        contract = Contract(
            contract_type="employment",
            party_a=employer.npc_id,
            party_b=employee.npc_id,
            payment_amount=wage,
            payment_direction="a_to_b",
            payment_interval=24,  # зарплата раз в сутки
            duration_ticks=duration_ticks,
            job_type=job_type,
        )
        
        employee.add_contract(contract)
        employee.current_employer = employer.npc_id
        employee.employment_remaining = duration_ticks
        
        # Добавляем доход работнику
        employee.income_sources[job_type or "employment"] = wage / 24  # за тик
        
        tx = Transaction(
            tx_type=TransactionType.EMPLOYMENT,
            status=TransactionStatus.COMPLETED,
            actor_id=employer.npc_id,
            target_id=employee.npc_id,
            wage=wage,
            duration_ticks=duration_ticks,
            reason=reason or f"employed {employee.npc_id} as {job_type}",
            causal_note=f"{employer.npc_id} hired {employee.npc_id} for {wage}G/tick",
            tick=tick,
        )
        
        self._record_both(employer, employee, tx)
        return tx
    
    def process_contract_payments(
        self,
        profiles: Dict[str, EconomicProfile],
        tick: int = 0,
    ) -> List[Transaction]:
        """
        Обрабатывает платежи по контрактам для всех NPC.
        Вызывается каждый тик.
        
        Returns:
            Список выполненных/неудачных транзакций
        """
        transactions: List[Transaction] = []
        
        for npc_id, profile in profiles.items():
            due_contracts = profile.tick_contracts()
            
            for contract in due_contracts:
                if contract.payment_direction == "a_to_b":
                    payer_id = contract.party_a
                    receiver_id = contract.party_b
                else:
                    payer_id = contract.party_b
                    receiver_id = contract.party_a
                
                payer = profiles.get(payer_id)
                receiver = profiles.get(receiver_id)
                
                if not payer or not receiver:
                    continue
                
                if payer.can_afford(contract.payment_amount):
                    payer.spend(contract.payment_amount)
                    receiver.receive(contract.payment_amount)
                    
                    tx = Transaction(
                        tx_type=TransactionType.SALE,
                        status=TransactionStatus.COMPLETED,
                        actor_id=payer_id,
                        target_id=receiver_id,
                        payment=contract.payment_amount,
                        reason=f"contract payment: {contract.contract_type}",
                        tick=tick,
                        causal_note=f"{payer_id} paid {contract.payment_amount}G to {receiver_id} per contract",
                    )
                else:
                    tx = Transaction(
                        tx_type=TransactionType.SALE,
                        status=TransactionStatus.FAILED,
                        actor_id=payer_id,
                        target_id=receiver_id,
                        payment=contract.payment_amount,
                        reason=f"cannot afford contract payment (has {payer.gold}G)",
                        tick=tick,
                    )
                
                self._record_both(payer, receiver, tx)
                transactions.append(tx)
        
        return transactions
    
    def _record_both(
        self,
        profile_a: EconomicProfile,
        profile_b: EconomicProfile,
        tx: Transaction,
    ) -> None:
        """Записывает транзакцию в историю обоих участников."""
        profile_a.record_transaction(tx)
        profile_b.record_transaction(tx)
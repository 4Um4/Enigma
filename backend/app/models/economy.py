from __future__ import annotations
# backend/app/models/economy.py
"""
Экономические структуры NPC.
Потребности → кандидаты действий → транзакции.

Назначение: Базовые структуры экономической системы. Потребности, транзакции, профиль NPC.
Зависимости: typing, dataclasses, enum
Основные сущности: Need, Transaction, EconomicProfile, ResourceType

КОНТРАКТ:
- Need — что NPC хочет/нуждается (еда, деньги, безопасность)
- Transaction — завершённая сделка между двумя сторонами
- EconomicProfile — экономическое состояние NPC (ресурсы + потребности)
"""


from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.constants import GOODS_PRICES as GOODS_BASE_PRICES


class NeedType(Enum):
    """Типы потребностей NPC."""

    FOOD = "food"  # еда/вода (быстрый decay: 0.02)
    SHELTER = "shelter"  # жильё/безопасность (медленный: 0.005)
    INCOME = "income"  # деньги (покупки, налоги) (средний: 0.01)
    SOCIAL = "social"  # общение/статус (медленный: 0.005)
    SECURITY = "security"  # защита от угроз (медленный: 0.005)
    CLEANLINESS = "cleanliness"  # порядок/чистота (средний: 0.01)
    TOOLS = "tools"  # инструменты для работы (медленный: 0.005)
    INFORMATION = "information"  # слухи/знания (очень медленный: 0.003)


# Дефолтные скорости decay по типу потребности
# Еда растёт быстро, жильё и общение — медленно
NEED_DECAY_RATES: Dict[NeedType, float] = {
    NeedType.FOOD: 0.08,  # ADR-S96.3: Унификация с LifeEngine._NEED_DECAY_PER_TICK
    NeedType.SHELTER: 0.005,
    NeedType.INCOME: 0.01,
    NeedType.SOCIAL: 0.005,
    NeedType.SECURITY: 0.005,
    NeedType.CLEANLINESS: 0.01,
    NeedType.TOOLS: 0.005,
    NeedType.INFORMATION: 0.003,
}

# Цены и зарплаты — единый источник правды в app.core.constants
# Здесь алиас GOODS_BASE_PRICES для совместимости с существующим кодом


class TransactionType(Enum):
    """Типы транзакций."""

    SALE = "sale"  # продажа товара
    PURCHASE = "purchase"  # покупка товара
    EMPLOYMENT = "employment"  # найм на работу
    BARTER = "barter"  # обмен без денег
    BRIBE = "bribe"  # взятка
    RENT = "rent"  # аренда
    GIFT = "gift"  # дар (односторонний)


class TransactionStatus(Enum):
    """Статус транзакции."""

    PROPOSED = "proposed"  # предложена
    ACCEPTED = "accepted"  # согласована
    COMPLETED = "completed"  # завершена
    REJECTED = "rejected"  # отклонена
    FAILED = "failed"  # не удалась (нет ресурсов)


@dataclass(frozen=True)
class Obligation:
    """
    Временное обязательство NPC (критично для давления времени).
    Если due_in <= 0 и не выполнено → стресс + штрафы.

    Примеры:
    - Аренда: 0.5G каждые 24 тика
    - Долг: 10G через 72 тика
    - Налог: 2G через 48 тиков
    """

    obligation_type: str  # "rent", "debt", "tax", "wage_payment"
    amount: float  # Сумма к уплате
    due_in_ticks: int  # Тиков до дедлайна (уменьшается каждый тик)
    penalty_per_tick: float = 0.01  # Штраф к стрессу за просрочку (каждый тик)
    creditor_id: Optional[str] = None  # Кому должен (NPC ID или "city")

    @property
    def is_overdue(self) -> bool:
        """Обязательство просрочено."""
        return self.due_in_ticks <= 0

    @property
    def urgency(self) -> float:
        """Срочность обязательства ∈ [0..1]. Растёт по мере приближения дедлайна."""
        if self.due_in_ticks <= 0:
            return 1.0  # просрочено = максимальная срочность
        # Линейный рост от 0.3 (далеко) до 1.0 (на грани)
        threshold = 48  # начинаем волноваться за 48 тиков (2 дня)
        if self.due_in_ticks > threshold:
            return 0.3
        return 0.3 + 0.7 * (1.0 - self.due_in_ticks / threshold)


@dataclass
class Contract:
    """
    Контракт между NPC (или NPC и игроком).
    Lightweight память об обязательствах.

    Примеры:
    - Трудовой контракт: NPC работает за зарплату
    - Аренда: NPC платит за жильё
    - Долговое обязательство: NPC должен вернуть деньги
    """

    contract_type: str  # "employment", "rent", "debt"
    party_a: str  # Инициатор (NPC ID)
    party_b: str  # Вторая сторона (NPC ID или "player")

    # Условия
    payment_amount: float = 0.0  # Сумма платежа (от A к B, или наоборот)
    payment_direction: str = "a_to_b"  # "a_to_b" или "b_to_a"
    payment_interval: int = 24  # Тиков между платежами

    # Сроки
    duration_ticks: int = 0  # Общая длительность (0 = бессрочно)
    ticks_elapsed: int = 0  # Прошло тиков

    # Связанные данные
    job_type: Optional[str] = None  # Тип работы (для employment)
    obligation_ids: List[str] = field(default_factory=list)  # ID связанных обязательств

    @property
    def is_expired(self) -> bool:
        """Контракт истёк."""
        return self.duration_ticks > 0 and self.ticks_elapsed >= self.duration_ticks

    @property
    def ticks_remaining(self) -> int:
        """Тиков до истечения."""
        if self.duration_ticks <= 0:
            return -1  # бессрочный
        return max(0, self.duration_ticks - self.ticks_elapsed)

    @property
    def next_payment_in(self) -> int:
        """Тиков до следующего платежа."""
        if self.payment_interval <= 0:
            return -1
        remainder = self.ticks_elapsed % self.payment_interval
        # Если ticks_elapsed кратно interval И уже прошёл хотя бы 1 тик — пора платить
        if remainder == 0 and self.ticks_elapsed > 0:
            return 0
        return self.payment_interval - remainder

    @property
    def is_payment_due(self) -> bool:
        """Пора платить."""
        return self.next_payment_in == 0

    def tick(self) -> None:
        """Увеличивает счётчик тиков."""
        self.ticks_elapsed += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "party_a": self.party_a,
            "party_b": self.party_b,
            "payment_amount": self.payment_amount,
            "payment_direction": self.payment_direction,
            "payment_interval": self.payment_interval,
            "duration_ticks": self.duration_ticks,
            "ticks_elapsed": self.ticks_elapsed,
            "job_type": self.job_type,
            "obligation_ids": self.obligation_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contract":
        return cls(
            contract_type=data.get("contract_type", "unknown"),
            party_a=data.get("party_a", ""),
            party_b=data.get("party_b", ""),
            payment_amount=float(data.get("payment_amount", 0.0)),
            payment_direction=data.get("payment_direction", "a_to_b"),
            payment_interval=int(data.get("payment_interval", 24)),
            duration_ticks=int(data.get("duration_ticks", 0)),
            ticks_elapsed=int(data.get("ticks_elapsed", 0)),
            job_type=data.get("job_type"),
            obligation_ids=data.get("obligation_ids", []),
        )


@dataclass(frozen=True)
class Need:
    """
    Потребность NPC.
    Frozen — создаётся заново при каждом рассчёте, не мутируется.

    decay_rate задаётся индивидуально, по умолчанию из NEED_DECAY_RATES.
    Еда (0.02): голод через ~30 часов, критично через ~42 часа
    Жильё (0.005): медленный рост, не критично каждый день
    """

    need_type: NeedType
    base_urgency: float  # Базовая важность ∈ [0..1]
    budget_share: float  # Доля дохода на эту потребность ∈ [0..1]
    skill_required: Optional[str] = None  # Навык для самостоятельного удовлетворения
    neglected_ticks: int = 0  # Тиков с последнего удовлетворения
    decay_rate: float = 0.0  # Скорость роста срочности (0 = использовать дефолт)

    @property
    def effective_decay_rate(self) -> float:
        """Возвращает decay_rate: индивидуальный или дефолтный для типа."""
        return (
            self.decay_rate
            if self.decay_rate > 0
            else NEED_DECAY_RATES.get(self.need_type, 0.01)
        )

    @property
    def effective_urgency(self) -> float:
        """
        Эффективная срочность с учётом neglect.
        Формула: min(base_urgency + neglected_ticks * decay_rate, 0.95)
        Cap на 0.95 — даже при полном neglect NPC не сходит с ума мгновенно.
        """
        urgency = self.base_urgency + self.neglected_ticks * self.effective_decay_rate
        return min(urgency, 0.95)

    @property
    def is_urgent(self) -> bool:
        """Потребность требует внимания (urgency >= 0.6)."""
        return self.effective_urgency >= 0.6

    @property
    def is_critical(self) -> bool:
        """Критическая потребность (urgency > 0.85)."""
        return self.effective_urgency > 0.85


@dataclass
class Transaction:
    """
    Запись о транзакции между двумя сторонами.
    Создаётся при завершении сделки, хранится в истории.
    """

    tx_type: TransactionType
    status: TransactionStatus = TransactionStatus.PROPOSED

    # Стороны
    actor_id: str = ""  # Инициатор
    target_id: str = ""  # Вторая сторона

    # Содержимое
    goods: Dict[str, float] = field(default_factory=dict)  # Предмет → количество
    payment: float = 0.0  # Деньги (от actor к target, или наоборот при purchase)
    wage: float = 0.0  # Для employment: зарплата за тик
    duration_ticks: int = 0  # Для employment: длительность

    # Контекст
    reason: str = ""  # Почему сделка произошла
    need_satisfied: Optional[NeedType] = None  # Какую потребность закрывает

    # Метаданные
    tick: int = 0  # Тик мира когда произошла
    causal_note: str = ""  # Для CausalLedger

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_type": self.tx_type.value,
            "status": self.status.value,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "goods": self.goods,
            "payment": self.payment,
            "wage": self.wage,
            "duration_ticks": self.duration_ticks,
            "reason": self.reason,
            "need_satisfied": self.need_satisfied.value
            if self.need_satisfied
            else None,
            "tick": self.tick,
            "causal_note": self.causal_note,
        }


@dataclass
class EconomicProfile:
    """
    Экономическое состояние NPC.
    Мутируется в рантайме через TransactionEngine.
    """

    npc_id: str

    # ── РЕСУРСЫ ──
    gold: float = 0.0  # Деньги
    goods: Dict[str, float] = field(
        default_factory=dict
    )  # Личные запасы: {"food": 5, "ale": 20}
    stock_for_sale: Dict[str, float] = field(
        default_factory=dict
    )  # Товар на продажу: тавернщик продаёт из этого

    # ── ДОХОДЫ ──
    # Источник → сумма за тик (мирной жизни)
    income_sources: Dict[str, float] = field(default_factory=dict)
    # Пример: {"tavern_keeping": 15, "bribes": 3}

    # ── РАСХОДЫ ──
    # Категория → сумма за тик
    expense_categories: Dict[str, float] = field(default_factory=dict)
    # Пример: {"food": 2, "rent": 5, "supplies": 1}

    # ── ПОТРЕБНОСТИ (базовые, из archetype) ──
    base_needs: List[Need] = field(default_factory=list)

    # ── ИСТОРИЯ ТРАНЗАКЦИЙ ──
    transactions: List[Transaction] = field(default_factory=list)
    tx_history_cap: int = 20

    # ── ЗАНЯТОСТЬ (legacy, будет заменена Contract) ──
    current_employer: Optional[str] = None  # ID нанимателя
    employment_remaining: int = 0  # Тиков до конца контракта

    # ── ОБЯЗАТЕЛЬСТВА (временное давление) ──
    obligations: List[Obligation] = field(default_factory=list)

    # ── КОНТРАКТЫ (память об договорах) ──
    contracts: List[Contract] = field(default_factory=list)

    @property
    def net_income(self) -> float:
        """Чистый доход за тик (доходы - расходы)."""
        total_income = sum(self.income_sources.values())
        total_expense = sum(self.expense_categories.values())
        return total_income - total_expense

    @property
    def wealth_level(self) -> float:
        """
        Уровень богатства ∈ [0..1].
        Нормализован относительно "комфортного порога" (50 золотых).
        """
        comfort_threshold = 50.0
        return min(self.get_total_wealth() / comfort_threshold, 1.0)

    def get_total_wealth(self) -> float:
        """
        Общая стоимость: золото + оценочная стоимость предметов.
        Используется для расчёта wealth_level и кредитоспособности.
        """
        goods_value = sum(
            count * GOODS_BASE_PRICES.get(good_id, 0.1)
            for good_id, count in self.goods.items()
        )
        return self.gold + goods_value

    def can_afford(self, amount: float) -> bool:
        """Проверка: достаточно ли золота."""
        return self.gold >= amount

    def spend(self, amount: float) -> bool:
        """Тратит золото. Returns False если не хватает."""
        if not self.can_afford(amount):
            return False
        self.gold -= amount
        return True

    def receive(self, amount: float) -> None:
        """Получает золото."""
        self.gold += amount

    def add_good(self, good_id: str, amount: float) -> None:
        """Добавляет предмет в инвентарь."""
        self.goods[good_id] = self.goods.get(good_id, 0.0) + amount

    def remove_good(self, good_id: str, amount: float) -> bool:
        """Убирает предмет. Returns False если не хватает."""
        current = self.goods.get(good_id, 0.0)
        if current < amount:
            return False
        self.goods[good_id] = current - amount
        if self.goods[good_id] <= 0:
            del self.goods[good_id]
        return True

    def has_good(self, good_id: str, amount: float = 1.0) -> bool:
        """Проверяет наличие предмета в личных запасах."""
        return self.goods.get(good_id, 0.0) >= amount

    def has_stock(self, good_id: str, amount: float = 1.0) -> bool:
        """Проверяет наличие товара на продажу."""
        return self.stock_for_sale.get(good_id, 0.0) >= amount

    def remove_stock(self, good_id: str, amount: float) -> bool:
        """Убирает товар из stock_for_sale. Returns False если не хватает."""
        current = self.stock_for_sale.get(good_id, 0.0)
        if current < amount:
            return False
        self.stock_for_sale[good_id] = current - amount
        if self.stock_for_sale[good_id] <= 0:
            del self.stock_for_sale[good_id]
        return True

    def can_afford_goods(self, goods: Dict[str, float]) -> bool:
        """Проверяет наличие всех товаров в нужном количестве."""
        for good_id, amount in goods.items():
            if not self.has_good(good_id, amount):
                return False
        return True

    def calculate_selling_price(
        self,
        good_id: str,
        buyer_trust: float = 0.0,
        urgency_modifier: float = 0.0,
        global_inflation: float = 1.0,
        local_modifier: float = 1.0,
    ) -> float:
        """
        Рассчитывает цену продажи для конкретного покупателя.

        Это НЕ TransactionEngine — это ЛОГИКА NPC (DecisionHub вызывает).

        Факторы:
        - base_price: рыночная цена из GOODS_BASE_PRICES (якорь)
        - global_inflation: мировая инфляция (Фаза 6: WorldTick обновляет)
        - local_modifier: локальный дефицит/изобилие (Фаза 3.1: LocationNode)
        - buyer_trust: доверие к покупателю (>0.7 = скидка, <0.3 = наценка)
        - urgency_modifier: срочная потребность в деньгах (>0.6 = скидка)

        ФОРМУЛА: final = base × inflation × local × trust × urgency

        Средневековая инфляция:
        - Нормальная: ~0.3% в год (global_inflation = 1.003 за 8760 тиков)
        - Кризис (неурожай/чума): 10-30% в год
        - Драйверы: урожай, война, приток золота, чеканка монет
        """
        base = GOODS_BASE_PRICES.get(good_id, 1.0)

        # Глобальная инфляция (Фаза 6: WorldTickEngine будет обновлять)
        # Сейчас всегда 1.0, архитектурно готов
        inflation_factor = global_inflation

        # Локальный модификатор (Фаза 3.1: LocationNode.market_modifier)
        # Пример: в осаждённом городе food × 2.0, в портовом iron_sword × 0.8
        # Сейчас всегда 1.0, архитектурно готов
        local_factor = local_modifier

        # Доверие: высокий = скидка, низкий = наценка
        trust_factor = 1.0
        if buyer_trust > 0.7:
            trust_factor = 0.9 - (buyer_trust - 0.7) * 0.3
        elif buyer_trust < 0.3:
            trust_factor = 1.0 + (0.3 - buyer_trust) * 0.5

        # Срочность: высокая = скидка (нужны деньги любой ценой)
        urgency_factor = 1.0
        if urgency_modifier > 0.6:
            urgency_factor = 1.0 - (urgency_modifier - 0.6) * 0.3

        final_price = (
            base * inflation_factor * local_factor * trust_factor * urgency_factor
        )
        return round(final_price, 2)

    def record_transaction(self, tx: Transaction) -> None:
        """Записывает транзакцию в историю (cap=20)."""
        self.transactions.append(tx)
        if len(self.transactions) > self.tx_history_cap:
            self.transactions = self.transactions[-self.tx_history_cap :]

    def get_urgent_needs(self, threshold: float = 0.6) -> List[Need]:
        """Возвращает список срочных потребностей."""
        return [n for n in self.base_needs if n.effective_urgency > threshold]

    def tick_needs(self) -> None:
        """Увеличивает neglect для всех потребностей (вызывается каждый мирный тик)."""
        self.base_needs = [
            Need(
                need_type=need.need_type,
                base_urgency=need.base_urgency,
                budget_share=need.budget_share,
                skill_required=need.skill_required,
                neglected_ticks=need.neglected_ticks + 1,
                decay_rate=need.decay_rate,
            )
            for need in self.base_needs
        ]

    def satisfy_need(self, need_type: NeedType) -> None:
        """Сбрасывает neglect для удовлетворённой потребности."""
        self.base_needs = [
            Need(
                need_type=need.need_type,
                base_urgency=need.base_urgency,
                budget_share=need.budget_share,
                skill_required=need.skill_required,
                neglected_ticks=0
                if need.need_type == need_type
                else need.neglected_ticks,
                decay_rate=need.decay_rate,
            )
            for need in self.base_needs
        ]

    # ── ОБЯЗАТЕЛЬСТВА ──

    def get_overdue_obligations(self) -> List[Obligation]:
        """Возвращает просроченные обязательства."""
        return [o for o in self.obligations if o.is_overdue]

    def get_urgent_obligations(self, threshold: float = 0.7) -> List[Obligation]:
        """Возвращает срочные обязательства (ближайшие к дедлайну)."""
        return [o for o in self.obligations if o.urgency > threshold]

    def tick_obligations(self) -> List[Obligation]:
        """
        Уменьшает due_in для всех обязательств.
        Returns: список только что просроченных.
        """
        just_overdue = []
        for obl in self.obligations:
            if not obl.is_overdue:
                # Создаём новый экземпляр с уменьшенным due_in
                idx = self.obligations.index(obl)
                new_obl = Obligation(
                    obligation_type=obl.obligation_type,
                    amount=obl.amount,
                    due_in_ticks=obl.due_in_ticks - 1,
                    penalty_per_tick=obl.penalty_per_tick,
                    creditor_id=obl.creditor_id,
                )
                self.obligations[idx] = new_obl
                if new_obl.is_overdue:
                    just_overdue.append(new_obl)
        return just_overdue

    def fulfill_obligation(self, obligation_type: str) -> bool:
        """
        Выполняет обязательство (списывает деньги).
        Returns False если не хватает денег.
        """
        for i, obl in enumerate(self.obligations):
            if obl.obligation_type == obligation_type and obl.is_overdue:
                if self.can_afford(obl.amount):
                    self.spend(obl.amount)
                    self.obligations.pop(i)
                    return True
        return False

    # ── КОНТРАКТЫ ──

    def add_contract(self, contract: Contract) -> None:
        """Добавляет контракт."""
        self.contracts.append(contract)

    def get_active_contracts(self) -> List[Contract]:
        """Возвращает активные (не истёкшие) контракты."""
        return [c for c in self.contracts if not c.is_expired]

    def tick_contracts(self) -> List[Contract]:
        """
        Обновляет все контракты.
        Returns: список контрактов с наступившим платёжом.
        """
        payment_due = []
        for contract in self.contracts:
            if not contract.is_expired:
                contract.tick()
                if contract.is_payment_due:
                    payment_due.append(contract)
        return payment_due

    def to_dict(self) -> Dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "gold": self.gold,
            "goods": self.goods,
            "income_sources": self.income_sources,
            "expense_categories": self.expense_categories,
            "base_needs": [
                {
                    "need_type": n.need_type.value,
                    "base_urgency": n.base_urgency,
                    "budget_share": n.budget_share,
                    "skill_required": n.skill_required,
                    "neglected_ticks": n.neglected_ticks,
                    "decay_rate": n.decay_rate,
                }
                for n in self.base_needs
            ],
            "current_employer": self.current_employer,
            "employment_remaining": self.employment_remaining,
            "obligations": [
                {
                    "obligation_type": o.obligation_type,
                    "amount": o.amount,
                    "due_in_ticks": o.due_in_ticks,
                    "penalty_per_tick": o.penalty_per_tick,
                    "creditor_id": o.creditor_id,
                }
                for o in self.obligations
            ],
            "contracts": [c.to_dict() for c in self.contracts],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EconomicProfile":
        needs_raw = data.get("base_needs", [])
        needs = [
            Need(
                need_type=NeedType(n["need_type"]),
                base_urgency=float(n.get("base_urgency", 0.3)),
                budget_share=float(n.get("budget_share", 0.1)),
                skill_required=n.get("skill_required"),
                neglected_ticks=int(n.get("neglected_ticks", 0)),
                decay_rate=float(n.get("decay_rate", 0.0)),
            )
            for n in needs_raw
        ]
        obligations_raw = data.get("obligations", [])
        obligations = [
            Obligation(
                obligation_type=o["obligation_type"],
                amount=float(o["amount"]),
                due_in_ticks=int(o["due_in_ticks"]),
                penalty_per_tick=float(o.get("penalty_per_tick", 0.01)),
                creditor_id=o.get("creditor_id"),
            )
            for o in obligations_raw
        ]
        contracts_raw = data.get("contracts", [])
        contracts = [Contract.from_dict(c) for c in contracts_raw]
        return cls(
            npc_id=data.get("npc_id", "unknown"),
            gold=float(data.get("gold", 0.0)),
            goods=data.get("goods", {}),
            income_sources=data.get("income_sources", {}),
            expense_categories=data.get("expense_categories", {}),
            base_needs=needs,
            current_employer=data.get("current_employer"),
            employment_remaining=int(data.get("employment_remaining", 0)),
            obligations=obligations,
            contracts=contracts,
        )

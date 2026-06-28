"""
backend/tests\sandbox\SUPERBOX/npc_sandbox.py
Автономная симуляция NPC — N тиков без pygame/LLM.

Запуск: cd backend ; python npc_sandbox.py           # 40 тиков (по умолчанию)
        cd backend ; python npc_sandbox.py full_test  # 1800 тиков

Симулирует:
- NeedEngine.tick() — рост потребностей
- DecisionHub.compute() — решения NPC
- StateApplicator — применение дельт
- apply_tick_recovery() — восстановление стресса
- EconomicModifier — влияние экономики на решения

Выводит:
- Консольную таблицу по тикам
- CSV для Excel
- Графики (matplotlib, если установлен)

Назначение: Симуляция NPC для отладки баланса
Зависимости: app.models.*, app.services.npc.*, app.services.economy.*, matplotlib (опционально)
Основные сущности: SandboxConfig, TickSnapshot, NPCSandbox, SandboxReporter
"""
from __future__ import annotations

import csv
import json
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
# ── Добавляем backend в path ──
# SUPERBOX — добавляем backend/ в path (на 2 уровня выше)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.services.npc.npc_loader import load_profile_from_legacy_json, load_l2_state_from_runtime_dict
from app.core.constants import GOODS_PRICES


@dataclass
class SandboxConfig:
    """Настройки симуляции."""
    campaign_id: str = "Open_road"
    location: str = "tavern_silver_wolf"
    tick_count: int = 168           # 1 неделя (24 часа × 7 дней)
    snapshot_interval: int = 24     # слепок каждый "день"
    actions_per_day: int = 24       # 1 тик = 1 час

    # Переопределения для конкретных NPC
    # {npc_id: {field: value}}
    npc_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Фильтр: только эти NPC (пусто = все по tier)
    only_npcs: List[str] = field(default_factory=list)

    # Какие tier включать (пусто = все)
    include_tiers: List[str] = field(default_factory=lambda: ["major", "minor"])

    # Запереть сцену (NPC не могут покинуть)
    locked: bool = True


@dataclass
class TickSnapshot:
    """Состояние NPC в один момент времени."""
    tick: int
    npc_id: str
    hp: int
    max_hp: int
    stress: float
    resentment: float
    identity_integrity: float
    intent: str
    intent_score: float
    emotion: str
    gold: float = 0.0
    # Дельты с прошлого слепка
    delta_stress: float = 0.0
    delta_gold: float = 0.0
    delta_hp: int = 0
    # Потребности
    max_urgency: float = 0.0
    active_drives: List[str] = field(default_factory=list)
    # Экономический модификатор
    eco_modifiers: Dict[str, float] = field(default_factory=dict)


class NPCSandbox:
    """
    Ядро симуляции. Не зависит от pygame/LLM.
    Работает чисто на Python — быстро, детерминированно.
    """

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self.snapshots: List[TickSnapshot] = []
        self._prev_states: Dict[str, Dict[str, float]] = {}
        # Трекеры для экономической симуляции (внешние, не в модели)
        self._daily_income: Dict[str, float] = {}       # NPC → накопленный доход за день
        self._last_talk_tick: Dict[str, int] = {}       # NPC → тик последнего разговора

    def run(self) -> List[TickSnapshot]:
        """Запускает симуляцию, возвращает список слепков."""
        # 1. Загружаем NPC из кампании
        npc_data = self._load_npcs()
        if not npc_data:
            print("[SANDBOX] Ошибка: NPC не найдены")
            return []

        _names = [n.get("id", "?") for n in npc_data] if npc_data else []
        print(f"[SANDBOX] Загружено {len(npc_data)} NPC: {_names}")
        print(f"[SANDBOX] Тиков: {self.config.tick_count}, локация: {self.config.location}")
        print()

        # 2. Применяем overrides
        for npc_id, overrides in self.config.npc_overrides.items():
            for npc_tuple in npc_data:
                if npc_tuple[0] == npc_id:
                    self._apply_overrides(npc_tuple[1], overrides)

        # 3. Создаём экономические профили (пустые, если нет в runtime)
        eco_profiles = self._create_eco_profiles(npc_data)

        # 4. Инициализируем движки
        from app.services.npc.decision_hub import DecisionHub, EventContext as HubEventContext
        from app.services.economy.need_engine import NeedEngine
        from app.services.economy.economic_modifier import EconomicModifier
        from app.services.npc.state_applicator import StateApplicator
        from app.services.npc.drive_resolver import DriveResolver
        from app.domain.identity_events import EffectiveDrives

        hub = DecisionHub()
        need_engine = NeedEngine()
        eco_mod = EconomicModifier()
        applicator = StateApplicator(relationship_store=None)
        drive_resolver = DriveResolver()

        from app.services.economy.transaction_engine import TransactionEngine
        from app.services.economy.trade_resolver import TradeResolver
        from app.services.economy.market_state import RandomMarketState
        from app.services.economy.traveller import TravellerGenerator
        tx_engine = TransactionEngine()
        trade_resolver = TradeResolver(tx_engine)
        market_state = RandomMarketState()
        traveller_gen = TravellerGenerator(market_state)

        # 4.5 Создаём начальные контракты (реальная экономика)
        self._setup_initial_contracts(eco_profiles, tx_engine)

        # 4.6 Предзагрузка state/profile — ONE TIME, не каждый тик
        # Без этого мутации (стресс, intent, черты) теряются между тиками
        npc_contexts: Dict[str, Dict[str, Any]] = {}
        for npc_raw in npc_data:
            npc_id = npc_raw.get("id", "unknown")
            state_l2 = load_l2_state_from_runtime_dict(npc_raw)
            profile_l0 = load_profile_from_legacy_json(npc_raw)
            if state_l2.hp <= 0:
                print(f"[SANDBOX] Пропуск {npc_id}: hp=0 (нет данных или мёртв)")
                continue
            npc_contexts[npc_id] = {
                "state": state_l2,
                "profile": profile_l0,
            }

        # 5. Цикл тиков
        for tick in range(1, self.config.tick_count + 1):
            print(f"[SANDBOX] === TICK {tick} ===")
            from app.models.npc_state import Intent, NPCState as NPCStateModel
            from app.services.events.event_types import EventType

            # Обработка контрактных платежей (деньги двигаются)
            from app.models.economy import NeedType
            contract_txs = tx_engine.process_contract_payments(eco_profiles, tick=tick)
            # Накапливаем доход для дневной проверки INCOME
            for tx in contract_txs:
                if tx.status.value == "completed":
                    receiver_id = tx.target_id
                    self._daily_income[receiver_id] = self._daily_income.get(receiver_id, 0.0) + tx.payment

            # Формируем событие world_tick
            tick_event = HubEventContext(
                event_type=EventType.WORLD_TICK,
                actor_id="sandbox",
                success=True,
                intensity=0.3,
                distance=0.0,
                witness_count=0,
                location=self.config.location,
                scene_flags=set(),
                scene_facts=[],
            )

            for npc_id, ctx in npc_contexts.items():
                state_l2 = ctx["state"]
                profile_l0 = ctx["profile"]

                # Сохраняем предыдущее состояние для дельт
                prev = {
                    "stress": state_l2.stress,
                    "gold": eco_profiles[npc_id].gold if npc_id in eco_profiles else 0.0,
                    "hp": state_l2.hp,
                }

                # === NEED ENGINE ===
                ep = eco_profiles.get(npc_id)
                drives = []
                if ep:
                    drives = need_engine.tick(ep)

                # === ECONOMIC MODIFIER ===
                eco_modifiers = {}
                active_drives = []
                if ep:
                    eco_result = eco_mod.calculate(ep, drives)
                    eco_modifiers = eco_result.modifiers
                    active_drives = eco_result.active_drives

                # === DECISION HUB ===
                try:
                    # ADR-O-304: DecisionHub требует L3 проекцию (effective_drives).
                    # В песочнице используем L0 + пустые убеждения (L2.5), так как нет L1Chronicle.
                    _effective_drives = drive_resolver.resolve_drives(profile_l0, None)
                    
                    result = hub.compute(
                        state=state_l2,
                        personality=profile_l0,
                        effective_drives=_effective_drives,
                        event=tick_event,
                        scene_state={},
                        social_modifiers=eco_modifiers if eco_modifiers else None,
                    )
                    intent_str = result.intent.value
                    intent_score = result.score
                    # Трекер: запоминаем когда NPC последний раз инициировал разговор
                    if intent_str == "talk":
                        self._last_talk_tick[npc_id] = tick

                    # Полное применение: стресс, эмоции, черты, нарратив
                    new_state = applicator.apply(
                        state=state_l2,
                        result=result,
                        campaign_id="sandbox",
                        current_tick=tick,
                    )
                except Exception as e:
                    print(f"[SANDBOX_ERROR] npc={npc_id} tick={tick} error={e}")
                    intent_str = "ERROR"
                    intent_score = 0.0
                    new_state = state_l2

                # === ЭКОНОМИЧЕСКИЙ И ПОТРЕБНОСТНЫЙ СТРЕСС ===
                # Единая функция — используется и в game_loop
                if ep:
                    from app.services.economy.stress_calculator import calculate_economic_stress
                    econ_stress, _reason = calculate_economic_stress(ep, need_engine)
                    if econ_stress > 0:
                        new_state.stress = min(100.0, new_state.stress + econ_stress)

                # === TICK RECOVERY ===
                # В реальной игре LifeEngine вызывает recovery после оценки угроз.
                # В мирном тике без стрессоров — восстановление не нужно каждый ход.
                # Вызываем только раз в "день" (каждые actions_per_day тиков).
                is_rest_tick = (tick % self.config.actions_per_day == 0)
                if is_rest_tick:
                    # Ночь = полный сон (15 ед.), не лёгкая передышка (5 ед.)
                    new_state = applicator.apply_tick_recovery(new_state, is_sleeping=True)
                    # Таверна = крыша над головой (SHELTER удовлетворяется nightly)
                    if self.config.locked:  # запертая сцена = есть укрытие
                        ep_satisfy = eco_profiles.get(npc_id)
                        if ep_satisfy:
                            ep_satisfy.satisfy_need(NeedType.SHELTER)

                # Сохраняем состояние для следующего тика
                ctx["state"] = new_state

                # Собираем TRADE интенты для TradeResolver
                if intent_str == "trade":
                    if not hasattr(self, '_trade_intents'):
                        self._trade_intents = {}
                    self._trade_intents[npc_id] = intent_score

                # === СНЕПОК ===
                if tick % self.config.snapshot_interval == 0:
                    max_urgency = 0.0
                    if ep:
                        for need in ep.base_needs:
                            if need.effective_urgency > max_urgency:
                                max_urgency = need.effective_urgency

                    snap = TickSnapshot(
                        tick=tick,
                        npc_id=npc_id,
                        hp=new_state.hp,
                        max_hp=new_state.max_hp,
                        stress=round(new_state.stress, 2),
                        resentment=round(new_state.resentment, 2),
                        identity_integrity=round(new_state.identity_integrity, 3),
                        intent=intent_str,
                        intent_score=round(intent_score, 3),
                        emotion=str(new_state.emotion) if new_state.emotion else "none",
                        gold=round(ep.gold, 2) if ep else 0.0,
                        delta_stress=round(new_state.stress - prev["stress"], 2),
                        delta_gold=round((ep.gold if ep else 0.0) - prev["gold"], 2),
                        delta_hp=new_state.hp - prev["hp"],
                        max_urgency=round(max_urgency, 2),
                        active_drives=active_drives,
                        eco_modifiers=eco_modifiers,
                    )
                    self.snapshots.append(snap)

            # === TRADE RESOLUTION ===
            trade_intents = getattr(self, '_trade_intents', {})
            # Всегда вызываем — второй проход покупает по потребностям даже без intent=trade
            trade_results = trade_resolver.resolve_tick(
                profiles=eco_profiles,
                trade_intents=trade_intents,
                location=self.config.location,
            )
            for tr in trade_results:
                if tr.success:
                    goods_str = "+".join(f"{k}×{v:.0f}" for k, v in tr.goods.items())
                    print(f"[TRADE] {tr.buyer_id} покупает {goods_str} у {tr.seller_id} за {tr.price}G")
                    # Накапливаем доход продавца для дневной проверки INCOME
                    self._daily_income[tr.seller_id] = self._daily_income.get(tr.seller_id, 0.0) + tr.price
                else:
                    if tick % 20 == 1:  # логируем ошибки реже
                        print(f"[TRADE] {tr.buyer_id} → {tr.seller_id}: {tr.reason}")
            self._trade_intents = {}

            # === TRAVELLER (внешний шок для экономики) ===
            # Странник ТОЛЬКО покупает — продаёт нельзя, нет цепочек использования
            # Когда появятся: iron→tools craft, lockpick→steal, silk→status — добавим продажи
            market_state.tick()
            visit = traveller_gen.maybe_generate(tick)
            if visit:
                print(f"[TRAVELLER] {visit}")
                for good_id, amount in visit.wants_to_buy.items():
                    for seller_id, seller_ep in eco_profiles.items():
                        if seller_ep.has_stock(good_id, amount):
                            cost = amount * GOODS_PRICES.get(good_id, 0.1)
                            if cost <= visit.gold_budget:
                                seller_ep.remove_stock(good_id, amount)
                                seller_ep.receive(cost)
                                self._daily_income[seller_id] = self._daily_income.get(seller_id, 0.0) + cost
                                visit.gold_budget -= cost
                                print(f"  [BUY] {amount:.0f}×{good_id} у {seller_id} за {cost:.2f}G")
                                break
                market_state.record_visit()

            # === PRODUCTION (восполнение stock_for_sale каждый "день") ===
            # Тавернщик варит похлёбку, кузнец кует — простая имитация
            is_day_start = (tick % self.config.actions_per_day == 1)
            if is_day_start:
                # Производство: кто что делает за день
                # Производство: один котёл похлёбки = 15-20 порций (историческая реальность)
                # Тавернщик варит на всех присутствующих, не по порциям
                PRODUCTION_RATES = {
                    "tavern_keeper_tornin": {"food": 20, "ale": 10},  # котёл похлёбки + бочка эля
                    "blacksmith_orm": {"tools": 1},                    # кует инструменты
                    "merchant_goran": {},                              # торговец не производит, перепродаёт
                }
                for producer_id, products in PRODUCTION_RATES.items():
                    ep = eco_profiles.get(producer_id)
                    if not ep:
                        continue
                    for good_id, amount in products.items():
                        ep.stock_for_sale[good_id] = ep.stock_for_sale.get(good_id, 0.0) + amount

            # === DAILY CHECK: INCOME и SOCIAL (раз в 24 тика) ===
            is_day_end = (tick % self.config.actions_per_day == 0)
            if is_day_end:
                DAILY_EXPENSES_MIN = 0.09  # минимум на еду (3 порции × 0.03G)
                
                for npc_id, ep in eco_profiles.items():
                    if not ep:
                        continue
                    psycho = getattr(ep, '_psycho', None)
                    
                    # --- INCOME: runway × savings_tendency + flow × (1 - tendency) ---
                    runway = ep.gold / DAILY_EXPENSES_MIN if DAILY_EXPENSES_MIN > 0 else float('inf')
                    runway_factor = min(1.0, runway / 30.0)  # 1.0 если runway > 30 дней
                    flow_factor = 1.0 if self._daily_income.get(npc_id, 0.0) > 0 else 0.0
                    
                    if psycho:
                        savings = psycho.get_savings_tendency()
                        income_satisfaction = runway_factor * savings + flow_factor * (1.0 - savings)
                    else:
                        # Fallback: равный вес buffer и flow
                        income_satisfaction = (runway_factor + flow_factor) / 2.0
                    
                    if income_satisfaction > 0.5:
                        ep.satisfy_need(NeedType.INCOME)
                    
                    # --- SOCIAL: talk кулдаун 24 тика, пассивный в таверне 48 тиков ---
                    last_talk = self._last_talk_tick.get(npc_id, -999)
                    ticks_since_talk = tick - last_talk
                    
                    if ticks_since_talk < 24:
                        # Недавно говорил — satisfied
                        ep.satisfy_need(NeedType.SOCIAL)
                    elif self.config.locked and ticks_since_talk >= 48:
                        # В запертой локации (таверна) — пассивная социализация раз в 2 дня
                        ep.satisfy_need(NeedType.SOCIAL)
                    
                # Сброс дневных аккумуляторов
                self._daily_income.clear()

            # === CONSUMPTION (еда — базовый инстинкт, не психологическое решение) ===
            # Психология влияет на decay_rate (как быстро голодает), не на акт еды
            for npc_id, ep in eco_profiles.items():
                if not ep:
                    continue
                
                # Ищем еду в личных запасах ИЛИ в stock_for_sale (тавернщик ест своё)
                food = ep.goods.get("food", 0.0)
                food_source = "goods"
                if food < 1.0 and ep.stock_for_sale.get("food", 0.0) >= 1.0:
                    food = ep.stock_for_sale.get("food", 0.0)
                    food_source = "stock"
                if food < 1.0:
                    continue  # нечего есть
                
                # Найти потребность FOOD
                food_need = None
                for need in ep.base_needs:
                    if need.need_type.value == "food":
                        food_need = need
                        break
                if not food_need:
                    continue
                
                # Есть если голоден (urgency >= 0.4 — базовый порог голода)
                if food_need.effective_urgency >= 0.4:
                    if food_source == "stock":
                        ep.remove_stock("food", amount=1.0)
                    else:
                        ep.remove_good("food", amount=1.0)
                    ep.satisfy_need(food_need.need_type)
                    remaining = ep.goods.get("food", 0.0) + ep.stock_for_sale.get("food", 0.0)
                    print(f"[EAT] {npc_id}: поел из {food_source} (urgency={food_need.effective_urgency:.2f} food_left={remaining:.0f})")

            self._prev_states.clear()

        return self.snapshots

    def _load_npcs(self) -> list:
        """Загружает NPC через load_npcs_merged: static из config/npc/ + runtime overlay."""
        from app.services.npc.npc_loader import load_npcs_merged, load_profile_from_legacy_json, load_l2_state_from_runtime_dict

        # Скрипт в backend/, файлы в корне проекта
        _project_root = Path(__file__).parent.parent

        runtime_path = _project_root / "saves" / self.config.campaign_id / "npc_runtime.json"
        if not runtime_path.exists():
            # Fallback: data/campaigns (дефолтный _saves_dir в game_loop)
            runtime_path = _project_root / "data" / "campaigns" / self.config.campaign_id / "npc_runtime.json"

        try:
            # ADR-S96.4: Self-seeding sandbox. Если runtime_path не существует,
            # load_npcs_merged загрузит чистый static из config/npc/individuals/.
            if runtime_path.exists():
                raw_npcs = load_npcs_merged(runtime_path=runtime_path)
                print(f"[SANDBOX] Загружен runtime: {runtime_path}")
            else:
                print(f"[SANDBOX] npc_runtime.json не найден. Self-seeding из static config...")
                raw_npcs = load_npcs_merged() # Без аргументов = чистый static
        except Exception as e:
            print(f"[SANDBOX] load_npcs_merged ошибка: {e}")
            return []
        result = []
        for raw in raw_npcs:
            npc_id = raw.get("id") or raw.get("npc_id")
            if not npc_id:
                continue
            tier = raw.get("tier", "minor")
            if self.config.include_tiers and tier not in self.config.include_tiers:
                continue
            if self.config.only_npcs and npc_id not in self.config.only_npcs:
                continue
            result.append(raw)

        return result

    def _create_eco_profiles(self, npc_data: list) -> Dict[str, 'EconomicProfile']:
        """Создаёт экономические профили через единую фабрику."""
        from app.services.economy.profile_factory import create_profile_from_npc
        from app.services.economy.psycho_economy import PsychoEconomy, PsychoProfile
        from app.models.economy import NeedType

        # Личные запасы — то, что NPC ест/использует сам
        ROLE_GOODS = {
            "Хозяин таверны": {"food": 5},
            "Служанка таверны": {"food": 1},
            "Торговец тканями": {"food": 3},
            "Кузнец": {"food": 3},
            "Стражник городских ворот": {"food": 2},
            "Вор": {"food": 1},
        }
        # Товар на продажу — только торговцы и ремесленники
        ROLE_STOCK = {
            "Хозяин таверны": {"food": 20, "ale": 30, "room_rent": 5},
            "Служанка таверны": {},
            "Торговец тканями": {"cloth": 50, "silk": 10},
            "Кузнец": {"iron": 30, "tools": 5},
            "Стражник городских ворот": {},
            "Вор": {},
        }
        # Расходы пересчитаны под реальные цены (food=0.03G, 3×/день = 0.09G)
        ROLE_EXPENSES = {
            "Хозяин таверны": {"supplies": 0.15, "maintenance": 0.1},  # закупка зерна, ремонт
            "Служанка таверны": {"food": 0.1},                         # еда (кров+еда от хозяина)
            "Торговец тканями": {"food": 0.1, "rent_stall": 0.3},     # еда + аренда лотка
            "Кузнец": {"coal": 0.2, "food": 0.1},                     # уголь + еда
            "Стражник городских ворот": {"food": 0.1, "equipment": 0.05},  # еда + ремонт снаряжения
            "Вор": {"food": 0.1},                                      # еда
        }

        profiles = {}
        print("[PSYCHO] Индивидуальные параметры:")
        
        for npc_raw in npc_data:
            npc_id = npc_raw.get("id", "unknown")
            title = npc_raw.get("status_profile", {}).get("title", "")

            # Психологический профиль из JSON drives
            drives_raw = npc_raw.get("drives", {})
            psycho = PsychoEconomy(PsychoProfile(
                control=float(drives_raw.get("control", 0.25)),
                significance=float(drives_raw.get("significance", 0.25)),
                fear=float(drives_raw.get("fear", 0.25)),
                desire=float(drives_raw.get("desire", 0.25)),
            ))

            # Фабрика создаёт профиль с едиными потребностями
            goods = dict(ROLE_GOODS.get(title, ROLE_GOODS["Вор"]))
            ep = create_profile_from_npc(
                npc_data=npc_raw,
                goods=goods,
                psycho=psycho,
            )
            ep.expense_categories = dict(ROLE_EXPENSES.get(title, ROLE_EXPENSES["Вор"]))
            # Товар на продажу — только для торговцев/ремесленников
            ep.stock_for_sale = dict(ROLE_STOCK.get(title, ROLE_STOCK["Вор"]))
            
            # Сохраняем PsychoEconomy для использования в trade/consumption
            ep._psycho = psycho
            profiles[npc_id] = ep

        # Выводим после создания
        for pid, p in profiles.items():
            psy = getattr(p, '_psycho', None)
            if psy:
                mods = psy._calculate_all_modifiers()
                print(f"  {pid}: еда×{mods.get(NeedType.FOOD, 1):.2f} "
                      f"доход×{mods.get(NeedType.INCOME, 1):.2f} "
                      f"ест каждые {psy.get_consumption_frequency()} тиков "
                      f"копит={psy.get_savings_tendency():.0%} "
                      f"риск={psy.get_risk_tolerance():.0%}")
        return profiles

    def _setup_initial_contracts(
        self,
        profiles: Dict[str, 'EconomicProfile'],
        tx_engine: 'TransactionEngine',
    ) -> None:
        """Создаёт начальные трудовые контракты для симуляции."""
        # Интервал — как часто платят (не каждый день!)
        # Контракты: (работодатель, работник, сумма_выплаты, интервал_в_днях)
        apd = self.config.actions_per_day  # действий в день

        EMPLOYMENT_CONTRACTS = [
            # Служанка: кров+еда от хозяина, мелкие деньги — 0.3G/день
            ("tavern_keeper_tornin", "maid_lusya", 0.3, 0),
            # Стражник: наёмник, еда включена — 0.7G/день
            ("merchant_goran", "guard_borko", 0.7, 0),
        ]

        for employer_id, employee_id, daily_wage, duration in EMPLOYMENT_CONTRACTS:
            employer = profiles.get(employer_id)
            employee = profiles.get(employee_id)
            if not employer or not employee:
                print(f"[SANDBOX] Пропуск контракта: {employer_id}→{employee_id} (нет профиля)")
                continue

            tx = tx_engine.execute_employment(
                employer=employer,
                employee=employee,
                wage=daily_wage,
                duration_ticks=duration,
                job_type="employment",
                reason=f"initial contract: {employer_id} hires {employee_id}",
                tick=0,
            )
            if tx.status.value == "completed":
                print(f"[SANDBOX] Контракт: {employer_id} → {employee_id} ({daily_wage}G/день)")
            else:
                print(f"[SANDBOX] Контракт провален: {tx.reason}")

    def _apply_overrides(self, state: Any, overrides: Dict[str, Any]) -> None:
        """Применяет переопределения к NPCState."""
        for key, value in overrides.items():
            if hasattr(state, key):
                setattr(state, key, value)


class SandboxReporter:
    """Вывод результатов симуляции."""

    # Маппинг для отображения — enum значения не трогаем, только вывод
    INTENT_LABELS: Dict[str, str] = {
        "spread_rumor": "распространить слух",
        "offer_job": "предложить работу",
        "change_role": "сменить роль",
        "seek_ally": "найти союзника",
        "call_for_help": "позвать на помощь",
        "request_service": "запросить услугу",
        "block_path": "преградить путь",
        "ambush": "устроить засаду",
        "talk": "разговор",
        "trade": "торговля",
        "observe": "наблюдение",
        "idle": "бездействие",
        "attack": "атака",
        "flee": "бегство",
        "warn": "предупреждение",
        "intimidate": "запугивание",
        "help": "помощь",
    }
    DRIVE_LABELS: Dict[str, str] = {
        "hunger": "голод",
        "income_urge": "нужда в доходе",
        "social_urge": "нужда в общении",
        "shelter_urge": "нужда в жилье",
    }

    def __init__(self, snapshots: List[TickSnapshot]) -> None:
        self.snaps = snapshots
        self.npc_ids = sorted(set(s.npc_id for s in snapshots))
        self.ticks = sorted(set(s.tick for s in snapshots))

    def _fmt_intent(self, intent: str) -> str:
        """Переводит intent для отображения."""
        return self.INTENT_LABELS.get(intent, intent)

    def _fmt_drives(self, drives: List[str]) -> str:
        """Переводит список драйвов для отображения."""
        if not drives:
            return "-"
        import re
        result = []
        for d in drives[:2]:
            # Формат: "hunger(0.60)" → извлекаем ключ и значение
            match = re.match(r'^(\w+)\(([\d.]+)\)$', d)
            if match:
                key, val = match.groups()
                label = self.DRIVE_LABELS.get(key, key)
                result.append(f"{label}({val})")
            else:
                result.append(self.DRIVE_LABELS.get(d, d))
        return ", ".join(result)

    def print_table(self) -> None:
        """Консольная таблица: каждый тик — строка на NPC."""
        if not self.snaps:
            print("[REPORTER] Нет данных")
            return

        print(f"{'ТИК':>5} | {'NPC':<25} | {'СТРЕСС':>7} | {'НАМЕРЕНИЕ':<22} | {'ОЦЕНКА':>6} | {'ЗОЛОТО':>8} | {'ПОБУЖДЕНИЯ':<30}")
        print("-" * 120)

        for tick in self.ticks:
            for npc_id in self.npc_ids:
                snap = next((s for s in self.snaps if s.tick == tick and s.npc_id == npc_id), None)
                if snap:
                    print(
                        f"{tick:>5} | {npc_id:<25} | {snap.stress:>7.2f} | {self._fmt_intent(snap.intent):<22} | {snap.intent_score:>6.3f} | {snap.gold:>8.1f} | {self._fmt_drives(snap.active_drives):<30}"
                    )
            print()

    def print_summary(self) -> None:
        """Итоговая таблица: кто выиграл/проиграл за всю симуляцию."""
        print("\n=== ИТОГИ СИМУЛЯЦИИ ===")
        print(f"{'NPC':<25} | {'Δ СТРЕСС':>9} | {'Δ ЗОЛОТО':>8} | {'Δ ОЗ':>6} | {'ИТОГ. СТРЕСС':>12} | {'ИТОГ. ЗОЛОТО':>11} | {'ВЕРДИКТ':<15}")
        print("-" * 105)

        for npc_id in self.npc_ids:
            first = next((s for s in self.snaps if s.npc_id == npc_id and s.tick == 1), None)
            last = next((s for s in self.snaps if s.npc_id == npc_id and s.tick == max(self.ticks)), None)
            if not first or not last:
                continue

            delta_stress = round(last.stress - first.stress, 2)
            delta_gold = round(last.gold - first.gold, 2)
            delta_hp = last.hp - first.hp

            # Вердикт (учитывает абсолютное богатство, не только дельту)
            if delta_stress < -5 and delta_gold > 0:
                verdict = "Процветает"
            elif delta_stress > 10:
                verdict = "На грани слома"
            elif last.gold < 5.0:
                verdict = "Нищий"
            elif delta_gold < -5 and last.gold < first.gold * 0.3:
                verdict = "Разорён"
            elif delta_gold > 5:
                verdict = "Прибыль"
            else:
                verdict = "Стабилен"

            print(
                f"{npc_id:<25} | {delta_stress:>+9.2f} | {delta_gold:>+8.2f} | {delta_hp:>+6d} | {last.stress:>10.2f} | {last.gold:>9.1f} | {verdict:<15}"
            )

    def save_csv(self, path: str = "sandbox_results.csv") -> None:
        """Сохраняет все слепки в CSV."""
        if not self.snaps:
            return
        fieldnames = [
            "tick", "npc_id", "hp", "max_hp", "stress", "resentment",
            "identity_integrity", "intent", "intent_score", "emotion",
            "gold", "delta_stress", "delta_gold", "delta_hp",
            "max_urgency", "active_drives",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for snap in self.snaps:
                row = {k: getattr(snap, k) for k in fieldnames}
                row["active_drives"] = "; ".join(snap.active_drives)
                writer.writerow(row)
        print(f"\n[REPORTER] CSV сохранён: {path}")

    def plot_charts(self, path_prefix: str = "sandbox_chart") -> None:
        """Рисует графики через matplotlib (опционально)."""
        try:
            import matplotlib
            matplotlib.use("Agg")  # без GUI
            import matplotlib.pyplot as plt
        except ImportError:
            print("[REPORTER] matplotlib не установлен — графики пропущены")
            print("  Установка: pip install matplotlib")
            return

        if not self.snaps:
            return

        # 1. Стресс по тикам
        fig, ax = plt.subplots(figsize=(12, 5))
        for npc_id in self.npc_ids:
            ticks = [s.tick for s in self.snaps if s.npc_id == npc_id]
            stresses = [s.stress for s in self.snaps if s.npc_id == npc_id]
            ax.plot(ticks, stresses, label=npc_id, marker="o", markersize=3)
        ax.set_xlabel("Тик")
        ax.set_ylabel("Стресс")
        ax.set_title("Стресс NPC по тикам")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_stress.png", dpi=150)
        plt.close(fig)

        # 2. Золото по тикам
        fig, ax = plt.subplots(figsize=(12, 5))
        for npc_id in self.npc_ids:
            ticks = [s.tick for s in self.snaps if s.npc_id == npc_id]
            golds = [s.gold for s in self.snaps if s.npc_id == npc_id]
            ax.plot(ticks, golds, label=npc_id, marker="s", markersize=3)
        ax.set_xlabel("Тик")
        ax.set_ylabel("Золото")
        ax.set_title("Деньги NPC по тикам")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_gold.png", dpi=150)
        plt.close(fig)

        # 3. Intent distribution (stacked bar)
        intent_set = set(s.intent for s in self.snaps)
        intent_ticks = {intent: {npc: 0 for npc in self.npc_ids} for intent in intent_set}
        for snap in self.snaps:
            intent_ticks[snap.intent][snap.npc_id] += 1

        fig, ax = plt.subplots(figsize=(12, 5))
        bottom = {npc: 0 for npc in self.npc_ids}
        for intent in sorted(intent_set):
            values = [intent_ticks[intent][npc] for npc in self.npc_ids]
            ax.bar(self.npc_ids, values, bottom=list(bottom.values()), label=intent, alpha=0.8)
            bottom = {npc: bottom[npc] + intent_ticks[intent][npc] for npc in self.npc_ids}
        ax.set_ylabel("Тики")
        ax.set_title("Распределение намерений по NPC")
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_intents.png", dpi=150)
        plt.close(fig)

        print(f"[REPORTER] Графики сохранены: {path_prefix}_*.png")


def main() -> None:
    """Точка входа для запуска sandbox."""
    # QUICK_DEBUG = 40 тиков (2 дня) — для отладки баланса
    # FULL_TEST = 1800 тиков (3 месяца) — для полноценного теста
    TICK_PRESETS = {
        "quick_debug": 168,   # 1 неделя (24 часа × 7 дней)
        "full_test": 1800,    # 75 дней (~2.5 месяца)
    }
    preset = sys.argv[1] if len(sys.argv) > 1 else "quick_debug"
    
    config = SandboxConfig(
        campaign_id="Open_road",
        location="tavern_silver_wolf",
        tick_count=TICK_PRESETS.get(preset, 40),
        snapshot_interval=1,
        # Пример: настроить конкретных NPC
        npc_overrides={
            # "thief_shadow": {"stress": 30.0, "resentment": 20.0},
            # "tavern_keeper_tornin": {"stress": 50.0},
        },
        # Фильтр: только эти NPC
        # only_npcs=["maid_lusya", "guard_borko", "thief_shadow"],
    )

    sandbox = NPCSandbox(config)
    snapshots = sandbox.run()

    if snapshots:
        reporter = SandboxReporter(snapshots)
        reporter.print_table()
        reporter.print_summary()
        reporter.save_csv()
        reporter.plot_charts()


if __name__ == "__main__":
    main()
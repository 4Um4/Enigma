"""
backend/npc_sandbox.py
Автономная симуляция NPC — N тиков без pygame/LLM.

Запуск: cd backend && python npc_sandbox.py

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

path: /backend/npc_sandbox.py
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
from typing import Any, Dict, List, Optional

# ── Добавляем backend в path ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.npc.npc_loader import load_profile_from_legacy_json, load_l2_state_from_runtime_dict


@dataclass
class SandboxConfig:
    """Настройки симуляции."""
    campaign_id: str = "Open_road"
    location: str = "tavern_silver_wolf"
    tick_count: int = 140           # ~1 неделя (20 действий/день × 7)
    snapshot_interval: int = 20     # слепок каждый "день"
    actions_per_day: int = 20       # сколько действий NPC за игровой день

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

        hub = DecisionHub()
        need_engine = NeedEngine()
        eco_mod = EconomicModifier()
        applicator = StateApplicator(relationship_store=None)

        from app.services.economy.transaction_engine import TransactionEngine
        from app.services.economy.trade_resolver import TradeResolver
        tx_engine = TransactionEngine()
        trade_resolver = TradeResolver(tx_engine)

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
            from app.models.npc_state import Intent, NPCState as NPCStateModel
            from app.services.events.event_types import EventType

            # Обработка контрактных платежей (деньги двигаются)
            tx_engine.process_contract_payments(eco_profiles, tick=tick)

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
                    result = hub.compute(
                        state=state_l2,
                        personality=profile_l0,
                        event=tick_event,
                        scene_state={},
                        social_modifiers=eco_modifiers if eco_modifiers else None,
                    )
                    intent_str = result.intent.value
                    intent_score = result.score

                    # Полное применение: стресс, эмоции, черты, нарратив
                    new_state = applicator.apply(
                        state=state_l2,
                        result=result,
                        campaign_id="sandbox",
                        current_tick=tick,
                    )
                except Exception as e:
                    intent_str = "ERROR"
                    intent_score = 0.0
                    new_state = state_l2

                # === ЭКОНОМИЧЕСКИЙ И ПОТРЕБНОСТНЫЙ СТРЕСС ===
                # Бедность/долги → микростресс (NeedEngine)
                # Критические потребности → пропорциональный стресс (естественная реакция)
                # Формула от urgency, не от типа — без хардкода значений
                if ep:
                    wealth_stress = need_engine.get_wealth_stress(ep)
                    obligation_stress = need_engine.get_obligation_stress(ep)
                    econ_stress = wealth_stress + obligation_stress
                    if econ_stress > 0:
                        new_state.stress = min(100.0, new_state.stress + econ_stress)

                    # Критическая потребность (urgency > 0.85) → стресс пропорционально глубине
                    # (0.95 - 0.85) * 10 = 1.0 стресса/тик при максимуме
                    # За 20 тиков = 20, за ночь recovery -15 → +5/день → реалистичный рост
                    for need in ep.base_needs:
                        if need.effective_urgency > 0.85:
                            need_stress = (need.effective_urgency - 0.85) * 10.0
                            new_state.stress = min(100.0, new_state.stress + need_stress)

                # === TICK RECOVERY ===
                # В реальной игре LifeEngine вызывает recovery после оценки угроз.
                # В мирном тике без стрессоров — восстановление не нужно каждый ход.
                # Вызываем только раз в "день" (каждые actions_per_day тиков).
                is_rest_tick = (tick % self.config.actions_per_day == 0)
                if is_rest_tick:
                    new_state = applicator.apply_tick_recovery(new_state, is_sleeping=False)

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
            if trade_intents:
                trade_results = trade_resolver.resolve_tick(
                    profiles=eco_profiles,
                    trade_intents=trade_intents,
                    location=self.config.location,
                )
                for tr in trade_results:
                    if tr.success:
                        goods_str = "+".join(f"{k}×{v:.0f}" for k, v in tr.goods.items())
                        print(f"[TRADE] {tr.buyer_id} покупает {goods_str} у {tr.seller_id} за {tr.price}G")
                    else:
                        if tick % 20 == 1:  # логируем ошибки реже
                            print(f"[TRADE] {tr.buyer_id} → {tr.seller_id}: {tr.reason}")
            self._trade_intents = {}

            # === CONSUMPTION (еда как решение, не рефлекс) ===
            for npc_id, ep in eco_profiles.items():
                if not ep:
                    continue
                psycho = getattr(ep, '_psycho', None)
                if not psycho:
                    continue
                
                food = ep.goods.get("food", 0.0)
                if food < 1.0:
                    continue  # нечего есть
                
                # Найти потребность FOOD и проверить уровень
                food_need = None
                for need in ep.base_needs:
                    if need.need_type.value == "food":
                        food_need = need
                        break
                if not food_need:
                    continue
                
                # Решение: есть или терпеть? Зависит от психологии
                # desire высокий → ест когда есть еда
                # control высокий → терпит ради цели
                # fear высокий → ест про запас (парадокс)
                eat_threshold = 0.4 + (psycho.profile.desire - 0.25) * 0.8
                
                if food_need.effective_urgency >= eat_threshold:
                    ep.remove_good("food", amount=1.0)
                    ep.satisfy_need(food_need.need_type)
                    if tick % 10 == 1:
                        print(f"[EAT] {npc_id}: поел (urgency={food_need.effective_urgency:.2f} threshold={eat_threshold:.2f})")
                # иначе: терпит — психология не позволяет есть "просто так"

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
        if not runtime_path.exists():
            print(f"[SANDBOX] npc_runtime.json не найден по обоим путям")
            print(f"  Искал: {runtime_path}")
            return []

        try:
            raw_npcs = load_npcs_merged(runtime_path=runtime_path)
        except Exception as e:
            print(f"[SANDBOX] load_npcs_merged ошибка: {e}")
            # Fallback: читаем напрямую
            try:
                raw_npcs = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
            except Exception:
                print(f"[SANDBOX] fallback тоже упал")
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
        """Создаёт экономические профили на основе роли, статуса и психологии NPC."""
        from app.models.economy import EconomicProfile, Need, NeedType
        from app.services.economy.psycho_economy import PsychoEconomy, PsychoProfile

        # Шаблоны по ролям: стартовые товары, расходы, потребности
        ROLE_TEMPLATES = {
            "Хозяин таверны": {
                "goods": {"food": 20, "ale": 30, "room_rent": 5},
                "expenses": {"supplies": 0.3, "maintenance": 0.2},
                "needs": [
                    Need(need_type=NeedType.FOOD, base_urgency=0.3, budget_share=0.1),
                    Need(need_type=NeedType.INCOME, base_urgency=0.8, budget_share=0.4),
                    Need(need_type=NeedType.SOCIAL, base_urgency=0.4, budget_share=0.1),
                ],
            },
            "Служанка таверны": {
                "goods": {"food": 1},
                "expenses": {"food": 0.2},
                "needs": [
                    Need(need_type=NeedType.FOOD, base_urgency=0.9, budget_share=0.5),
                    Need(need_type=NeedType.INCOME, base_urgency=0.9, budget_share=0.4),
                    Need(need_type=NeedType.SOCIAL, base_urgency=0.6, budget_share=0.1),
                ],
            },
            "Торговец тканями": {
                "goods": {"cloth": 50, "silk": 10},
                "expenses": {"food": 0.3, "rent_stall": 0.5},
                "needs": [
                    Need(need_type=NeedType.FOOD, base_urgency=0.5, budget_share=0.15),
                    Need(need_type=NeedType.INCOME, base_urgency=0.7, budget_share=0.5),
                    Need(need_type=NeedType.SOCIAL, base_urgency=0.3, budget_share=0.1),
                ],
            },
            "Кузнец": {
                "goods": {"iron": 30, "tools": 5},
                "expenses": {"coal": 0.4, "food": 0.3},
                "needs": [
                    Need(need_type=NeedType.FOOD, base_urgency=0.6, budget_share=0.2),
                    Need(need_type=NeedType.INCOME, base_urgency=0.6, budget_share=0.4),
                    Need(need_type=NeedType.SOCIAL, base_urgency=0.2, budget_share=0.05),
                ],
            },
            "Стражник городских ворот": {
                "goods": {"food": 2},
                "expenses": {"food": 0.25, "equipment": 0.1},
                "needs": [
                    Need(need_type=NeedType.FOOD, base_urgency=0.7, budget_share=0.3),
                    Need(need_type=NeedType.INCOME, base_urgency=0.8, budget_share=0.4),
                    Need(need_type=NeedType.SOCIAL, base_urgency=0.3, budget_share=0.1),
                ],
            },
            "Вор": {
                "goods": {"lockpick": 2},
                "expenses": {"food": 0.2},
                "needs": [
                    Need(need_type=NeedType.FOOD, base_urgency=0.8, budget_share=0.3),
                    Need(need_type=NeedType.INCOME, base_urgency=0.95, budget_share=0.5),
                    Need(need_type=NeedType.SOCIAL, base_urgency=0.2, budget_share=0.05),
                ],
            },
        }

        profiles = {}
        for npc_raw in npc_data:
            npc_id = npc_raw.get("id", "unknown")
            title = npc_raw.get("status_profile", {}).get("title", "")
            wealth_score = npc_raw.get("status_profile", {}).get("wealth", 20)

            template = ROLE_TEMPLATES.get(title, ROLE_TEMPLATES["Вор"])

            # wealth_score (0-100) → золото (бедный 2G, богатый 100G)
            gold = round(2.0 + (wealth_score / 100.0) * 98.0, 1)

            # Психологический профиль из JSON drives
            drives_raw = npc_raw.get("drives", {})
            psycho = PsychoEconomy(PsychoProfile(
                control=float(drives_raw.get("control", 0.25)),
                significance=float(drives_raw.get("significance", 0.25)),
                fear=float(drives_raw.get("fear", 0.25)),
                desire=float(drives_raw.get("desire", 0.25)),
            ))

            # Применяем психологию к потребностям (индивидуальные decay_rate)
            personalized_needs = [psycho.apply_to_need(n) for n in template["needs"]]

            ep = EconomicProfile(
                npc_id=npc_id,
                gold=gold,
                goods=dict(template["goods"]),
                income_sources={},  # доход только через контракты
                expense_categories=dict(template["expenses"]),
                base_needs=personalized_needs,
            )
            # Сохраняем PsychoEconomy для использования в trade/consumption
            ep._psycho = psycho
            profiles[npc_id] = ep
            
            # Debug: выводим психо-профиль при первом NPC
            if len(profiles) == 1:
                print("[PSYCHO] Индивидуальные параметры:")
            
        # Выводим всех после создания
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
            # Служанка: подёнщица, платят раз в 2 недели (14 дней × 20 тиков)
            ("tavern_keeper_tornin", "maid_lusya", 4.0, 14 * apd),
            # Стражник: наёмник, платят раз в месяц (30 дней × 20 тиков)
            ("merchant_goran", "guard_borko", 8.0, 30 * apd),
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

    def __init__(self, snapshots: List[TickSnapshot]) -> None:
        self.snaps = snapshots
        self.npc_ids = sorted(set(s.npc_id for s in snapshots))
        self.ticks = sorted(set(s.tick for s in snapshots))

    def print_table(self) -> None:
        """Консольная таблица: каждый тик — строка на NPC."""
        if not self.snaps:
            print("[REPORTER] Нет данных")
            return

        print(f"{'TICK':>5} | {'NPC':<25} | {'STRESS':>7} | {'INTENT':<12} | {'SCORE':>6} | {'GOLD':>8} | {'DRIVES':<30}")
        print("-" * 110)

        for tick in self.ticks:
            for npc_id in self.npc_ids:
                snap = next((s for s in self.snaps if s.tick == tick and s.npc_id == npc_id), None)
                if snap:
                    drives_str = ", ".join(snap.active_drives[:2]) if snap.active_drives else "-"
                    print(
                        f"{tick:>5} | {npc_id:<25} | {snap.stress:>7.2f} | {snap.intent:<12} | {snap.intent_score:>6.3f} | {snap.gold:>8.1f} | {drives_str:<30}"
                    )
            print()

    def print_summary(self) -> None:
        """Итоговая таблица: кто выиграл/проиграл за всю симуляцию."""
        print("\n=== ИТОГИ СИМУЛЯЦИИ ===")
        print(f"{'NPC':<25} | {'Δ STRESS':>9} | {'Δ GOLD':>8} | {'Δ HP':>6} | {'FIN STRESS':>10} | {'FIN GOLD':>9} | {'ВЕРДИКТ':<15}")
        print("-" * 100)

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

        # 1. Stress по тикам
        fig, ax = plt.subplots(figsize=(12, 5))
        for npc_id in self.npc_ids:
            ticks = [s.tick for s in self.snaps if s.npc_id == npc_id]
            stresses = [s.stress for s in self.snaps if s.npc_id == npc_id]
            ax.plot(ticks, stresses, label=npc_id, marker="o", markersize=3)
        ax.set_xlabel("Тик")
        ax.set_ylabel("Stress")
        ax.set_title("Стресс NPC по тикам")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_stress.png", dpi=150)
        plt.close(fig)

        # 2. Gold по тикам
        fig, ax = plt.subplots(figsize=(12, 5))
        for npc_id in self.npc_ids:
            ticks = [s.tick for s in self.snaps if s.npc_id == npc_id]
            golds = [s.gold for s in self.snaps if s.npc_id == npc_id]
            ax.plot(ticks, golds, label=npc_id, marker="s", markersize=3)
        ax.set_xlabel("Тик")
        ax.set_ylabel("Gold")
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
        ax.set_title("Распределение интентов по NPC")
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_intents.png", dpi=150)
        plt.close(fig)

        print(f"[REPORTER] Графики сохранены: {path_prefix}_*.png")


def main() -> None:
    """Точка входа для запуска sandbox."""
    config = SandboxConfig(
        campaign_id="Open_road",
        location="tavern_silver_wolf",
        tick_count=140,
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
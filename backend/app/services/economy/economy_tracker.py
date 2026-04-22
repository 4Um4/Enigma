# backend/app/services/economy/economy_tracker.py
"""
EconomyTracker — внешние трекеры для экономической симуляции.

Вынесено из npc_sandbox.py для интеграции в game_loop.
Отвечает за трекинг доходов и разговоров, дневную проверку INCOME/SOCIAL.

path: /backend/app/services/economy/economy_tracker.py
Назначение: Трекинг доходов/разговоров, проверка удовлетворения INCOME/SOCIAL
Зависимости: app.models.economy, app.core.constants, app.services.economy.psycho_economy
Основные сущности: EconomyTracker
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from app.core.constants import DAILY_EXPENSES_MIN, TICKS_PER_DAY
from app.models.economy import EconomicProfile, NeedType
from app.services.economy.psycho_economy import PsychoEconomy, PsychoProfile

logger = logging.getLogger(__name__)


class EconomyTracker:
    """
    Трекер экономических событий для дневных проверок.
    
    Контракт:
    - record_income(): вызывается при каждой транзакции, где NPC получает золото
    - record_talk(): вызывается при диалоге NPC
    - check_daily_needs(): вызывается раз в TICKS_PER_DAY тиков
    - reset_daily(): вызывается после дневной проверки
    """
    
    def __init__(self) -> None:
        # NPC ID → накопленный доход за текущий день
        self._daily_income: Dict[str, float] = {}
        # NPC ID → тик последнего разговора
        self._last_talk_tick: Dict[str, int] = {}
    
    def record_income(self, npc_id: str, amount: float) -> None:
        """Регистрация дохода NPC (от продажи, контракта, кражи)."""
        # TODO: временная заглушка — метод не подключен к TransactionEngine
        # будет удалено после: Фаза 2 (кража) или Фаза 3 (craft) — интеграция TradeResolver
        if amount <= 0:
            return
        self._daily_income[npc_id] = self._daily_income.get(npc_id, 0.0) + amount
    
    def record_talk(self, npc_id: str, tick: int) -> None:
        """Регистрация разговора NPC (любой диалог)."""
        # TODO: временная заглушка — нет точки вызова (NPC говорят через DM в R3_DIRECT)
        # будет удалено после: вербализация NPC через отдельный агент или экстракция из DM-ответа
        self._last_talk_tick[npc_id] = tick
    
    def check_daily_needs(
        self,
        profiles: Dict[str, EconomicProfile],
        npc_drives: Dict[str, Dict[str, float]],
        tick: int,
        location_locked: bool = False,
    ) -> Tuple[int, int]:
        """
        Дневная проверка удовлетворения INCOME и SOCIAL.
        
        Вызывается раз в TICKS_PER_DAY тиков.
        Использует формулы из npc_sandbox.py (проверенные 75-дневным тестом).
        
        Args:
            profiles: Все экономические профили NPC
            npc_drives: {npc_id: {"control": x, "desire": x, ...}} базовые драйвы
            tick: текущий тик мира
            location_locked: заперта ли локация (пассивная социализация)
            
        Returns:
            (income_satisfied_count, social_satisfied_count)
        """
        income_count = 0
        social_count = 0
        
        for npc_id, ep in profiles.items():
            if not ep:
                continue
            
            # ── INCOME: runway × savings + flow × (1 - savings) ──
            runway = ep.gold / DAILY_EXPENSES_MIN if DAILY_EXPENSES_MIN > 0 else float('inf')
            runway_factor = min(1.0, runway / 30.0)  # 1.0 если runway > 30 дней
            flow_factor = 1.0 if self._daily_income.get(npc_id, 0.0) > 0 else 0.0
            
            drives = npc_drives.get(npc_id)
            if drives:
                psycho = PsychoEconomy(PsychoProfile(
                    control=drives.get("control", 0.25),
                    significance=drives.get("significance", 0.25),
                    fear=drives.get("fear", 0.25),
                    desire=drives.get("desire", 0.25),
                ))
                savings = psycho.get_savings_tendency()
                income_satisfaction = runway_factor * savings + flow_factor * (1.0 - savings)
            else:
                # Fallback: равный вес buffer и flow
                income_satisfaction = (runway_factor + flow_factor) / 2.0
            
            if income_satisfaction > 0.5:
                ep.satisfy_need(NeedType.INCOME)
                income_count += 1
            
            # ── SOCIAL: кулдаун-модель ──
            last_talk = self._last_talk_tick.get(npc_id, -999)
            ticks_since_talk = tick - last_talk
            
            if ticks_since_talk < TICKS_PER_DAY:
                # Недавно говорил — satisfied
                ep.satisfy_need(NeedType.SOCIAL)
                social_count += 1
            elif location_locked and ticks_since_talk >= TICKS_PER_DAY * 2:
                # В запертой локации — пассивная социализация раз в 2 дня
                ep.satisfy_need(NeedType.SOCIAL)
                social_count += 1
        
        return income_count, social_count
    
    def reset_daily(self) -> None:
        """Сброс дневных аккумуляторов. Вызывается после check_daily_needs()."""
        self._daily_income.clear()
    
    def get_daily_income(self, npc_id: str) -> float:
        """Текущий накопленный доход за день (для диагностики)."""
        return self._daily_income.get(npc_id, 0.0)
    
    def get_ticks_since_talk(self, npc_id: str, current_tick: int) -> int:
        """Тиков с последнего разговора (для диагностики)."""
        last = self._last_talk_tick.get(npc_id, -999)
        return current_tick - last

    def get_snapshot(
        self,
        profiles: Dict[str, EconomicProfile],
        npc_drives: Dict[str, Dict[str, float]],
        tick: int,
    ) -> List[Dict[str, object]]:
        """
        Снепшот экономического состояния всех NPC (для диагностики).
        Не мутирует состояние — только чтение.
        """
        snapshot = []
        for npc_id, ep in profiles.items():
            if not ep:
                continue
            drives = npc_drives.get(npc_id)
            savings = 0.5
            if drives:
                psycho = PsychoEconomy(PsychoProfile(
                    control=drives.get("control", 0.25),
                    significance=drives.get("significance", 0.25),
                    fear=drives.get("fear", 0.25),
                    desire=drives.get("desire", 0.25),
                ))
                savings = psycho.get_savings_tendency()
            
            runway = ep.gold / DAILY_EXPENSES_MIN if DAILY_EXPENSES_MIN > 0 else float('inf')
            needs_status = {
                nt.value: f"{n.effective_urgency:.2f}"
                for nt, n in ep.get_needs_dict().items()
            }
            
            snapshot.append({
                "npc_id": npc_id,
                "gold": round(ep.gold, 2),
                "runway_days": round(min(runway, 999), 1),
                "savings_tendency": round(savings, 2),
                "daily_income": round(self._daily_income.get(npc_id, 0.0), 3),
                "needs": needs_status,
            })
        return snapshot
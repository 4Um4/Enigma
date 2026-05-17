"""
Фабрика экономических профилей NPC.

Вынесена из models/economy.py чтобы не раздувать дата-модель.
Принцип: чистая функция без побочных эффектов.

path: /backend/app/services/economy/profile_factory.py
Назначение: Фабрика EconomicProfile из разных источников (NPC raw, sandbox templates)
Зависимости: app.models.economy (EconomicProfile, Need, NeedType), app.services.economy.psycho_economy (опционально)
Основные сущности: create_profile_from_npc()
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.models.economy import EconomicProfile, Need, NeedType
from app.services.economy.psycho_economy import PsychoEconomy


def create_profile_from_npc(
    npc_data: Dict[str, Any],
    goods: Optional[Dict[str, float]] = None,
    psycho: Optional[PsychoEconomy] = None,
) -> EconomicProfile:
    """
    Создаёт EconomicProfile из сырых данных NPC.
    
    Источник данных: config/npc/ + runtime overlay (merged).
    Единственная точка создания профиля — и для game_loop, и для sandbox.
    
    Args:
        npc_data: merged NPC dict с status_profile, drives, gold
        goods: начальные товары (из carried_objects в игре, из шаблонов в sandbox)
        psycho: психологический профиль для персонализации decay_rate
    
    Returns:
        EconomicProfile с потребностями, настроенными по wealth/role
    """
    npc_id = npc_data.get("id", "unknown")
    status = npc_data.get("status_profile", {})
    wealth = float(status.get("wealth", 20))
    
    # wealth (0-100) → gold (бедный 2G, богатый 100G)
    gold = round(2.0 + (wealth / 100.0) * 98.0, 1)
    # Если в runtime есть точное значение — используем его
    if "gold" in npc_data and npc_data["gold"]:
        gold = float(npc_data["gold"])
    
    # Базовые потребности — одинаковы для всех
    # Разница в decay_rate через психологию, не через разные base_urgency
    base_needs = [
        Need(need_type=NeedType.FOOD, base_urgency=0.0, budget_share=0.3),
        Need(need_type=NeedType.INCOME, base_urgency=0.3, budget_share=0.5),
        Need(need_type=NeedType.SHELTER, base_urgency=0.1, budget_share=0.1),
        Need(need_type=NeedType.SOCIAL, base_urgency=0.15, budget_share=0.1),
    ]
    
    # Персонализация через психологию (если передана)
    if psycho:
        base_needs = [psycho.apply_to_need(n) for n in base_needs]
    
    return EconomicProfile(
        npc_id=npc_id,
        gold=gold,
        goods=goods if goods is not None else {},
        income_sources={},
        expense_categories={},
        base_needs=base_needs,
    )
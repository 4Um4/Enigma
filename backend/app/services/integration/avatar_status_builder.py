"""
path: /project/backend/app/services/integration/avatar_status_builder.py
Назначение: Сборка EmbodiedStatusDTO из EconomicProfile и BodyTopology для UI.
Зависимости: app.domain.presentation, app.models.economy, app.services.economy.need_presentation_mapper
Основные сущности: AvatarStatusBuilder
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.presentation import EmbodiedStatusDTO
from app.models.economy import EconomicProfile
from app.services.economy.need_presentation_mapper import NeedPresentationMapper

logger = logging.getLogger(__name__)


class AvatarStatusBuilder:
    """Собирает EmbodiedStatusDTO, не вычисляя внутренние метрики."""

    def __init__(self, need_mapper: NeedPresentationMapper) -> None:
        self._need_mapper = need_mapper

    def build(
        self,
        eco_profile: Optional[EconomicProfile],
        body_topology: Optional[Dict[str, Any]] = None,
    ) -> EmbodiedStatusDTO:
        """Формирует DTO состояния аватара для фронтенда. Никогда не возвращает None."""
        if not eco_profile:
            return EmbodiedStatusDTO(
                gold=0.0, food_count=0.0, current_weight=0.0, max_weight=0.0, active_needs=[]
            )

        _gold = round(eco_profile.gold, 1)
        _food_count = self._extract_food_count(eco_profile)
        _active_needs = self._need_mapper.map_needs(eco_profile.base_needs)
        _weight, _max_weight = self._extract_weight(body_topology)

        return EmbodiedStatusDTO(
            gold=_gold,
            food_count=_food_count,
            current_weight=_weight,
            max_weight=_max_weight,
            active_needs=_active_needs,
        )

    def _extract_weight(
        self,
        topology: Optional[Dict[str, Any]],
    ) -> tuple[float, float]:
        """
        Извлекает текущий и максимальный вес из BodyTopology.
        TODO (S152): Делегировать в BodyTopologyService, когда интерфейс стабилизируется.
        """
        if not topology:
            return 0.0, 0.0
        # Предполагаем структуру S148: {"stats": {"current_weight": x, "max_weight": y}}
        _stats = topology.get("stats", {})
        return float(_stats.get("current_weight", 0.0)), float(_stats.get("max_weight", 0.0))

    def _extract_food_count(
        self,
        profile: EconomicProfile,
    ) -> float:
        """
        Извлекает количество еды.
        TODO (S152): Заменить на InventoryService.count_food(), когда появится 
        детальная классификация предметов (хлеб, мясо, ягоды).
        Пока берём из EconomicProfile, так как TradeResolver кладёт товары туда.
        """
        return float(profile.goods.get("food", 0.0))
"""
path: /project/backend/app/services/economy/need_presentation_mapper.py
Назначение: Универсальный маппер Need -> NeedStatusDTO. Не зависит от EconomicProfile.
Зависимости: app.models.economy, app.domain.presentation
Основные сущности: NeedPresentationMapper
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from app.domain.presentation import NeedSeverity, NeedStatusDTO
from app.models.economy import Need, NeedType


class NeedPresentationMapper:
    """Конвертирует Need в NeedStatusDTO, фильтруя неактуальные (< 0.2)."""

    # Декларативная таблица порогов: (max_urgency, severity)
    _LEVELS: Tuple[Tuple[float, Optional[NeedSeverity]], ...] = (
        (0.2, None),
        (0.4, NeedSeverity.MINOR),
        (0.6, NeedSeverity.MODERATE),
        (0.8, NeedSeverity.MAJOR),
        (0.95, NeedSeverity.CRITICAL),
        (1.01, NeedSeverity.EXTREME),
    )

    # Маппинг NeedType -> id (строка для фронтенда)
    _ID_MAP = {
        NeedType.FOOD: "food",
        NeedType.INCOME: "income",
        NeedType.SHELTER: "shelter",
        NeedType.SOCIAL: "social",
    }

    def map_needs(self, needs: Iterable[Need]) -> List[NeedStatusDTO]:
        """Фильтрует и преобразует список потребностей в DTO."""
        _active_needs = []
        for need in needs:
            _dto = self.map_need(need)
            if _dto:
                _active_needs.append(_dto)
        return _active_needs

    def map_need(self, need: Need) -> Optional[NeedStatusDTO]:
        """Преобразует одну потребность в DTO. Возвращает None если < 0.2."""
        _id = self._ID_MAP.get(need.need_type)
        if not _id:
            return None

        _severity = self._map_urgency(need.effective_urgency)
        if not _severity:
            return None

        return NeedStatusDTO(id=_id, severity=_severity)

    def _map_urgency(self, urgency: float) -> Optional[NeedSeverity]:
        """Находит уровень по таблице порогов."""
        for threshold, severity in self._LEVELS:
            if urgency < threshold:
                return severity
        return NeedSeverity.EXTREME
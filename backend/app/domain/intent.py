"""
path: /backend/app/domain/intent.py
Назначение: Намерение игрока. Пересекает границу frontend → backend.
Зависимости: dataclasses, typing
Основные сущности: IntentDTO
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class IntentParametersDTO:
    """Строгий контракт семантических параметров (ADR-035).
    Убивает Dict[str, Any] и энтропию транспорта.
    """
    semantic_action: Optional[str] = None
    target_reference: Optional[str] = None
    target_id: Optional[str] = None # Слой 2: ID цели, найденной через fuzzy matching
    physical_force: float = 0.1
    emotional_charge: float = 0.1
    social_pressure: float = 0.0
    commitment_level: float = 0.8


@dataclass(frozen=True)
class IntentDTO:
    """Намерение игрока.
    
    Парсер (intent_parser) выдаёт это. Backend получает и обрабатывает.
    Не содержит ссылок на внутренние объекты — только строки и примитивы.
    """
    action: str              # 'go', 'talk', 'attack', 'look', 'idle'
    target: str              # 'npc_lucy', 'door_north', 'sword', ''
    parameters: IntentParametersDTO = field(default_factory=IntentParametersDTO)  # Строгая типизация
    text: str = ""           # оригинальный текст игрока
    campaign_id: str = ""    # какой кампании принадлежит
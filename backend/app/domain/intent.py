"""
path: /backend/app/domain/intent.py
Назначение: Намерение игрока. Пересекает границу frontend → backend.
Зависимости: dataclasses, typing
Основные сущности: IntentDTO
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class IntentDTO:
    """Намерение игрока.
    
    Парсер (intent_parser) выдаёт это. Backend получает и обрабатывает.
    Не содержит ссылок на внутренние объекты — только строки и примитивы.
    """
    action: str              # 'go', 'talk', 'attack', 'look', 'idle'
    target: str              # 'npc_lucy', 'door_north', 'sword', ''
    parameters: Dict[str, str] = field(default_factory=dict)  # {'direction': 'north'}
    text: str = ""           # оригинальный текст игрока
    campaign_id: str = ""    # какой кампании принадлежит
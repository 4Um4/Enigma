"""
path: /backend/app/domain/intent.py
Назначение: Намерение игрока. Пересекает границу frontend → backend.
Зависимости: dataclasses, typing
Основные сущности: IntentDTO
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class IntentParametersDTO:
    """Строгий контракт семантических параметров (ADR-035).
    Убивает Dict[str, Any] и энтропию транспорта.
    """

    semantic_action: Optional[str] = None
    actor_id: Optional[str] = (
        None  # ADR-O-315: Кто совершает действие ("player", "tornin")
    )
    target_reference: Optional[str] = None
    target_id: Optional[str] = (
        None  # DEPRECATED ADR-125: Factually dead. Truth goes via PlayerTargetExtractor + intent.target. Kept as archaeological divergence indicator during migration.
    )
    physical_force: float = 0.1
    emotional_charge: float = 0.1
    social_pressure: float = 0.0
    commitment_level: float = 0.8
    # ── UnderstandingSchema (ЭТАП 2, вердикт Мастера): поля семантики,
    # транспортируемые через границу SemanticField → DTO. Инвариант
    # «понятое не умирает на конвертации»; UNKNOWN = None, догадки
    # запрещены (§ENIGMA-003). addressee — авансом: транспорт есть,
    # источник (LLM-schema шаг) добавляется следом.
    # Additive: все существующие читатели — attribute-access, не ломаются.
    addressee: Optional[str] = None  # кому адресовано (R15); источник — промпт-слой, следующим шагом
    condition: Optional[str] = None  # условие действия
    tool_reference: Optional[str] = None  # чем (сырая строка; канонизация — будущий реестр предметов)
    target_zone: Optional[str] = None  # нормализованная зона (боевая логика)
    zone_raw: Optional[str] = None  # сырая зона LLM (латеральность; гранулярная модель — доктрина §1-3)
    proposition_subject: Optional[str] = None
    proposition_predicate: Optional[str] = None
    proposition_object_id: Optional[str] = None
    proposition_polarity: Optional[bool] = None


@dataclass(frozen=True)
class IntentDTO:
    """Намерение игрока.

    Парсер (intent_parser) выдаёт это. Backend получает и обрабатывает.
    Не содержит ссылок на внутренние объекты — только строки и примитивы.
    """

    action: str  # 'go', 'talk', 'attack', 'look', 'idle'
    target: str  # 'npc_lucy', 'door_north', 'sword', ''
    parameters: IntentParametersDTO = field(
        default_factory=IntentParametersDTO
    )  # Строгая типизация
    text: str = ""  # оригинальный текст игрока
    campaign_id: str = ""  # какой кампании принадлежит

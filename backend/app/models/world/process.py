from __future__ import annotations

# backend/app/models/world/process.py
"""
Назначение: Слой Process — первоклассная сущность «преобразование состояния мира
            без исполнителя» (ТЗ Отчёт №6 §2, ADR-O-445). Process — декларативное
            описание трансформации; НЕ заменяет EventDTO/SceneChange/StateApplicator,
            а при запуске (ProcessExecutor, Спринт 2) порождает те же каналы.
            Конкретный источник — отдельная сущность ProcessSource (кем/чем угодно:
            NPC, локация, предмет, явление, время суток).
Зависимости: stdlib only (dataclasses, typing); app.models.world.world_predicate (WorldPredicate).
Основные сущности: WorldStateDelta, Process, ProcessSource
"""

from dataclasses import dataclass
from typing import Any, Tuple

from app.models.world.world_predicate import WorldPredicate


@dataclass(frozen=True)
class WorldStateDelta:
    """Дельта состояния мира, которую применяет Process."""

    domain: str
    attribute: str
    delta: Any
    target_ref: str


@dataclass(frozen=True)
class Process:
    """Абстрактная трансформация состояния мира без исполнителя.

    Не знает, кто/что её запускает. Знает только: какие WorldStateDelta
    применяет, какие WorldPredicate требует для запуска, сколько длится.
    """

    process_id: str
    applies_deltas: Tuple[WorldStateDelta, ...]
    requires_world_state: Tuple[WorldPredicate, ...]
    duration_ticks: int = 1
    side_effects: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcessSource:
    """Конкретный источник Process. source_kind — открытая строка
    ('npc' | 'location' | 'item' | 'environment' | 'time' | ...)."""

    source_id: str
    source_kind: str
    available_processes: Tuple[str, ...]
    requires_provider_state: Tuple[WorldPredicate, ...] = ()

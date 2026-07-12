"""
path: backend/app/domain/action_windup.py
Назначение: DTO для окна реактивности (Action Windup). Представляет собой фазу подготовки к действию, создавая окно для прерывания.
Зависимости: typing
Основные сущности: ActionWindup, WindupStatus
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class WindupStatus(str, Enum):
    """Статус окна подготовки."""

    PENDING = "pending"  # Идёт подготовка
    COMPLETED = "completed"  # Подготовка завершена, действие исполняется
    INTERRUPTED = "interrupted"  # Подготовка сорвана внешним вмешательством


@dataclass(frozen=True)
class ActionWindup:
    """Окно подготовки к значимому действию (DEBT-310.1).

    Pure Temporal Gate (I-CORE-02/03).
    Не хранит и не интерпретирует намерение. Хранит только ID отложенного интента.
    Живёт в TickOrchestrator._windup_registry.
    """

    actor_id: str
    target_id: str
    action_type: str  # "attack", "cast", "steal"
    started_tick: int
    duration_ticks: int  # Сколько тиков длится подготовка
    status: WindupStatus = WindupStatus.PENDING
    # Условие прерывания: например, порог шока или уровня HP
    interrupt_shock_threshold: float = 0.7
    # DEBT-310.1: ID интента, отложенного в TickOrchestrator._pending_intents.
    held_intent_id: Optional[str] = None

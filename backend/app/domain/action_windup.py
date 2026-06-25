"""
path: backend/app/domain/action_windup.py
Назначение: DTO для окна реактивности (Action Windup). Представляет собой фазу подготовки к действию, создавая окно для прерывания.
Зависимости: typing
Основные сущности: ActionWindup, WindupStatus
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any, List
from enum import Enum

class WindupStatus(str, Enum):
    """Статус окна подготовки."""
    PENDING = "pending"           # Идёт подготовка
    COMPLETED = "completed"       # Подготовка завершена, действие исполняется
    INTERRUPTED = "interrupted"   # Подготовка сорвана внешним вмешательством

@dataclass(frozen=True)
class ActionWindup:
    """Окно подготовки к значимому действию (ADR-O-310).
    
    Не хранится в NPCState (эпемерно для боя).
    Живёт в TickOrchestrator._windup_registry.
    """
    actor_id: str
    target_id: str
    action_type: str          # "attack", "cast", "steal"
    started_tick: int
    duration_ticks: int       # Сколько тиков длится подготовка
    status: WindupStatus = WindupStatus.PENDING
    # Условие прерывания: например, порог шока или уровня HP
    interrupt_shock_threshold: float = 0.7
    # ADR-O-310: Замороженный EventDTO, который будет опубликован по завершении.
    pending_event: Optional[Any] = None
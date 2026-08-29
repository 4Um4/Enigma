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

    def to_dict(self) -> dict:
        """S203.4 (Э6, Н-40): JSON-сериализация для scene_state-персистентности.
        Все поля — примитивы или str-Enum; round-trip без потерь (§12 WARA)."""
        return {
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "action_type": self.action_type,
            "started_tick": self.started_tick,
            "duration_ticks": self.duration_ticks,
            "status": self.status.value,
            "interrupt_shock_threshold": self.interrupt_shock_threshold,
            "held_intent_id": self.held_intent_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "ActionWindup":
        """S203.4 (Э6): восстановление из JSON (после atomic_commit → load)."""
        return ActionWindup(
            actor_id=d["actor_id"],
            target_id=d["target_id"],
            action_type=d["action_type"],
            started_tick=d["started_tick"],
            duration_ticks=d["duration_ticks"],
            status=WindupStatus(d["status"]),
            interrupt_shock_threshold=d.get("interrupt_shock_threshold", 0.7),
            held_intent_id=d.get("held_intent_id"),
        )

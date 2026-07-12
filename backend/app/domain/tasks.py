"""
path: /backend/app/domain/tasks.py
Назначение: Универсальный контракт асинхронных задач (Universal Task Layer). Разделяет потребность (Decision) и материализацию (Executor/Artifact).
Зависимости: dataclasses, enum, typing, uuid
Основные сущности: Task, TaskKind, TaskState, TaskPriority, TaskPayload, DialoguePayload
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class TaskKind(Enum):
    """Виды задач. Ядро знает только этот Enum, но не знает, как они исполняются."""

    DIALOGUE = "dialogue"
    TRADE = "trade"
    CRAFT = "craft"
    EAT = "eat"
    OBSERVE = "observe"


class TaskState(Enum):
    """Минимальный жизненный цикл задачи."""

    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class TaskPriority(Enum):
    """Value Object для приоритета. Защищает от инфляции int (напр. priority=9999)."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass(frozen=True)
class TaskPayload:
    """Базовый интерфейс для типизированных полезных нагрузок задачи.
    Защищает систему от JSON-мусорки (payload["whatever"])."""

    pass


@dataclass(frozen=True)
class DialoguePayload(TaskPayload):
    """Типизированный груз для диалога.
    Task не знает про LLM, он знает только что нужно поговорить на эту тему."""

    topic: str
    intent_type: str
    target_id: str


@dataclass
class Task:
    """
    Универсальный объект исполнения.
    Не знает кто его выполнит (Executor) и что получится в итоге (Artifact).
    Ядро симуляции создаёт Task, инфраструктура его потребляет.
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: TaskKind = TaskKind.DIALOGUE
    state: TaskState = TaskState.CREATED
    priority: TaskPriority = TaskPriority.NORMAL

    producer_id: str = ""  # NPC, инициировавший задачу
    participants: List[str] = field(
        default_factory=list
    )  # Другие участники (напр. target_id)
    payload: TaskPayload = field(
        default_factory=lambda: DialoguePayload(
            topic="", intent_type="talk", target_id="player"
        )
    )  # Типизированный груз

    created_tick: int = 0
    started_tick: Optional[int] = None
    completed_tick: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.producer_id:
            raise ValueError("Task requires a producer_id (NPC or Player)")
        if not isinstance(self.payload, TaskPayload):
            raise TypeError(
                f"payload must be subclass of TaskPayload, got {type(self.payload)}"
            )

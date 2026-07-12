"""
path: /backend/app/domain/execution.py
Назначение: Контракты универсального Execution Framework. Разделяет Command (домен), Scheduler (очередь), Executor (исполнение), Artifact (результат) и Materializer (проекция в мир).
Зависимости: typing, dataclasses, enum
Основные сущности: TaskKind, TaskState, TaskPriority, QueuedTask, TaskExecutor, Artifact, Materializer
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Protocol

# ==========================================
# 1. COMMAND LAYER (Доменные запросы)
# ==========================================
# DialogueRequest, TradeRequest, CraftRequest будут жить в своих доменах.
# Execution Framework ничего не знает об их содержимом.


class TaskKind(Enum):
    """Виды команд. Используется для маршрутизации к Executor."""

    DIALOGUE = "dialogue"
    TRADE = "trade"
    CRAFT = "craft"
    EAT = "eat"


class TaskState(Enum):
    """Минимальный жизненный цикл инфраструктурной задачи."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    FINISHED = "FINISHED"


class TaskPriority(Enum):
    """Value Object для приоритета."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


# ==========================================
# 2. SCHEDULER LAYER (Инфраструктура)
# ==========================================
@dataclass
class QueuedTask:
    """Инфраструктурный контейнер. Не знает, как исполнять команду."""

    task_id: str
    tick: int
    counter: int
    kind: TaskKind
    priority: TaskPriority = TaskPriority.NORMAL
    state: TaskState = TaskState.PENDING

    creator_system: str = "AI"  # Кто создал (NPC, Scheduler, QuestSystem)
    owner_id: str = ""  # Главный исполнитель (NPC)
    target_ids: List[str] = field(default_factory=list)  # Участники
    campaign_id: str = ""  # Для контекста исполнителей (напр. LLM)

    payload: Any = None  # Сама Command (напр. DialogueRequest)

    retry_count: int = 0
    created_tick: int = 0
    started_tick: Optional[int] = None
    completed_tick: Optional[int] = None
    version: int = 1


# ==========================================
# 3. EXECUTOR LAYER
# ==========================================
@dataclass(frozen=True)
class Artifact:
    """Чистый результат выполнения. Не знает про EventBus и WorldEvent."""

    task_id: str
    success: bool
    result_type: str  # Напр. "dialogue_line", "item_consumed"
    data: Dict[str, Any]  # Данные результата (напр. {"text": "Привет"})
    error_message: Optional[str] = None


class TaskExecutor(Protocol):
    """Исполнитель. Не имеет метода can_execute.
    Scheduler сам мапит TaskKind на конкретный Executor."""

    def execute(self, task: QueuedTask) -> Iterable[Artifact]:
        """Выполняет задачу и возвращает поток артефактов."""
        ...


# ==========================================
# 4. MATERIALIZER LAYER
# ==========================================
class Materializer(Protocol):
    """Превращает доменный Artifact в WorldEvent (EventDTO) для EventBus.
    Связывает Execution Framework с миром симуляции."""

    def materialize(self, artifact: Artifact) -> Iterable[Any]:
        """Возвращает список EventDTO для публикации."""
        ...

from __future__ import annotations
# backend/app/models/phase8.py
"""
Контракты Фазы 8 — детерминированный drain-этап.

EventBus накапливает факты (Фазы 2/7).
Фаза 8 дренирует буферы подписчиков и обрабатывает в фиксированном порядке.

Принципы:
  - Phase8Context READ-ONLY для обработчиков. Все выходы — через Phase8Result.
  - drain_events() — снимок + очистка. Если handle() падает — события теряются
    в одном тике, пайплайн не крашится.
  - Порядок обработчиков фиксирован в оркестраторе, не в подписках.

path: backend/app/models/phase8.py
Назначение: Контракты Фазы 8 — детерминированный drain-этап (Устав §3, Фаза 8)
Зависимости: app.models.state_delta.StateDeltas, app.domain.events.EventDTO
Основные сущности: Phase8Context, Phase8Result, Phase8Handler

TODO: после миграции на delta_buffer удалить prop_dirty и весь код, завязанный на него (в т.ч. в оркестраторе)
"""


from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple, runtime_checkable

from app.domain.events import EventDTO
from app.models.state_delta import StateDeltas


@dataclass(frozen=True)
class Phase8Context:
    """READ-ONLY контекст для обработчиков Фазы 8.

    frozen=True — гарантия неизменяемости.
    Оркестратор создаёт один экземпляр, все обработчики читают.
    """

    all_npcs_raw: List[Dict[str, Any]]
    all_npc_contexts: List[Dict[str, Any]]  # для perception
    shared_context: Any  # TODO: типизировать после миграции SharedContext
    campaign_id: str
    tick_ctx: Any  # TODO: типизировать после миграции _TickContext
    physical_deltas_materialized: Tuple[
        StateDeltas, ...
    ] = ()  # Материализованный Physical Layer (t)


@dataclass
class Phase8Result:
    """Результат одного обработчика Фазы 8.

    Все выходы — только через этот DTO. Никакой мутации Phase8Context.
    Оркестратор синхронизирует perception ∪ social (Задача 3).
    """

    deltas: List[StateDeltas] = field(default_factory=list)
    perceiving_npc_ids: Optional[Set[str]] = None
    socially_affected_npc_ids: Optional[Set[str]] = None
    events_processed: int = 0
    prop_dirty: bool = False  # DEPRECATED после миграции на delta_buffer


@runtime_checkable
class Phase8Handler(Protocol):
    """Протокол обработчика Фазы 8.

    Жизненный цикл:
      1. Шина вызывает _on_event() → накапливает в буфер (Фазы 2/7)
      2. Оркестратор вызывает drain_events() → снимок + очистка
      3. Оркестратор вызывает handle(events, ctx) → Phase8Result
    """

    @property
    def name(self) -> str: ...

    def drain_events(self) -> List[EventDTO]:
        """Возвращает накопленные события и очищает буфер.

        Вызывается оркестратором строго один раз за тик.
        Если handle() упадёт — события уже потеряны (допустимо).
        """
        ...

    def handle(self, events: List[EventDTO], ctx: Phase8Context) -> Phase8Result:
        """Обрабатывает события с явным контекстом.

        events — из drain_events(), может быть пустым.
        ctx — READ-ONLY, не мутировать.
        Возвращает Phase8Result — все выходы только через него.
        """
        ...

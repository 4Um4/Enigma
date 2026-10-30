"""
path: /project/backend/app/services/events/tick_campaign_context.py
Назначение: C3-A1 contextvars-мост для изоляции доставки NPC_ADDRESSES_PLAYER
    по campaign_id и tick_id. Утверждён Мастером: TickCampaignContext dataclass
    содержит campaign_id, tick_id и staged_events (двухфазное помещение:
    staging при publish, commit после успешного Phase 10).
    ContextVar изолирует per-context (thread/asyncio task): параллельные тики
    разных кампаний получают независимые значения. publish() синхронен —
    subscriber выполняется в том же call stack и видит правильный контекст.
Зависимости: contextvars, dataclasses, typing
Основные сущности: TickCampaignContext, _current_tick_context, set_tick_context,
    reset_tick_context, get_current_tick_context
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.domain.events import EventDTO


@dataclass
class TickCampaignContext:
    """Контекст исполнения тика для delivery-изоляции (C3-A1).

    Устанавливается в TickOrchestrator.execute() через contextvars.ContextVar.
    Subscriber читает контекст в момент publish() (синхронный call stack)
    и добавляет событие в staged_events (Фаза 1: staging).

    После успешного Phase 10 + scene_manager.commit — orchestrator вызывает
    subscriber.commit_staged() для переноса staged_events в delivery queue
    (Фаза 2: commit). При exception в Phase 10 — commit_staged НЕ вызывается,
    staged_events уничтожаются вместе с контекстом (ContextVar.reset).

    Lifecycle: per-execute(). Не persistent. Не переживает restart.
    """

    campaign_id: str
    tick_id: int
    staged_events: list = field(default_factory=list)


_current_tick_context: contextvars.ContextVar[Optional[TickCampaignContext]] = (
    contextvars.ContextVar("c3_tick_campaign_context", default=None)
)


def get_current_tick_context() -> Optional[TickCampaignContext]:
    """Возвращает активный контекст тика или None (вне execute())."""
    return _current_tick_context.get()


def set_tick_context(ctx: TickCampaignContext) -> contextvars.Token:
    """Устанавливает контекст тика. Возвращает token для reset().

    Поддерживает вложенность (contextvars.reset восстанавливает предыдущий).
    """
    return _current_tick_context.set(ctx)


def reset_tick_context(token: contextvars.Token) -> None:
    """Сбрасывает контекст тика. Вызывать после execute() (try/finally).

    Token обязателен — гарантирует восстановление предыдущего контекста
    (вложенные execute(), тесты).
    """
    _current_tick_context.reset(token)
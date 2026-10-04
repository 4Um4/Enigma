# -*- coding: utf-8 -*-
"""
path: backend/app/services/events/relationship_event_semantics.py
Назначение: ADR-O-418 (RE M2/D) — Phase8Handler событийной семантики
    Relationship Engine: needs-touching события §5.5 → StateDeltas
    (domain=RELATIONSHIP, payload=NeedDeltaPayload). Pure reducer:
    EventDTO → дельты; НЕ знает StateApplicator/Store/NPCState, ничего
    не мутирует (вердикт Мастера, PRE-FLIGHT п.9).
Зависимости: app.models.phase8, app.models.state_delta, app.models.delta_payloads,
    app.domain.events, app.domain.relationship_contracts (реестр + валидация),
    app.services.events.event_bus, app.services.events.event_types.
Основные сущности: RelationshipEventSemantics, relationship_events_enabled,
    RELATIONSHIP_EVENT_PROFILES, RE_NEEDS_EVENT_MAGNITUDE.
"""

import logging
import os
from typing import Dict, List, Tuple

from app.domain.events import EventDTO
from app.domain.relationship_contracts import (
    RELATIONSHIP_EVENT_REGISTRY,
    RELATIONSHIP_NEEDS_TOUCHING_EVENTS,
    ContractValidationError,
)
from app.models.delta_payloads import NeedDeltaPayload
from app.models.phase8 import Phase8Context, Phase8Result
from app.models.state_delta import DeltaDomain, StateDeltas
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)


def relationship_events_enabled() -> bool:
    """Env-флаг RELATIONSHIP_EVENTS_ENABLED (default OFF = полный no-op,
    байт-идентичный baseline; прецеденты BC1_ENABLED / W3_G3_ENABLED).
    Флаг читается один раз при инстанцировании — динамическое включение
    на лету не поддерживается (консистентно с conclusion_runtime)."""
    return os.environ.get("RELATIONSHIP_EVENTS_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# ADR-O-418: плейсхолдер до фаз G/H (запрет №15 ТЗ-RE-01 — формулы §6 заморожены).
# Калибровка — только через Calibration Lab (прецедент ADR-O-383).
RE_NEEDS_EVENT_MAGNITUDE = 0.2  # CALIBRATION_CANDIDATE

# Таблица базовых направлений (утверждена вердиктом Мастера M2/D; §8.1 ТЗ).
# Формат: event_type → кортеж (subject, need_id, field, signed_magnitude).
# subject: "source" — инициатор события; "both" — source и target (encounter).
# ЕДИНСТВЕННАЯ точка расширения будущего слоя индивидуального переживания
# (вердикт Мастера: базовое направление — да; фиксированная универсальная
# дельта как окончательная игровая модель — нет; привыкание — фазы G/H;
# индивидуальная интерпретация — отдельный слой ПОСЛЕ G/H).
RELATIONSHIP_EVENT_PROFILES: Dict[str, Tuple[Tuple[str, str, str, float], ...]] = {
    EventType.FLIRT_ACCEPTED.value: (
        ("source", "intimacy", "pressure", -1.0),  # relief, Ф4 (качество>0)
    ),
    EventType.FLIRT_REJECTED.value: (
        ("source", "intimacy", "frustration", +1.0),  # путь 2, Фр1=C
    ),
    EventType.INTIMATE_ENCOUNTER.value: (
        ("both", "sexual", "pressure", -1.0),  # relief, Ф4
        ("both", "sexual", "satiation", +1.0),  # рост по качеству, Сат4
    ),
    EventType.INTIMATE_REJECTION.value: (
        ("source", "sexual", "frustration", +1.0),  # путь 2, Фр1=C
    ),
}


def _resolve_need_magnitude(event: EventDTO, subject_id: str) -> float:
    """Точка расширения слоя индивидуального переживания (M2/D — константа).

    Будущий слой (после G/H) заменит константное разрешение на функцию от
    накопленного опыта NPC; pipeline/Store/apply-путь не меняются.
    Параметры — сигнатура будущего слоя, сознательно не используются сейчас.
    """
    return RE_NEEDS_EVENT_MAGNITUDE


def _resolve_actor_ids(event: EventDTO) -> Tuple[str, str]:
    """Акторы события: EventDTO.source — SSOT идентификации (Устав §2.1),
    payload["source_id"] — фолбэк для ручных публикаций. Пустой source —
    каузальный разрыв (актор неизвестен) → fail-loud."""
    payload = event.payload or {}
    source_id = (event.source or "").strip() or str(payload.get("source_id") or "")
    if not source_id:
        raise ContractValidationError(
            f"RelationshipEventSemantics: {event.type} без source_id "
            f"(event_id={event.id}) — каузальный разрыв, актор неизвестен"
        )
    return source_id, str(payload.get("target_id") or "")


def _resolve_subjects(
    subject: str, source_id: str, target_id: str, event: EventDTO
) -> Tuple[str, ...]:
    """Субъекты профиля: 'source' — инициатор; 'both' — source+target
    (target обязателен); иной subject — конфигурационный разрыв профиля."""
    if subject == "source":
        return (source_id,)
    if subject == "both":
        if not target_id:
            raise ContractValidationError(
                f"RelationshipEventSemantics: {event.type} требует "
                f"target_id в payload (event_id={event.id})"
            )
        return (source_id, target_id)
    raise ContractValidationError(
        f"RelationshipEventSemantics: неизвестный subject '{subject}' "
        f"в профиле {event.type}"
    )


def _build_need_delta(
    npc_id: str,
    need_id: str,
    field: str,
    magnitude: float,
    event_id: str,
    source_tag: str,
) -> StateDeltas:
    """Сборка одной дельты. Явные keyword-аргументы (не **unpack): детекция
    писателей полей сканером ADR-O-414 (слепая зона Слоя 1 — writers через **)."""
    return StateDeltas(
        npc_id=npc_id,
        domain=DeltaDomain.RELATIONSHIP,
        payload=NeedDeltaPayload(
            need_id=need_id,
            pressure_delta=magnitude if field == "pressure" else 0.0,
            satiation_delta=magnitude if field == "satiation" else 0.0,
            frustration_delta=magnitude if field == "frustration" else 0.0,
            source_event_id=event_id,
        ),
        source=source_tag,
    )


class RelationshipEventSemantics:
    """Phase8Handler: RE-события → NeedDeltaPayload-дельты (pure).

    Жизненный цикл (протокол Phase8Handler):
      1. Шина → _on_event() накапливает EventDTO (Фазы 2/7)
      2. Оркестратор → drain_events() снимок + очистка (Фаза 8)
      3. Оркестратор → handle(events, ctx) → Phase8Result

    При флаге OFF подписка не выполняется: события не накапливаются,
    drain пуст, handle не вызывается (ранний выход _execute_handler) —
    нулевой вклад в тик (паттерн INV-BC1-NOOP).
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_events: List[EventDTO] = []
        if relationship_events_enabled():
            for et in self._subscribed_types():
                self._event_bus.subscribe(et, self._on_event)

    @staticmethod
    def _subscribed_types() -> Tuple[EventType, ...]:
        """Единственные живые EventType M2/D — needs-touching подмножество
        §5.5 (вердикт Мастера F2: без мёртвых enum-значений)."""
        return (
            EventType.FLIRT_ACCEPTED,
            EventType.FLIRT_REJECTED,
            EventType.INTIMATE_ENCOUNTER,
            EventType.INTIMATE_REJECTION,
        )

    def _on_event(self, event: EventDTO) -> None:
        """EventHandler: накапливает событие для обработки на Фазе 8."""
        self._pending_events.append(event)
        return None

    @property
    def name(self) -> str:
        return "relationship_events"

    def drain_events(self) -> List[EventDTO]:
        """Снимок буфера + очистка. Вызывается строго один раз за тик."""
        snapshot = list(self._pending_events)
        self._pending_events.clear()
        return snapshot

    def handle(self, events: List[EventDTO], ctx: Phase8Context) -> Phase8Result:
        """Pure редукция: события → дельты. ctx читается, не мутируется."""
        deltas: List[StateDeltas] = []
        for event in events:
            deltas.extend(self._reduce_event(event))
        return Phase8Result(deltas=deltas, events_processed=len(events))

    def _reduce_event(self, event: EventDTO) -> List[StateDeltas]:
        """Одно событие → List[StateDeltas] по профилю (pure)."""
        if event.type not in RELATIONSHIP_EVENT_REGISTRY:
            # Событие вне канонического реестра §5.5 — обработке не подлежит
            # (ADR-O-418: хендлер знает только канон RE-событий).
            return []
        if event.type not in RELATIONSHIP_NEEDS_TOUCHING_EVENTS:
            return []  # каноническое событие без needs-профиля (фазы C/E/F/J)
        profile = RELATIONSHIP_EVENT_PROFILES.get(event.type)
        if profile is None:
            # Реестр знает событие, профиль отсутствует — конфигурационный
            # разрыв между domain-реестром и таблицей профилей. Fail-loud (L4).
            raise ContractValidationError(
                f"RelationshipEventSemantics: событие '{event.type}' в реестре "
                f"needs-touching, но без профиля редукции — рассинхрон ADR-O-418"
            )
        source_id, target_id = _resolve_actor_ids(event)
        event_id = str(event.id)
        source_tag = f"relationship_{event.type}"
        deltas: List[StateDeltas] = []
        for subject, need_id, field, signed in profile:
            magnitude = signed * _resolve_need_magnitude(event, source_id)
            for npc_id in _resolve_subjects(subject, source_id, target_id, event):
                deltas.append(
                    _build_need_delta(
                        npc_id, need_id, field, magnitude, event_id, source_tag
                    )
                )
        logger.debug(
            f"[RE_SEMANTICS] {event.type}: {len(deltas)} need-delta(s) "
            f"event_id={event_id}"
        )
        return deltas

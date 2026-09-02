"""
Назначение: E2.0 — единственный мост интерпретация→состояние; whitelist полей с потребителями; клампы; идемпотентность по trace_id; Python — SSOT дельт
Зависимости: app.domain.state_delta_proposal
Основные сущности: DeltaGate
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional, Tuple

from app.domain.state_delta_proposal import StateDeltaProposal

logger = logging.getLogger(__name__)


class DeltaGate:
    """E2.0: единственный легальный вход «интерпретация → состояние».

    INV-LLM-NOT-SSOT: без apply() этого гейта ни Proposal (в т.ч.
    LLM-порождённый), ни любой другой внешний текст не меняет ни одного
    поля психики. Потребители — белые списки, не словари «что угодно».
    """

    # поле → (min, max, потребитель-диспетчер)
    WHITELIST: Dict[str, Tuple[float, float, str]] = {
        "threat_gradient": (-1.0, 1.0, "perceptual_kernel"),
        "danger_belief": (0.0, 1.0, "r7_beliefs"),
    }

    def __init__(self) -> None:
        # идемпотентность: trace_id+field → применён
        self._applied: set = set()

    def validate(self, proposal: StateDeltaProposal) -> Optional[float]:
        """Валидация без применения: whitelist → кламп → идемпотентность.
        Возвращает клампнутое значение или None с причиной в логе."""
        if proposal.field not in self.WHITELIST:
            logger.warning(
                f"[DELTA_GATE] отклонено: поле '{proposal.field}' вне whitelist"
            )
            return None
        lo, hi, _consumer = self.WHITELIST[proposal.field]
        clamped = max(lo, min(hi, proposal.value))
        key = (proposal.trace_id, proposal.field)
        if key in self._applied:
            logger.info(
                f"[DELTA_GATE] идемпотентность: {key} уже применён — пропуск"
            )
            return None
        return clamped

    def apply(
        self,
        proposal: StateDeltaProposal,
        consumer_dispatch: Optional[Callable[[str, str, float], bool]] = None,
    ) -> bool:
        """Валидация + диспетчеризация потребителю + публикация трассы.

        E2.0-b (вердикт AG1-04): Gate — аудит и трассировка причинного
        изменения, НЕ второй писатель. Belief-проекция остаётся на
        тиковой ветке (BeliefTransitionEngine); связь доказывается
        trace_id/causal_parent (AG1-INV-TRACE-ONCE: один event.id →
        один trace → ≤1 дельты поля → проекция либо несёт trace,
        либо отсутствует с причиной).

        consumer_dispatch(consumer, trace_id, value) → bool: применение
        ПО ИМЕЮЩЕМУСЯ каналу потребителя (Perception — sync).
        None → dry-run (валидация без эффекта).

        Публикация: EXPERIENCE_DELTA_COMMITTED в EventBus — единственный
        выход для Chronicaler (cross-cutting, не UI).
        """
        clamped = self.validate(proposal)
        if clamped is None:
            return False
        _, _, consumer = self.WHITELIST[proposal.field]
        key = (proposal.trace_id, proposal.field)
        if consumer_dispatch is not None:
            ok = consumer_dispatch(consumer, proposal.trace_id, clamped)
            if not ok:
                logger.warning(
                    f"[DELTA_GATE] потребитель '{consumer}' отверг дельту {key}"
                )
                return False
        self._applied.add(key)
        logger.info(
            f"[DELTA_GATE] применено: {key} = {clamped} "
            f"(источник: {proposal.source})"
        )
        # E2.0-b: трасса причинности для Chronicaler — observation only
        # (Закон XI: наблюдение не создаёт причинность)
        try:
            from app.domain.events import EventDTO
            from app.services.events.event_bus import get_event_bus
            from app.services.events.event_types import EventType

            if hasattr(EventType, "EXPERIENCE_DELTA_COMMITTED"):
                get_event_bus().publish(
                    EventDTO.create(
                        event_type=EventType.EXPERIENCE_DELTA_COMMITTED.value,
                        source="delta_gate",
                        payload={
                            "trace_id": proposal.trace_id,
                            "causal_parent": proposal.causal_parent,
                            "field": proposal.field,
                            "value": clamped,
                            "consumer": consumer,
                            "source": proposal.source,
                        },
                        persistence_level="working",
                    )
                )
        except Exception as _pub_err:  # noqa: ENIGMA001
            # публикация трассы не роняет причинный поток (XI.2);
            # отказ наблюдаем в логе
            logger.warning(f"[DELTA_GATE] trace publish failed: {_pub_err}")
        return True
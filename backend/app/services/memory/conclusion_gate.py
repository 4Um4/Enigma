# backend/app/services/memory/conclusion_gate.py
"""
Назначение: BC-1/ADR-O-381 — единственный легальный вход «интерпретация → вывод».
    INV-CONCLUSION-GATE: без apply() этого гейта ни ConclusionProposal,
    ни любой другой генератор не пишет ни одной записи ConclusionStore.
Зависимости: app.domain.conclusions, app.services.npc.conclusion_store,
    app.domain.events, app.services.events.event_bus, app.services.events.event_types.
Основные сущности: ConclusionGate.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.domain.conclusions import ConclusionProposal
from app.services.npc.conclusion_store import ConclusionApplyResult

logger = logging.getLogger(__name__)

# Тип диспатч-функции (цель — ConclusionStore.apply)
ConsumerDispatch = Callable[[ConclusionProposal, float], ConclusionApplyResult]


class ConclusionGate:
    """BC-1: единственный легальный вход «интерпретация → вывод».

    Два осознанных отклонения от DeltaGate:
    (А) сигнатура диспатча — (proposal, clamped) вместо (consumer_tag, trace_id, value):
        у ConclusionGate один потребитель (Store), тег-церемония не нужна;
    (Б) инстанс персистентен, _applied переживает тики: повтор события в другом
        окне не должен порождать дубликат вывода.
    """

    def __init__(self) -> None:
        self._applied: set[tuple[str, str, str]] = set()

    def validate(self, proposal: ConclusionProposal) -> Optional[float]:
        """Валидация proposal перед диспатчем. Возвращает clamped confidence или None."""
        if not proposal.owner_id or not proposal.subject:
            logger.warning(
                f"[CONCLUSION_GATE] reject: пустые owner_id/subject "
                f"(trace_id={proposal.trace_id})"
            )
            return None
        predicate: object = proposal.predicate
        if not predicate:
            logger.warning(
                f"[CONCLUSION_GATE] reject: пустой predicate "
                f"(trace_id={proposal.trace_id})"
            )
            return None

        return max(0.0, min(1.0, proposal.confidence))

    def apply(
        self,
        proposal: ConclusionProposal,
        consumer_dispatch: Optional[ConsumerDispatch] = None,
    ) -> bool:
        """Валидация + диспатч потребителю + публикация трассы (только при CREATED).

        Gate — аудит и трассировка, НЕ второй писатель (F2б).
        consumer_dispatch None -> dry-run (валидация без эффекта).

        ВАЖНО: CONCLUSION_FORMED публикуется ТОЛЬКО при CREATED (новое формирование).
        При REINFORCED (усиление существующего) событие НЕ публикуется, чтобы
        избежать спама и ложных срабатываний downstream-слоёв.
        """
        clamped = self.validate(proposal)
        if clamped is None:
            return False

        apply_result = ConclusionApplyResult.CREATED  # default для dry-run
        if consumer_dispatch is not None:
            result = consumer_dispatch(proposal, clamped)
            result_value: object = result
            if not isinstance(result_value, ConclusionApplyResult):
                logger.warning(
                    f"[CONCLUSION_GATE] потребитель вернул неожиданный тип "
                    f"{type(result).__name__} ({proposal.trace_id})"
                )
                return False
            apply_result = result

        key = (proposal.trace_id, proposal.subject, proposal.predicate.value)
        self._applied.add(key)
        logger.info(
            f"[CONCLUSION_GATE] применено: {key} = {clamped} "
            f"(источник: {proposal.source}; parent: {proposal.causal_parent}; "
            f"результат: {apply_result.value})"
        )

        # Публикация CONCLUSION_FORMED только при CREATED (новое формирование)
        if apply_result == ConclusionApplyResult.CREATED:
            try:
                from app.domain.events import EventDTO
                from app.services.events.event_bus import get_event_bus
                from app.services.events.event_types import EventType

                if hasattr(EventType, "CONCLUSION_FORMED"):
                    get_event_bus().publish(
                        EventDTO.create(
                            event_type=EventType.CONCLUSION_FORMED.value,
                            source="conclusion_gate",
                            payload={
                                "owner_id": proposal.owner_id,
                                "subject": proposal.subject,
                                "predicate": proposal.predicate.value,
                                "object": proposal.object,
                                "confidence": clamped,
                                "evidence": list(proposal.evidence),
                                "trace_id": proposal.trace_id,
                                "causal_parent": proposal.causal_parent,
                                "source": proposal.source,
                            },
                            persistence_level="working",
                        )
                    )
            except Exception as _pub_err:  # noqa: ENIGMA001
                logger.warning(f"[CONCLUSION_GATE] trace publish failed: {_pub_err}")
        else:
            logger.debug(
                f"[CONCLUSION_GATE] reinforcement (без публикации): {key}"
            )

        return True

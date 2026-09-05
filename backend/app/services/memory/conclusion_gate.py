# backend/app/services/memory/conclusion_gate.py
"""
Назначение: BC-1/ADR-O-381 — мембрана Conclusion-слоя (по образу DeltaGate
    E2.0, delta_gate.py): validate (source-фильтр → NO-VACUUM backstop →
    полнота идентичности → кламп confidence [0..1] → идемпотентность) и
    apply (диспатч ConclusionStore.apply — единственный write-path;
    публикация CONCLUSION_FORMED, observation-only). Gate — аудит и
    трассировка, НЕ второй писатель (вердикт F2б; дословная семантика
    DeltaGate docstring :56-60).
Зависимости: app.domain.conclusions; лениво — app.domain.events (EventDTO),
    app.services.events.event_bus, app.services.events.event_types.
Основные сущности: ConclusionGate.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from app.domain.conclusions import (
    CONCLUSION_SOURCE_DIRECT,
    ConclusionPredicate,
    ConclusionProposal,
)

logger = logging.getLogger(__name__)


class ConclusionGate:
    """BC-1: единственный легальный вход «интерпретация → вывод».

    INV-CONCLUSION-GATE: без apply() этого гейта ни ConclusionProposal
    (механический или LLM-порождённый), ни любой другой генератор не
    пишет ни одной записи ConclusionStore.

    Два осознанных отклонения от DeltaGate (см. docstring методов):
    (А) сигнатура диспатча — (proposal, clamped) вместо
    (consumer_tag, trace_id, value): у ConclusionGate один потребитель
    (Store), тег-церемония не нужна;
    (Б) инстанс персистентен, _applied переживает тики (оркестраторная
    проводка): повтор события в другом окне не должен порождать дубликат
    вывода — двойная защита с Store-идентичностью (Шаг 3).
    """

    # Закрытый predicate-реестр — зеркало dom/conclusions (single source:
    # enum-члены; расширение = мини-ADR, класс ADR-O-349).
    _PREDICATES = {p.value for p in ConclusionPredicate}

    # Диспатч: (proposal, clamped_confidence) -> bool (отклонение А).
    ConsumerDispatch = Callable[[ConclusionProposal, float], bool]

    def __init__(self) -> None:
        # Идемпотентность (перенос AG1-INV-TRACE-ONCE):
        # (trace_id, subject, predicate) -> применён.
        # Отклонение Б: множество переживает тики в оркестраторной сборке.
        self._applied: set = set()

    def validate(self, proposal: ConclusionProposal) -> Optional[float]:
        """Валидация без применения (параллель DeltaGate.validate):
        source-фильтр -> NO-VACUUM backstop -> полнота -> кламп ->
        идемпотентность. Возвращает клампнутый confidence или None с
        причиной в логе."""

        # (1) source-фильтр: BC-1 = только прямой опыт; TESTIMONY — BC-5.
        if proposal.source != CONCLUSION_SOURCE_DIRECT:
            logger.warning(
                f"[CONCLUSION_GATE] отклонено: source='{proposal.source}' "
                f"не 'direct_experience' (BC-1; testimony — BC-5)"
            )
            return None

        # (2) NO-VACUUM backstop (досье §13.1, мембранный дубль):
        # вывод без нового причинного опыта не существует.
        if not proposal.causal_parent or not proposal.evidence:
            logger.warning(
                "[CONCLUSION_GATE] отклонено: NO-VACUUM — пустой "
                "causal_parent/evidence (вывод из отсутствия опыта)"
            )
            return None

        # (3) Полнота идентичности: owner/subject/trace — ключи записи.
        if not proposal.owner_id or not proposal.subject or not proposal.trace_id:
            logger.warning(
                "[CONCLUSION_GATE] отклонено: неполная идентичность "
                "(owner_id/subject/trace_id)"
            )
            return None

        # (4) Predicate-реестр (закрытый: не-члены enum сюда не попадут
        # типом; проверка-зеркало — для сериализованных/гипотетических).
        if proposal.predicate.value not in self._PREDICATES:
            logger.warning(
                f"[CONCLUSION_GATE] отклонено: predicate "
                f"'{proposal.predicate.value}' вне реестра"
            )
            return None

        # (5) Кламп confidence [0..1] (гейт — место клампа, не генератор).
        clamped = max(0.0, min(1.0, proposal.confidence))

        # (6) Идемпотентность: один event.id -> один trace -> <=1
        # conclusion-дельты на (subject, predicate) — перенос
        # AG1-INV-TRACE-ONCE (ключ = trace+subject+predicate).
        key = (proposal.trace_id, proposal.subject, proposal.predicate.value)
        if key in self._applied:
            logger.info(
                f"[CONCLUSION_GATE] идемпотентность: {key} уже применён — пропуск"
            )
            return None

        return clamped

    def apply(
        self,
        proposal: ConclusionProposal,
        consumer_dispatch: Optional[ConsumerDispatch] = None,
    ) -> bool:
        """Валидация + диспатч потребителю + публикация трассы.

        Gate — аудит и трассировка, НЕ второй писатель (F2б): применение
        по ИМЕЮЩЕМУСЯ каналу потребителя — ConclusionStore.apply
        (единственный write-path). consumer_dispatch None -> dry-run
        (валидация без эффекта).

        Отказ потребителя -> False, ключ в _applied НЕ добавляется
        (retry легален — параллель DeltaGate :74-81).

        Публикация CONCLUSION_FORMED — observation-only (Закон XI):
        наблюдение не создаёт причинность и не роняет поток (XI.2);
        отказ наблюдаем в логе. hasattr-guard — по образу DeltaGate :98:
        член EventType появится в Шаге 4, гейт начнёт эмитить без
        правок этого файла.
        """
        clamped = self.validate(proposal)
        if clamped is None:
            return False

        if consumer_dispatch is not None:
            ok = consumer_dispatch(proposal, clamped)
            if not ok:
                logger.warning(
                    f"[CONCLUSION_GATE] потребитель отверг дельту "
                    f"({proposal.trace_id}, {proposal.subject})"
                )
                return False

        key = (proposal.trace_id, proposal.subject, proposal.predicate.value)
        self._applied.add(key)
        logger.info(
            f"[CONCLUSION_GATE] применено: {key} = {clamped} "
            f"(источник: {proposal.source}; parent: {proposal.causal_parent})"
        )

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
            # публикация трассы не роняет причинный поток (XI.2);
            # отказ наблюдаем в логе (дословный прецедент DeltaGate :114-117)
            logger.warning(f"[CONCLUSION_GATE] trace publish failed: {_pub_err}")
        return True

"""
Назначение: BC-2 — feature gate BC2_ENABLED (default OFF = полный no-op, INV-BC2-NOOP), ленивая инициализация Store/коллектора/подписки на CONCLUSION_FORMED, Phase 9 wrapper: drain collector → bridge → store. Симметрично conclusion_runtime.py.
Зависимости: app.services.npc.expectation_store, app.services.npc.expectation_bridge, app.domain.conclusions, app.services.events.event_types; logging, os, typing.
Основные сущности: bc2_enabled, ensure_expectation_layer, run_expectation_formation_guarded, _reconstruct_conclusion.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def bc2_enabled() -> bool:
    """Env-флаг BC2_ENABLED (default OFF = полный no-op).

    Прецедент BC1_ENABLED (conclusion_runtime.py:22-25).
    """
    return os.environ.get("BC2_ENABLED", "").strip().lower() in (
        "1", "true", "on", "yes",
    )


def ensure_expectation_layer(orchestrator: Any) -> None:
    """Ленивая инициализация Store + подписка на CONCLUSION_FORMED.

    Симметрично ensure_conclusion_layer (conclusion_runtime.py:33-65).
    Идемпотентно: повторные ensure не плодят подписчиков (флаг-гвард).
    """
    if not bc2_enabled():
        return
    from app.services.events.event_types import EventType
    from app.services.npc.expectation_store import ContextualExpectationStore

    if getattr(orchestrator, "_expectation_store", None) is None:  # noqa: ENIGMA002
        orchestrator._expectation_store = ContextualExpectationStore()
    if getattr(orchestrator, "_expectation_collector", None) is None:  # noqa: ENIGMA002
        orchestrator._expectation_collector = []
    if getattr(orchestrator, "_expectation_collector_subscribed", False):
        return
    orchestrator._expectation_collector_subscribed = True
    bus = orchestrator._get_event_bus()

    def _on_conclusion_formed(event: Any) -> None:
        if getattr(event, "type", None) == EventType.CONCLUSION_FORMED.value:  # noqa: ENIGMA002
            orchestrator._expectation_collector.append(event)

    bus.subscribe(EventType.CONCLUSION_FORMED, _on_conclusion_formed)
    logger.info("[BC2] Expectation layer ON (dormant->wired, BC2_ENABLED=1)")


def run_expectation_formation_guarded(ctx: Any, orchestrator: Any) -> None:
    """Wrapper Фазы 9 (после BC-1 wrapper'а): collector → bridge → store.

    Гарантии — mirror run_conclusion_formation_guarded
    (conclusion_runtime.py:68-103):
    (1) OFF → return (INV-BC2-NOOP);
    (2) ensure идемпотентен;
    (3) пустой коллектор → bridge не вызывается (NO-VACUUM);
    (4) отказ слоя → warning, тик жив (D5).
    """
    if not bc2_enabled():
        return
    collector = getattr(orchestrator, "_expectation_collector", None) or []  # noqa: ENIGMA002
    try:
        ensure_expectation_layer(orchestrator)
        store = getattr(orchestrator, "_expectation_store", None)  # noqa: ENIGMA002
        if store is None:
            return
        if not collector:
            return

        from app.services.npc.expectation_bridge import (
            build_expectation_context,
            conclusion_to_expectations,
        )

        current_tick = int(getattr(ctx, "tick_number", 0))
        for formed_event in collector:
            payload = getattr(formed_event, "payload", None) or {}  # noqa: ENIGMA002
            conclusion = _reconstruct_conclusion(payload)
            if conclusion is None:
                continue
            context = build_expectation_context(conclusion, ctx, orchestrator)
            for expectation in conclusion_to_expectations(
                conclusion, context, current_tick
            ):
                store.apply(expectation)
        if collector:
            logger.info(
                f"[BC2] tick={current_tick}: processed {len(collector)} "
                f"conclusion(s) -> expectation store (size={len(store)})"
            )
    except Exception as _bc2_err:  # noqa: ENIGMA001
        logger.warning(f"[BC2] expectation formation failed: {_bc2_err}")
    finally:
        collector.clear()


def _reconstruct_conclusion(payload: dict) -> Optional[Any]:
    """Восстановление ConclusionRecord из payload CONCLUSION_FORMED.

    Payload не содержит conclusion_id, но содержит все компоненты
    идентичности (owner, subject, predicate, object, source). Реконструкция
    через публичный ConclusionRecord.conclusion_id() — не угадываем правило.

    formed_tick=0 — BC-1 пишет 0 (не наша зона); tick берётся из ctx
    в run_expectation_formation_guarded.
    """
    try:
        from app.domain.conclusions import (
            CONCLUSION_SOURCE_DIRECT,
            ConclusionPredicate,
            ConclusionRecord,
        )

        return ConclusionRecord(
            owner_id=str(payload.get("owner_id", "")),
            subject=str(payload.get("subject", "")),
            predicate=ConclusionPredicate(payload.get("predicate")),
            object=str(payload.get("object", "")),
            confidence=float(payload.get("confidence", 0.0)),
            evidence=tuple(payload.get("evidence") or ()),
            trace_id=str(payload.get("trace_id", "")),
            causal_parent=str(payload.get("causal_parent", "")),
            source=str(payload.get("source", CONCLUSION_SOURCE_DIRECT)),
            formed_tick=0,
        )
    except Exception as _err:  # noqa: ENIGMA001
        logger.warning(f"[BC2] conclusion reconstruct failed: {_err}")
        return None
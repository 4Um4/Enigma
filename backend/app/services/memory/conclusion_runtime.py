# backend/app/services/memory/conclusion_runtime.py
"""
Назначение: BC-1/ADR-O-381 — runtime-проводка слоя (dormant): env-флаг
    BC1_ENABLED (default OFF = полный no-op, INV-BC1-NOOP), ленивая
    инициализация store/gate при ON, инвокация ConclusionEngine в Фазе 9
    (wrapper оркестратора), drain коллектора. Паттерн G2 (ADR-O-378):
    guarded-функция с деградацией, не падение тика (D5).
Зависимости: app.domain.conclusions, app.services.memory.conclusion_engine,
    app.services.memory.conclusion_gate, app.services.npc.conclusion_store.
Основные сущности: bc1_enabled, run_conclusion_formation_guarded.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def bc1_enabled() -> bool:
    """Env-флаг BC1_ENABLED (default OFF = полный no-op; прецедент
    W3_G2_ENABLED, affordance_facts.py:43-50)."""
    return os.environ.get("BC1_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def ensure_conclusion_layer(orchestrator: Any) -> None:
    """Ленивая инициализация store/gate/подписки коллектора при ON.

    Вызывается из wrapper'а Фазы 9 (каждый тик, идемпотентно —
    атрибут-гвард). Подписка коллектора: EXPERIENCE_DELTA_COMMITTED —
    append в orchestrator._conclusion_collector; читается и очищается
    этим же wrapper'ом (drain в run_conclusion_formation_guarded).
    """
    if not bc1_enabled():
        return
    from app.services.events.event_types import EventType
    from app.services.memory.conclusion_gate import ConclusionGate
    from app.services.npc.conclusion_store import ConclusionStore

    # Стор, восстановленный из персистенции (build_game_loop), НЕ
    # перезаписываем — до-создаются только гейт и подписка.
    if getattr(orchestrator, "_conclusion_store", None) is None:
        orchestrator._conclusion_store = ConclusionStore()
    if getattr(orchestrator, "_conclusion_gate", None) is None:
        orchestrator._conclusion_gate = ConclusionGate()
    # Подписка однократна: повторные ensure (init + каждый тик) не
    # плодят подписчиков (флаг-гвард).
    if getattr(orchestrator, "_conclusion_collector_subscribed", False):
        return
    orchestrator._conclusion_collector_subscribed = True
    bus = orchestrator._get_event_bus()

    def _on_experience_delta(event: Any) -> None:
        if getattr(event, "type", None) == EventType.EXPERIENCE_DELTA_COMMITTED.value:
            orchestrator._conclusion_collector.append(event)

    bus.subscribe(EventType.EXPERIENCE_DELTA_COMMITTED, _on_experience_delta)
    logger.info("[BC1] Conclusion layer ON (dormant->wired, BC1_ENABLED=1)")


def run_conclusion_formation_guarded(ctx: Any, orchestrator: Any) -> None:
    """Wrapper Фазы 9: ensure → engine → gate → store; drain коллектора.

    Гарантии: (1) OFF → return (ноль вычислений, атрибуты не создаются —
    INV-BC1-NOOP); (2) ensure идемпотентен (init-вызов уже создал слой;
    здесь — только ремонт после restore); (3) пустой коллектор → engine
    не вызывается (NO-VACUUM); (4) отказ слоя → warning, тик жив (D5).
    """
    if not bc1_enabled():
        return
    collector = getattr(orchestrator, "_conclusion_collector", None) or []
    try:
        ensure_conclusion_layer(orchestrator)
        store = getattr(orchestrator, "_conclusion_store", None)
        gate = getattr(orchestrator, "_conclusion_gate", None)
        if store is None or gate is None:
            return
        if not collector:
            return
        from app.services.memory.conclusion_engine import (
            generate_conclusion_proposals,
        )

        proposals = generate_conclusion_proposals(collector)
        for proposal in proposals:
            gate.apply(proposal, consumer_dispatch=store.apply)
        if proposals:
            logger.info(
                f"[BC1] tick={ctx.tick_number}: {len(proposals)} proposal(s) "
                f"-> gate"
            )
    except Exception as _bc1_err:  # noqa: ENIGMA001
        # D5: деградация канала, не тика (паттерн run_affordance_facts_guarded)
        logger.warning(f"[BC1] conclusion formation failed: {_bc1_err}")
    finally:
        collector.clear()

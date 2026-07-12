"""
path: /project/backend/app/services/phases/post_decision.py
Назначение: Инкапсуляция логики Фаз 6 и 7 (IntentEventAdapter, Windup Registry).
Зависимости: app.services.events.intent_event_adapter, app.domain.action_windup
Основные сущности: run_phase_6_post_decision, run_phase_7_windup_resolution
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_phase_6_post_decision(ctx: Any, orchestrator: Any) -> None:
    """IntentEventAdapter: CommunicationIntent → EventDTO (Устав §3.3).

    Единственная легальная точка CommunicationIntent → EventDTO.
    Когда Phase 5 начнёт производить CommunicationIntent — провода уже готовы.
    ADR-O-310: WindupWriteGate — перехват ATTACK для создания ActionWindup.
    """
    if not ctx.communication_intents:
        from app.services.npc.decision_hub import DecisionHub

        _verbal = sum(
            1
            for d in ctx.decisions
            if getattr(d, "intent", "") in DecisionHub._VERBAL_INTENTS
        )
        if _verbal > 0:
            from app.errors import SimulationIntegrityError

            raise SimulationIntegrityError(
                invariant_id="INV-DIALOGUE-PIPELINE",
                message=(
                    f"Phase 6: ctx.communication_intents пуст, но Phase 5 вернула "
                    f"{_verbal} вербальных решений."
                ),
                suspect_files=[
                    "backend/app/services/npc/decision_hub.py:_build_communication (строка 286)",
                    "backend/app/services/npc/life_engine.py:719 (communication_intents.append)",
                    "backend/app/services/pipeline_runner.py:87 (ctx.communication_intents = mutation...)",
                ],
                file=__file__,
                line=23,
            )
        return

    from app.services.events.event_bus import get_event_bus
    from app.services.events.intent_event_adapter import IntentEventAdapter

    bus = get_event_bus()
    adapter = IntentEventAdapter()
    converted = 0
    windups_created = 0

    for intent in ctx.communication_intents:
        # ADR-O-313: Перехват разговорных интентов в Universal Task Layer.
        # Разговор больше не является немедленным событием. Это задача (QueuedTask).
        # Всё, что не атака (уходит в Windup), считается диалогом/социальным действием.
        if getattr(intent, "intent_type", "") != "attack":
            from app.domain.communication import DialogueRequest
            from app.domain.execution import QueuedTask, TaskKind, TaskPriority

            # S118 FIX: Используем audience, так как в CommunicationIntent нет поля target_id.
            # Если audience="all", передаём None, чтобы TaskScheduler выбрал цель через SpatialQueryService.
            _target_id = intent.audience if intent.audience != "all" else None

            _req = DialogueRequest(
                topic=intent.topic,
                target_id=_target_id,
                exposure=intent.exposure_level,
                intent_type=intent.intent_type,
            )

            _task = QueuedTask(
                task_id=f"task-{ctx.tick_number}-{intent.speaker}-dlg",
                tick=ctx.tick_number,
                counter=len(ctx.communication_intents),
                kind=TaskKind.DIALOGUE,
                priority=TaskPriority.NORMAL,
                creator_system="DecisionHub",
                owner_id=intent.speaker,
                target_ids=[intent.target_id] if intent.target_id else [],
                payload=_req,
                created_tick=ctx.tick_number,
            )

            if "pending_tasks" not in ctx.scene_state:
                ctx.scene_state["pending_tasks"] = []
            # Ручная сериализация, чтобы избежать проблем с frozen dataclasses и Enums
            _task_dict = {
                "task_id": _task.task_id,
                "tick": _task.tick,
                "counter": _task.counter,
                "kind": _task.kind.value,
                "priority": _task.priority.value,
                "state": _task.state.value,
                "creator_system": _task.creator_system,
                "owner_id": _task.owner_id,
                "target_ids": _task.target_ids,
                "payload": {
                    "topic": _req.topic,
                    "target_id": _req.target_id,
                    "exposure_semantic": _req.exposure.semantic,
                    "intent_type": _req.intent_type,
                },
                "created_tick": _task.created_tick,
            }
            ctx.scene_state["pending_tasks"].append(_task_dict)
            continue

        event = adapter.to_event(intent)

        # ADR-O-310: Windup Write Gate
        if getattr(intent, "intent_type", "") == "attack":
            from app.domain.action_windup import ActionWindup, WindupStatus

            _actor_id = getattr(intent, "speaker", "")
            _target_id = getattr(intent, "target_id", "")

            if _actor_id and _target_id:
                # B1.5-FIX: Изоляция по campaign_id (ключ - кортеж).
                _reg_key = (ctx.campaign_id, _actor_id)
                if _reg_key not in orchestrator._windup_registry:
                    orchestrator._windup_registry[_reg_key] = []

                # B1.5-FIX: Защита от накопления (Deduplication).
                _has_active = any(
                    w.target_id == _target_id
                    and w.action_type == "attack"
                    and w.status == WindupStatus.PENDING
                    for w in orchestrator._windup_registry[_reg_key]
                )

                if not _has_active:
                    import uuid

                    # DEBT-310.1: Сохраняем сам интент, генерируем ID для него.
                    _intent_id = uuid.uuid4().hex
                    orchestrator._pending_intents[_intent_id] = intent

                    from app.core.constants import ATTACK_WINDUP_DURATION_TICKS

                    # Создаём окно подготовки (BUG-P3-07: длительность вынесена в константу)
                    windup = ActionWindup(
                        actor_id=_actor_id,
                        target_id=_target_id,
                        action_type="attack",
                        started_tick=ctx.tick_number,
                        duration_ticks=ATTACK_WINDUP_DURATION_TICKS,
                        status=WindupStatus.PENDING,
                        held_intent_id=_intent_id,  # DEBT-310.1: Pure temporal gate
                    )
                    # Добавляем в стек подготовок актёра (на уровне Orchestrator)
                    orchestrator._windup_registry[_reg_key].append(windup)
                    windups_created += 1

                    # ADR-O-310: НЕ публикуем EventDTO сейчас. Он будет опубликован в Фазе 7.
                    continue  # Пропускаем bus.publish(event) ниже

        bus.publish(event)
        converted += 1

    logger.info(
        f"[TICK_ORCH] Фаза 6: {converted} intents → EventDTO, {windups_created} windups created"
    )


def run_phase_7_windup_resolution(ctx: Any, orchestrator: Any) -> None:
    """ADR-O-310: Windup Execution Gate.

    Проверяет self._windup_registry на завершённые подготовки.
    Если windup завершён (started_tick + duration_ticks <= ctx.tick_number),
    реконструирует CommunicationIntent из ActionCommitment и передаёт в IntentEventAdapter.
    """
    from app.domain.action_windup import WindupStatus
    from app.services.events.event_bus import get_event_bus
    from app.services.events.intent_event_adapter import IntentEventAdapter

    bus = get_event_bus()
    adapter = IntentEventAdapter()
    executed_windups = 0

    for _reg_key, windups in list(orchestrator._windup_registry.items()):
        _campaign_id, _actor_id = _reg_key
        if _campaign_id != ctx.campaign_id:
            continue

        updated_windups = []
        for windup in windups:
            if windup.status == WindupStatus.PENDING:
                if windup.started_tick + windup.duration_ticks <= ctx.tick_number:
                    # DEBT-310.1: Windup completed! Pure release of held intent.
                    if windup.held_intent_id:
                        _held_intent = orchestrator._pending_intents.pop(
                            windup.held_intent_id, None
                        )
                        if _held_intent:
                            _actor_id = getattr(_held_intent, "speaker", "")
                            _target_id = getattr(_held_intent, "target_id", "")

                            # DEBT-310.2: Minimal Guard - Stale Intent Validation
                            _is_stale = False
                            _reason = ""

                            # 1. Actor validation
                            _actor_dict = next(
                                (
                                    n
                                    for n in ctx.all_npcs_raw
                                    if n.get("npc_id") == _actor_id
                                    or n.get("id") == _actor_id
                                ),
                                None,
                            )
                            if not _actor_dict:
                                _is_stale, _reason = True, "actor_missing"
                            elif (
                                _actor_dict.get("body_state", {}).get("life_status")
                                == "DEAD"
                            ):
                                _is_stale, _reason = True, "actor_dead"

                            # 2. Target validation (if actor is valid)
                            if not _is_stale and _target_id:
                                if _target_id == "player":
                                    if "player" not in ctx.scene_state.get(
                                        "npc_positions", {}
                                    ):
                                        _is_stale, _reason = (
                                            True,
                                            "target_player_missing",
                                        )
                                else:
                                    _target_dict = next(
                                        (
                                            n
                                            for n in ctx.all_npcs_raw
                                            if n.get("npc_id") == _target_id
                                            or n.get("id") == _target_id
                                        ),
                                        None,
                                    )
                                    if (
                                        _target_dict
                                        and _target_dict.get("body_state", {}).get(
                                            "life_status"
                                        )
                                        == "DEAD"
                                    ):
                                        _is_stale, _reason = True, "target_dead"
                                    elif (
                                        not _target_dict
                                        and _target_id
                                        not in ctx.scene_state.get("npc_positions", {})
                                    ):
                                        _is_stale, _reason = True, "target_missing"

                            if _is_stale:
                                logger.info(
                                    f"[PHASE_7][STALE_INTERRUPT] npc={_actor_id} target={_target_id} reason={_reason}"
                                )
                                windup = dataclasses.replace(
                                    windup, status=WindupStatus.INTERRUPTED
                                )
                            else:
                                event = adapter.to_event(_held_intent)
                                bus.publish(event)
                                executed_windups += 1
                                windup = dataclasses.replace(
                                    windup, status=WindupStatus.COMPLETED
                                )
                        else:
                            windup = dataclasses.replace(
                                windup, status=WindupStatus.COMPLETED
                            )
                    else:
                        windup = dataclasses.replace(
                            windup, status=WindupStatus.COMPLETED
                        )
            if windup.status == WindupStatus.PENDING:
                updated_windups.append(windup)

        orchestrator._windup_registry[_reg_key] = [
            w for w in updated_windups if w.status == WindupStatus.PENDING
        ]

    if executed_windups > 0:
        logger.info(
            f"[TICK_ORCH] Фаза 7: {executed_windups} windups executed (EventDTO published)"
        )

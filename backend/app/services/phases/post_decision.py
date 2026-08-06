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

            _svc = ctx.npc_services
            _memory_mgr = _svc.memory_manager if _svc else getattr(orchestrator, "_memory_manager", None)
            if _memory_mgr is None:
                logger.error("MemoryManager missing in both NpcServices and Orchestrator. Check wiring.")
            _intent_type = getattr(intent, "intent_type", "")
            # ADR-O-342: Hard Contract (Принцип 2). Если нет STM (истории разговора),
            # нельзя начинать содержательный диалог. Принудительно меняем на approach.
            # Исключение: soliloquy (разговор с самим собой) — STM не нужен.
            if _memory_mgr and _target_id and _target_id not in ("all", "soliloquy"):
                _stm_check = _memory_mgr.get_stm_prompt_block_pair(
                    ctx.campaign_id, intent.speaker, _target_id
                )
                if not _stm_check and _intent_type not in ("greeting", "approach"):
                    logger.debug(f"[POST_DECISION] Intercept {intent.speaker} -> {_target_id}: No STM, changing intent '{_intent_type}' to 'approach'")
                    _intent_type = "approach"

            # T-04: Формируем npc_npc_context (историю взаимодействий с целью)
            _history_text = ""
            if _svc and _svc.memory_manager and _target_id and _target_id != "all":
                try:
                    _cache = _svc.memory_manager.load_narrative_from_sqlite(
                        ctx.campaign_id, intent.speaker
                    )
                    _memories = _svc.memory_manager.recall(
                        narrative_cache=_cache,
                        target_npc_id=_target_id,
                        pressure=0,
                    )
                    if _memories:
                        _history_text = " ".join(
                            getattr(_m, 'summary', getattr(_m, 'description', str(_m)))
                            for _m in _memories[:3]
                        )
                except Exception as _e:
                    logger.warning(f"[POST_DECISION] T-04: Failed to recall memory for {intent.speaker}: {_e}")

            # BUG-DL-04: Генерируем thread_id для изоляции нити диалога
            import uuid
            _thread_id = getattr(intent, "thread_id", "") or f"thread-{uuid.uuid4().hex[:8]}"

            # V8-DLG-10 FIX: Собираем prepared_prompt через VerbalizationContext
            _prepared_prompt = ""
            if _svc and _svc.memory_manager:
                try:
                    import copy
                    from app.services.npc.npc_tick_pipeline import build_verbalization_context
                    from app.services.npc.npc_loader import load_l2_state_from_runtime_dict, load_profile_from_legacy_json

                    _npc_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == intent.speaker or n.get("id") == intent.speaker), None)
                    if _npc_dict:
                        _npc_dict_copy = copy.deepcopy(dict(_npc_dict))
                        _profile_l0 = load_profile_from_legacy_json(_npc_dict_copy)
                        _state_l2 = load_l2_state_from_runtime_dict(_npc_dict_copy)

                        _hub_event = ctx.interventions[0] if ctx.interventions else None
                        _raw_input = getattr(_hub_event, "payload", {}).get("raw_input", "") if _hub_event else ""

                        _v_ctx = build_verbalization_context(
                            memory_manager=_svc.memory_manager,
                            profile_l0=_profile_l0,
                            state_for_llm=_state_l2,
                            intent_value=_intent_type,  # ADR-O-342: Используем перехваченный тип
                            intent_target=_target_id,
                            hub_event=_hub_event,
                            raw_input=_raw_input,
                            campaign_id=ctx.campaign_id,
                            topic=intent.topic
                        )
                        
                        # V8-DLG-10 FIX: Собираем статическую часть промпта из VerbalizationContext.
                        # Динамическая часть (STM, beliefs) будет добавлена в DialogueExecutor.
                        _prepared_prompt = (
                            f"Твоё имя: {_v_ctx.npc_name}. "
                            f"Краткое описание твоей натуры: {_v_ctx.backstory or 'неизвестно'}. "
                        )
                        if _v_ctx.voice_profile:
                            _prepared_prompt += f"Твоя манера речи: {_v_ctx.voice_profile}. "
                        if _v_ctx.author_notes:
                            _prepared_prompt += f"Важные ограничения: {_v_ctx.author_notes}. "
                        if _v_ctx.emotional_nuance:
                            _prepared_prompt += f"Твоё текущее состояние: {_v_ctx.emotional_nuance}. "
                except Exception as _e:
                    logger.warning(f"[POST_DECISION] V8-DLG-10: Failed to build prepared_prompt for {intent.speaker}: {_e}")

            _req = DialogueRequest(
                topic=intent.topic,
                target_id=_target_id,
                exposure=intent.exposure_level,
                intent_type=_intent_type,  # BUG-PERC-032 FIX: Используем перехваченный _intent_type (approach если нет STM)
                emotional_state=intent.emotional_state,
                npc_npc_context=_history_text,
                thread_id=_thread_id,
                prepared_prompt=_prepared_prompt,
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
                    "emotional_state": _req.emotional_state,
                    "npc_npc_context": _req.npc_npc_context,
                    "thread_id": _req.thread_id,
                    "prepared_prompt": _req.prepared_prompt, # V8-DLG-10 FIX
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

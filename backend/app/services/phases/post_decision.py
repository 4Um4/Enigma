"""
path: /project/backend/app/services/phases/post_decision.py
Назначение: Инкапсуляция логики Фаз 6 и 7 (IntentEventAdapter, Windup Registry).
Зависимости: app.services.events.intent_event_adapter, app.domain.action_windup
Основные сущности: run_phase_6_post_decision, run_phase_7_windup_resolution
"""
from __future__ import annotations

# S203.4 (Э6, Н-40): ключи scene_state для персистентности RAM-структур
# оркестратора. Tuple-ключ (campaign_id, actor_id) → строковый для JSON.
_KEY_WINDUP_REGISTRY = "windup_registry"
_KEY_HELD_INTENTS = "windup_held_intents"  # НЕ "pending_tasks" — разные сущности


def _windup_key(campaign_id: str, actor_id: str) -> str:
    """F3: строковый ключ для JSON-сериализации tuple-ключа."""
    return f"{campaign_id}::{actor_id}"

import copy
import dataclasses
import logging
import uuid
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
        # Windowed-действия (attack, steal) уходят в Windup (S209), всё остальное —
        # диалог/социальное действие.
        if getattr(intent, "intent_type", "") not in ("attack", "steal"):  # noqa: ENIGMA002
            from app.domain.communication import DialogueRequest
            from app.domain.execution import QueuedTask, TaskKind, TaskPriority

            # S118 FIX: Используем audience, так как в CommunicationIntent нет поля target_id.
            # Если audience="all", передаём None, чтобы TaskScheduler выбрал цель через SpatialQueryService.
            _target_id = intent.audience if intent.audience != "all" else None  # noqa: ENIGMA001

            _svc = ctx.npc_services
            _memory_mgr = _svc.memory_manager if _svc else getattr(orchestrator, "_memory_manager", None)  # noqa: ENIGMA002
            if _memory_mgr is None:
                logger.error("MemoryManager missing in both NpcServices and Orchestrator. Check wiring.")
            _intent_type = getattr(intent, "intent_type", "")  # noqa: ENIGMA002
            # ADR-O-342: Hard Contract (Принцип 2). Если нет STM (истории разговора),
            # нельзя начинать содержательный диалог. Принудительно меняем на approach.
            # Исключение: soliloquy (разговор с самим собой) — STM не нужен.
            if _memory_mgr and _target_id and _target_id not in ("all", "soliloquy"):
                _stm_check = _memory_mgr.get_stm_prompt_block_pair(
                    ctx.campaign_id, intent.speaker, _target_id
                )
                # S199.2: Классификация интентов для обхода ADR-O-342.
                # claim-producing действия (warn, intimidate) не требуют контекста диалога (STM)
                # и могут быть материализованы детерминированно.
                _CLAIM_PRODUCING_INTENTS = {"warn", "intimidate"}
                if not _stm_check and _intent_type not in ("greeting", "approach") and _intent_type not in _CLAIM_PRODUCING_INTENTS:
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
            _thread_id = getattr(intent, "thread_id", "") or f"thread-{uuid.uuid4().hex[:8]}"  # noqa: ENIGMA002

            # V8-DLG-10 FIX: Собираем prepared_prompt через VerbalizationContext
            _prepared_prompt = ""
            if _svc and _svc.memory_manager:
                try:
                    from app.services.npc.npc_loader import (
                        load_l2_state_from_runtime_dict,
                        load_profile_from_legacy_json,
                    )
                    from app.services.npc.npc_tick_pipeline import build_verbalization_context

                    _npc_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == intent.speaker or n.get("id") == intent.speaker), None)
                    if _npc_dict:
                        _npc_dict_copy = copy.deepcopy(dict(_npc_dict))
                        _profile_l0 = load_profile_from_legacy_json(_npc_dict_copy)
                        _state_l2 = load_l2_state_from_runtime_dict(_npc_dict_copy)

                        _hub_event = ctx.interventions[0] if ctx.interventions else None  # noqa: ENIGMA001
                        _raw_input = getattr(_hub_event, "payload", {}).get("raw_input", "") if _hub_event else ""  # noqa: ENIGMA002

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

            # S197: Конвертация Proposition в dict для сериализуемого DialogueRequest
            _prop = getattr(intent, "proposition", None)  # noqa: ENIGMA002
            _prop_data = None
            if _prop:
                _prop_data = {
                    "subject_id": _prop.subject_id,
                    "predicate": _prop.predicate.value,
                    "object_id": _prop.object_id,
                    "polarity": _prop.polarity
                }

            _req = DialogueRequest(
                topic=intent.topic,
                target_id=_target_id,
                exposure=intent.exposure_level,
                intent_type=_intent_type,
                emotional_state=intent.emotional_state,
                npc_npc_context=_history_text,
                thread_id=_thread_id,
                prepared_prompt=_prepared_prompt,
                proposition=_prop_data,
            )

            # M-30 FIX: Добавляем counter в task_id для предотвращения коллизий
            _task_counter = len(ctx.communication_intents)
            _task = QueuedTask(
                task_id=f"task-{ctx.tick_number}-{intent.speaker}-{_task_counter}-dlg",
                tick=ctx.tick_number,
                counter=_task_counter,
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

            # M-29 FIX: Очищаем pending_tasks от старых задач (оставляем только текущего тика)
            # S203.4 (terminal-mapping v2): вычищенные = тихая смерть → EXPIRED
            # строго по executor_ref (mirror_task_expired_by_ref).
            from app.services.action.commitment_registry import CommitmentRegistry

            for _old in ctx.scene_state["pending_tasks"]:
                if _old.get("tick", 0) < ctx.tick_number - 1:
                    CommitmentRegistry.mirror_task_expired_by_ref(
                        ctx.scene_state,
                        _old.get("owner_id", ""),
                        _old.get("task_id", ""),
                        ctx.tick_number,
                    )
            ctx.scene_state["pending_tasks"] = [
                t for t in ctx.scene_state["pending_tasks"]
                if t.get("tick", 0) >= ctx.tick_number - 1
            ]
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
                    "proposition": _req.proposition, # S197: Добавлено для сериализации
                },
                "created_tick": _task.created_tick,
            }
            ctx.scene_state["pending_tasks"].append(_task_dict)
            # S203.4 (Ц1, D-8): canonical-класс = produces_claim ∨ proposition —
            # получает владельца; ambient — non-ownership Sims-слой (ADR-O-365).
            from app.domain.intent_profiles import produces_claim

            if produces_claim(_intent_type) or bool(
                _task_dict["payload"].get("proposition")
            ):
                from app.domain.action_priority import resolve_candidate_priority
                from app.services.action.commitment_registry import CommitmentRegistry

                CommitmentRegistry.mirror_task_committed(
                    ctx.scene_state,
                    ctx.tick_number,
                    intent.speaker,
                    cause=f"dialogue_task:{_intent_type}",
                    task_id=_task.task_id,
                    priority=resolve_candidate_priority(intent_type=_intent_type),
                )
            continue

        event = adapter.to_event(intent)

        # ADR-O-310: Windup Write Gate (S209: параметризован attack|steal)
        _gate_intent_type = getattr(intent, "intent_type", "")  # noqa: ENIGMA002
        if _gate_intent_type in ("attack", "steal"):
            from app.domain.action_windup import ActionWindup, WindupStatus

            _actor_id = getattr(intent, "speaker", "")  # noqa: ENIGMA002
            _target_id = getattr(intent, "target_id", "")  # noqa: ENIGMA002

            if _actor_id and _target_id:
                # S203.4 (Э6, Н-40): персистентность через scene_state (строковый
                # ключ; tuple-ключ не сериализуется в JSON). F3.
                _wkey = _windup_key(ctx.campaign_id, _actor_id)
                _windup_store = ctx.scene_state.setdefault(_KEY_WINDUP_REGISTRY, {})
                _windup_list = _windup_store.setdefault(_wkey, [])

                # B1.5-FIX: Защита от накопления (Deduplication).
                _has_active = any(
                    w["target_id"] == _target_id
                    and w["action_type"] == _gate_intent_type
                    and w["status"] == WindupStatus.PENDING.value
                    for w in _windup_list
                )

                if not _has_active:

                    # S203.4 (Э5-c): зеркало владения ДО windup — commitment_id
                    # становится held_intent_id (детерминизм, закон №4; Н-31 не
                    # размножается). Коллизия → legacy uuid4-путь без владения.
                    from app.services.action.commitment_registry import CommitmentRegistry

                    _w_cm = CommitmentRegistry.mirror_windup_committed(
                        ctx.scene_state,
                        ctx.tick_number,
                        _actor_id,
                        action_type=_gate_intent_type,
                        target_id=_target_id,
                        cause=f"windup:{_gate_intent_type}",
                    )
                    _intent_id = (
                        _w_cm["commitment_id"] if _w_cm else uuid.uuid4().hex
                    )
                    # S203.4 (Э6): held intent → scene_state (персистентность).
                    _held_store = ctx.scene_state.setdefault(_KEY_HELD_INTENTS, {})
                    _held_store[_intent_id] = intent.to_dict()

                    from app.core.constants import (
                        ATTACK_WINDUP_DURATION_TICKS,
                        STEAL_WINDUP_DURATION_TICKS,
                    )

                    # S209: steal — windowed action: 2 тика подкрадывания =
                    # окно, где свидетель может заметить подготовку (драматургия slice).
                    _is_steal = _gate_intent_type == "steal"
                    windup = ActionWindup(
                        actor_id=_actor_id,
                        target_id=_target_id,
                        action_type=_gate_intent_type,
                        started_tick=ctx.tick_number,
                        duration_ticks=(
                            STEAL_WINDUP_DURATION_TICKS
                            if _is_steal
                            else ATTACK_WINDUP_DURATION_TICKS
                        ),
                        status=WindupStatus.PENDING,
                        held_intent_id=_intent_id,
                    )
                    # S203.4 (Э6): windup → scene_state как dict (персистентность).
                    _windup_list.append(windup.to_dict())
                    windups_created += 1

                    continue

        bus.publish(event)
        converted += 1

    logger.info(
        f"[TICK_ORCH] Фаза 6: {converted} intents → EventDTO, {windups_created} windups created"
    )


def _gate_type_is_object_action(action_type: str) -> bool:
    """S209: действия, чья цель — объект мира, а не сущность (кража).
    Расширение списка — с мини-ADR на каждое новое действие."""
    return action_type in ("steal",)


def run_phase_7_windup_resolution(ctx: Any, orchestrator: Any) -> None:
    """ADR-O-310: Windup Execution Gate.

    Проверяет self._windup_registry на завершённые подготовки.
    Если windup завершён (started_tick + duration_ticks <= ctx.tick_number),
    реконструирует CommunicationIntent из ActionCommitment и передаёт в IntentEventAdapter.
    """
    from app.domain.action_windup import ActionWindup, WindupStatus
    from app.services.events.event_bus import get_event_bus
    from app.services.events.intent_event_adapter import IntentEventAdapter

    bus = get_event_bus()
    adapter = IntentEventAdapter()
    executed_windups = 0

    # S203.4 (Э6, Н-40): чтение из scene_state (персистентность).
    _windup_store = ctx.scene_state.get(_KEY_WINDUP_REGISTRY) or {}
    _held_store = ctx.scene_state.get(_KEY_HELD_INTENTS) or {}

    for _wkey, _windup_dicts in list(_windup_store.items()):
        # F3: обратный трансформ строкового ключа
        _parts = _wkey.split("::", 1)
        if len(_parts) != 2:
            continue
        _campaign_id, _actor_id = _parts
        if _campaign_id != ctx.campaign_id:
            continue

        updated_windups = []
        for _wdict in _windup_dicts:
            windup = ActionWindup.from_dict(_wdict)
            if windup.status == WindupStatus.PENDING:
                if windup.started_tick + windup.duration_ticks <= ctx.tick_number:
                    # DEBT-310.1: Windup completed! Pure release of held intent.
                    if windup.held_intent_id:
                        _held_dict = _held_store.pop(windup.held_intent_id, None)
                        if _held_dict:
                            from app.domain.communication import CommunicationIntent

                            _held_intent = CommunicationIntent.from_dict(_held_dict)
                            _actor_id = getattr(_held_intent, "speaker", "")  # noqa: ENIGMA002
                            _target_id = getattr(_held_intent, "target_id", "")  # noqa: ENIGMA002

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
                                elif _gate_type_is_object_action(windup.action_type):
                                    # S209: кража целит в ОБЪЕКТ мира (сундук, золото),
                                    # не в сущность. Валидация существования живой цели
                                    # неприменима: объект не обязан быть в npc_positions.
                                    # Наличие цели — ответственность DecisionHub
                                    # (target resolve на этапе выбора интента).
                                    pass
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
            # S203.4 (Э5-c terminals): windup достиг терминала — зеркало.
            # Одна точка после всего if/else (4 ветки COMPLETED + 1 INTERRUPTED).
            if windup.status == WindupStatus.INTERRUPTED:
                from app.domain.action_commitment import INTERRUPT_WINDUP_STALE_INTENT
                from app.services.action.commitment_registry import CommitmentRegistry

                CommitmentRegistry.mirror_task_terminal(
                    ctx.scene_state, windup.actor_id, ctx.tick_number,
                    "INTERRUPTED",
                    interrupt_reason=INTERRUPT_WINDUP_STALE_INTENT,
                    executor="windup",
                )
            elif windup.status == WindupStatus.COMPLETED:
                from app.services.action.commitment_registry import CommitmentRegistry

                CommitmentRegistry.mirror_task_terminal(
                    ctx.scene_state, windup.actor_id, ctx.tick_number,
                    "COMPLETED", executor="windup",
                )

            if windup.status == WindupStatus.PENDING:
                updated_windups.append(windup)

        # H-37 FIX: Сохраняем PENDING для audit trail (COMPLETED/INTERRUPTED
        # отфильтрованы выше). S203.4 (Э6): запись в scene_state (персистентность).
        _windup_store[_wkey] = [w.to_dict() for w in updated_windups] if updated_windups else []
        if not _windup_store[_wkey]:
            del _windup_store[_wkey]

    if executed_windups > 0:
        logger.info(
            f"[TICK_ORCH] Фаза 7: {executed_windups} windups executed (EventDTO published)"
        )

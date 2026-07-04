"""
path: /project/backend/app/services/phases/post_decision.py
Назначение: Инкапсуляция логики Фаз 6 и 7 (IntentEventAdapter, Windup Registry).
Зависимости: app.services.events.intent_event_adapter, app.domain.action_windup
Основные сущности: run_phase_6_post_decision, run_phase_7_windup_resolution
"""

from __future__ import annotations
from typing import Any
import logging
import dataclasses

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
        event = adapter.to_event(intent)
        
        # ADR-O-310: Windup Write Gate
        if getattr(intent, 'intent_type', '') == "attack":
            from app.domain.action_windup import ActionWindup, WindupStatus, ActionCommitment
            _actor_id = getattr(intent, 'speaker', '')
            _target_id = getattr(intent, 'target_id', '')
            
            if _actor_id and _target_id:
                # B1.5-FIX: Изоляция по campaign_id (ключ - кортеж).
                _reg_key = (ctx.campaign_id, _actor_id)
                if _reg_key not in orchestrator._windup_registry:
                    orchestrator._windup_registry[_reg_key] = []
                
                # B1.5-FIX: Защита от накопления (Deduplication).
                _has_active = any(
                    w.target_id == _target_id and w.action_type == "attack" and w.status == WindupStatus.PENDING
                    for w in orchestrator._windup_registry[_reg_key]
                )
                
                if not _has_active:
                    import uuid
                    # DEBT-310.1: Сохраняем сам интент, генерируем ID для него.
                    _intent_id = uuid.uuid4().hex
                    orchestrator._pending_intents[_intent_id] = intent
                    
                    # Создаём окно подготовки (пока статичная длительность = 2 тика для тестов)
                    windup = ActionWindup(
                        actor_id=_actor_id,
                        target_id=_target_id,
                        action_type="attack",
                        started_tick=ctx.tick_number,
                        duration_ticks=2,
                        status=WindupStatus.PENDING,
                        held_intent_id=_intent_id # DEBT-310.1: Pure temporal gate
                    )
                    # Добавляем в стек подготовок актёра (на уровне Orchestrator)
                    orchestrator._windup_registry[_reg_key].append(windup)
                    windups_created += 1
                    
                    # ADR-O-310: НЕ публикуем EventDTO сейчас. Он будет опубликован в Фазе 7.
                    continue # Пропускаем bus.publish(event) ниже
        
        bus.publish(event)
        converted += 1

    logger.info(f"[TICK_ORCH] Фаза 6: {converted} intents → EventDTO, {windups_created} windups created")


def run_phase_7_windup_resolution(ctx: Any, orchestrator: Any) -> None:
    """ADR-O-310: Windup Execution Gate.
    
    Проверяет self._windup_registry на завершённые подготовки.
    Если windup завершён (started_tick + duration_ticks <= ctx.tick_number),
    реконструирует CommunicationIntent из ActionCommitment и передаёт в IntentEventAdapter.
    """
    from app.domain.action_windup import WindupStatus
    from app.services.events.intent_event_adapter import IntentEventAdapter
    from app.services.events.event_bus import get_event_bus
    
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
                        _held_intent = orchestrator._pending_intents.pop(windup.held_intent_id, None)
                        if _held_intent:
                            _actor_id = getattr(_held_intent, 'speaker', '')
                            _target_id = getattr(_held_intent, 'target_id', '')
                            
                            # DEBT-310.2: Minimal Guard - Stale Intent Validation
                            _is_stale = False
                            _reason = ""
                            
                            # 1. Actor validation
                            _actor_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _actor_id or n.get("id") == _actor_id), None)
                            if not _actor_dict:
                                _is_stale, _reason = True, "actor_missing"
                            elif _actor_dict.get("body_state", {}).get("life_status") == "DEAD":
                                _is_stale, _reason = True, "actor_dead"
                                
                            # 2. Target validation (if actor is valid)
                            if not _is_stale and _target_id:
                                if _target_id == "player":
                                    if "player" not in ctx.scene_state.get("npc_positions", {}):
                                        _is_stale, _reason = True, "target_player_missing"
                                else:
                                    _target_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _target_id or n.get("id") == _target_id), None)
                                    if _target_dict and _target_dict.get("body_state", {}).get("life_status") == "DEAD":
                                        _is_stale, _reason = True, "target_dead"
                                    elif not _target_dict and _target_id not in ctx.scene_state.get("npc_positions", {}):
                                        _is_stale, _reason = True, "target_missing"
                            
                            if _is_stale:
                                logger.info(f"[PHASE_7][STALE_INTERRUPT] npc={_actor_id} target={_target_id} reason={_reason}")
                                windup = dataclasses.replace(windup, status=WindupStatus.INTERRUPTED)
                            else:
                                event = adapter.to_event(_held_intent)
                                bus.publish(event)
                                executed_windups += 1
                                windup = dataclasses.replace(windup, status=WindupStatus.COMPLETED)
                        else:
                            windup = dataclasses.replace(windup, status=WindupStatus.COMPLETED)
                    else:
                        windup = dataclasses.replace(windup, status=WindupStatus.COMPLETED)
            if windup.status == WindupStatus.PENDING:
                updated_windups.append(windup)
        
        orchestrator._windup_registry[_reg_key] = [w for w in updated_windups if w.status == WindupStatus.PENDING]

    if executed_windups > 0:
        logger.info(f"[TICK_ORCH] Фаза 7: {executed_windups} windups executed (EventDTO published)")
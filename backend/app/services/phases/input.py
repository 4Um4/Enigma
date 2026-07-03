"""
path: /project/backend/app/services/phases/input.py
Назначение: Инкапсуляция логики Фазы 1 (Воля игрока, WillpowerGate, Affective Resonance).
Зависимости: app.services.will, app.services.affect, app.models.delta_payloads
Основные сущности: Phase1InputDeps, run_phase_1_input, publish_player_intent
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import logging

from app.services.dto import _TickContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Phase1InputDeps:
    """Зависимости Фазы 1. Frozen для предотвращения мутаций."""
    pass  # WillpowerGate не требует внешних сервисов, всё через ctx и чистые функции


def publish_player_intent(ctx: _TickContext, intent: Any) -> None:
    """Публикация разрешенного намерения игрока в шину."""
    from app.domain.events import EventDTO, EventType
    from app.services.event_utils import get_event_bus

    _evt_map = {
        "attack": EventType.PLAYER_ATTACKS,
        "player_attacks": EventType.PLAYER_ATTACKS,
    }
    _act = getattr(intent, 'action', "") or ""
    _resolved_type = _evt_map.get(_act, EventType.PLAYER_INTERACTS)
    
    get_event_bus().publish(EventDTO.create(
        event_type=_resolved_type.value,
        source="player",
        payload={"action": _act, "target": getattr(intent, 'target', "") or ""}
    ))


def run_phase_1_input(ctx: _TickContext, deps: Phase1InputDeps) -> None:
    """Фильтрация воли игрока через WillpowerGate (ADR-031).
    
    Если интент угрожает идентичности аватара — возникает конфликт воли.
    """
    import sys
    logger.debug(f"[WILL_TRACE] _phase_1_input CALLED. Has intent: {ctx.player_intent is not None}")
    
    if not ctx.player_intent:
        return # Idle-тик или нет ввода от игрока

    intent = ctx.player_intent
    _sem_action = getattr(intent, 'parameters', None) and intent.parameters.semantic_action or getattr(intent, 'action', 'UNKNOWN')
    _sem_target = getattr(intent, 'target', 'UNKNOWN')  # ADR-125: DTO.target_id deprecated. Truth is in intent.target
    logger.warning(f"[WILL_TRACE] 1. Intent action: '{_sem_action}', target: '{_sem_target}', NPCs in raw: {len(ctx.all_npcs_raw)}")
    
    # Извлекаем снапшот аватара из симуляции
    player_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
    
    if not player_dict:
        logger.error(f"[WILL_TRACE] FAIL: Аватар 'player' НЕ НАЙДЕН в all_npcs_raw (len={len(ctx.all_npcs_raw)}). Воля отключена!")
        publish_player_intent(ctx, intent)
        return
        
    logger.warning(f"[WILL_TRACE] 2. Avatar found. Psyche: {player_dict.get('psyche', {})}")

    # 1. Вектор давления берется из результата Фазы 1 (Единая точка вычисления)
    # Повторный вызов resolve_intent_pressure ЗАПРЕЩЕН (каузальная integrity)
    from app.services.will import resolve_intent_pressure, compute_willpower
    pressure = ctx.player_pressure or resolve_intent_pressure(intent)
    psyche = player_dict.get("psyche", {})
    
    # 2. Affect Resonance Scan (Искажение интерпретации реальности)
    # Травма - это не бафф, это искажение. Resonance -> Distortion -> Will.
    from app.services.affect import scan_affective_resonance, distort_pressure
    from app.models.affect import AffectiveImprint
    imprints = tuple(AffectiveImprint(**imp) for imp in player_dict.get("affective_imprints", []))
    
    # TODO: Передать PsychologicalPressure и PerceivedPhenomenon от CFRM P2, когда LocalCausalSolver будет генерировать их для хода игрока
    resonance = scan_affective_resonance(intent, None, None, imprints)
    distorted_pressure = distort_pressure(pressure, resonance, psyche)
    
    # 3. Вычисление реакции аватара (Cumulative Strain Model на искаженном давлении)
    will_response = compute_willpower(distorted_pressure, psyche)

    # ДИАГНОСТИКА: Почему нет конфликта?
    logger.warning(f"[WILL_TRACE] 2. Pressure: identity={pressure.identity_deviation:.2f}, humiliation={pressure.humiliation:.2f}")
    logger.warning(f"[WILL_TRACE] 3. Will state: {will_response.state.value}, Resistance: {will_response.resistance:.2f}")

    # 4. Маршрутизация исходов
    from app.models.will import WillState
    from app.models.state_delta import StateDeltas, DeltaDomain
    from app.models.delta_payloads import IdentityPayload, WillConflictPayload, EmotionPayload

    if resonance.trigger_strength > 0.1:
        logger.info(f"[AFFECT] Resonance detected: strength={resonance.trigger_strength:.2f}, bias={resonance.dominant_bias.value}, triggered={resonance.triggered_imprints}")
        
    if will_response.state in (WillState.COMPLY, WillState.RELUCTANT, WillState.CONDITIONED):
        # Аватар подчиняется (возможно, с неохотой или привыканием)
        publish_player_intent(ctx, intent)
        
        # Фиксация урона идентичности
        if will_response.identity_damage > 0:
            ctx.delta_buffer.append(StateDeltas(
                npc_id="player",
                domain=DeltaDomain.IDENTITY,
                target="player",
                payload=IdentityPayload(identity_integrity_delta=-will_response.identity_damage)
            ))

        # ADR-039 FIX: Если Аватар подчинился неохотно (RELUCTANT+) или получил урон — 
        # это каузальное событие Воли. Пишем в ОБЕ трубы: DeltaBuffer (для NPC/истории) и shared_context (для API Игрока)
        if will_response.state != WillState.COMPLY or will_response.identity_damage > 0:
            ctx.delta_buffer.append(StateDeltas(
                npc_id="player",
                domain=DeltaDomain.WILL,
                target="player",
                payload=WillConflictPayload(
                    state=will_response.state.value,
                    resistance=will_response.resistance,
                    embodied_vector=will_response.embodied_vector.value if will_response.embodied_vector else None,
                    identity_damage=will_response.identity_damage
                )
            ))
            from app.services.will import get_embodied_impulse_text
            ctx.shared_context.will_conflict_data = {
                "original_intent": getattr(intent, 'parameters', None) and intent.parameters.semantic_action or getattr(intent, 'action', "UNKNOWN"),
                "state": will_response.state.value,
                "resistance": will_response.resistance,
                "embodied_vector": will_response.embodied_vector.value if will_response.embodied_vector else None,
                "counter_offer_text": get_embodied_impulse_text(will_response.embodied_vector) if will_response.embodied_vector else None
            }
            logger.info(f"[WILL] Conflict data written: state={will_response.state.value}, R={will_response.resistance:.2f}")
    else:
        # Аватар сопротивляется. Действие блокируется, публикуется WILL_CONFLICT
        logger.info(f"[WILL] Аватар сопротивляется! State={will_response.state.value}, R={will_response.resistance:.2f}")
        from app.domain.events import EventDTO, EventType
        
        # Генерируем структурный конфликт Воли через DeltaBuffer
        ctx.delta_buffer.append(StateDeltas(
            npc_id="player",
            domain=DeltaDomain.WILL,
            target="player",
            payload=WillConflictPayload(
                state=will_response.state.value,
                resistance=will_response.resistance,
                embodied_vector=will_response.embodied_vector.value if will_response.embodied_vector else None,
                identity_damage=will_response.identity_damage
            )
        ))
        
        # Восстанавливаем запись в shared_context для API ответа
        from app.services.will import get_embodied_impulse_text
        ctx.shared_context.will_conflict_data = {
            "original_intent": getattr(intent, 'parameters', None) and intent.parameters.semantic_action or getattr(intent, 'action', "UNKNOWN"),
            "state": will_response.state.value,
            "resistance": will_response.resistance,
            "embodied_vector": will_response.embodied_vector.value if will_response.embodied_vector else None,
            "counter_offer_text": get_embodied_impulse_text(will_response.embodied_vector) if will_response.embodied_vector else None
        }
        
        # Публикуем событие блокировки для других систем (DM, NPC реакция)
        from app.services.event_utils import get_event_bus
        get_event_bus().publish(EventDTO.create(
            event_type=EventType.WILL_CONFLICT.value,
            source="player",
            payload={"state": will_response.state.value, "resistance": will_response.resistance}
        ))
        
        # Эмоциональный отклик аватара на давление
        if will_response.fear_delta > 0:
            ctx.delta_buffer.append(StateDeltas(
                npc_id="player",
                domain=DeltaDomain.EMOTION,
                target="player",
                payload=EmotionPayload(stress_delta=will_response.fear_delta * 50, emotion_tag="fear")
            ))

        # WillpowerGate stress: моральное нарушение генерирует стресс аватара
        if will_response.stress_delta > 0:
            logger.info(f"[WILL] Moral stress applied: {will_response.stress_delta:.1f} points (resistance={will_response.resistance:.2f})")
            ctx.delta_buffer.append(StateDeltas(
                npc_id="player",
                domain=DeltaDomain.EMOTION,
                target="player",
                payload=EmotionPayload(stress_delta=will_response.stress_delta, emotion_tag="distress")
            ))

    # ADR-036: Affective Conditioning (Sensitization & New Trauma)
    # Аватар учится через боль. Травма укрепляется при подавлении воли.
    if will_response.identity_damage > 0 or resonance.trigger_strength > 0.1:
        from app.services.affect import apply_conditioning
        from dataclasses import asdict
        current_game_time = ctx.scene_state.get("game_time_seconds", 0)
        updated_imprints = apply_conditioning(imprints, resonance, will_response, intent, current_game_time)
        player_dict["affective_imprints"] = [asdict(imp) for imp in updated_imprints]
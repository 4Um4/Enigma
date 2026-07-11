# path: backend/app/services/game_loop/phase_1_input.py
"""
ФАЗА 1: Input — игрок → EventBus.

Устав 5.1: EventBus.publish() — единственная точка входа событий.
Все действия игрока публикуются здесь, нигде больше.

Назначение: ФАЗА 1 — публикация событий игрока на EventBus (Устав 5.1) + Phase 1 Boundary Adapter (ADR-032)
Зависимости: logging, app.domain.events.EventDTO, app.services.events.event_types.EventType, app.services.events.event_bus.get_event_bus, app.services.will
Основные сущности: resolve_player_intent, publish_player_action, publish_player_speech
"""

import logging
from typing import Any, Dict, List, Optional
from difflib import get_close_matches

from app.domain.events import EventDTO
from app.domain.intent import IntentDTO, IntentParametersDTO
from app.domain.intent_profile import IntentSemanticField, ActionType
from app.models.will import IntentResolution
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.will import compute_willpower, resolve_intent_pressure

logger = logging.getLogger(__name__)


def _resolve_target_reference(field: IntentSemanticField, scene_context: Any) -> str:
    """Слой 2: Target Resolution. Fuzzy matching по списку NPC в сцене."""
    if not field.target_reference or not scene_context:
        return ""

    ref = field.target_reference.lower()
    
    # Извлекаем словарь {npc_name.lower(): npc_id} из контекста сцены
    # Ожидаем, что scene_context содержит all_npcs_raw или npc_positions с именами
    npc_name_map = {}
    if isinstance(scene_context, dict):
        # Вариант 1: all_npcs_raw
        for npc in scene_context.get("all_npcs_raw", []):
            if isinstance(npc, dict) and npc.get("name") and npc.get("npc_id"):
                npc_name_map[npc["name"].lower()] = npc["npc_id"]
        # Вариант 2: npc_positions
        if not npc_name_map:
            for npc_id, pos_data in scene_context.get("npc_positions", {}).items():
                if isinstance(pos_data, dict):
                    # Поддержка обоих ключей: display_name (DTO) и name (scene_state)
                    if _name := pos_data.get("display_name") or pos_data.get(
                        "name"
                    ):
                        npc_name_map[_name.lower()] = npc_id

    # ADR-046: Диагностика Fuzzy Matching (Слой 2)
    logger.warning(f"[TARGET_RESOLVE] ref='{ref}', map_size={len(npc_name_map)}, keys={list(npc_name_map.keys())[:5]}")

    if not npc_name_map:
        return ""

    # Fuzzy matching (порог 0.6 — терпим к опечаткам и падежам)
    matches = get_close_matches(ref, npc_name_map.keys(), n=1, cutoff=0.6)
    return npc_name_map[matches[0]] if matches else ""

def resolve_player_intent(
    raw_action: str,
    action_type: str,
    target: str,
    player_dict: Optional[Dict[str, Any]] = None,
    scene_context: Optional[Any] = None,
) -> IntentResolution:
    """Phase 1 Boundary Adapter (ADR-031 Fix).
    
    Содержит Слой 1 (Fast-path Compression) и Слой 2 (Target Resolution).
    LLM-парсинг (slow_path/await) КАТЕГОРИЧЕСКИ ЗАПРЕЩЕН в каузальном солвере.
    """
    # 1. Слой 1: Сжатие языка в Семантическое Поле (Только Fast-Path)
    semantic_field = None
    try:
        from app.services.input.intent_compressor import IntentCompressor
        _compressor = IntentCompressor(llm_client=None)
        logger.debug(f"[PIPELINE][INPUT] raw_action={raw_action!r}")
        semantic_field = _compressor._fast_path_parse(raw_action)
        logger.debug(f"[ARCHAE-FASTPATH] raw={raw_action!r} result={semantic_field.action_type if semantic_field else 'None'} target_ref={semantic_field.target_reference if semantic_field else 'N/A'}")
        logger.debug(f"[PIPELINE][INPUT] result={semantic_field}")
        if semantic_field:
            logger.warning(f"[LAYER1] Fast path success: action={semantic_field.action_type}, target_ref={semantic_field.target_reference}")
    except Exception as e:
        logger.error(f"[LAYER1] Compressor crashed: {e}")

    if semantic_field is None:
        # Fallback: если словарь не распознал действие, используем базовый UNCERTAIN профиль
        logger.debug(f"[ARCHAE-FASTPATH-FALLBACK] raw={raw_action!r} → UNCERTAIN (fast_path returned None)")
        semantic_field = IntentSemanticField(raw_text=raw_action, action_type=ActionType.UNCERTAIN)
    
    # 2. Слой 2: Разрешение цели (Строка -> ID)
    resolved_target_id = _resolve_target_reference(semantic_field, scene_context)
    
    # Формируем канонический IntentDTO
    final_action = semantic_field.action_type.value
    if final_action == "UNCERTAIN" and action_type:
        final_action = action_type

    # ADR-035: Строгая типизация семантики (Убийство Dict[str, Any])
    # ЗАПРЕЩЕНО превращать UNCERTAIN в None — это убивает S28 Gate и Трубу Воли.
    # Система должна знать, что действие неопределено, а не считать, что его нет.
    _intent_params = IntentParametersDTO(
        semantic_action=semantic_field.action_type.value,
        target_reference=semantic_field.target_reference,
        target_id=resolved_target_id, # Инъекция ID из Слоя 2
        physical_force=semantic_field.physical_force,
        emotional_charge=semantic_field.emotional_charge,
        social_pressure=semantic_field.social_pressure,
        commitment_level=semantic_field.commitment_level
    )
        
    intent = IntentDTO(
        action=final_action,
        target=resolved_target_id or target,
        parameters=_intent_params,
        text=raw_action,
    )
    
    # ADR-O: УБИТ SEMANTIC MOVE BRIDGE. Игрок говорит → NPC решает.
    # Фаза ввода не имеет права генерировать imperative movement.
    # Приказ пробрасывается через Pressure Pipeline → DecisionHub.

    # Если аватара нет в симуляции — давление не вычисляется
    if not player_dict:
        return IntentResolution(original_intent=intent)

    # 3. Слой 3: Вычисление вектора давления (ADR-031)
    # TODO: В будущем resolve_intent_pressure должен принимать IntentSemanticField,
    # а не IntentDTO, чтобы использовать physical_force и emotional_charge.
    pressure = resolve_intent_pressure(intent)
    
    return IntentResolution(original_intent=intent, pressure_profile=pressure)


# --- LEGACY PUBLISHERS (оставлены для совместимости) ---

def _publish_raw_action(
    player_name: str,
    player_text: str,
    action_type: str,
    location: str,
) -> None:
    """Публикация сырого действия игрока — PLAYER_INTERACTS."""
    if player_text.startswith("[TELEGRAPH"):
        return
    try:
        get_event_bus().publish(EventDTO.create(
            event_type=EventType.PLAYER_INTERACTS,
            source=player_name,
            payload={
                "content": player_text,
                "action_type": action_type,
                "location": location,
            },
            persistence_level="working",
        ))
    except Exception as _bus_err:
        logger.debug(f"[EVENT_BUS] player_action publish skipped: {_bus_err}")


def publish_player_speech(
    player_name: str,
    action_text: str,
    classified_type: str,
    semantic_action: Optional[str] = None,
    target_reference: Optional[str] = None,
) -> None:
    """Публикация вербального действия — PLAYER_SPOKE."""
    if not action_text:
        return
    try:
        _payload = {
            "content": action_text[:120],
            "action_type": classified_type,
        }
        # ADR-035: Проброс семантического вектора от Слоя 1 в каузальную шину
        if semantic_action:
            _payload["semantic_action"] = semantic_action
        if target_reference:
            _payload["target_reference"] = target_reference.lower() # Нормализация для маппинга

        get_event_bus().publish(EventDTO.create(
            event_type=EventType.PLAYER_SPOKE,
            source=player_name or "Игрок",
            payload=_payload,
            persistence_level="working",
        ))
    except Exception as _bus_err:
        logger.debug(f"[EVENT_BUS] player_speech publish skipped: {_bus_err}")


# Интенсивность по типу действия — единый источник для EventDTO.payload
from app.domain.constants import ACTION_INTENSITY


def publish_classified_player_event(
    shared_context: Any,
    location: str,
    campaign_id: str,
    raw_input: str,
) -> None:
    """Публикация классифицированного события игрока после DM-обработки."""
    _evt_map = {
        "dialogue": EventType.PLAYER_SPOKE,
        "player_interacts": EventType.PLAYER_SPOKE,
        "attack": EventType.PLAYER_ATTACKED,
        "player_attacks": EventType.PLAYER_ATTACKED,
        "move": EventType.PLAYER_MOVED,
        "stealth": EventType.PLAYER_MOVED,
    }
    _raw_type = shared_context.action_type or "dialogue"
    # ADR-082: Case-Insensitive Routing. NLP возвращает 'ATTACK', маппинг ждет 'attack'.
    # Без .lower() удар уходит в PLAYER_SPOKE, минуя CombatSubscriber и ImpactEngine.
    _resolved_type = _evt_map.get(_raw_type.lower(), EventType.PLAYER_SPOKE)
    _evt_radius = 15.0 if _resolved_type == EventType.PLAYER_ATTACKED else 999.0
    _intensity = ACTION_INTENSITY.get(_raw_type, 0.2)
    # ADR-035: Извлекаем строгую семантику из IntentParametersDTO
    _semantic_action = None
    _target_reference = None
    _target_id = None
    _physical_force = 0.1
    _social_pressure = 0.0
    if hasattr(shared_context, 'intent_resolution') and shared_context.intent_resolution:
        _params = shared_context.intent_resolution.original_intent.parameters
        if isinstance(_params, IntentParametersDTO):
            _semantic_action = _params.semantic_action
            _target_reference = _params.target_reference
            _target_id = _params.target_id # Извлекаем ID Слоя 2
            _physical_force = _params.physical_force
            _social_pressure = _params.social_pressure
        else:
            logger.error(f"[SEMANTIC_BRIDGE] Legacy dict parameters detected: {_params}")

        if not _semantic_action:
            logger.debug("[SEMANTIC_BRIDGE] No semantic_action in DTO")
        else:
            logger.warning(f"[SEMANTIC_BRIDGE] Extracted: action={_semantic_action}, target={_target_reference}, id={_target_id}")
    
    # ADR-091: IntentCompressor Priority Override
    # IntentCompressor (50+ ATTACK глаголов) — авторитет классификации.
    # DM Router (16 глаголов) перезаписывает "укусить/толкнуть/душить" → player_interacts.
    # Без override: ATTACK → PLAYER_SPOKE → CombatSubscriber не вызывается → нет крови/боли.
    # ADR-091 diagnostics removed — override logic confirmed working
    if _semantic_action:
        _IC_PRIORITY_MAP = {
            "ATTACK": "attack",
            "THREATEN": "player_threatens",
            "STEAL": "player_steals",
            "MOVE": "move",
        }
        _ic_override = _IC_PRIORITY_MAP.get(_semantic_action)
        if _ic_override and _ic_override != _raw_type:
            logger.debug(f"[ADR-091] IntentCompressor override: DM_Router='{_raw_type}' → IC='{_ic_override}'")
            _raw_type = _ic_override
            _resolved_type = _evt_map.get(_raw_type.lower(), EventType.PLAYER_SPOKE)
            _evt_radius = 15.0 if _resolved_type == EventType.PLAYER_ATTACKED else 999.0

    _payload = {
        "location": location,
        "campaign_id": campaign_id,
        "target_id": shared_context.player_target_id,
        "raw_input": raw_input,
        "action_type": _raw_type,
        "intensity": _intensity,
    }
    # Проброс семантического вектора Слоя 1 для NPC-рефлексов (ADR-035)
    if _semantic_action:
        _payload["semantic_action"] = _semantic_action
        _payload["physical_force"] = _physical_force
        _payload["social_pressure"] = _social_pressure
    if _target_reference:
        _payload["target_reference"] = _target_reference.lower()
    # Перехват ID цели из Слоя 2, если старый контекст пуст
    if _target_id and not _payload.get("target_id"):
        _payload["target_id"] = _target_id

    _game_evt = EventDTO.create(
        event_type=_resolved_type.value,
        source="player",
        payload=_payload,
        radius=_evt_radius,
    )
    get_event_bus().publish(_game_evt)
    logger.warning(f"[EVENT_BUS] Published: {_game_evt.type}, target={_game_evt.payload.get('target_id')}, action_type={_raw_type}")
    # L1 Фиксация перенесена в npc_orchestration.py (единая точка каузальной эмиссии).
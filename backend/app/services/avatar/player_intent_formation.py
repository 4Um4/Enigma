"""
path: /project/backend/app/services/avatar/player_intent_formation.py
Назначение: Player Intent Identity — симметрия с AvatarIntentRecord.
    Player Intent получает детерминированный intent_id через
    next_intent_identity + IntentIdentity.for_player_input.
    Записывается в scene_state["intent_lifecycle"] (canonical store).
    Continuity: тот же (action, target) → тот же intent_id (как Avatar Step 2.1.1).
    НЕ создаёт вторую систему намерений — использует существующий
    IntentIdentity + intent_lifecycle + next_intent_identity.
Зависимости: app.domain.intent_identity, app.services.events.event_identity
Основные сущности: store_player_intent, get_active_player_intent
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.events.event_identity import (
    intent_id_str,
    next_intent_identity,
)

logger = logging.getLogger(__name__)

# Player character_id (single-avatar MVP — "player")
_PLAYER_CHARACTER_ID = "player"


def store_player_intent(
    scene_state: Dict[str, Any],
    player_name: str,
    action: str,
    target: Optional[str],
    tick: int,
) -> Optional[str]:
    """Store Player Intent in intent_lifecycle (canonical store).

    Симметрично store_avatar_intent (Step 2.1). Uses
    IntentIdentity.for_player_input(player_name, character_id).

    Continuity (Step 2.1.1 pattern): тот же (action, target) →
    UPDATE urgency/target, preserve intent_id. Смена action или target →
    SUPERSEDE previous, new intent_id.

    Возвращает intent_id (для shared_context, если понадобится BodyArbiter).
    """
    lifecycle = scene_state.setdefault("intent_lifecycle", {})

    # Найти текущий ACTIVE player intent
    _active_intent_id = None
    _active_entry = None
    for _id, _entry in lifecycle.items():
        if (
            isinstance(_entry, dict)
            and _entry.get("control_source") == "player_input"
            and _entry.get("lifecycle_state") == "ACTIVE"
        ):
            _active_intent_id = _id
            _active_entry = _entry
            break

    # Continuity check: тот же action И тот же target → UPDATE, preserve intent_id
    if (
        _active_entry is not None
        and _active_entry.get("action") == action
        and _active_entry.get("target") == (target or "")
    ):
        # Same action + target — refresh transitioned_tick only.
        # intent_id preserved (continuity across ticks).
        _active_entry["transitioned_tick"] = tick
        return _active_intent_id

    # Different action OR target → SUPERSEDE previous
    if _active_entry is not None:
        _active_entry["lifecycle_state"] = "SUPERSEDED"
        _active_entry["transitioned_tick"] = tick

    # Step 3.1-Identity Fix: owner = UUID-P (player consciousness),
    # body_id = UUID-B (shared body). Reads identity_uuids from scene_state
    # (loaded by tick_orchestrator from PlayerAvatarService.ensure_identity_uuids).
    # Falls back to legacy 'player' string if identity_uuids absent (tests/old saves).
    from app.domain.identity_uuids import IdentityUUIDs

    uuids_data = scene_state.get("identity_uuids")
    uuids = IdentityUUIDs.from_dict(uuids_data) if uuids_data else None
    if uuids is not None:
        owner_id = uuids.player_consciousness  # UUID-P
        body_id = uuids.body                    # UUID-B
    else:
        # Backward compat: legacy string-based identity (tests, old saves)
        owner_id = player_name or "player"
        body_id = "player"

    # Generate intent_id using UUID-P as owner (separate counter from Avatar)
    _tick_id, _ordinal = next_intent_identity(scene_state, owner_id, action)
    _intent_id = intent_id_str(_tick_id, owner_id, action, _ordinal)

    lifecycle[_intent_id] = {
        "intent_id": _intent_id,
        "owner": owner_id,
        "body_id": body_id,
        "control_source": "player_input",
        "action": action,
        "target": target or "",
        "desire_ref": None,  # Player intent не порождён Desire
        "urgency": None,     # НЕ urgency=1.0 автоматически (Master test 9)
        "lifecycle_state": "ACTIVE",
        "arbitration_result": "PENDING",
        "execution_status": "NOT_EXECUTED",
        "created_tick": tick,
        "transitioned_tick": tick,
    }

    logger.info(
        f"[PLAYER_INTENT] formed: intent_id={_intent_id} action={action} "
        f"target={target} tick={tick} owner={owner_id} "
        f"source=player_input"
    )

    return _intent_id


def get_active_player_intent(
    scene_state: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Read current ACTIVE player intent from intent_lifecycle.

    Reader only — не второе хранилище. Возвращает lifecycle entry
    или None если нет ACTIVE player intent.
    """
    lifecycle = scene_state.get("intent_lifecycle", {})
    for _entry in lifecycle.values():
        if (
            isinstance(_entry, dict)
            and _entry.get("control_source") == "player_input"
            and _entry.get("lifecycle_state") == "ACTIVE"
        ):
            return _entry
    return None


def voided_player_intents(scene_state: Dict[str, Any], tick: int) -> None:
    """Stale cleanup: mark all ACTIVE player intents as VOIDED.

    Вызывается на exception — старое намерение не остаётся актуальным.
    """
    lifecycle = scene_state.get("intent_lifecycle", {})
    for _entry in lifecycle.values():
        if (
            isinstance(_entry, dict)
            and _entry.get("control_source") == "player_input"
            and _entry.get("lifecycle_state") == "ACTIVE"
        ):
            _entry["lifecycle_state"] = "VOIDED"
            _entry["transitioned_tick"] = tick

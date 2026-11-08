"""
path: /project/backend/app/services/avatar/avatar_intent_formation.py
Назначение: Avatar agency — formation of Intent from Desire.
    Читает Avatar desires (сформированные Step 1 adapter),
    определяет наиболее срочное желание, маппит на существующий Intent,
    оборачивает в AvatarIntentRecord с IntentIdentity.for_avatar_initiative.
    Formation only — НЕ запускает исполнение (нет CommunicationIntent,
    нет MovementIntent). BodyArbiter (следующий шаг) решает исполнение.
Зависимости: app.domain.avatar_intent_record, app.domain.intent_identity,
             app.domain.desire (DesireSource), app.models.npc_state (Intent)
Основные сущности: form_avatar_intent
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.avatar_intent_record import AvatarIntentRecord
from app.domain.intent_identity import IntentIdentity
from app.models.npc_state import Intent

logger = logging.getLogger(__name__)

# Reverse mapping: Desire subject_class → Intent (enum).
# НЕ вводит произвольные пороги — Intent формируется для любого
# существующего Desire. Urgency сохраняется в record для BodyArbiter.
_DESIRE_SUBJECT_TO_INTENT: Dict[str, Intent] = {
    "food": Intent.APPROACH,       # голод → подойти к источнику еды
    "ale": Intent.APPROACH,        # жажда → подойти к источнику питья
    "shelter": Intent.IDLE,        # усталость → отдых на месте
    "rest": Intent.IDLE,           # sleep_pressure → отдых на месте
    "social": Intent.TALK,         # social_urge → вступить в разговор
}

# Avatar character_id (Stranger). В single-avatar MVP это "player".
_AVATAR_CHARACTER_ID = "player"


def form_avatar_intent(
    npc_dict: Dict[str, Any],
    tick: int,
) -> Optional[AvatarIntentRecord]:
    """Формирует AvatarIntentRecord из desires Avatar.

    Читает npc_dict["desires"] (созданные desire_generator.update_all
    через Step 1 adapter _ensure_avatar_needs). Выбирает наиболее
    срочный Desire, маппит на Intent, оборачивает с identity.

    НЕ запускает исполнение — только formation. Результат хранится
    на scene_state["avatar_pending_intent"] для BodyArbiter.

    Возвращает None если:
      - npc_dict не Avatar (npc_id != "player")
      - нет desires
      - desires пустые
      - subject_class не в mapping (честное UNKNOWN, §ENIGMA-003)
    """
    npc_id = npc_dict.get("npc_id") or npc_dict.get("id", "")
    if npc_id != _AVATAR_CHARACTER_ID:
        return None

    desires = npc_dict.get("desires")
    if not isinstance(desires, list) or not desires:
        return None

    # Выбираем наиболее срочный Desire (без порога — любой)
    most_urgent = None
    max_urgency = -1.0
    for d in desires:
        if not isinstance(d, dict):
            continue
        urgency = float(d.get("urgency", 0.0))
        if urgency > max_urgency:
            max_urgency = urgency
            most_urgent = d

    if most_urgent is None:
        return None

    subject_class = most_urgent.get("subject_class", "")
    desire_id = most_urgent.get("desire_id", "")
    urgency = float(most_urgent.get("urgency", 0.0))

    # Mapping subject → Intent. Если subject не в mapping — честное
    # отсутствие (§ENIGMA-003), не выдумываем Intent.
    intent = _DESIRE_SUBJECT_TO_INTENT.get(subject_class)
    if intent is None:
        logger.debug(
            f"[AVATAR_INTENT] subject_class={subject_class!r} not in mapping — "
            f"no Intent formed (honest UNKNOWN)"
        )
        return None

    # Target: из desire target_class (если есть) или None.
    # Spatial resolution — отдельный шаг (BodyArbiter или MovementEngine).
    target = most_urgent.get("target_class") or None

    # IntentIdentity.for_avatar_initiative — Avatar сам решил, не Player.
    identity = IntentIdentity.for_avatar_initiative(_AVATAR_CHARACTER_ID)

    record = AvatarIntentRecord(
        intent=intent,
        identity=identity,
        desire_ref=desire_id,
        target=target,
        formed_tick=tick,
        urgency=urgency,
    )

    logger.info(
        f"[AVATAR_INTENT] formed: intent={intent.value} desire_ref={desire_id} "
        f"urgency={urgency:.2f} target={target} tick={tick} "
        f"owner={identity.intent_owner} source={identity.control_source.value}"
    )

    return record


def store_avatar_intent(
    scene_state: Dict[str, Any],
    record: Optional[AvatarIntentRecord],
    tick: int,
) -> None:
    """Store AvatarIntentRecord in intent_lifecycle (canonical store).

    НЕ отдельный avatar_pending_intent ключ — использует intent_lifecycle
    (Commit 1 canonical container) с intent_id из next_intent_identity.

    Step 2.1.1 continuity: при том же desire_ref и intent — обновляет
    urgency/target существующей ACTIVE записи, НЕ создаёт новый intent_id.
    При смене desire_ref или intent — предыдущий → SUPERSEDED, новый
    ACTIVE. При исчезновении desires (record=None) — предыдущий → SUPERSEDED.

    Continuity invariant (Step 2.1.1):
      - Same desire_ref + same intent + ACTIVE exists → UPDATE urgency/target,
        preserve intent_id (no accumulation).
      - Different desire_ref OR different intent → SUPERSEDE previous, new id.
      - record=None → SUPERSEDE previous, no new created.

    Lifecycle-поля живут в lifecycle entry, не на AvatarIntentRecord.
    """
    from app.services.events.event_identity import (
        intent_id_str,
        next_intent_identity,
    )

    lifecycle = scene_state.setdefault("intent_lifecycle", {})

    # Найти текущий ACTIVE avatar intent
    _active_intent_id = None
    _active_entry = None
    for _id, _entry in lifecycle.items():
        if (
            isinstance(_entry, dict)
            and _entry.get("control_source") == "avatar_initiative"
            and _entry.get("lifecycle_state") == "ACTIVE"
        ):
            _active_intent_id = _id
            _active_entry = _entry
            break

    if record is None:
        # Desire исчез → SUPERSEDE previous, no new created
        if _active_entry is not None:
            _active_entry["lifecycle_state"] = "SUPERSEDED"
            _active_entry["transitioned_tick"] = tick
        return

    # Continuity check: тот же desire_ref И тот же intent → UPDATE, не новый id
    if (
        _active_entry is not None
        and _active_entry.get("desire_ref") == record.desire_ref
        and _active_entry.get("action") == record.intent.value
    ):
        # Same desire, same intent — refresh urgency/target only.
        # intent_id preserved (continuity across ticks).
        _active_entry["urgency"] = record.urgency
        _active_entry["target"] = record.target
        _active_entry["transitioned_tick"] = tick
        return

    # Different desire_ref OR different intent → SUPERSEDE previous
    if _active_entry is not None:
        _active_entry["lifecycle_state"] = "SUPERSEDED"
        _active_entry["transitioned_tick"] = tick

    # Step 3.1-Identity Fix: owner = UUID-A (avatar consciousness),
    # body_id = UUID-B (shared body). Reads identity_uuids from scene_state.
    # Falls back to legacy 'player' string if identity_uuids absent (tests/old saves).
    from app.domain.identity_uuids import IdentityUUIDs

    uuids_data = scene_state.get("identity_uuids")
    uuids = IdentityUUIDs.from_dict(uuids_data) if uuids_data else None
    if uuids is not None:
        owner_id = uuids.avatar_consciousness  # UUID-A
        body_id = uuids.body                    # UUID-B
    else:
        # Backward compat: legacy string-based identity (tests, old saves)
        owner_id = "player"
        body_id = "player"

    # Generate new intent_id using UUID-A as owner (separate counter from Player)
    _tick_id, _ordinal = next_intent_identity(
        scene_state, owner_id, record.intent.value
    )
    _intent_id = intent_id_str(_tick_id, owner_id, record.intent.value, _ordinal)
    lifecycle[_intent_id] = {
        "intent_id": _intent_id,
        "owner": owner_id,
        "body_id": body_id,
        "control_source": "avatar_initiative",
        "action": record.intent.value,
        "target": record.target,
        "desire_ref": record.desire_ref,
        "urgency": record.urgency,
        "lifecycle_state": "ACTIVE",
        "arbitration_result": "PENDING",
        "execution_status": "NOT_EXECUTED",
        "created_tick": record.formed_tick,
        "transitioned_tick": record.formed_tick,
    }


def voided_avatar_intents(scene_state: Dict[str, Any], tick: int) -> None:
    """Stale cleanup: mark all ACTIVE avatar intents as VOIDED.

    Вызывается на exception в formation pipeline — старое намерение
    не должно оставаться доступным как актуальное после ошибки генерации.
    """
    lifecycle = scene_state.get("intent_lifecycle", {})
    for _entry in lifecycle.values():
        if (
            isinstance(_entry, dict)
            and _entry.get("control_source") == "avatar_initiative"
            and _entry.get("lifecycle_state") == "ACTIVE"
        ):
            _entry["lifecycle_state"] = "VOIDED"
            _entry["transitioned_tick"] = tick


def get_active_avatar_intent(
    scene_state: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Read current ACTIVE avatar intent from intent_lifecycle.

    Reader only — не второе хранилище. Возвращает lifecycle entry
    или None если нет ACTIVE avatar intent.
    """
    lifecycle = scene_state.get("intent_lifecycle", {})
    for _entry in lifecycle.values():
        if (
            isinstance(_entry, dict)
            and _entry.get("control_source") == "avatar_initiative"
            and _entry.get("lifecycle_state") == "ACTIVE"
        ):
            return _entry
    return None

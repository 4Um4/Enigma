"""
Rule 54/55 (ADR-128 + WOUNDS-TZ FIX): Wound/Condition/TemporaryDrive переживают
save→load аватара игрока.

Регрессия: до фикса write-path писал несуществующие поля Wound
(damage_type/tick/healing_ticks) → AttributeError/TypeError при сериализации,
а read-path молча терял раны (Wound(damage_type=...) → TypeError → except → skip).
Condition.tick — bound method модели, попадал в JSON (json.dumps падал).
temporary_drives сериализовались как dict(list[TemporaryDrive]) → TypeError
при непустом списке и НЕ восстанавливались при загрузке.

Запуск: cd backend; python -m pytest tests/sandbox/persistence/test_player_wounds_conditions_drives_roundtrip.py -v --tb=short; cd ..

TODO:

"""

import json

from app.models.npc_state import NPCState, TemporaryDrive
from app.models.physical import Condition, Wound, WoundSeverity
from app.services.player_avatar_service import PlayerAvatarService


def _state_with_injuries() -> NPCState:
    """NPCState с непустыми conditions / wounds / temporary_drives."""
    state = NPCState(npc_id="player_test")
    state.conditions["bleeding"] = Condition(
        type="bleeding", severity=0.5, duration_ticks=3, decay_per_tick=0.1, tick_applied=7
    )
    state.wounds.append(
        Wound(
            body_part="torso",
            severity=WoundSeverity.SEVERE,
            cause="sword_slash",
            tick_received=11,
            persistent=True,
            heal_ticks=0,
        )
    )
    state.temporary_drives.append(
        TemporaryDrive(
            drive_type="vengeance",
            urgency=0.8,
            reason="Торнин избил Люсю",
            source_npc_id="tornin",
            tick_born=5,
            tick_age=2,
        )
    )
    return state


def test_wounds_conditions_drives_roundtrip() -> None:
    """write-path JSON-сериализуем, read-path возвращает те же значения."""
    svc = PlayerAvatarService()
    state = _state_with_injuries()

    saved = svc._state_to_dict(state)
    # Раньше здесь падал json.dumps (bound method Condition.tick / list drives).
    json.dumps(saved)

    restored = svc._state_from_dict(saved)

    assert restored.conditions["bleeding"].tick_applied == 7
    assert restored.wounds, "раны потеряны при round-trip (WOUNDS-TZ FIX)"
    wound = restored.wounds[0]
    assert wound.cause == "sword_slash"
    assert wound.severity is WoundSeverity.SEVERE
    assert wound.tick_received == 11
    assert wound.persistent is True
    assert restored.temporary_drives, "temporary_drives потеряны при round-trip"
    assert restored.temporary_drives[0].drive_type == "vengeance"
    assert restored.temporary_drives[0].urgency == 0.8
    assert restored.temporary_drives[0].tick_age == 2


def test_legacy_wound_keys_are_read() -> None:
    """Старые сейвы (damage_type/tick/healing_ticks, temporary_drives={}) читаются."""
    svc = PlayerAvatarService()
    legacy = {
        "npc_id": "p",
        "conditions": {},
        "wounds": [
            {
                "body_part": "arm_left",
                "severity": "minor",
                "damage_type": "blunt_impact",
                "tick": 3,
                "healing_ticks": 20,
            }
        ],
        "temporary_drives": {},
    }

    state = svc._state_from_dict(legacy)

    assert state.wounds, "legacy-раны потеряны при загрузке"
    wound = state.wounds[0]
    assert wound.cause == "blunt_impact"
    assert wound.tick_received == 3
    assert wound.heal_ticks == 20
    assert wound.severity is WoundSeverity.MINOR
    assert state.temporary_drives == []

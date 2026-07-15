"""
Rule 54/55 (ADR-128): Player body_state/affective_load/perceptual_kernel переживают save/load.
Без этого теста любой рефакторинг PlayerAvatarService может молча откатить ADR-128,
и игрок снова станет "бессмертным" при загрузке (injuries/pain/shock сбросятся в 0).

Запуск: cd backend; python -m pytest tests/sandbox/persistence/test_player_body_state_survives_save_load.py -v --tb=short; cd ..

TODO:

"""

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.player_avatar_service import PlayerAvatarService


def test_player_body_state_survives_save_load():
    """
    Полный round-trip: real_dict → _state_from_dict → _state_to_dict → _state_from_dict.
    Проверяем, что ADR-128 поля (body_state, affective_load, perceptual_kernel)
    не теряются при сериализации/десериализации.
    """
    svc = PlayerAvatarService()

    # 1. Структура реальных данных (имитирует то, что _state_to_dict пишет на диск)
    # Используем полный набор полей, чтобы from_dict не крашнулся на KeyError
    real_dict = {
        "npc_id": "player_test",
        "stress": 0.8,
        "resentment": 0.1,
        "dependency": 0.2,
        "identity_integrity": 0.9,
        "pressure_resistance": 0.5,
        "will_state": "free",
        "behavior_mask": {},
        "trauma_markers": ["witnessed_violence"],
        "current_role": "adventurer",
        "hp": 60,
        "max_hp": 100,
        "conditions": {},  # ADR-128: legacy, SSOT = body_state
        "wounds": {},  # ADR-128: legacy, SSOT = body_state
        "posture": "hunched",
        # === ADR-128: КРИТИЧЕСКИЕ ПОЛЯ (SSOT физиологии) ===
        "body_state": {
            "current_hp": 60,
            "pain": 85.0,
            "fatigue": 40.0,
            "blood_loss": 0.45,
            "shock_impulse": 0.7,
            "consciousness": 0.3,
            "life_status": "DEAD",  # ADR-127: DEATH LOCK должен пережить save/load
            "injuries": [{"target_zone": "chest", "structural_damage": 0.8, "damage_type": "slash"}],
            "modifiers": {"attack_penalty": -5},
            "statuses": ["bleeding", "unconscious"],
        },
        "affective_load": 0.65,
        "emotion": "PANIC",
        "emotion_delta": 0.2,
        "state_modifiers": {},
        # === ADR-128: Perceptual Kernel ===
        "perceptual_kernel": {
            "threat_gradient": 0.9,
            "trust_gradient": 0.1,
            "uncertainty": 0.5,
            "anomaly_score": 0.2,
            "last_hostile_direction": "north",
            "dominant_emotion": "fear",
            "aggression_inhibition": 0.8,
            "initiative_suppression": 0.6,
            "compliance_bias": 0.1,
            "recent_directive": None,
        },
    }

    # 2. Создание объекта ЧЕРЕЗ ФАБРИКУ (§12.3 Устава — прямой конструктор ЗАПРЕЩЁН)
    state = svc._state_from_dict(real_dict)

    # 3. Сериализация обратно в dict (write path)
    saved_dict = svc._state_to_dict(state)

    # 4. Верификация write path: критические поля ADR-128 не потеряны
    assert "body_state" in saved_dict, "body_state потерян при save!"
    assert saved_dict["body_state"].get("life_status") == "DEAD", "DEATH LOCK (ADR-127) потерян при save!"
    assert saved_dict["body_state"].get("blood_loss") == 0.45, "blood_loss потерян при save!"
    assert saved_dict["body_state"].get("pain") == 85.0, "pain потерян при save!"
    assert saved_dict["body_state"].get("shock_impulse") == 0.7, "shock_impulse потерян при save!"
    assert len(saved_dict["body_state"].get("injuries", [])) == 1, "injuries потеряны при save!"

    # 5. Верификация affective_load и perceptual_kernel (Rule 55)
    assert "affective_load" in saved_dict, "affective_load потерян при save!"
    assert saved_dict["affective_load"] == 0.65, "affective_load искажён при save!"

    assert "perceptual_kernel" in saved_dict, "perceptual_kernel потерян при save!"
    assert saved_dict["perceptual_kernel"].get("threat_gradient") == 0.9, "threat_gradient потерян при save!"
    assert saved_dict["perceptual_kernel"].get("initiative_suppression") == 0.6, (
        "initiative_suppression потерян при save!"
    )

    # 6. Round-trip целостность: повторная десериализация сохранённого dict
    state_rt = svc._state_from_dict(saved_dict)
    assert state_rt.body_state.get("life_status") == "DEAD", "DEATH LOCK не пережил round-trip!"
    assert state_rt.body_state.get("blood_loss") == 0.45, "blood_loss не пережил round-trip!"
    assert state_rt.affective_load == 0.65, "affective_load не пережил round-trip!"
    assert state_rt.perceptual_kernel.initiative_suppression == 0.6, "initiative_suppression не пережил round-trip!"

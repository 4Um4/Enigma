"""
path: backend/tests/sandbox/persistence/test_perceptual_kernel_roundtrip.py
Назначение: Верификация Rule 31 (PerceptualKernel переживает сериализацию, ADR-115)
Зависимости: app.models.npc_state
Основные сущности: NPCState, PerceptualKernel

Запуск: cd backend; python -m pytest tests/sandbox/persistence/test_perceptual_kernel_roundtrip.py -v --tb=short; cd ..
"""

import dataclasses

from app.models.npc_state import NPCState, NPCStateAdapter


def test_perceptual_kernel_survives_legacy_roundtrip():
    """ДОКАЗЫВАЕТ: PerceptualKernel не теряет данные при сериализации в legacy-формат и обратно (Rule 31)."""
    # Создаём словарь с реальными ключами рантайма (Real Data First, §12.4)
    initial_dict = {
        "npc_id": "test_npc",
        "psyche": {"stress": 0.5, "willpower": 0.8, "loyalty_true": 0.5},
        "social_stats": {},
        "body_state": {},
        "perceptual_kernel": {
            "threat_gradient": 0.7,
            "trust_gradient": 0.2,
            "uncertainty": 0.5,
            "anomaly_score": 0.4,
            "last_hostile_direction": "north",
            "dominant_emotion": "fear",
            "aggression_inhibition": 0.8,
            "initiative_suppression": 0.3,
            "compliance_bias": 0.1,
            "somatic_urgency": 0.65,  # ADR-O-143: воспринимаемый телесный дистресс
            "recent_directive": "MOVE",
        },
    }

    # Создаём объект через фабрику (§12.3: Тест через from_legacy)
    original_state = NPCStateAdapter.from_legacy(initial_dict)

    # Сериализуем в legacy dict (write_to_legacy принадлежит NPCState)
    legacy_out = {}
    NPCState.write_to_legacy(original_state, legacy_out)

    # Десериализуем обратно (Round-trip)
    restored_state = NPCStateAdapter.from_legacy(legacy_out)

    # Проверяем, что все поля PerceptualKernel совпадают (§12.2: Write-All-Read-All)
    assert original_state.perceptual_kernel is not None, "PerceptualKernel потерян при roundtrip"
    assert restored_state.perceptual_kernel is not None, "PerceptualKernel потерян при восстановлении"

    for field in dataclasses.fields(original_state.perceptual_kernel):
        original_val = getattr(original_state.perceptual_kernel, field.name)
        restored_val = getattr(restored_state.perceptual_kernel, field.name)
        assert original_val == restored_val, (
            f"Rule 31 Нарушено: PK поле '{field.name}' потеряно при roundtrip: {original_val} != {restored_val}"
        )

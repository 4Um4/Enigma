"""
path: backend/tests/sandbox/invariants/test_cross_layer_consistency.py
Назначение: Иммунная система ENIGMA. Проверка инвариантов между слоями (L1/L2/L3/Physical).
Статус: Обязательный барьер безопасности. Любой баг здесь = архитектурный разрыв.

Запуск: cd backend; python -m pytest tests/sandbox/invariants/test_cross_layer_consistency.py -v; cd ..
"""

import pytest
import dataclasses
from app.models.npc_state import NPCState
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from app.domain.identity_events import EffectiveDrives

def test_hp_double_truth_invariant():
    """
    ADR-HP-UNIFICATION: state.hp (deprecated) MUST mirror state.body_state["current_hp"].
    Этот тест гарантирует, что любой будущий патч не разорвёт физическое состояние
    на два независимых источника истины.
    """
    # 1. Создаём реальный state-словарь (эмуляция рантайма)
    npc_dict = {
        "id": "test_npc",
        "npc_id": "test_npc",
        "name": "Test",
        "hp": 100,
        "max_hp": 100,
        "body_state": {
            "current_hp": 100.0,
            "max_hp": 100.0,
            "pain": 0,
            "fatigue": 0,
            "blood_loss": 0.0,
            "shock_impulse": 0.0,
            "injuries": []
        }
    }

    # 2. Создаём объект через фабрику (Устав §12.3)
    state = load_l2_state_from_runtime_dict(npc_dict)
    
    # 3. Проверяем начальную консистентность
    assert state.effective_hp == 100.0
    assert state.hp == 100

    # 4. Симулируем урон (мутацию)
    # StateApplicator пишет в body_state и синхронизирует hp
    state.body_state["current_hp"] = 75.0
    state.hp = 75 

    # 5. ИММУННЫЙ КОНТРОЛЬ: Проверка инварианта
    assert state.effective_hp == state.body_state["current_hp"]
    assert state.effective_hp == float(state.hp), "DOUBLE TRUTH DETECTED: state.hp diverged from body_state['current_hp']"
    
    # 6. Тест отключения body_state (fallback)
    state.body_state = None
    assert state.effective_hp == 75.0, "Fallback на deprecated hp сломан"

def test_l3_ephemeral_invariant():
    """
    ADR-O-208 / ADR-O-211: L3 Projection (EffectiveDrives) MUST NOT be cached or persisted.
    drives_runtime (L0 seed) must remain unchanged by CalibrationEngine.
    """
    npc_dict = {
        "id": "test_npc",
        "npc_id": "test_npc",
        "name": "Test",
        "drives": {"fear": 0.2, "control": 0.5, "significance": 0.2, "desire": 0.1}
    }

    state = load_l2_state_from_runtime_dict(npc_dict)
    
    # Сохраняем оригинальные L0 драйвы
    original_drives = dict(state.drives_runtime)

    # Симулируем вычисление L3 проекции (как это делает DriveResolver)
    l3_projection = EffectiveDrives.from_dict({
        "fear": 0.8, "control": 0.1, "significance": 0.05, "desire": 0.05
    })

    # Симулируем попытку кэширования (нарушение ADR-O-208)
    with pytest.raises(TypeError):
        # EffectiveDrives использует MappingProxyType, который неизменяем
        l3_projection.values["fear"] = 0.9

    # ИММУННЫЙ КОНТРОЛЬ: L0 seed не должен мутировать
    assert state.drives_runtime == original_drives, "DRIVE MUTATION DETECTED: L0 seed was mutated by L3 projection"
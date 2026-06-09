"""
Rule 56 (ADR-128): wounds/conditions (legacy identity layer) ≠ body_state.injuries (runtime simulation truth).
body_state = SSOT. Чтение wounds как источник физиологического состояния ЗАПРЕЩЕНО.
Без этого теста CombatSubscriber может начать читать wounds, создав DOUBLE TRUTH.

Запуск: cd backend; python -m pytest tests/sandbox/persistence/test_wounds_not_used_as_physiology_source.py -v --tb=short; cd ..

TODO: 

"""
import pytest
from app.services.combat.combat_subscriber import CombatSubscriber


def test_player_snapshot_ignores_legacy_wounds_reads_body_state():
    """
    Если player_dict содержит ОБА источника (wounds и body_state.injuries),
    _make_player_snapshot ДОЛЖЕН читать ТОЛЬКО body_state.injuries.
    wounds = legacy projection, body_state = SSOT (ADR-128).
    """
    svc = CombatSubscriber
    
    player_dict = {
        # Legacy слой (устаревший, может быть неполным или рассинхронизированным)
        "wounds": [
            {"zone": "head", "severity": "critical", "bleeding": True}  # Фантомная рана
        ],
        "conditions": ["concussion"],
        
        # Runtime truth (SSOT — единственный источник истины)
        "body_state": {
            "current_hp": 80,
            "pain": 30.0,
            "blood_loss": 0.1,
            "shock_impulse": 0.2,
            "consciousness": 1.0,
            "life_status": "ALIVE",
            "injuries": [
                # Реальная рана, которая отличается от legacy
                {"target_zone": "arm", "structural_damage": 0.3, "damage_type": "slash"}
            ],
            "modifiers": {},
            "statuses": ["bleeding"]
        },
        "body_profile": {
            "max_hp": 100.0,
            "abilities": {"strength": 10.0},
        }
    }
    
    snap = svc._make_player_snapshot(player_dict)
    
    # VERDICT: Снапшот должен содержать ТОЛЬКО injury из body_state
    assert "arm" in snap["injuries_by_zone"], "body_state.injury (arm) НЕ попал в снапшот!"
    assert "head" not in snap["injuries_by_zone"], "LEGACY wound (head) ПРОНИК в снапшот! DOUBLE TRUTH обнаружен."
    
    # Дополнительная проверка: HP и pain из body_state, не из wounds
    assert snap["pain"] == 30.0, "Pain взят не из body_state!"
    assert snap["blood_loss"] == 0.1, "blood_loss взят не из body_state!"


def test_npc_snapshot_ignores_legacy_wounds_reads_body_state():
    """
    Тот же инвариант (Rule 56), но для NPC через _build_snapshot.
    _build_snapshot также обязан читать injuries ИСКЛЮЧИТЕЛЬНО из body_state.
    """
    npc_id = "guard_1"
    npc_dict = {
        "id": npc_id,
        "npc_id": npc_id,
        "psyche": {},
        "social_stats": {},
        "body_profile": {"max_hp": 100.0, "abilities": {}},
        # Legacy
        "wounds": [{"zone": "leg", "severity": "light"}],
        # Runtime truth
        "body_state": {
            "current_hp": 90,
            "pain": 10.0,
            "fatigue": 5.0,
            "blood_loss": 0.05,
            "consciousness": 1.0,
            "shock_impulse": 0.0,
            "injuries": [
                {"target_zone": "chest", "structural_damage": 0.6, "damage_type": "blunt"}
            ],
            "modifiers": {},
            "statuses": []
        }
    }
    npc_by_id = {npc_id: npc_dict}
    
    snap = CombatSubscriber._build_snapshot(npc_id, npc_by_id)
    
    assert snap is not None, "Снапшот NPC не создан"
    # VERDICT: Снапшот должен содержать ТОЛЬКО injury из body_state
    assert "chest" in snap["injuries_by_zone"], "body_state.injury (chest) НЕ попал в снапшот NPC!"
    assert "leg" not in snap["injuries_by_zone"], "LEGACY wound (leg) ПРОНИК в снапшот NPC! DOUBLE TRUTH обнаружен."
# backend/tests/pbt/properties/test_npc_state_roundtrip.py
"""
Invariant 12.2 (WARA): to_persistence_dict обязан записывать КАЖДОЕ поле,
которое from_legacy читает.

Запуск: cd backend; python -m pytest tests/pbt/properties/test_npc_state_roundtrip.py -v; cd ..
"""
from hypothesis import given, settings, HealthCheck
from tests.pbt.strategies import npc_legacy_strategy
from app.models.npc_state import NPCState, NPCStateAdapter

@given(npc_dict=npc_legacy_strategy)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_npc_state_roundtrip_preserves_critical_fields(npc_dict: dict):
    """Тест: from_legacy -> to_persistence_dict -> from_legacy не теряет данные."""
    # 1. Создаём объект из сгенерированного dict
    original_state = NPCStateAdapter.from_legacy(npc_dict)
    
    # 2. Сериализуем обратно в dict
    written_dict = dict(npc_dict)  # Копируем, чтобы to_persistence_dict мог мутировать
    NPCState.to_persistence_dict(original_state, written_dict)
    
    # 3. Снова создаём объект из записанного dict
    final_state = NPCStateAdapter.from_legacy(written_dict)
    
    # 4. Проверяем, что критические поля не потерялись
    assert original_state.npc_id == final_state.npc_id, f"npc_id changed! {original_state.npc_id} -> {final_state.npc_id}"
    
    # Проверяем body_state (ADR-HP-UNIFICATION) — хранится как dict
    if original_state.body_state and final_state.body_state:
        assert original_state.body_state.get("current_hp") == final_state.body_state.get("current_hp"), "current_hp lost in round-trip!"
        
    # Проверяем расщеплённые поля psyche (stress, will_state)
    assert original_state.stress == final_state.stress, f"stress lost in round-trip! {original_state.stress} -> {final_state.stress}"
    assert original_state.will_state == final_state.will_state, f"will_state lost in round-trip! {original_state.will_state} -> {final_state.will_state}"
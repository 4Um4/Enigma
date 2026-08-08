# backend/tests/pbt/properties/test_inv_causal_provenance.py
"""
Property Test: Инвариант I (Causal Provenance) для любого InterventionEvent.

Запуск: cd backend; python -m pytest tests/pbt/properties/test_inv_causal_provenance.py -v; cd ..
"""
from hypothesis import given, strategies as st
from tests.pbt.strategies import npc_legacy_strategy
from tests.pbt.validators import CausalProvenanceValidator

# Стратегия для InterventionEvent
intervention_strategy = st.fixed_dictionaries({
    "source": st.sampled_from(["player", "dm", "world"]),
    "target_id": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
    "payload": st.text(min_size=1, max_size=50)
})

@given(
    npc_list=st.lists(npc_legacy_strategy, min_size=2, max_size=5, unique_by=lambda x: x["id"]),
    intervention=intervention_strategy
)
def test_inv_causal_provenance_holds_for_any_intervention(npc_list, intervention):
    """
    Invariant I: любое изменение наблюдаемого состояния имеет конечную причинную цепь.
    """
    # Снапшот "До": состояние мира
    snapshot_before = {"npcs": npc_list}
    
    # Создаём снапшот "После", изменяя только целевого NPC (как и должно быть)
    target_id = intervention["target_id"]
    npc_after_list = []
    for npc in npc_list:
        if npc["id"] == target_id:
            # Изменяем стейт цели (например, стресс)
            _modified = npc.copy()
            _modified["psyche"] = npc["psyche"].copy()
            _modified["psyche"]["stress"] = min(1.0, npc["psyche"]["stress"] + 0.1)
            npc_after_list.append(_modified)
        else:
            npc_after_list.append(npc.copy()) # Остальные неизменны
            
    snapshot_after = {"npcs": npc_after_list}
    
    drift = CausalProvenanceValidator.validate(snapshot_before, snapshot_after, intervention)
    assert drift.has_causal_chain(), f"Нарушение инварианта I: {drift.unexplained_changes}"
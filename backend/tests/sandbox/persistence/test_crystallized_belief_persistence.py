# backend/tests/sandbox/persistence/test_crystallized_belief_persistence.py
# ФАЗА -1: Проверка персистентности CrystallizedBeliefStore (DEEP-013)

import pytest
from app.domain.identity_events import CrystallizedBelief
from app.services.memory.sqlite_store import SqliteMemoryStore
from app.services.npc.crystallized_belief_store import CrystallizedBeliefStore


@pytest.fixture
def memory_store():
    return SqliteMemoryStore(":memory:")


def test_beliefs_survive_restart(memory_store):
    """DEEP-013: Убеждения должны сохраняться при рестарте через SQLite backing."""
    store1 = CrystallizedBeliefStore(store=memory_store, campaign_id="test_camp")
    belief = CrystallizedBelief(
        source_id="player",
        trait="fear",
        weight=0.8,
        last_updated_tick=10,
    )
    store1.update_beliefs("npc_1", [belief])
    
    assert len(store1.get_beliefs("npc_1")) == 1
    
    # Симулируем рестарт сервера (создаём новый объект с тем же store)
    store2 = CrystallizedBeliefStore(store=memory_store, campaign_id="test_camp")
    
    # Данные должны были сохраниться
    beliefs = store2.get_beliefs("npc_1")
    assert len(beliefs) == 1
    assert beliefs[0].source_id == "player"
    assert beliefs[0].trait == "fear"
    assert beliefs[0].weight == 0.8
    assert beliefs[0].last_updated_tick == 10

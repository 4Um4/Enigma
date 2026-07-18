# backend/tests/sandbox/persistence/test_l1_chronicle_archival.py
# ФАЗА -1: Проверка архивации L1Chronicle (R2 Z.ai Audit)

import pytest
from app.domain.identity_events import TraitDriftEvent
from app.services.memory.sqlite_store import SqliteMemoryStore
from app.services.npc.l1_chronicle import L1Chronicle


@pytest.fixture
def memory_store():
    return SqliteMemoryStore(":memory:")


def test_archive_old_events_does_not_crash(memory_store):
    """Проверка R2: archive_old_events не должен падать с tuple index out of range."""
    chronicle = L1Chronicle(store=memory_store, campaign_id="test_camp")
    
    # Добавляем 10 событий
    for i in range(10):
        evt = TraitDriftEvent(
            tick_id=i,
            target_id="npc_1",
            source_id="player",
            effect_value=0.1,
            observation_weight=1.0,
            event_type="player_attacks",
        )
        chronicle.append(evt)
    
    # Архивируем события старше 5 тика
    # Ранее здесь падало: tuple index out of range
    chronicle.archive_old_events(current_tick=10, max_ticks_in_memory=5)
    
    # Проверяем, что в активной таблице остались только события >= 5
    rows = memory_store.query(
        "SELECT tick_id FROM l1_chronicle_events WHERE target_id = ?",
        ("npc_1",)
    )
    assert len(rows) == 5
    assert all(r["tick_id"] >= 5 for r in rows)

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
    
    # Проверяем, что в RAM-кэше остались только события >= 5
    # Rule 28: L1Chronicle строго append-only, SQL-таблица не очищается, query_raw возвращает RAM+SQL.
    active_events = chronicle._events.get("npc_1", [])
    assert len(active_events) == 5
    assert all(e.tick_id >= 5 for e in active_events)

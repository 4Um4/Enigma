"""P0-1..P0-5: campaign reset очищает старую кампанию, не повреждая другие.

- P0-1: _identity_cache in-memory (per-campaign prefix)
- P0-2: state_collections["identity_cache"] (persist + reload)
- P0-4: memory_crystals (per-campaign)
- P0-5: experience_traces (per-campaign)
- §4.5: reset одной кампании не уничтожает память другой
- §4.6: состояние после повторной загрузки из SQLite

P0-3 (_pending_dialogue_memories) — DEFERRED: EventDTO не несёт campaign_id.
Контракт add_pending_dialogue_memory не расширялся; глобальный буфер не чистится.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.memory.layered_memory import LayeredMemory
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.sqlite_store import SqliteMemoryStore


CAMPAIGN_A = "camp_A"
CAMPAIGN_B = "camp_B"
NPC_A = "npc_a"
NPC_B = "npc_b"


def _make_manager(tmp_path):
    store = SqliteMemoryStore(tmp_path / "enigma_memory.db")
    layered = LayeredMemory(store)
    manager = MemoryManager(layered, data_dir=str(tmp_path))
    return manager, store


def _seed_identity(manager, campaign, npc, trait):
    manager.apply_identity_weights(campaign, npc, [(trait, 0.5)])


def _seed_crystal(store, campaign, subject):
    crystal = SimpleNamespace(
        owner_id="owner",
        subject=subject,
        predicate="is",
        origin_reference=f"origin-{subject}",
        object="object",
        source="test",
        related_episodes=(),
        confidence=0.5,
        retrieval_strength=0.5,
        emotional_weight=0.0,
        last_reinforced=0,
        times_recalled=0,
    )
    store.save_crystal(campaign, crystal)


def _seed_trace(store, campaign, content_ref):
    trace = SimpleNamespace(
        owner_id="owner",
        content_reference=content_ref,
        source_id=f"src-{content_ref}",
        source_type=SimpleNamespace(value="testimony"),
        actor_id="actor",
        meaning=None,
        valence=0.0,
        arousal=0.0,
        novelty=0.0,
        personal_relevance=0.0,
        social_relevance=0.0,
        identity_relevance=0.0,
        belief_relevance=0.0,
        confidence=0.5,
        retrieval_strength=0.5,
        timestamp=0,
        diagnostic=1,
        applied_consumers=(),
    )
    store.save_trace(campaign, trace)


def test_p0_1_reset_clears_identity_cache_in_memory_for_one_campaign(tmp_path):
    manager, _ = _make_manager(tmp_path)
    _seed_identity(manager, CAMPAIGN_A, NPC_A, "resentment")
    _seed_identity(manager, CAMPAIGN_B, NPC_B, "dependency")
    manager.reset_campaign_state(CAMPAIGN_A)

    assert manager.get_identity_traits(CAMPAIGN_A, NPC_A) == {}
    assert manager.get_identity_traits(CAMPAIGN_B, NPC_B) == {"dependency": 0.5}


def test_p0_2_reset_persists_filtered_identity_cache_to_store(tmp_path):
    manager, store = _make_manager(tmp_path)
    _seed_identity(manager, CAMPAIGN_A, NPC_A, "resentment")
    _seed_identity(manager, CAMPAIGN_B, NPC_B, "dependency")
    manager.reset_campaign_state(CAMPAIGN_A)

    persisted = store.load_state("identity_cache")
    assert f"{CAMPAIGN_A}:{NPC_A}" not in persisted
    assert f"{CAMPAIGN_B}:{NPC_B}" in persisted


def test_p0_2_reset_survives_manager_reload_from_store(tmp_path):
    manager, store = _make_manager(tmp_path)
    _seed_identity(manager, CAMPAIGN_A, NPC_A, "resentment")
    _seed_identity(manager, CAMPAIGN_B, NPC_B, "dependency")
    manager.reset_campaign_state(CAMPAIGN_A)

    reloaded = MemoryManager(LayeredMemory(store), data_dir=str(tmp_path))
    assert reloaded.get_identity_traits(CAMPAIGN_A, NPC_A) == {}
    assert reloaded.get_identity_traits(CAMPAIGN_B, NPC_B) == {"dependency": 0.5}


def test_p0_4_p0_5_delete_campaign_removes_crystals_and_traces(tmp_path):
    _, store = _make_manager(tmp_path)
    _seed_crystal(store, CAMPAIGN_A, "subj_A")
    _seed_crystal(store, CAMPAIGN_B, "subj_B")
    _seed_trace(store, CAMPAIGN_A, "cr_A")
    _seed_trace(store, CAMPAIGN_B, "cr_B")

    store.delete_campaign(CAMPAIGN_A)

    assert store.load_crystals(CAMPAIGN_A, "owner") == []
    assert store.load_crystals(CAMPAIGN_B, "owner") != []
    assert store.load_traces(CAMPAIGN_A, "owner") == []
    assert store.load_traces(CAMPAIGN_B, "owner") != []


def test_reset_does_not_touch_other_campaign_state(tmp_path):
    manager, store = _make_manager(tmp_path)
    _seed_identity(manager, CAMPAIGN_A, NPC_A, "resentment")
    _seed_identity(manager, CAMPAIGN_B, NPC_B, "dependency")
    _seed_crystal(store, CAMPAIGN_A, "subj_A")
    _seed_crystal(store, CAMPAIGN_B, "subj_B")
    _seed_trace(store, CAMPAIGN_A, "cr_A")
    _seed_trace(store, CAMPAIGN_B, "cr_B")

    manager.reset_campaign_state(CAMPAIGN_A)

    assert manager.get_identity_traits(CAMPAIGN_A, NPC_A) == {}
    assert store.load_crystals(CAMPAIGN_A, "owner") == []
    assert store.load_traces(CAMPAIGN_A, "owner") == []

    assert manager.get_identity_traits(CAMPAIGN_B, NPC_B) == {"dependency": 0.5}
    assert store.load_crystals(CAMPAIGN_B, "owner") != []
    assert store.load_traces(CAMPAIGN_B, "owner") != []


def test_p0_x2_delete_campaign_uses_exact_collection_match(tmp_path):
    """P0-X2: entries LIKE %cid% удалял подстроки чужих кампаний (data loss).

    Ожидание после фикса:
    - точные коллекции целевой кампании удалены: campaign_canon_<A>,
      playthrough_<A>, npc_memory_<A>;
    - коллекции другой кампании и подстрочные коллизии целы;
    - world_canon_{wid} не трогается (world-scoped, не per-campaign).
    """
    _, store = _make_manager(tmp_path)

    # Целевая кампания A — три per-campaign коллекции
    store.append("campaign_canon_A", {"event": "A1"})
    store.append("playthrough_A", {"event": "A2"})
    store.append("npc_memory_A", {"event": "A3"})

    # Другая кампания B — не должна трогаться
    store.append("campaign_canon_B", {"event": "B1"})
    store.append("playthrough_B", {"event": "B2"})
    store.append("npc_memory_B", {"event": "B3"})

    # Подстрочные коллизии (LIKE %A% убивал их, точный IN — не должен)
    store.append("campaign_canon_A_old", {"event": "old"})
    store.append("campaign_canon_ABCD", {"event": "abcd"})
    store.append("playthrough_X_A_suffix", {"event": "suffix"})

    # world_canon — world-scoped, не per-campaign
    store.append("world_canon_W_A", {"event": "world"})

    store.delete_campaign("A")

    # Целевая A — пусто
    assert store.recent("campaign_canon_A", limit=10) == []
    assert store.recent("playthrough_A", limit=10) == []
    assert store.recent("npc_memory_A", limit=10) == []

    # Другая кампания B — цела
    assert store.recent("campaign_canon_B", limit=10) != []
    assert store.recent("playthrough_B", limit=10) != []
    assert store.recent("npc_memory_B", limit=10) != []

    # Подстрочные коллизии — целы (регресс от старого LIKE)
    assert store.recent("campaign_canon_A_old", limit=10) != []
    assert store.recent("campaign_canon_ABCD", limit=10) != []
    assert store.recent("playthrough_X_A_suffix", limit=10) != []

    # world_canon не тронут
    assert store.recent("world_canon_W_A", limit=10) != []


def test_p0_3_pending_dialogue_memories_deferred():
    pytest.skip(
        "P0-3 deferred: EventDTO does not carry campaign_id; "
        "add_pending_dialogue_memory contract unchanged; "
        "global buffer is not cleared automatically."
    )

"""
Тесты восстановления состояния NPC при TRANSFER между локациями (ADR-O-442).

Доказывают границу долговременной фиксации:
- Сценарий A: Crash до unlock_tick -> восстанавливается OLD_LOCATION, дубликатов нет.
- Сценарий B: Успешный unlock_tick -> восстанавливается NEW_LOCATION, дубликатов нет.
"""
import pytest
from pathlib import Path
import sys

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.state.sqlite_persistence_adapter import SqlitePersistenceAdapter
from app.services.tick_orchestrator import TickOrchestrator
from unittest.mock import MagicMock

CAMPAIGN = "transfer_test_camp"
NPC_ID = "test_npc_1"
OLD_LOC = "tavern"
NEW_LOC = "market"


def _create_initial_state():
    all_npcs_raw = [
        {
            "id": NPC_ID,
            "npc_id": NPC_ID,
            "location_id": OLD_LOC,
            "location": OLD_LOC,
            "name": "Test NPC",
        }
    ]
    scene_old = {
        "location_id": OLD_LOC,
        "campaign_id": CAMPAIGN,
        "tick": 1,
        "npc_positions": {
            NPC_ID: {"position": f"{OLD_LOC}:node_1", "name": "Test NPC"}
        },
    }
    return all_npcs_raw, scene_old


def _simulate_transfer_in_ram(all_npcs_raw, scene_old):
    all_npcs_raw[0]["location_id"] = NEW_LOC
    all_npcs_raw[0]["location"] = NEW_LOC
    scene_old["npc_positions"].pop(NPC_ID, None)
    scene_new = {
        "location_id": NEW_LOC,
        "campaign_id": CAMPAIGN,
        "tick": 1,
        "npc_positions": {
            NPC_ID: {"position": f"{NEW_LOC}:node_1", "name": "Test NPC"}
        },
    }
    return scene_new


def test_transfer_crash_before_unlock(tmp_path):
    db_path = tmp_path / "crash_before.db"
    
    adapter = SqlitePersistenceAdapter(db_path)
    all_npcs_raw, scene_old = _create_initial_state()
    adapter.atomic_commit_all(CAMPAIGN, {OLD_LOC: scene_old}, all_npcs_raw)
    
    scene_new = _simulate_transfer_in_ram(all_npcs_raw, scene_old)
    
    adapter.close()
    
    new_adapter = SqlitePersistenceAdapter(db_path)
    
    loaded_npcs = new_adapter.load_npc_runtime(CAMPAIGN)
    assert loaded_npcs is not None, "NPC runtime должен быть загружен"
    
    loaded_npc = next((n for n in loaded_npcs if n.get("id") == NPC_ID), None)
    assert loaded_npc is not None, "NPC должен быть найден в загруженных данных"
    
    assert loaded_npc["location_id"] == OLD_LOC, (
        f"Crash до unlock_tick должен восстановить OLD_LOCATION. "
        f"Ожидалось: {OLD_LOC}, получено: {loaded_npc['location_id']}"
    )
    
    loaded_scene_old = new_adapter.load_scene_at(CAMPAIGN, OLD_LOC)
    assert loaded_scene_old is not None, "Старая сцена должна быть загружена"
    assert NPC_ID in loaded_scene_old.get("npc_positions", {}), (
        "NPC должен остаться в npc_positions старой сцены при откате"
    )
    
    loaded_scene_new = new_adapter.load_scene_at(CAMPAIGN, NEW_LOC)
    assert loaded_scene_new is None or NPC_ID not in loaded_scene_new.get("npc_positions", {}), (
        "NPC не должен присутствовать в новой сцене, т.к. коммита не было"
    )
    
    mock_scene_manager = MagicMock()
    mock_scene_manager._persistence = new_adapter
    new_orch = TickOrchestrator(scene_manager=mock_scene_manager)
    
    assert not getattr(new_orch, "_npc_runtime_locations", {}), (
        "Новый TickOrchestrator должен иметь пустой _npc_runtime_locations после restart"
    )
    
    new_adapter.close()


def test_transfer_successful_unlock_then_restart(tmp_path):
    db_path = tmp_path / "successful_unlock.db"
    
    adapter = SqlitePersistenceAdapter(db_path)
    all_npcs_raw, scene_old = _create_initial_state()
    adapter.atomic_commit_all(CAMPAIGN, {OLD_LOC: scene_old}, all_npcs_raw)
    
    scene_new = _simulate_transfer_in_ram(all_npcs_raw, scene_old)
    
    success = adapter.atomic_commit_all(
        CAMPAIGN, 
        {OLD_LOC: scene_old, NEW_LOC: scene_new}, 
        all_npcs_raw
    )
    assert success is True, "atomic_commit_all должен вернуть True при успешном коммите"
    
    adapter.close()
    new_adapter = SqlitePersistenceAdapter(db_path)
    
    loaded_npcs = new_adapter.load_npc_runtime(CAMPAIGN)
    assert loaded_npcs is not None, "NPC runtime должен быть загружен"
    
    loaded_npc = next((n for n in loaded_npcs if n.get("id") == NPC_ID), None)
    assert loaded_npc is not None, "NPC должен быть найден в загруженных данных"
    
    assert loaded_npc["location_id"] == NEW_LOC, (
        f"После успешного unlock_tick должна восстановиться NEW_LOCATION. "
        f"Ожидалось: {NEW_LOC}, получено: {loaded_npc['location_id']}"
    )
    
    loaded_scene_old = new_adapter.load_scene_at(CAMPAIGN, OLD_LOC)
    assert loaded_scene_old is not None, "Старая сцена должна быть загружена"
    assert NPC_ID not in loaded_scene_old.get("npc_positions", {}), (
        "NPC должен быть удалён из npc_positions старой сцены после успешного TRANSFER"
    )
    
    loaded_scene_new = new_adapter.load_scene_at(CAMPAIGN, NEW_LOC)
    assert loaded_scene_new is not None, "Новая сцена должна быть загружена"
    assert NPC_ID in loaded_scene_new.get("npc_positions", {}), (
        "NPC должен присутствовать в npc_positions новой сцены после успешного TRANSFER"
    )
    
    mock_scene_manager = MagicMock()
    mock_scene_manager._persistence = new_adapter
    new_orch = TickOrchestrator(scene_manager=mock_scene_manager)
    
    assert not getattr(new_orch, "_npc_runtime_locations", {}), (
        "Новый TickOrchestrator должен иметь пустой _npc_runtime_locations после restart"
    )
    
    new_adapter.close()
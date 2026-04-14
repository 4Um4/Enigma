# tests/test_persistence_port.py
"""Тесты PersistencePort и SceneStateManager.commit()"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from app.services.state.persistence_port import PersistencePort
from app.services.state.json_persistence_adapter import JsonPersistenceAdapter
from app.services.scene_state_manager import SceneStateManager


class TestPersistencePortContract:
    """Порт требует реализации обоих методов."""
    
    def test_cannot_instantiate_abstract(self):
        """PersistencePort нельзя создать напрямую."""
        with pytest.raises(TypeError):
            PersistencePort()
    
    def test_concrete_implementation_works(self, tmp_path):
        """JsonPersistenceAdapter реализует оба метода."""
        adapter = JsonPersistenceAdapter(tmp_path)
        assert hasattr(adapter, "save_scene")
        assert hasattr(adapter, "save_npcs")


class TestJsonPersistenceAdapter:
    """Тесты JSON реализации."""
    
    def test_save_npcs_creates_file(self, tmp_path):
        """save_npcs создаёт файл major_npcs.json."""
        adapter = JsonPersistenceAdapter(tmp_path)
        adapter.save_npcs([{"id": "test_npc", "psyche": {"stress": 50}}])
        
        result_file = tmp_path / "npcs" / "major_npcs.json"
        assert result_file.exists()
        
        import json
        with open(result_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["id"] == "test_npc"
    
    def test_save_scene_creates_campaign_file(self, tmp_path):
        """save_scene создаёт campaign_state.json."""
        adapter = JsonPersistenceAdapter(tmp_path)
        scene = {"location_id": "tavern", "objects": {}}
        adapter.save_scene("test-campaign", scene)
        
        result_file = tmp_path / "campaigns" / "test-campaign" / "campaign_state.json"
        assert result_file.exists()
        
        import json
        with open(result_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["scene_state"]["location_id"] == "tavern"


class TestSceneStateManagerCommit:
    """Тесты commit boundary в SceneStateManager."""
    
    def test_commit_without_persistence_returns_zero(self):
        """commit() без порта возвращает 0 и не падает."""
        manager = SceneStateManager()
        result = manager.commit("test", {"location": "tavern"})
        assert result == 0
    
    def test_commit_calls_both_saves(self, tmp_path):
        """commit() с портом вызывает save_scene + save_npcs."""
        mock_port = MagicMock(spec=PersistencePort)
        manager = SceneStateManager(tmp_path, persistence=mock_port)
        
        scene = {"location_id": "tavern"}
        npcs = [{"id": "npc1"}]
        
        result = manager.commit("camp-1", scene, npcs)
        
        assert result == 2
        mock_port.save_scene.assert_called_once_with("camp-1", scene)
        mock_port.save_npc_runtime.assert_called_once_with("camp-1", npcs)
    
    def test_commit_scene_only(self, tmp_path):
        """commit() без npc_dicts сохраняет только сцену."""
        mock_port = MagicMock(spec=PersistencePort)
        manager = SceneStateManager(tmp_path, persistence=mock_port)
        
        result = manager.commit("camp-1", {"location": "tavern"})
        
        assert result == 1
        mock_port.save_scene.assert_called_once()
        mock_port.save_npc_runtime.assert_not_called()
    
    def test_commit_continues_on_scene_error(self, tmp_path):
        """commit() продолжает сохранять NPC даже если сцена упала."""
        mock_port = MagicMock(spec=PersistencePort)
        mock_port.save_scene.side_effect = OSError("disk full")
        manager = SceneStateManager(tmp_path, persistence=mock_port)
        
        result = manager.commit("camp-1", {"loc": "x"}, [{"id": "n1"}])
        
        # scene упал (0), npc runtime сохранился (1)
        assert result == 1
        mock_port.save_npc_runtime.assert_called_once_with("camp-1", [{"id": "n1"}])

# tests/test_persistence_port.py
"""Тесты PersistencePort и SceneStateManager.commit()"""

from unittest.mock import MagicMock

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.scene_state_manager import SceneStateManager
from app.services.state.json_persistence_adapter import JsonPersistenceAdapter
from app.services.state.persistence_port import PersistencePort


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

        result_file = tmp_path / "saves" / "test-campaign" / "campaign_state.json"
        assert result_file.exists()

        import json

        with open(result_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["scenes"]["tavern"]["location_id"] == "tavern"


class TestSceneStateManagerCommit:
    """Тесты commit boundary в SceneStateManager."""

    def test_commit_without_persistence_returns_zero(self):
        """commit() без порта возвращает 0 и не падает."""
        manager = SceneStateManager()
        result = manager.commit("test", {"location": "tavern"})
        assert result == 0

    def test_commit_calls_both_saves(self, tmp_path):
        """commit() с портом делегирует в atomic_commit_all через unlock_tick.

        _version инкрементируется при commit() — версионность состояния.
        """
        mock_port = MagicMock(spec=PersistencePort)
        mock_port.atomic_commit.return_value = True
        manager = SceneStateManager(tmp_path, persistence=mock_port)

        scene = {"location_id": "tavern"}
        npcs = [{"id": "npc1"}]

        # S186: Эмулируем успешную блокировку тика и заполнение RAM-кэша.
        manager._tick_locked = True
        manager._tick_campaign_id = "camp-1"
        manager._tick_scenes = {"tavern": scene}
        
        result = manager.commit("camp-1", scene, npcs)
        manager.unlock_tick("camp-1")

        assert result == 2
        mock_port.atomic_commit_all.assert_called_once()

    def test_commit_scene_only(self, tmp_path):
        """commit() без npc_dicts делегирует в atomic_commit с None.

        _version инкрементируется при commit() — версионность состояния,
        отдельно от тика (время = ось, состояние = срез).
        """
        mock_port = MagicMock(spec=PersistencePort)
        mock_port.atomic_commit.return_value = True
        manager = SceneStateManager(tmp_path, persistence=mock_port)

        scene = {"location_id": "tavern"}
        
        manager._tick_locked = True
        manager._tick_campaign_id = "camp-1"
        manager._tick_scenes = {"tavern": scene}
        
        result = manager.commit("camp-1", scene)
        manager.unlock_tick("camp-1")

        assert result == 2
        mock_port.atomic_commit_all.assert_called_once()

    def test_commit_continues_on_scene_error(self, tmp_path):
        """unlock_tick вызывает atomic_commit_all даже для невалидных сцен (fallback на 'default')."""
        mock_port = MagicMock(spec=PersistencePort)
        manager = SceneStateManager(tmp_path, persistence=mock_port)

        scene = {"loc": "x"} # Невалидная сцена (нет location_id)
        
        manager._tick_locked = True
        manager._tick_campaign_id = "camp-1"
        manager._tick_scenes = {}
        
        result = manager.commit("camp-1", scene, [{"id": "n1"}])
        manager.unlock_tick("camp-1")

        # S186: commit() всегда возвращает 2 (успех обновления RAM-кэша)
        assert result == 2
        # commit() добавил сцену в кэш под ключом "default", поэтому atomic_commit_all вызывается
        mock_port.atomic_commit_all.assert_called_once()

class TestSaveVersioningContract:
    """COV-D59 / ADR-O-426 Шаг 2 (вердикт В5): версия, содержимое, metadata,
    обратная совместимость v0-ридера — раздельные проверки, не подгонка."""

    def test_save_scene_at_stamps_version(self, tmp_path):
        adapter = JsonPersistenceAdapter(tmp_path)
        adapter.save_scene_at("c", "tavern", {"location_id": "tavern", "x": 1})
        import json
        data = json.loads((tmp_path / "saves" / "c" / "campaign_state.json").read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
        assert data["scenes"]["tavern"]["x"] == 1

    def test_save_scene_at_drops_legacy_key(self, tmp_path):
        adapter = JsonPersistenceAdapter(tmp_path)
        state_file = tmp_path / "saves" / "c" / "campaign_state.json"
        state_file.parent.mkdir(parents=True)
        import json
        state_file.write_text(json.dumps({"scene_state": {"location_id": "old", "stale": True}}), encoding="utf-8")
        adapter.save_scene_at("c", "tavern", {"location_id": "tavern"})
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert "scene_state" not in data
        assert data["scenes"]["tavern"]["location_id"] == "tavern"
        assert data["schema_version"] == 1

    def test_save_scene_at_preserves_metadata(self, tmp_path):
        adapter = JsonPersistenceAdapter(tmp_path)
        state_file = tmp_path / "saves" / "c" / "campaign_state.json"
        state_file.parent.mkdir(parents=True)
        import json
        state_file.write_text(json.dumps({"metadata": {"current_location": "tavern"}}), encoding="utf-8")
        adapter.save_scene_at("c", "tavern", {"location_id": "tavern"})
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["metadata"] == {"current_location": "tavern"}

    def test_v0_reader_compat(self, tmp_path):
        from app.services.state.save_migrations import extract_scene_payload
        adapter = JsonPersistenceAdapter(tmp_path)
        adapter.save_scene_at("c", "tavern", {"location_id": "tavern", "x": 1})
        import json
        data = json.loads((tmp_path / "saves" / "c" / "campaign_state.json").read_text(encoding="utf-8"))
        scene = extract_scene_payload(data, "tavern")
        assert scene is not None and scene["x"] == 1
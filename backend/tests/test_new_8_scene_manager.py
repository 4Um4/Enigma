# backend/tests/test_new_8_scene_manager.py
import tempfile
from pathlib import Path

import pytest
from app.services.scene_state_manager import SceneStateManager


def test_new_8_scene_manager_preserves_recognition():
    db_path = Path(tempfile.gettempdir()) / "test_scene_mgr_recognition.db"
    if db_path.exists():
        db_path.unlink()
        
    mgr = SceneStateManager(data_dir=Path(tempfile.gettempdir()), saves_dir=Path(tempfile.gettempdir()))
    # Подменяем persistence на SQLite in-memory/file
    from app.services.state.sqlite_persistence_adapter import SqlitePersistenceAdapter
    mgr._persistence = SqlitePersistenceAdapter(db_path)
    
    # Мокаем методы обогащения, чтобы не зависеть от файлов локаций
    mgr._enrich_local_positions = lambda campaign_id, scene_state: None
    mgr._enrich_spatial_data = lambda campaign_id, scene_state: None
    
    campaign_id = "test_campaign"
    npc_id = "maid_lusya"
    location_id = "tavern"

    # 1. Arrange: Начальная сцена с player_recognition
    initial_scene = {
        "location_id": location_id,
        "tick": 1,
        "npc_positions": {npc_id: {"x": 1.0, "y": 2.0, "name": "Люся"}},
        "player_recognition": {npc_id: {"confidence": 1.0}}
    }
    mgr.save_scene_state(campaign_id, initial_scene)

    # 2. Act: Симуляция тика (lock -> mutate -> commit -> unlock)
    locked_scene = mgr.lock_for_tick(campaign_id, location_id)
    assert locked_scene is not None, "lock_for_tick вернул None!"
    
    # Проверяем, что распознавание загрузилось
    assert "player_recognition" in locked_scene, "player_recognition потерян при lock_for_tick!"
    assert locked_scene["player_recognition"][npc_id]["confidence"] == 1.0

    # Симулируем мутацию ядра (например, изменение позиции)
    locked_scene["tick"] = 2
    locked_scene["npc_positions"][npc_id]["x"] = 1.5
    
    # Коммитим результат тика
    mgr.commit_tick_result(campaign_id, locked_scene)
    
    # Разблокируем тик (сохранение на диск)
    mgr.unlock_tick(campaign_id)
    
    # 3. Act: Симуляция следующего тика (lock)
    next_scene = mgr.lock_for_tick(campaign_id, location_id)
    
    # 4. Assert
    assert next_scene is not None, "lock_for_tick на следующем тике вернул None!"
    assert next_scene["tick"] == 2, "Тик не сохранился!"
    assert "player_recognition" in next_scene, "player_recognition потерян после unlock/lock!"
    assert npc_id in next_scene["player_recognition"], "NPC потерян из player_recognition!"
    confidence = next_scene["player_recognition"][npc_id].get("confidence", 0.0)
    assert confidence == 1.0, f"Confidence сбросился после тика! Ожидалось 1.0, получено {confidence}"

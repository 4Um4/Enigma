# backend/tests/test_new_8_recognition_memory.py
import pytest
import tempfile
from pathlib import Path
from app.services.state.sqlite_persistence_adapter import SqlitePersistenceAdapter

def test_new_8_player_recognition_survives_save_load():
    db_path = Path(tempfile.gettempdir()) / "test_recognition.db"
    if db_path.exists():
        db_path.unlink()
        
    adapter = SqlitePersistenceAdapter(db_path)
    campaign_id = "test_campaign"
    npc_id = "maid_lusya"
    
    scene_state = {
        "location_id": "tavern",
        "tick": 1,
        "npc_positions": {
            npc_id: {"x": 1.0, "y": 2.0, "name": "Lusya"}
        },
        "player_recognition": {
            npc_id: {"confidence": 1.0}
        }
    }
    
    adapter.save_scene(campaign_id, scene_state)
    loaded_scene = adapter.load_scene(campaign_id)
    
    assert loaded_scene is not None
    assert "player_recognition" in loaded_scene
    assert npc_id in loaded_scene["player_recognition"]
    confidence = loaded_scene["player_recognition"][npc_id].get("confidence", 0.0)
    assert confidence == 1.0

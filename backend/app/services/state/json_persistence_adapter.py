# backend/app/services/state/json_persistence_adapter.py
"""
JsonPersistenceAdapter — JSON реализация PersistencePort.

Сохраняет:
- scene_state -> campaigns/{id}/campaign_state.json
- npc_dicts -> npcs/major_npcs.json

Использует ту же структуру файлов, что и оригинальный код.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path

from app.services.state.persistence_port import PersistencePort

logger = logging.getLogger(__name__)


class JsonPersistenceAdapter(PersistencePort):
    """
    JSON реализация порта сохранения.
    Совместима с текущей структурой данных ENIGMA.
    """
    
    def __init__(self, data_dir: Path) -> None:
        self._campaigns_dir = data_dir / "campaigns"
        self._npcs_path = data_dir / "npcs" / "major_npcs.json"
    
    def save_scene(self, campaign_id: str, scene_state: dict) -> None:
        """Сохраняет scene_state в campaign_state.json."""
        campaign_file = self._campaigns_dir / campaign_id / "campaign_state.json"
        try:
            campaign_file.parent.mkdir(parents=True, exist_ok=True)
            data: dict = {}
            if campaign_file.exists():
                with open(campaign_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["scene_state"] = scene_state
            with open(campaign_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[PERSISTENCE] Scene saved: {campaign_id}")
        except OSError as e:
            logger.error(f"[PERSISTENCE] Error saving scene: {e}")
    
    def save_npcs(self, npc_dicts: list[dict]) -> None:
        """Сохраняет NPC в major_npcs.json."""
        try:
            self._npcs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._npcs_path, "w", encoding="utf-8") as f:
                json.dump(npc_dicts, f, ensure_ascii=False, indent=2)
            logger.debug(f"[PERSISTENCE] NPCs saved: {len(npc_dicts)} records")
        except OSError as e:
            logger.error(f"[PERSISTENCE] Error saving NPCs: {e}")

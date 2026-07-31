"""
Назначение: скрипт, который проверяет, в каком формате сохранена кампания.
"""

import json
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

def is_legacy_save(campaign_state: dict) -> bool:
    """True если сейв в старом формате (single scene_state, без scenes dict)."""
    if not isinstance(campaign_state, dict):
        return False
    if 'scenes' in campaign_state:
        return False # новый формат
    if 'scene_state' in campaign_state:
        return True # старый формат (одиночная scene_state)
    return False # пустой сейв или неизвестный формат

def detect_legacy_saves(saves_dir: Path) -> List[str]:
    """Возвращает список campaign_id с legacy сейвами."""
    legacy = []
    if not saves_dir.exists():
        return legacy
        
    for campaign_dir in saves_dir.iterdir():
        if not campaign_dir.is_dir():
            continue
        state_file = campaign_dir / 'campaign_state.json'
        if not state_file.exists():
            continue
            
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if is_legacy_save(state):
                legacy.append(campaign_dir.name)
        except Exception as e:
            logger.warning(f"[SAVE_DETECTOR] Error reading {state_file}: {e}")
            
    return legacy
"""
map_editor/data/npc_data.py
Загрузка и сохранение данных NPC (индивидуалы, визуал, психика).
"""

import json
from pathlib import Path
from typing import List, Dict, Tuple

# Путь к реальным NPC из конфига
_NPC_INDIVIDUALS_DIR = (
    Path(__file__).parent.parent.parent.parent / "config" / "npc" / "individuals"
)

# Визуальный маппинг для отрисовки NPC в редакторе (ref_id -> спрайт)
NPC_SPRITE_MAP = {
    "merchant_goran": ("Deadbeat/deadbeat_b", 25, 21),
    "thief_shadow": ("Deadbeat/deadbeat_b", 25, 22),
}


def load_npc_individuals() -> List[Dict[str, str]]:
    """Загружает список реальных NPC из config/npc/individuals/*.json.
    Возвращает список словарей с ключами: id, name, filename."""
    result: List[Dict[str, str]] = []
    if not _NPC_INDIVIDUALS_DIR.exists():
        print(f"[NPC_LOAD] Dir not found: {_NPC_INDIVIDUALS_DIR}")
        return result
    for json_file in sorted(_NPC_INDIVIDUALS_DIR.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            npc_id = data.get("id", json_file.stem)
            npc_name = data.get("name", npc_id)
            result.append(
                {
                    "id": npc_id,
                    "name": npc_name,
                    "filename": json_file.name,
                }
            )
        except Exception as e:
            print(f"[NPC_LOAD] Error loading {json_file.name}: {e}")
            continue
    return result


def load_npc_visual_casting(npc_id: str) -> Dict:
    """S176: Загружает visual_casting конфиг для конкретного NPC."""
    if not _NPC_INDIVIDUALS_DIR.exists():
        return {}
    for json_file in _NPC_INDIVIDUALS_DIR.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if data.get("id") == npc_id:
                return data.get("visual_casting", {})
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def save_npc_visual_casting(npc_id: str, casting: Dict) -> bool:
    """S176: Сохраняет visual_casting конфиг в JSON индивида."""
    if not _NPC_INDIVIDUALS_DIR.exists():
        return False
    for json_file in _NPC_INDIVIDUALS_DIR.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if data.get("id") == npc_id:
                data["visual_casting"] = casting
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
        except (json.JSONDecodeError, OSError):
            continue
    return False


def load_npc_calibration(npc_id: str) -> Tuple[Dict, Dict]:
    """Загружает psyche и drives NPC для калибровки."""
    if not _NPC_INDIVIDUALS_DIR.exists():
        return {}, {}
    for json_file in _NPC_INDIVIDUALS_DIR.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if data.get("id") == npc_id:
                return data.get("psyche", {}), data.get("drives", {})
        except (json.JSONDecodeError, OSError):
            continue
    return {}, {}


def save_npc_calibration(npc_id: str, psyche: Dict, drives: Dict) -> bool:
    """Сохраняет psyche и drives в JSON NPC."""
    if not _NPC_INDIVIDUALS_DIR.exists():
        return False
    for json_file in _NPC_INDIVIDUALS_DIR.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if data.get("id") == npc_id:
                data["psyche"] = psyche
                data["drives"] = drives
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
        except (json.JSONDecodeError, OSError) as e:
            print(f"[CALIB_SAVE] Error saving {npc_id}: {e}")
            continue
    return False
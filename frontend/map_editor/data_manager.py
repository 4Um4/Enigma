"""
map_editor/data_manager.py
Управление данными локаций: загрузка, сохранение, валидация
Поддерживает: стены, комнаты, узлы, объекты, порталы
"""
import json
from pathlib import Path
from datetime import datetime
from copy import deepcopy
from typing import Dict, List, Optional, Tuple, Any

TEMPLATE_DIR = Path(__file__).parent / "location_templates"
CACHE_DIR = Path(__file__).parent / "runtime_cache"

# Типы объектов с настройками по умолчанию
OBJECT_PRESETS = {
    # === Обычная мебель ===
    "table": {
        "label": "Стол",
        "icon": "🪑",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": True, "crawl_under": True, "climb_on": True, "walk_around": True},
        "cover": 0.5,
        "height": 0.8,
        "color": "#8B7355",
        "default_size": {"w": 1.5, "h": 0.9},
        "sprite": ("Deadbeat/deadbeat_b", 5, 11)
    },
    "chair": {
        "label": "Стул",
        "icon": "💺",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.3,
        "height": 0.5,
        "color": "#A0522D",
        "default_size": {"w": 0.5, "h": 0.5},
        "sprite": ("Deadbeat/deadbeat_b", 8, 17)
    },
    "bar": {
        "label": "Барная стойка",
        "icon": "🍺",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.8,
        "height": 1.2,
        "color": "#654321",
        "default_size": {"w": 2.5, "h": 0.6}
    },
    "decoration": {
        "label": "Декорация",
        "icon": "🌿",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.5,
        "color": "#90EE90",
        "default_size": {"w": 0.5, "h": 0.5}
    },
    # === Объекты в стенах (требуют стену при создании) ===
    "door": {
        "label": "Дверь",
        "icon": "🚪",
        "rotation_mode": "mirror",
        "requires_wall": True,
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 2.2,
        "color": "#D2691E",
        "default_size": {"w": 1.0, "h": 0.2},
        "default_properties": {"open": True, "locked": False, "durability": 20, "visibility_through": 0.1},
        "sprite": ("Deadbeat/deadbeat_b", 3, 9)
    },
    "window": {
        "label": "Окно",
        "icon": "🪟",
        "rotation_mode": "mirror",
        "requires_wall": True,
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.0,
        "height": 1.5,
        "color": "#87CEEB",
        "default_size": {"w": 1.2, "h": 0.2},
        "default_properties": {"opacity": 0.3, "destructible": True, "durability": 15, "sound_attenuation": 0.3, "visibility_through": 0.8}
    },
    "gap": {
        "label": "Пролом",
        "icon": "💥",
        "rotation_mode": "mirror",
        "requires_wall": True,
        "passability": {"walk": True, "jump_over": True, "crawl_under": True, "climb_on": True, "walk_around": True},
        "cover": 0.0,
        "height": 2.5,
        "color": "#AAAAAA",
        "default_size": {"w": 1.5, "h": 2.0},
        "default_properties": {"visibility_through": 1.0, "sound_attenuation": 0.0},
        "sprite": ("Deadbeat/deadbeat_b", 6, 9)
    },
    # === Переходы между этажами ===
    "stairs_up": {
        "label": "Лестница вверх",
        "icon": "🔼",
        "rotation_mode": "free",
        "requires_wall": False,
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.3,
        "color": "#32CD32",
        "default_size": {"w": 1.2, "h": 2.0},
        "default_properties": {"direction": "up"}
    },
    "stairs_down": {
        "label": "Лестница вниз",
        "icon": "🔽",
        "rotation_mode": "free",
        "requires_wall": False,
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.3,
        "color": "#DC143C",
        "default_size": {"w": 1.2, "h": 2.0},
        "default_properties": {"direction": "down"}
    },
    "ladder": {
        "label": "Люк",
        "icon": "⬛",
        "rotation_mode": "free",
        "requires_wall": False,
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.0,
        "height": 0.1,
        "color": "#9370DB",
        "default_size": {"w": 1.0, "h": 1.0},
        "default_properties": {"direction": "down"}
    },
    # === Внешние переходы (между локациями) ===
    "door_transition": {
        "label": "Дверь переход",
        "icon": "🚸",
        "rotation_mode": "mirror",
        "requires_wall": True,
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 2.2,
        "color": "#FF8C00",
        "default_size": {"w": 1.0, "h": 0.2},
        "default_properties": {"open": True, "locked": False, "durability": 25, "visibility_through": 0.0,
                               "target_file": "", "target_portal": ""},
        "sprite": ("Deadbeat/deadbeat_b", 0, 9)
    },
    "portal_magic": {
        "label": "Магический портал",
        "icon": "✨",
        "rotation_mode": "free",
        "requires_wall": False,
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 2.5,
        "color": "#FF69B4",
        "default_size": {"w": 1.5, "h": 1.5},
        "default_properties": {"target_file": "", "target_portal": "", "visibility_through": 0.5}
    },
    # === Природа ===
    "spruce": {
        "label": "Ель",
        "icon": "🌲",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.8,
        "height": 4.0,
        "color": "#006400",
        "default_size": {"w": 1.0, "h": 1.0},
        "sprite": ("Deadbeat/deadbeat_b", 6, 2)
    },
    "tree": {
        "label": "Дерево",
        "icon": "🌳",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.7,
        "height": 5.0,
        "color": "#228B22",
        "default_size": {"w": 1.0, "h": 1.0},
        "sprite": ("Deadbeat/deadbeat_b", 6, 3)
    },
    "grass": {
        "label": "Трава",
        "icon": "🌿",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.1,
        "height": 0.3,
        "color": "#32CD32",
        "default_size": {"w": 0.5, "h": 0.5},
        "sprite": ("Deadbeat/deadbeat_b", 6, 0)
    },
    "apple_tree": {
        "label": "Яблоня",
        "icon": "🍎",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.7,
        "height": 4.0,
        "color": "#8B4513",
        "default_size": {"w": 1.0, "h": 1.0},
        "sprite": ("Deadbeat/deadbeat_b", 7, 0)
    },
    "palm": {
        "label": "Пальма",
        "icon": "🌴",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.6,
        "height": 6.0,
        "color": "#2E8B57",
        "default_size": {"w": 1.0, "h": 1.0},
        "sprite": ("Deadbeat/deadbeat_b", 7, 4)
    },
    "rocks": {
        "label": "Камни",
        "icon": "🪨",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.4,
        "height": 0.5,
        "color": "#808080",
        "default_size": {"w": 1.0, "h": 0.8},
        "sprite": ("Deadbeat/deadbeat_b", 7, 7)
    },
    # === Мебель ===
    "bookshelf": {
        "label": "Книжный шкаф",
        "icon": "📚",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.9,
        "height": 2.0,
        "color": "#8B4513",
        "default_size": {"w": 1.0, "h": 0.4},
        "sprite": ("Deadbeat/deadbeat_b", 6, 18)
    },
    "toilet": {
        "label": "Туалет",
        "icon": "🚽",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.3,
        "height": 0.5,
        "color": "#F5F5F5",
        "default_size": {"w": 0.5, "h": 0.5},
        "sprite": ("Deadbeat/deadbeat_b", 7, 16)
    },
    "tent": {
        "label": "Палатка",
        "icon": "⛺",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.8,
        "height": 2.0,
        "color": "#D2691E",
        "default_size": {"w": 2.0, "h": 2.0},
        "sprite": ("Deadbeat/deadbeat_b", 7, 21)
    },
    "bed": {
        "label": "Кровать",
        "icon": "🛏️",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.2,
        "height": 0.6,
        "color": "#8B4513",
        "default_size": {"w": 2.0, "h": 1.0},
        "sprite": ("Deadbeat/deadbeat_b", 8, 15)
    },
    "stool": {
        "label": "Табурет",
        "icon": "🪑",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.2,
        "height": 0.5,
        "color": "#A0522D",
        "default_size": {"w": 0.4, "h": 0.4},
        "sprite": ("Deadbeat/deadbeat_b", 8, 16)
    },
    # === Интерактивные ===
    "sign_flophouse": {
        "label": "Вывеска ночлежки",
        "icon": "🏷️",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 2.5,
        "color": "#DAA520",
        "default_size": {"w": 1.0, "h": 0.3},
        "sprite": ("Deadbeat/deadbeat_b", 9, 19)
    },
    "hatch": {
        "label": "Люк",
        "icon": "🕳️",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.1,
        "color": "#696969",
        "default_size": {"w": 1.0, "h": 1.0},
        "default_properties": {"open": True, "locked": False, "target_file": "", "target_z": -1},
        "sprite": ("Deadbeat/deadbeat_b", 11, 4)
    },
    "cauldron": {
        "label": "Котел",
        "icon": "🍲",
        "rotation_mode": "free",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.3,
        "height": 0.8,
        "color": "#696969",
        "default_size": {"w": 0.8, "h": 0.8},
        "sprite": ("Deadbeat/deadbeat_b", 11, 16)
    },
    "campfire": {
        "label": "Костер",
        "icon": "🔥",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": True, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.5,
        "color": "#FF4500",
        "default_size": {"w": 0.8, "h": 0.8},
        "default_properties": {"light_radius": 5.0, "temperature": 800},
        "sprite": ("Deadbeat/deadbeat_b", 11, 17)
    },
    # === Декорации ===
    "bones": {
        "label": "Кости",
        "icon": "💀",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": True, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.1,
        "color": "#FFFFF0",
        "default_size": {"w": 0.5, "h": 0.5},
        "sprite": ("Deadbeat/deadbeat_b", 15, 18)
    },
    "heart": {
        "label": "Сердечко",
        "icon": "❤️",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.2,
        "color": "#FF0000",
        "default_size": {"w": 0.3, "h": 0.3},
        "sprite": ("Deadbeat/deadbeat_b", 22, 13)
    },
    "heart_empty": {
        "label": "Пустое сердечко",
        "icon": "🖤",
        "rotation_mode": "free",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.2,
        "color": "#333333",
        "default_size": {"w": 0.3, "h": 0.3},
        "sprite": ("Deadbeat/deadbeat_b", 22, 12)
    },
    # === NPC-спрайты (используются в системе NPC, не размещаются как объекты) ===
    # mage: c23_r22, warrior: c25_r21, person: c23_r21, thief: c25_r22
    # cow: c25_r28, knight: c26_r21
}

# Визуальный маппинг для отрисовки NPC в редакторе (ref_id -> спрайт)
# Не все NPC имеют свой спрайт — остальные используют person по умолчанию
NPC_SPRITE_MAP = {
    "merchant_goran": ("Deadbeat/deadbeat_b", 25, 21),
    "thief_shadow": ("Deadbeat/deadbeat_b", 25, 22),
}

# Путь к реальным NPC из конфига
_NPC_INDIVIDUALS_DIR = Path(__file__).parent.parent.parent / "config" / "npc" / "individuals"


def load_npc_individuals() -> List[Dict[str, str]]:
    """Загружает список реальных NPC из config/npc/individuals/*.json.
    Возвращает список словарей с ключами: id, name, filename."""
    result: List[Dict[str, str]] = []
    if not _NPC_INDIVIDUALS_DIR.exists():
        return result
    for json_file in sorted(_NPC_INDIVIDUALS_DIR.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            npc_id = data.get("id", json_file.stem)
            npc_name = data.get("name", npc_id)
            result.append({
                "id": npc_id,
                "name": npc_name,
                "filename": json_file.name,
            })
        except (json.JSONDecodeError, OSError):
            continue
    return result


# Пресеты NPC для размещения на карте через редактор (оставлены как фоллбэк)
NPC_PRESETS = {
    "mage": {
        "label": "Маг",
        "icon": "🧙",
        "sprite": ("Deadbeat/deadbeat_b", 23, 22),
    },
    "warrior": {
        "label": "Воин",
        "icon": "⚔️",
        "sprite": ("Deadbeat/deadbeat_b", 25, 21),
    },
    "person": {
        "label": "Житель",
        "icon": "👤",
        "sprite": ("Deadbeat/deadbeat_b", 23, 21),
    },
    "thief": {
        "label": "Вор",
        "icon": "🗡️",
        "sprite": ("Deadbeat/deadbeat_b", 25, 22),
    },
    "cow": {
        "label": "Корова",
        "icon": "🐄",
        "sprite": ("Deadbeat/deadbeat_b", 25, 28),
    },
    "knight": {
        "label": "Рыцарь",
        "icon": "🛡️",
        "sprite": ("Deadbeat/deadbeat_b", 26, 21),
    },
}


class DataManager:
    """Управляет всеми данными локаций"""

    @staticmethod
    def _next_id(items: List[Dict], prefix: str) -> str:
        """Генерирует уникальный id: ищет максимальный индекс и прибавляет 1"""
        max_idx = -1
        for item in items:
            iid = item.get("id", "")
            if iid.startswith(prefix):
                try:
                    idx = int(iid[len(prefix):])
                    if idx > max_idx:
                        max_idx = idx
                except ValueError:
                    pass  # iid имеет неожиданный формат, пропускаем
        return f"{prefix}{max_idx + 1}"
    
    def __init__(self):
        self.base_dir = TEMPLATE_DIR
        self.base_dir.mkdir(exist_ok=True)
        CACHE_DIR.mkdir(exist_ok=True)
        self.locations: Dict[str, dict] = {}
        self.load_all()
    
    def set_base_dir(self, path) -> None:
        """Переключает рабочую директорию (для кампаний)"""
        from pathlib import Path
        self.base_dir = Path(path)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.load_all()
    
    def load_all(self):
        """Загружает все локации из папки templates"""
        self.locations.clear()
        for f in self.base_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    # Установка значений по умолчанию
                    # Миграция: старые файлы с world_pos → origin
                    if "world_pos" in data:
                        data["origin"] = data.pop("world_pos")
                    data.setdefault("origin", {"x": (len(self.locations) % 5) * 30, "y": (len(self.locations) // 5) * 25})
                    data.setdefault("location_id", "")  # связывает с location_id в игре
                    data.setdefault("size", {"w": 20, "h": 15})
                    data.setdefault("grid_cell_size", 1.0)
                    data.setdefault("is_outdoor", False)
                    data.setdefault("rooms", [])  # Комнаты (замкнутые области)
                    data.setdefault("walls", [])   # Стены (линии)
                    data.setdefault("nodes", {})   # Навигационные узлы
                    data.setdefault("objects", []) # Объекты (мебель и т.д.)
                    data.setdefault("passages", []) # Внутренние проходы (двери в стенах)
                    # portals удалены — внешние переходы теперь объекты door_transition/portal_magic
                    data.setdefault("npcs", [])     # NPC в локации
                    data.setdefault("labels", [])    # Произвольные надписи
                    data.setdefault("player_spawn", {"x": data["origin"]["x"] + 1, "y": data["origin"]["y"] + 1, "z": 0})
                    self._migrate_to_global_coords(data)
                    self.locations[f.name] = data
            except Exception as e:
                print(f"⚠️ Ошибка загрузки {f}: {e}")
    
    def create_location(self, filename: str, width: int = 20, height: int = 15, 
                       label: str = "", is_outdoor: bool = False) -> Tuple[bool, str]:
        """Создаёт новую локацию"""
        if not filename.endswith(".json"):
            filename += ".json"
        if filename in self.locations:
            return False, "Файл уже существует"
        
        # Авто-позиция на карте мира
        pos_x = (len(self.locations) % 5) * 30
        pos_y = (len(self.locations) // 5) * 25
        
        self.locations[filename] = {
            "filename": filename,
            "label": label or filename.replace(".json", ""),
            "location_id": "",  # заполнить в UI — связывает с location_id в игре
            "origin": {"x": pos_x, "y": pos_y},
            "size": {"w": width, "h": height},
            "grid_cell_size": 1.0,
            "is_outdoor": is_outdoor,
            "rooms": [],
            "walls": [],
            "nodes": {},
            "objects": [],
            "passages": [],
            "portals": [],
            "npcs": [],
            "labels": [],
            "player_spawn": {"x": pos_x + 1, "y": pos_y + 1, "z": 0},
            "global_coords": True,
            "created_at": datetime.now().isoformat(),
            "modified_at": datetime.now().isoformat()
        }
        return True, ""
    
    def _migrate_to_global_coords(self, data: dict) -> None:
        """Мигрирует локальные координаты в глобальные (однократно при загрузке).
        Старые файлы хранили координаты от (0,0). Глобальные — от origin."""
        if data.get("global_coords"):
            return
        
        ox = data["origin"]["x"]
        oy = data["origin"]["y"]
        
        for room in data.get("rooms", []):
            room.setdefault("area_sqm", round(room.get("width", 0) * room.get("height", 0), 1))
            # Миграция: создаём polygon из прямоугольника если нет
            if "polygon" not in room:
                rx, ry = room["x"], room["y"]
                rw, rh = room.get("width", 0), room.get("height", 0)
                room["polygon"] = [
                    (round(rx, 2), round(ry, 2)),
                    (round(rx + rw, 2), round(ry, 2)),
                    (round(rx + rw, 2), round(ry + rh, 2)),
                    (round(rx, 2), round(ry + rh, 2))
                ]
            room["x"] = round(room["x"] + ox, 2)
            room["y"] = round(room["y"] + oy, 2)
        
        for wall in data.get("walls", []):
            wall["x1"] = round(wall["x1"] + ox, 2)
            wall["y1"] = round(wall["y1"] + oy, 2)
            wall["x2"] = round(wall["x2"] + ox, 2)
            wall["y2"] = round(wall["y2"] + oy, 2)
        
        for node in data.get("nodes", {}).values():
            node["x"] = round(node["x"] + ox, 2)
            node["y"] = round(node["y"] + oy, 2)
        
        for idx, obj in enumerate(data.get("objects", [])):
            # Миграция: старые объекты без id/name
            if "id" not in obj:
                obj["id"] = f"obj_{idx}"
            if "name" not in obj:
                otype = obj.get("type", "decoration")
                preset = OBJECT_PRESETS.get(otype, OBJECT_PRESETS["decoration"])
                obj["name"] = f"{preset.get('label', otype)} #{idx + 1}"
            obj.setdefault("show_name", False)
            obj["position"]["x"] = round(obj["position"]["x"] + ox, 2)
            obj["position"]["y"] = round(obj["position"]["y"] + oy, 2)
        
        for portal in data.get("portals", []):
            portal["position"]["x"] = round(portal["position"]["x"] + ox, 2)
            portal["position"]["y"] = round(portal["position"]["y"] + oy, 2)
        
        for passage in data.get("passages", []):
            passage["position"]["x"] = round(passage["position"]["x"] + ox, 2)
            passage["position"]["y"] = round(passage["position"]["y"] + oy, 2)
        
        for npc in data.get("npcs", []):
            npc["position"]["x"] = round(npc["position"]["x"] + ox, 2)
            npc["position"]["y"] = round(npc["position"]["y"] + oy, 2)
        
        for label in data.get("labels", []):
            label["x"] = round(label["x"] + ox, 2)
            label["y"] = round(label["y"] + oy, 2)
        
        spawn = data.get("player_spawn")
        if spawn:
            spawn["x"] = round(spawn["x"] + ox, 2)
            spawn["y"] = round(spawn["y"] + oy, 2)
        
        data["global_coords"] = True
    
    def shift_all(self, filename: str, dx: float, dy: float) -> None:
        """Сдвигает все координаты внутри локации на (dx, dy).
        Используется при перетаскивании локации на карте мира."""
        loc = self.locations[filename]
        
        # Глобальная позиция локации
        loc["origin"]["x"] = round(loc["origin"]["x"] + dx, 2)
        loc["origin"]["y"] = round(loc["origin"]["y"] + dy, 2)
        
        # Комнаты
        for room in loc.get("rooms", []):
            room["x"] = round(room["x"] + dx, 2)
            room["y"] = round(room["y"] + dy, 2)
        
        # Стены
        for wall in loc.get("walls", []):
            wall["x1"] = round(wall["x1"] + dx, 2)
            wall["y1"] = round(wall["y1"] + dy, 2)
            wall["x2"] = round(wall["x2"] + dx, 2)
            wall["y2"] = round(wall["y2"] + dy, 2)
        
        # Навигационные узлы
        for node in loc.get("nodes", {}).values():
            node["x"] = round(node["x"] + dx, 2)
            node["y"] = round(node["y"] + dy, 2)
        
        # Объекты
        for obj in loc.get("objects", []):
            obj["position"]["x"] = round(obj["position"]["x"] + dx, 2)
            obj["position"]["y"] = round(obj["position"]["y"] + dy, 2)
        
        # Проходы (внутренние)
        for passage in loc.get("passages", []):
            passage["position"]["x"] = round(passage["position"]["x"] + dx, 2)
            passage["position"]["y"] = round(passage["position"]["y"] + dy, 2)
        
        # Порталы (внешние)
        for portal in loc.get("portals", []):
            portal["position"]["x"] = round(portal["position"]["x"] + dx, 2)
            portal["position"]["y"] = round(portal["position"]["y"] + dy, 2)
        
        # NPC
        for npc in loc.get("npcs", []):
            npc["position"]["x"] = round(npc["position"]["x"] + dx, 2)
            npc["position"]["y"] = round(npc["position"]["y"] + dy, 2)
        
        # Точка спавна игрока
        spawn = loc.get("player_spawn")
        if spawn:
            spawn["x"] = round(spawn["x"] + dx, 2)
            spawn["y"] = round(spawn["y"] + dy, 2)
        
        # Надписи
        for label in loc.get("labels", []):
            label["x"] = round(label["x"] + dx, 2)
            label["y"] = round(label["y"] + dy, 2)
    
    def save(self, filename: str) -> bool:
        """Сохраняет локацию в JSON"""
        if filename not in self.locations:
            return False
        self.locations[filename]["modified_at"] = datetime.now().isoformat()
        # ADR-061: Schema Enforcement. location_id ОБЯЗАН быть заполнен.
        # Если UI не заполнил — наследуем из имени файла (tavern.json -> tavern)
        if not self.locations[filename].get("location_id"):
            inferred_id = filename.replace(".json", "")
            self.locations[filename]["location_id"] = inferred_id
        path = self.base_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.locations[filename], f, indent=2, ensure_ascii=False)
        return True
    
    def save_all(self):
        """Сохраняет все локации"""
        for fname in self.locations:
            self.save(fname)
    
    def delete_location(self, filename: str) -> bool:
        """Удаляет локацию"""
        if filename not in self.locations:
            return False
        path = self.base_dir / filename
        if path.exists():
            path.unlink()
        del self.locations[filename]
        return True
    
    # === Управление комнатами ===
    @staticmethod
    def _polygon_area(points: List[Tuple[float, float]]) -> float:
        """Площадь полигона по формуле шнурков"""
        n = len(points)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]
        return abs(area) / 2.0
    
    @staticmethod
    def _point_in_polygon(px: float, py: float,
                          points: List[Tuple[float, float]]) -> bool:
        """Лучевой метод: точка внутри полигона?"""
        n = len(points)
        if n < 3:
            return False
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = points[i]
            xj, yj = points[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside
    
    def add_room(self, filename: str, name: str, x: float, y: float,
                 width: float, height: float,
                 polygon: Optional[List[Tuple[float, float]]] = None,
                 area_sqm: Optional[float] = None) -> str:
        """Добавляет комнату. polygon — список точек контура, area_sqm — явная площадь."""
        loc = self.locations[filename]
        room_id = f"room_{len(loc['rooms'])}"
        
        # Полигон: переданный или прямоугольник по умолчанию
        if polygon and len(polygon) >= 3:
            pts = [(round(p[0], 2), round(p[1], 2)) for p in polygon]
        else:
            pts = [(round(x, 2), round(y, 2)),
                   (round(x + width, 2), round(y, 2)),
                   (round(x + width, 2), round(y + height, 2)),
                   (round(x, 2), round(y + height, 2))]
        
        # Площадь: явная или вычисленная
        if area_sqm is not None:
            final_area = round(area_sqm, 1)
        else:
            final_area = round(self._polygon_area(pts), 1)
        
        room = {
            "id": room_id,
            "name": name,
            "x": round(x, 2),
            "y": round(y, 2),
            "width": round(width, 2),
            "height": round(height, 2),
            "polygon": pts,
            "area_sqm": final_area
        }
        self.locations[filename]["rooms"].append(room)
        return room_id
    
    def remove_room(self, filename: str, room_id: str) -> bool:
        """Удаляет комнату"""
        loc = self.locations[filename]
        for i, room in enumerate(loc["rooms"]):
            if room["id"] == room_id:
                loc["rooms"].pop(i)
                return True
        return False
    
    def rename_room(self, filename: str, room_id: str, new_name: str) -> bool:
        """Переименовывает комнату"""
        loc = self.locations[filename]
        for room in loc["rooms"]:
            if room["id"] == room_id:
                room["name"] = new_name
                return True
        return False
    
    def rename_entity(self, filename: str, entity_type: str, entity_id: str,
                      new_name: str) -> bool:
        """Универсальное переименование сущности по типу и id.
        Поддерживает: room, object, portal."""
        loc = self.locations[filename]
        target = None
        name_key = "name"
        
        if entity_type == "room":
            target = next((r for r in loc["rooms"] if r["id"] == entity_id), None)
        elif entity_type == "object":
            target = next((o for o in loc["objects"] if o.get("id") == entity_id), None)
        elif entity_type == "portal":
            target = next((p for p in loc["portals"] if p["id"] == entity_id), None)
            name_key = "label"
        
        if target:
            target[name_key] = new_name
            return True
        return False
    
    def get_entity_name(self, filename: str, entity_type: str, entity_id: str) -> str:
        """Возвращает текущее имя сущности"""
        loc = self.locations[filename]
        name_key = "name"
        
        if entity_type == "room":
            target = next((r for r in loc["rooms"] if r["id"] == entity_id), None)
        elif entity_type == "object":
            target = next((o for o in loc["objects"] if o.get("id") == entity_id), None)
        elif entity_type == "portal":
            target = next((p for p in loc["portals"] if p["id"] == entity_id), None)
            name_key = "label"
        else:
            return ""
        
        return target[name_key] if target else ""
    
    # === Управление стенами ===
    def add_wall(self, filename: str, x1: float, y1: float, x2: float, y2: float,
                 wall_type: str = "wall", thickness: float = 0.2) -> str:
        """Добавляет стену (отрезок)"""
        wall_id = f"wall_{len(self.locations[filename]['walls'])}"
        wall = {
            "id": wall_id,
            "type": wall_type,
            "x1": round(x1, 2),
            "y1": round(y1, 2),
            "x2": round(x2, 2),
            "y2": round(y2, 2),
            "thickness": thickness
        }
        self.locations[filename]["walls"].append(wall)
        return wall_id
    
    def remove_wall(self, filename: str, wall_id: str) -> bool:
        """Удаляет стену и все привязанные к ней объекты (двери, окна)"""
        loc = self.locations[filename]
        for i, wall in enumerate(loc["walls"]):
            if wall["id"] == wall_id:
                loc["walls"].pop(i)
                self.remove_passages_for_wall(filename, wall_id)
                # Удаляем объекты привязанные к этой стене
                loc["objects"] = [o for o in loc["objects"]
                                  if o.get("properties", {}).get("wall_id") != wall_id]
                return True
        return False
    
    # === Управление узлами ===
    def add_node(self, filename: str, node_id: str, x: float, y: float, 
                 label: str = "") -> bool:
        """Добавляет навигационный узел"""
        if not node_id:
            node_id = f"node_{len(self.locations[filename]['nodes'])}"
        self.locations[filename]["nodes"][node_id] = {
            "x": round(x, 2),
            "y": round(y, 2),
            "label": label or node_id,
            "connections": []
        }
        return True
    
    def remove_node(self, filename: str, node_id: str) -> bool:
        """Удаляет узел и все связи с ним"""
        loc = self.locations[filename]
        if node_id not in loc["nodes"]:
            return False
        
        # Удаляем связи на этот узел из других узлов
        for nid, ndata in loc["nodes"].items():
            if node_id in ndata.get("connections", []):
                ndata["connections"].remove(node_id)
        
        del loc["nodes"][node_id]
        return True
    
    def add_connection(self, filename: str, node_id: str, target: str):
        """Добавляет связь между узлами"""
        loc = self.locations[filename]
        if node_id in loc["nodes"]:
            loc["nodes"][node_id].setdefault("connections", [])
            if target not in loc["nodes"][node_id]["connections"]:
                loc["nodes"][node_id]["connections"].append(target)
    
    def remove_connection(self, filename: str, node_id: str, target: str):
        """Удаляет связь между узлами"""
        loc = self.locations[filename]
        if node_id in loc["nodes"]:
            conns = loc["nodes"][node_id].get("connections", [])
            if target in conns:
                conns.remove(target)
    
    # === Управление объектами ===
    def add_object(self, filename: str, obj_type: str, x: float, y: float,
                   width: float = 1.0, height: float = 1.0, rotation: float = 0,
                   wall_id: str = "") -> str:
        """Добавляет объект (мебель, декор, проходы), возвращает строковый id 'obj_N'"""
        loc = self.locations[filename]
        preset = OBJECT_PRESETS.get(obj_type, OBJECT_PRESETS["decoration"])
        # Счётчик по типу для имени: "Стол №1", "Стул №2"
        same_type_count = sum(1 for o in loc["objects"] if o.get("type") == obj_type)
        obj_id = self._next_id(loc["objects"], "obj_")
        obj = {
            "id": obj_id,
            "name": f"{preset['label']} №{same_type_count + 1}",
            "type": obj_type,
            "position": {"x": round(x, 2), "y": round(y, 2)},
            "size": {"w": width, "h": height, "d": preset.get("height", 1.0)},
            "rotation": rotation,
            "passability": preset["passability"].copy(),
            "cover": preset["cover"],
            "color": preset["color"],
            "show_name": False,
            "properties": {k: deepcopy(v) for k, v in preset.get("default_properties", {}).items()}
        }
        # Привязка к стене (для дверей, окон, проломов)
        if wall_id:
            obj["properties"]["wall_id"] = wall_id
        
        loc["objects"].append(obj)
        return obj_id
    
    def remove_object(self, filename: str, obj_id: str) -> bool:
        """Удаляет объект по строковому id"""
        loc = self.locations[filename]
        for i, obj in enumerate(loc["objects"]):
            if obj.get("id") == obj_id:
                loc["objects"].pop(i)
                return True
        return False
    
    # === Управление проходами (внутренние двери/окна в стенах) ===
    def add_passage(self, filename: str, wall_id: str, passage_type: str,
                    position: Dict[str, float], z: int = 0,
                    properties: Optional[Dict] = None) -> str:
        """Создаёт проход в стене. Возвращает id 'pass_N'."""
        loc = self.locations[filename]
        passage_id = f"pass_{len(loc['passages'])}"
        # Свойства по умолчанию в зависимости от типа
        default_props: Dict[str, Any] = {"open": True, "locked": False, "width": 1.0,
                                          "durability": 20, "visibility_through": 0.1}
        if passage_type == "window":
            default_props.update({"open": False, "durability": 15, "visibility_through": 0.8})
        elif passage_type == "gap":
            default_props.update({"open": True, "durability": 0, "visibility_through": 1.0,
                                   "width": 1.5})
        if properties:
            default_props.update(properties)
        passage = {
            "id": passage_id,
            "type": passage_type,
            "wall_id": wall_id,
            "position": {"x": round(position["x"], 2), "y": round(position["y"], 2)},
            "z": z,
            "properties": default_props
        }
        loc["passages"].append(passage)
        return passage_id
    
    def remove_passage(self, filename: str, passage_id: str) -> bool:
        """Удаляет проход по id"""
        loc = self.locations[filename]
        for i, p in enumerate(loc["passages"]):
            if p["id"] == passage_id:
                loc["passages"].pop(i)
                return True
        return False
    
    def remove_passages_for_wall(self, filename: str, wall_id: str) -> int:
        """Удаляет все проходы привязанные к стене. Возвращает количество удалённых."""
        loc = self.locations[filename]
        before = len(loc["passages"])
        loc["passages"] = [p for p in loc["passages"] if p.get("wall_id") != wall_id]
        return before - len(loc["passages"])
    
    # === Управление NPC ===
    def add_npc(self, filename: str, ref_id: str,
                x: float, y: float, room_id: str = "") -> str:
        """Добавляет NPC в локацию. Возвращает 'npc_{ref_id}'."""
        loc = self.locations[filename]
        npc_entry = {
            "ref_id": ref_id,
            "position": {"x": round(x, 2), "y": round(y, 2)},
            "room_id": room_id
        }
        loc["npcs"].append(npc_entry)
        return f"npc_{ref_id}"
    
    def remove_npc(self, filename: str, npc_ref_id: str) -> bool:
        """Удаляет NPC по ref_id"""
        loc = self.locations[filename]
        for i, npc in enumerate(loc["npcs"]):
            if npc["ref_id"] == npc_ref_id:
                loc["npcs"].pop(i)
                return True
        return False
    
    def move_npc(self, filename: str, npc_ref_id: str,
                 x: float, y: float, room_id: str = "") -> bool:
        """Перемещает NPC, опционально обновляет room_id"""
        loc = self.locations[filename]
        for npc in loc["npcs"]:
            if npc["ref_id"] == npc_ref_id:
                npc["position"]["x"] = round(x, 2)
                npc["position"]["y"] = round(y, 2)
                if room_id:
                    npc["room_id"] = room_id
                return True
        return False
    
    def find_room_at(self, filename: str, x: float, y: float) -> str:
        """Определяет в какой комнате находится точка. Возвращает room_id или ''."""
        loc = self.locations[filename]
        for room in loc.get("rooms", []):
            # Быстрая проверка по bounding box
            rx, ry = room["x"], room["y"]
            rw, rh = room["width"], room["height"]
            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue
            # Точная проверка по полигону если есть
            poly = room.get("polygon")
            if poly:
                pts = [(p[0], p[1]) for p in poly]
                if self._point_in_polygon(x, y, pts):
                    return room["id"]
            else:
                return room["id"]
        return ""
    
    def set_player_spawn(self, filename: str, x: float, y: float, z: int = 0) -> None:
        """Устанавливает точку спавна игрока"""
        self.locations[filename]["player_spawn"] = {
            "x": round(x, 2), "y": round(y, 2), "z": z
        }
    
    # === Управление надписями ===
    def add_label(self, filename: str, x: float, y: float,
                  text: str = "Надпись", font_size: int = 14) -> str:
        """Создаёт произвольную надпись на карте. Возвращает id 'label_N'."""
        loc = self.locations[filename]
        label_id = f"label_{len(loc['labels'])}"
        loc["labels"].append({
            "id": label_id,
            "x": round(x, 2),
            "y": round(y, 2),
            "text": text,
            "font_size": font_size
        })
        return label_id
    
    def remove_label(self, filename: str, label_id: str) -> bool:
        """Удаляет надпись"""
        loc = self.locations[filename]
        for i, lbl in enumerate(loc["labels"]):
            if lbl["id"] == label_id:
                loc["labels"].pop(i)
                return True
        return False
    
    def rename_label(self, filename: str, label_id: str, new_text: str) -> bool:
        """Меняет текст надписи"""
        loc = self.locations[filename]
        for lbl in loc["labels"]:
            if lbl["id"] == label_id:
                lbl["text"] = new_text
                return True
        return False
    
    def move_label(self, filename: str, label_id: str,
                   x: float, y: float) -> bool:
        """Перемещает надпись"""
        loc = self.locations[filename]
        for lbl in loc["labels"]:
            if lbl["id"] == label_id:
                lbl["x"] = round(x, 2)
                lbl["y"] = round(y, 2)
                return True
        return False
    
    # === Валидация и связи ===
    def get_all_connectable(self, exclude_file: str) -> List[str]:
        """Возвращает список всех доступных для связи целей"""
        result = []
        for fname, data in self.locations.items():
            if fname == exclude_file:
                continue
            # Узлы
            for nid in data.get("nodes", {}):
                result.append(f"{fname}:{nid}")
            # Порталы
            for p in data.get("portals", []):
                result.append(f"{fname}:{p['id']}")
        return sorted(result)
    
    def validate_external_link(self, link: str) -> Tuple[bool, str]:
        """Проверяет корректность внешней ссылки"""
        if ":" not in link:
            return False, "Формат: 'файл.json:узел_или_портал'"
        loc_file, target_id = link.split(":", 1)
        if loc_file not in self.locations:
            return False, f"Файл {loc_file} не найден"
        data = self.locations[loc_file]
        if target_id in data.get("nodes", {}) or any(p["id"] == target_id for p in data.get("portals", [])):
            return True, ""
        return False, f"Цель {target_id} не найдена в {loc_file}"
    
    def export_to_location_graph(self, filename: str) -> dict:
        """Экспортирует локацию в формат для location_graph.py"""
        loc = self.locations.get(filename, {})
        
        # Формируем узлы в формате location_graph
        positions = {}
        for nid, ndata in loc.get("nodes", {}).items():
            positions[nid] = {
                "x": ndata["x"],
                "y": ndata["y"],
                "connections": ndata.get("connections", []),
                "label": ndata.get("label", nid)
            }
        
        return {
            "location_id": filename.replace(".json", ""),
            "positions": positions,
            "bounds": loc.get("size", {"w": 20, "h": 15}),
            "is_outdoor": loc.get("is_outdoor", False)
        }

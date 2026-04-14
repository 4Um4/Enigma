"""
map_editor/data_manager.py
Управление данными локаций: загрузка, сохранение, валидация
Поддерживает: стены, комнаты, узлы, объекты, порталы
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

TEMPLATE_DIR = Path(__file__).parent / "location_templates"
CACHE_DIR = Path(__file__).parent / "runtime_cache"

# Типы объектов с настройками по умолчанию
OBJECT_PRESETS = {
    "wall": {
        "label": "Стена",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 1.0,
        "height": 2.5,
        "color": "#8B4513",
        "default_size": {"w": 0.2, "h": 1.0}
    },
    "bar": {
        "label": "Барная стойка",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.8,
        "height": 1.2,
        "color": "#654321",
        "default_size": {"w": 2.5, "h": 0.6}
    },
    "table": {
        "label": "Стол",
        "passability": {"walk": False, "jump_over": True, "crawl_under": True, "climb_on": True, "walk_around": True},
        "cover": 0.5,
        "height": 0.8,
        "color": "#8B7355",
        "default_size": {"w": 1.5, "h": 0.9}
    },
    "chair": {
        "label": "Стул",
        "passability": {"walk": False, "jump_over": True, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.3,
        "height": 0.5,
        "color": "#A0522D",
        "default_size": {"w": 0.5, "h": 0.5}
    },
    "door": {
        "label": "Дверь",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 2.2,
        "color": "#D2691E",
        "default_size": {"w": 1.0, "h": 0.2}
    },
    "window": {
        "label": "Окно",
        "passability": {"walk": False, "jump_over": False, "crawl_under": False, "climb_on": True, "walk_around": True},
        "cover": 0.0,
        "height": 1.5,
        "color": "#87CEEB",
        "default_size": {"w": 1.2, "h": 0.2}
    },
    "stairs": {
        "label": "Лестница",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.3,
        "color": "#696969",
        "default_size": {"w": 1.2, "h": 2.0}
    },
    "decoration": {
        "label": "Декорация",
        "passability": {"walk": True, "jump_over": False, "crawl_under": False, "climb_on": False, "walk_around": True},
        "cover": 0.0,
        "height": 0.5,
        "color": "#90EE90",
        "default_size": {"w": 0.5, "h": 0.5}
    }
}

# Типы порталов
PORTAL_TYPES = {
    "door": {"label": "Дверь", "color": "#FFD700"},
    "stairs_up": {"label": "Лестница вверх", "color": "#32CD32"},
    "stairs_down": {"label": "Лестница вниз", "color": "#DC143C"},
    "ladder": {"label": "Лестница/Люк", "color": "#9370DB"},
    "transition": {"label": "Переход (улица)", "color": "#00CED1"},
    "teleport": {"label": "Телепорт", "color": "#FF69B4"}
}


class DataManager:
    """Управляет всеми данными локаций"""
    
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
                    data.setdefault("size", {"w": 20, "h": 15})
                    data.setdefault("grid_cell_size", 1.0)
                    data.setdefault("is_outdoor", False)
                    data.setdefault("rooms", [])  # Комнаты (замкнутые области)
                    data.setdefault("walls", [])   # Стены (линии)
                    data.setdefault("nodes", {})   # Навигационные узлы
                    data.setdefault("objects", []) # Объекты (мебель и т.д.)
                    data.setdefault("portals", []) # Порталы (двери, переходы)
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
            "origin": {"x": pos_x, "y": pos_y},
            "size": {"w": width, "h": height},
            "grid_cell_size": 1.0,
            "is_outdoor": is_outdoor,
            "rooms": [],
            "walls": [],
            "nodes": {},
            "objects": [],
            "portals": [],
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
        
        for obj in data.get("objects", []):
            obj["position"]["x"] = round(obj["position"]["x"] + ox, 2)
            obj["position"]["y"] = round(obj["position"]["y"] + oy, 2)
        
        for portal in data.get("portals", []):
            portal["position"]["x"] = round(portal["position"]["x"] + ox, 2)
            portal["position"]["y"] = round(portal["position"]["y"] + oy, 2)
        
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
        
        # Порталы
        for portal in loc.get("portals", []):
            portal["position"]["x"] = round(portal["position"]["x"] + dx, 2)
            portal["position"]["y"] = round(portal["position"]["y"] + dy, 2)
    
    def save(self, filename: str) -> bool:
        """Сохраняет локацию в JSON"""
        if filename not in self.locations:
            return False
        self.locations[filename]["modified_at"] = datetime.now().isoformat()
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
    def add_room(self, filename: str, name: str, x: float, y: float, 
                 width: float, height: float) -> str:
        """Добавляет комнату (прямоугольную область)"""
        room_id = f"room_{len(self.locations[filename]['rooms'])}"
        room = {
            "id": room_id,
            "name": name,
            "x": round(x, 2),
            "y": round(y, 2),
            "width": round(width, 2),
            "height": round(height, 2)
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
        """Удаляет стену"""
        loc = self.locations[filename]
        for i, wall in enumerate(loc["walls"]):
            if wall["id"] == wall_id:
                loc["walls"].pop(i)
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
                   width: float = 1.0, height: float = 1.0, rotation: float = 0) -> str:
        """Добавляет объект (мебель, декор), возвращает строковый id 'obj_N'"""
        loc = self.locations[filename]
        preset = OBJECT_PRESETS.get(obj_type, OBJECT_PRESETS["decoration"])
        # Счётчик по типу для имени: "Стол №1", "Стул №2"
        same_type_count = sum(1 for o in loc["objects"] if o.get("type") == obj_type)
        obj_id = f"obj_{len(loc['objects'])}"
        obj = {
            "id": obj_id,
            "name": f"{preset['label']} №{same_type_count + 1}",
            "type": obj_type,
            "position": {"x": round(x, 2), "y": round(y, 2)},
            "size": {"w": width, "h": height, "d": preset.get("height", 1.0)},
            "rotation": rotation,
            "passability": preset["passability"].copy(),
            "cover": preset["cover"],
            "color": preset["color"]
        }
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
    
    # === Управление порталами ===
    def add_portal(self, filename: str, portal_type: str, x: float, y: float,
                   label: str = "", target: str = "") -> str:
        """Добавляет портал (дверь, лестница, переход)"""
        portal_id = f"{portal_type}_{len(self.locations[filename].get('portals', []))}"
        portal_info = PORTAL_TYPES.get(portal_type, PORTAL_TYPES["door"])
        portal = {
            "id": portal_id,
            "type": portal_type,
            "position": {"x": round(x, 2), "y": round(y, 2)},
            "size": {"w": 1.0, "h": 1.0},
            "label": label or portal_info["label"],
            "target": target,
            "one_way": False,
            "color": portal_info["color"]
        }
        self.locations[filename]["portals"].append(portal)
        return portal_id
    
    def remove_portal(self, filename: str, portal_id: str) -> bool:
        """Удаляет портал"""
        loc = self.locations[filename]
        for i, p in enumerate(loc.get("portals", [])):
            if p["id"] == portal_id:
                loc["portals"].pop(i)
                return True
        return False
    
    def connect_portal(self, filename: str, portal_id: str, target: str) -> bool:
        """Связывает портал с внешней целью"""
        loc = self.locations[filename]
        for p in loc.get("portals", []):
            if p["id"] == portal_id:
                p["target"] = target
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

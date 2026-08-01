"""
path: /project/backend/app/services/body/body_topology_service.py
Назначение: Управление топологией тела (инвентарём). Загрузка YAML, операции с предметами.
Зависимости: app.domain.body, app.services.persistence.yaml_loader
Основные сущности: BodyTopologyService
"""
import os
import yaml
from typing import Dict, List, Optional, Tuple
from app.domain.body import BodyTopology, BodySlot, Item, EncumbranceLevel

# Константы ключей YAML
_YAML_TOPOLOGY_KEY = "human_body_topology"
_YAML_ENCUMBRANCE_KEY = "encumbrance_rules"
_YAML_HANDS = "hands"
_YAML_BELT = "belt"
_YAML_POCKETS = "pockets"
_YAML_BACKPACK = "backpack"
_YAML_WORN = "worn"
_YAML_HIDDEN = "hidden"

class BodyTopologyService:
    """Сервис управления физической топологией тела."""
    
    _topology_template: Optional[Dict] = None
    _encumbrance_rules: Optional[Dict] = None

    @classmethod
    def load_template(cls, yaml_path: str = "architecture/body_topology.yaml") -> None:
        """Загружает стандартную топологию человека из YAML (один раз)."""
        if cls._topology_template is not None:
            return
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"BodyTopology YAML не найден: {yaml_path}")
        
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        cls._topology_template = data.get(_YAML_TOPOLOGY_KEY, {})
        cls._encumbrance_rules = data.get(_YAML_ENCUMBRANCE_KEY, {})

    @classmethod
    def create_topology(cls, avatar_id: str, strength_score: int = 10) -> BodyTopology:
        """Создаёт экземпляр BodyTopology из загруженного шаблона."""
        if cls._topology_template is None:
            cls.load_template()
            
        topology = BodyTopology(avatar_id=avatar_id, strength_score=strength_score)
        
        # Парсинг рук (Dict)
        for hand_data in cls._topology_template.get(_YAML_HANDS, []):
            slot = cls._parse_slot(hand_data)
            topology.hands[slot.slot_id] = slot
            
        # Парсинг пояса (List)
        topology.belt = [cls._parse_slot(d) for d in cls._topology_template.get(_YAML_BELT, [])]
        
        # Парсинг карманов (List)
        topology.pockets = [cls._parse_slot(d) for d in cls._topology_template.get(_YAML_POCKETS, [])]
        
        # Парсинг рюкзака (List)
        topology.backpack = [cls._parse_slot(d) for d in cls._topology_template.get(_YAML_BACKPACK, [])]
        
        # Парсинг надетого (Dict)
        for worn_data in cls._topology_template.get(_YAML_WORN, []):
            slot = cls._parse_slot(worn_data)
            topology.worn[slot.slot_id] = slot
            
        # Парсинг скрытых (List)
        topology.hidden = [cls._parse_slot(d) for d in cls._topology_template.get(_YAML_HIDDEN, [])]
        
        return topology

    @staticmethod
    def _parse_slot(data: Dict) -> BodySlot:
        """Парсит данные слота из dict в BodySlot."""
        return BodySlot(
            slot_id=data.get("slot_id", "unknown"),
            slot_type=data.get("slot_type", "misc"),
            body_part=data.get("body_part", "unknown"),
            accessibility=float(data.get("accessibility", 1.0)),
            visibility=float(data.get("visibility", 1.0)),
            requires_inspection=bool(data.get("requires_inspection", False)),
            capacity=int(data.get("capacity", 1)),
            max_bulk=int(data.get("max_bulk", 10)),
            item_type_restriction=data.get("item_type_restriction"),
            is_locked=bool(data.get("is_locked", False)),
            lock_difficulty=data.get("lock_difficulty"),
            concealment=float(data.get("concealment", 0.0)),
            don_time_ticks=int(data.get("don_time_ticks", 0)),
            doff_time_ticks=int(data.get("doff_time_ticks", 0))
        )

    @staticmethod
    def add_item(topology: BodyTopology, slot_id: str, item: Item) -> bool:
        """Добавляет предмет в слот. Возвращает True при успехе."""
        slot = next((s for s in topology.all_slots() if s.slot_id == slot_id), None)
        if not slot:
            return False
            
        # Проверка замка
        if slot.is_locked:
            return False
            
        # Проверка типа
        if slot.item_type_restriction and item.item_type != slot.item_type_restriction:
            return False
            
        # Проверка габаритов
        if item.bulk > slot.max_bulk:
            return False
            
        current_items = topology.contents.get(slot_id, ())
        if len(current_items) >= slot.capacity:
            return False
            
        # Добавление
        topology.contents[slot_id] = current_items + (item,)
        return True

    @staticmethod
    def remove_item(topology: BodyTopology, slot_id: str, item_id: str) -> Optional[Item]:
        """Удаляет предмет из слота. Возвращает удалённый предмет или None."""
        slot = next((s for s in topology.all_slots() if s.slot_id == slot_id), None)
        if not slot:
            return None
            
        current_items = topology.contents.get(slot_id, ())
        for i, item in enumerate(current_items):
            if item.item_id == item_id:
                # Удаляем элемент
                new_items = current_items[:i] + current_items[i+1:]
                topology.contents[slot_id] = new_items
                return item
        return None

    @staticmethod
    def transfer_item(
        source: BodyTopology, 
        source_slot_id: str, 
        target: BodyTopology, 
        target_slot_id: str, 
        item_id: str
    ) -> bool:
        """Перенос предмета между аватарами (торговля, кража)."""
        item = BodyTopologyService.remove_item(source, source_slot_id, item_id)
        if not item:
            return False
            
        if BodyTopologyService.add_item(target, target_slot_id, item):
            return True
        # Откат, если не удалось положить
        BodyTopologyService.add_item(source, source_slot_id, item)
        return False

    @staticmethod
    def inspect_slot(topology: BodyTopology, slot_id: str, inspection_skill: int = 0) -> List[Item]:
        """
        Осмотр слота. Возвращает видимые предметы.
        Учитывает requires_inspection, lock_difficulty и concealment.
        """
        slot = next((s for s in topology.all_slots() if s.slot_id == slot_id), None)
        if not slot:
            return []
            
        # Если слот требует осмотра и проверка провалена — пусто
        if slot.requires_inspection:
            if slot.is_locked and slot.lock_difficulty:
                if inspection_skill < slot.lock_difficulty:
                    return []
            elif slot.visibility < 0.1 and inspection_skill < 10:
                return []
                
        items = list(topology.contents.get(slot_id, ()))
        
        # Concealment (например, плащ) скрывает часть содержимого
        if slot.concealment > 0:
            visible_count = int(len(items) * (1.0 - slot.concealment))
            return items[:visible_count]
            
        return items
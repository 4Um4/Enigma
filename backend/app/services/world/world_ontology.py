# backend/app/services/world/world_ontology.py
"""
Онтологический контракт мира ENIGMA.

Определяет границу между физическими объектами и семантическими маркерами.
Только физические объекты могут существовать в scene_state["objects"].

Назначение: Онтологический контракт мира — что считается физическим объектом.
Зависимости: нет
Основные сущности: PHYSICAL_OBJECT_TYPES, is_physical_object()

Правило: объект физичен если он может быть передан, брошен, украден или уничтожен.
"""

from typing import FrozenSet

# Реестр физических типов предметов.
# Расширяется по мере роста контента — никогда не удаляется.
# Ключи — это obj_id или их префиксы из JSON.
PHYSICAL_OBJECT_TYPES: FrozenSet[str] = frozenset({
    # Оружие
    "spear", "sword", "knife", "dagger", "axe", "bow", "crossbow",
    "club", "staff", "mace",
    # Броня и одежда
    "city_guard_armor", "armor", "shield", "helmet", "apron",
    "cloak", "boots", "gloves",
    # Ключи и инструменты
    "keys", "key", "tool", "lockpick", "torch", "lantern",
    # Деньги
    "gold", "silver", "copper", "coin_pouch", "purse",
    # Еда и напитки
    "bread", "ale", "wine", "potion", "food",
    # Символы и печати
    "city_emblem", "signet", "seal", "badge",
    # Контейнеры
    "bag", "chest", "pouch", "sack",
    # Сырьё и прочее
    "stone", "rope", "wood", "cloth",
})


def is_physical_object(obj_id: str) -> bool:
    """
    Проверяет является ли маркер физическим объектом мира.
    Только физические объекты регистрируются в scene_state["objects"].

    Traits (scar_on_cheek, heavy_build) и role-маркеры (former_soldier)
    возвращают False — они принадлежат NPC L1/L2, не миру.
    """
    return obj_id.lower() in PHYSICAL_OBJECT_TYPES
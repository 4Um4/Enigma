"""
path: backend/app/services/scene/salience_engine.py
Назначение: Фильтрация объектов сцены по важности, зависящая от режима
Зависимости: app.models.scene_mode
Основные сущности: SalienceEngine
"""

from typing import Any, Dict, List, Tuple

from app.models.scene_mode import SceneMode, determine_scene_mode

# Лимиты количества объектов для каждого режима
_MODE_LIMITS: Dict[SceneMode, int] = {
    SceneMode.EXPLORATION: 10,
    SceneMode.INTERACTION: 5,
    SceneMode.COMBAT: 2,
}

# Состояния-маркеры инвентаря/одежды — всегда фоновый мусор
_INVENTORY_STATES = {"equipped", "in_inventory", "worn"}

# Теги объектов которые имеют смысл только при прямом взаимодействии
# (владелец ≠ None означает "принадлежит NPC")
_OWNER_EXCLUSIONS = {"фартук", "ключи", "кошелёк", "оружие"}


class SalienceEngine:
    """
    Фильтрует объекты сцены перед передачей в LLM-промпт.

    Принцип: Python решает что важно, LLM только рендерит.
    Нет сложной физики — простая эвристика на основе роли объекта.
    """

    def _salience_score(self, obj_id: str, obj: Dict[str, Any]) -> float:
        """
        Оценивает важность одного объекта. Больше = важнее.
        """
        score = 1.0

        # Неинтерактивные объекты (очаг, стены) — фон
        if not obj.get("interactable", False):
            score *= 0.1

        # Инвентарь/надетое — всегда мусор
        state = obj.get("state", "")
        if state in _INVENTORY_STATES:
            return 0.0

        # Принадлежит NPC и имя в исключениях — фоновый мусор
        owner = obj.get("owner")
        name = obj.get("name", "").lower()
        if owner and any(excl in name for excl in _OWNER_EXCLUSIONS):
            return 0.0

        # Сломанные объекты менее важны (кроме оружия)
        if state == "broken":
            score *= 0.5

        # Множественные мелкие объекты (свечи) — меньше веса
        count = obj.get("count", 1)
        if count and count > 3:
            score *= 0.3

        return score

    def get_filtered_objects(
        self,
        objects: Dict[str, Dict[str, Any]],
        event_type: str,
        max_npc_stress: float,
        player_target_object: str = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Возвращает отфильтрованный список объектов для промпта.

        Args:
            objects: словарь объектов из SceneState
            event_type: классификация из Router
            max_npc_stress: максимальный стресс среди видимых NPC
            player_target_object: id объекта с которым взаимодействует игрок

        Returns:
            Список (obj_id, obj) отсортированный по salience, обрезанный по лимиту режима
        """
        scene_mode = determine_scene_mode(event_type, max_npc_stress)
        limit = _MODE_LIMITS[scene_mode]

        scored: List[Tuple[float, str, Dict[str, Any]]] = []

        for obj_id, obj in objects.items():
            # Объект с которым взаимодействует игрок — всегда в фокусе
            if player_target_object and obj_id == player_target_object:
                scored.append((999.0, obj_id, obj))
                continue

            score = self._salience_score(obj_id, obj)
            if score > 0.05:  # Отсекаем абсолютный мусор
                scored.append((score, obj_id, obj))

        # Сортировка по убыванию важности
        scored.sort(key=lambda x: x[0], reverse=True)

        # Обрезка по лимиту режима
        return [(obj_id, obj) for _, obj_id, obj in scored[:limit]]

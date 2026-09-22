"""
Назначение: Валидация допустимости SceneChange перед применением. DEGOD ITER2: байт-в-байт перенос класса из scene_state_manager.py.
Зависимости: app.services.scene_change
Основные сущности: ChangeValidator
"""


from app.services.scene_change import ChangeType, SceneChange


class ChangeValidator:
    """
    Проверяет допустимость SceneChange перед применением.
    Возвращает (valid: bool, reason: str).
    """

    @staticmethod
    def validate(scene_state: dict, change: SceneChange) -> tuple[bool, str]:
        ct = change.type

        if ct == ChangeType.OBJECT_STATE:
            if change.target not in scene_state.get("objects", {}):
                return False, f"Объект '{change.target}' не существует в SceneState"
            return True, ""

        if ct == ChangeType.OBJECT_REMOVE:
            if change.target not in scene_state.get("objects", {}):
                return False, f"Объект '{change.target}' не существует — нечего удалять"
            return True, ""

        if ct == ChangeType.OBJECT_ADD:
            if change.target in scene_state.get("objects", {}):
                return False, f"Объект '{change.target}' уже существует в SceneState"
            return True, ""

        if ct == ChangeType.OBJECT_MOVE:
            if change.target not in scene_state.get("objects", {}):
                return (
                    False,
                    f"Объект '{change.target}' не существует — нечего перемещать",
                )
            return True, ""

        if ct in (ChangeType.NPC_POSITION, ChangeType.NPC_STATE):
            return True, ""

        if ct == ChangeType.ENVIRONMENT:
            return True, ""

        return True, ""

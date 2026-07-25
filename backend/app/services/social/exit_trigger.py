"""
Файл: backend/app/services/social/exit_trigger.py
Назначение: Проверка выхода игрока за пределы локации.
Зависимости: typing
"""

from typing import Any, Dict


class ExitTrigger:
    """Единственный триггер оценки — выход из таверны."""

    # Порог X-координаты для выхода на восток (условное значение для MVP)
    _EXIT_X_THRESHOLD = 18.0

    def check_exit(self, scene_state: Dict[str, Any]) -> bool:
        """Проверяет, покинул ли игрок локацию."""
        player_pos_data = scene_state.get("npc_positions", {}).get("player", {})
        local_pos = player_pos_data.get("local_position", {})

        x = local_pos.get("x", 0.0)
        y = local_pos.get("y", 0.0)

        # Игрок должен быть за пределами восточной стены
        if x >= self._EXIT_X_THRESHOLD:
            return True

        return False

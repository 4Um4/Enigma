"""
Файл: backend/app/services/social/exit_trigger.py
Назначение: Проверка выхода игрока за пределы локации.
Зависимости: typing
"""

from typing import Any, Dict


class ExitTrigger:
    """Единственный триггер оценки — выход из таверны."""

    # NEW-MVP-003 FIX: Унифицированы координаты с фронтендом (Y >= 12.5).
    _EXIT_Y_THRESHOLD = 12.5

    def check_exit(self, scene_state: Dict[str, Any]) -> bool:
        """Проверяет, покинул ли игрок локацию."""
        player_pos_data = scene_state.get("npc_positions", {}).get("player", {})
        local_pos = player_pos_data.get("local_position", {})

        y = local_pos.get("y", 0.0)

        # Игрок должен пересечь порог южной двери
        if y >= self._EXIT_Y_THRESHOLD:
            return True

        return False

from app.models.schemas import PlayerAction


class RulesAgent:
    """Агент правил D&D 5e с логикой определения необходимости броска."""

    # Рутинные действия - для них НЕ требуется бросок d20
    ROUTINE_ACTIONS = {
        "купить", "выпить", "заказать", "спросить", "осмотреть",
        "посмотреть", "взять", "положить", "идти", "войти", "выйти",
        "сесть", "встать", "лечь", "отдохнуть", "поесть", "съесть",
        "поговорить", "поздороваться", "попрощаться", "расспросить",
        "пройти", "подойти", "отойти", "открыть", "закрыть",
        "достать", "показать", "подать", "передать", "прочитать", "послушать",
    }

    # Ключевые слова, требующие броска (реальный риск или последствия)
    RISK_KEYWORDS = {
        "подкупить", "взломать", "скрыт", "убедить", "обмануть", "выкрасть",
        "атаковать", "ударить", "убить", "защищаться", "уклониться",
        "ловушка", "опасн", "враг", "монстр", "бой", "сражение",
        "прыжок", "карабкаться", "плаван", "алхимия", "магия", "заклинани",
    }

    def _is_routine_action(self, action_text: str) -> bool:
        """Определяет, является ли действие рутинным (без броска)."""
        action_lower = action_text.lower()

        for routine_word in self.ROUTINE_ACTIONS:
            if routine_word in action_lower:
                # Проверяем наличие слов риска
                for risk_word in self.RISK_KEYWORDS:
                    if risk_word in action_lower:
                        if risk_word in {"подкупить", "взломать", "скрыт", "убедить", "обмануть", "выкрасть"}:
                            return False  # требует бросок
                return True
        return False

    def check_need_roll(self, action: str) -> bool:
        """
        Определяет, требуется ли бросок d20 для данного действия.
        Returns:
            True - нужен бросок, False - автоматический успех
        """
        action_lower = action.lower()

        if self._is_routine_action(action):
            return False

        for risk_word in self.RISK_KEYWORDS:
            if risk_word in action_lower:
                return True

        return False  # спорные случаи - по умолчанию

    def calculate_difficulty(self, action: str) -> int:
        """Возвращает DC для броска на основе ключевых слов."""
        hard_keywords = ("взлом", "скрыт", "древн", "босс")
        if any(word in action.lower() for word in hard_keywords):
            return 15
        return 12

    def resolve_skill_check(self, dice_result: int, dc: int) -> str:
        if dice_result >= dc:
            return "успех"
        elif dice_result >= dc - 3:
            return "частичный успех"
        return "провал"

    def resolve_damage(self, base_damage: int, modifier: int = 0) -> int:
        return max(0, base_damage + modifier)

    def run(self, actions: list[PlayerAction], shared_context: dict | None = None) -> dict:
        """
        Main run method for RulesAgent - evaluates player actions with smart dice logic.
        SAFE FALLBACK: Always returns {"checks": [...]} even on error.
        """
        try:
            checks = []
            for action in actions:
                needs_roll = self.check_need_roll(action.action)
                dc = self.calculate_difficulty(action.action)
                if needs_roll:
                    check = {
                        "player": action.player_name,
                        "action": action.action,
                        "needs_roll": True,
                        "dc": dc,
                        "instruction": f"Бросьте d20 для {action.action} (DC {dc})"
                    }
                else:
                    check = {
                        "player": action.player_name,
                        "action": action.action,
                        "needs_roll": False,
                        "result": "автоматический успех"
                    }
                checks.append(check)
            return {"checks": checks}
        except Exception:
            # Minimal fallback
            return {"checks": []}
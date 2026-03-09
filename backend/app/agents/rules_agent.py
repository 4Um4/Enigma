from app.models.schemas import PlayerAction


class RulesAgent:
    """Агент правил D&D 5e с логикой определения необходимости броска."""
    
    # Рутинные действия - для них НЕ требуется бросок d20
    ROUTINE_ACTIONS = {
        "купить", "выпить", "купить", "заказать", "спросить", "осмотреть",
        "посмотреть", "взять", "положить", "идти", "войти", "выйти",
        "сесть", "встать", "лечь", "отдохнуть", "поесть", "съесть",
        "поговорить", "поздороваться", "попрощаться", "расспросить",
        "пройти", "подойти", "отойти", "подойти", "подойти",
        "открыть", "закрыть", "достать", "достать", "показать",
        "подать", "взять", "передать", "прочитать", "послушать",
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
        
        # Проверяем есть ли рутинные глаголы
        for routine_word in self.ROUTINE_ACTIONS:
            if routine_word in action_lower:
                # Если есть рутинное слово, проверяем нет ли ключей риска
                for risk_word in self.RISK_KEYWORDS:
                    if risk_word in action_lower:
                        # Есть и рутинное слово и слово риска - требует уточнения
                        # Но если это явный подкуп/взлом - нужен бросок
                        if risk_word in ["подкупить", "взломать", "скрыт", "убедить", "обмануть", "выкрасть"]:
                            return False
                return True
        return False

    def check_need_roll(self, action: str) -> bool:
        """
        Определяет, требуется ли бросок d20 для данного действия.
        
        Returns:
            True - нужен бросок, False - автоматический успех
        """
        action_lower = action.lower()
        
        # Явные случаи когда бросок НЕ нужен
        if self._is_routine_action(action):
            return False
        
        # Явные случаи когда бросок НУЖЕН
        for risk_word in self.RISK_KEYWORDS:
            if risk_word in action_lower:
                return True
        
        # Спорные случаи - по умолчанию НЕ требуем бросок
        # Пусть лучше модель опишет действие, чем будет требовать кубики на ровном месте
        return False

    def calculate_difficulty(self, action: str) -> int:
        hard_keywords = ("взлом", "скрыт", "древн", "босс")
        if any(word in action.lower() for word in hard_keywords):
            return 15
        return 12

    def resolve_skill_check(self, dice_result: int, dc: int) -> str:
        if dice_result >= dc:
            return "успех"
        if dice_result >= dc - 3:
            return "частичный успех"
        return "провал"

    def resolve_damage(self, base_damage: int, modifier: int = 0) -> int:
        return max(0, base_damage + modifier)

    def evaluate_actions(self, actions: list[PlayerAction]) -> dict:
        """Оценивает действия игроков с умной логикой бросков."""
        checks = []
        for action in actions:
            # Используем умную проверку: нужен ли бросок для этого действия?
            need_roll = self.check_need_roll(action.action)
            
            if action.dice_result is None:
                if need_roll:
                    # Действие требует броска - запрашиваем
                    checks.append(
                        {
                            "player": action.player_name,
                            "instruction": "Сделайте бросок d20",
                            "status": "awaiting_roll",
                        }
                    )
                else:
                    # Рутинное действие - автоматический успех
                    checks.append(
                        {
                            "player": action.player_name,
                            "result": "автоматический успех",
                            "status": "routine_success",
                        }
                    )
                continue

            # Если результат броска передан - обрабатываем его
            dc = self.calculate_difficulty(action.action)
            result = self.resolve_skill_check(action.dice_result, dc)
            checks.append(
                {
                    "player": action.player_name,
                    "roll": action.dice_result,
                    "dc": dc,
                    "result": result,
                }
            )
        return {"checks": checks}

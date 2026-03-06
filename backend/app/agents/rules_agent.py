from app.models.schemas import PlayerAction


class RulesAgent:
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
        checks = []
        for action in actions:
            if action.dice_result is None:
                checks.append(
                    {
                        "player": action.player_name,
                        "instruction": "Сделайте бросок d20",
                        "status": "awaiting_roll",
                    }
                )
                continue

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

from app.models.schemas import PlayerAction


class DmAgent:
    def narrate(
        self,
        location: str,
        actions: list[PlayerAction],
        rules_result: dict,
        npc_result: dict,
        world_result: dict,
        world_canon_exists: bool,
    ) -> dict:
        action_lines = " ".join([f"{a.player_name}: {a.action}." for a in actions])
        canon_guard = (
            ""
            if world_canon_exists
            else "Уточните детали мира/модуля, чтобы не противоречить канону. "
        )
        return {
            "dm_response": (
                f"Локация: {location}. {canon_guard}{action_lines} "
                f"Проверки: {rules_result['checks']}. "
                "Мир продолжает жить своими событиями."
            ),
            "npc_reactions": npc_result["npc_reactions"],
            "world_changes": world_result["world_events"],
        }

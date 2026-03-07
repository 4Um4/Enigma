from app.models.schemas import PlayerAction


class DmAgent:
    """Narrative DM layer with canon-safety guard."""

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
        if not world_canon_exists:
            return {
                "dm_response": (
                    f"Локация: {location}. Канон мира ещё не загружен, поэтому я не буду додумывать детали. "
                    "Пожалуйста, загрузите кампанию через /api/campaign/load или уточните каноничное описание сцены. "
                    f"Заявленные действия: {action_lines} Проверки: {rules_result['checks']}."
                ),
                "npc_reactions": ["NPC ждут уточнения канона мира перед развитием сцены."],
                "world_changes": ["Симуляция сюжетных изменений отложена до загрузки канона."],
            }

        return {
            "dm_response": (
                f"Локация: {location}. {action_lines} "
                f"Проверки: {rules_result['checks']}. "
                "Мир продолжает жить своими событиями."
            ),
            "npc_reactions": npc_result["npc_reactions"],
            "world_changes": world_result["world_events"],
        }

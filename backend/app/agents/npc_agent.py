from app.models.schemas import PlayerAction


class NpcAgent:
    def react(self, location: str, actions: list[PlayerAction], npc_memory: list[dict] | None = None) -> dict:
        reactions = []
        memory_lines = []
        for action in actions:
            reactions.append(f"NPC в {location} реагируют на действие '{action.action}' игрока {action.player_name}.")
            memory_lines.append(f"{action.player_name} в {location}: {action.action}")

        if npc_memory:
            last = npc_memory[-1].get("note") if isinstance(npc_memory[-1], dict) else None
            if last:
                reactions.append(f"NPC помнят прошлый контекст: {last}")

        return {"npc_reactions": reactions, "npc_memory_updates": memory_lines}

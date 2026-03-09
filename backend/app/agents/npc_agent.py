"""
NPC Agent - NPC Dialogue Generation

Uses capability-based routing for realistic NPC conversations.
"""

from typing import Optional

from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, Capability, get_router


class NpcAgent:
    """
    NPC agent with automatic model selection.
    
    Uses ModelRouter to request 'dialogue' capability.
    Automatically selects best model for conversations.
    """

    def __init__(self, router: Optional[ModelRouter] = None) -> None:
        self._router = router
        self._npc_context: dict = {}

    @property
    def router(self) -> ModelRouter:
        """Lazy initialization of router via global singleton."""
        if self._router is None:
            self._router = get_router()
        return self._router

    def react(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: list[dict] | None = None,
    ) -> dict:
        """
        Generate NPC reactions using automatic model selection.
        
        The agent requests 'dialogue' capability.
        Router automatically selects: yandex (forwen_7b dialogue) or q.
        """
        # Build context for NPC
        prompt = self._build_prompt(location, actions, npc_memory)
        
        # Get system prompt for dialogue
        system_prompt = self._get_system_prompt()
        
        memory_lines = []
        for action in actions:
            memory_lines.append(f"{action.player_name} в {location}: {action.action}")

        try:
            # Request via router - automatic model selection
            response = self.router.request(
                capability=Capability.DIALOGUE,
                prompt=prompt,
                system_prompt=system_prompt,
            )
            
            return {
                "npc_reactions": [response],
                "npc_memory_updates": memory_lines,
            }
        except Exception as e:
            print(f"NPC Agent error: {e}, using fallback")
            return self._fallback_react(location, actions, npc_memory)

    def speak_as(
        self,
        npc_name: str,
        context: str,
        player_action: str,
    ) -> str:
        """
        Generate dialogue for specific NPC.
        
        Args:
            npc_name: Имя NPC
            context: Текущий контекст ситуации
            player_action: Действие игрока, на которое реагирует NPC
            
        Returns:
            Ответ NPC
        """
        prompt = f"""Ситуация: {context}
Действие игрока: {player_action}

Ответь от лица {npc_name}."""
        
        system_prompt = f"""Ты - {npc_name}, персонаж D&D 5e кампании.
Отвечай от первого лица, как персонаж.
Будь аутентичен: учитывай личность, мотивацию, настроение.
Не описывай действия - только говори."""
        
        try:
            return self.router.request(
                capability=Capability.DIALOGUE,
                prompt=prompt,
                system_prompt=system_prompt,
            )
        except Exception as e:
            print(f"NPC speak error: {e}")
            return f"{npc_name} молча смотрит на тебя."

    def _build_prompt(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: list[dict] | None,
    ) -> str:
        """Build NPC reaction prompt."""
        action_str = "\n".join(f"- {a.player_name}: {a.action}" for a in actions)
        
        memory_str = ""
        if npc_memory:
            last = npc_memory[-1].get("note") if isinstance(npc_memory[-1], dict) else None
            if last:
                memory_str = f"\nКонтекст из памяти: {last}"
        
        return f"""Локация: {location}
Действия игроков:
{action_str}
{memory_str}

Сгенерируй реакцию NPC на действия игроков.
Опиши диалоги и поведение персонажей.
Будь краток (1-2 предложения)."""

    def _get_system_prompt(self) -> str:
        """Get system prompt for NPC dialogue."""
        return """Ты - NPC в D&D 5e кампании.
Генерируй реалистичные диалоги и реакции персонажей.
Отвечай от первого лица.
Учитывай контекст ситуации и отношения с игроками.
Будь краток и атмосферен."""

    def _fallback_react(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: list[dict] | None,
    ) -> dict:
        """Fallback when LLM is unavailable."""
        reactions = []
        memory_lines = []
        
        for action in actions:
            reactions.append(f"NPC в {location} реагируют на '{action.action}'.")
            memory_lines.append(f"{action.player_name}: {action.action}")

        if npc_memory:
            last = npc_memory[-1].get("note") if isinstance(npc_memory[-1], dict) else None
            if last:
                reactions.append(f"NPC помнят: {last}")

        return {"npc_reactions": reactions, "npc_memory_updates": memory_lines}


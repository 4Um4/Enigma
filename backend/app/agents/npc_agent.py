"""
NPC Agent - NPC Dialogue Generation

Uses capability-based routing for realistic NPC conversations.
Supports NPC Levels: major (important NPCs use npc_major model) 
and mass (background NPCs use npc_mass model).
"""

from typing import Optional

from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, Capability, get_router
from app.services.llm.provider import GenerationParams
from app.services.llm.provider_manager import get_model_pool
from app.core.config import settings


class NpcAgent:
    """
    NPC agent with automatic model selection.
    
    Uses ModelRouter to request 'dialogue' capability.
    Automatically selects best model for conversations.
    Supports NPC Levels:
    - major: Important NPCs use npc_major model (full quality)
    - mass: Background NPCs use npc_mass model (fast)
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

    def _get_capability_for_npc(self, npc_importance: Optional[str] = None) -> Capability:
        """
        Get the appropriate capability based on NPC importance.
        
        Args:
            npc_importance: 'major' for important NPCs, 'mass' for background
            
        Returns:
            Capability for model selection
        """
        if npc_importance == "major":
            return Capability.DIALOGUE_GENERATION
        return Capability.DIALOGUE

    def run(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
        shared_context: Optional[dict] = None,
        npc_importance: str = "mass",
    ) -> dict:
        """
        Main run method for NpcAgent - generates NPC reactions.
        SAFE FALLBACK: Always returns minimal dict if exception occurs.
        """
        try:
            return self.react(location, actions, npc_memory, shared_context, npc_importance)
        except Exception:
            return self._fallback_react(location, actions, npc_memory)

    def speak_as(
        self,
        npc_name: str,
        context: str,
        player_action: str,
    ) -> str:
        """
        Generate dialogue for a specific NPC.
        
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
                capability=self._get_capability_for_npc("major"),
                prompt=prompt,
                system_prompt=system_prompt,
                params=GenerationParams(max_tokens=400),
            )
        except Exception as e:
            print(f"NPC speak error: {e}")
            return f"{npc_name} молча смотрит на тебя."

    def _build_prompt(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
        shared_context: Optional[dict] = None,
    ) -> str:
        """Build NPC reaction prompt with shared context."""
        action_str = "\n".join(f"- {a.player_name}: {a.action}" for a in actions)

        # Build memory context from multiple sources
        memory_str = ""

        # 1. From NPC memory
        if npc_memory:
            last = npc_memory[-1].get("note") if isinstance(npc_memory[-1], dict) else None
            if last:
                memory_str += f"\nКонтекст NPC: {last}"

        # 2. From shared_context recent_memory
        if shared_context:
            recent = shared_context.get("recent_memory", [])
            if recent:
                last_event = recent[-1]
                event_type = last_event.get("type", "event")
                memory_str += f"\nНедавнее событие: {event_type}"

        return f"""Локация: {location}
Действия игроков:
{action_str}
{memory_str}

Сгенерируй реакцию NPC на действия игроков.
Опиши диалоги и поведение персонажей.
Будь краток (1-2 предложения)."""

    def _get_system_prompt(self) -> str:
        """Get system prompt for NPC dialogue."""
        tone = ""
        if getattr(settings, "hardcore_mode", False):
            tone = """

HARDCORE: разрешены грубость, мат, угрозы, мрачные детали, жестокость.
Не морализируй и не смягчай речь игрока/сцены. Не "воспитывай" игрока.
"""

        return f"""Ты - NPC в D&D 5e кампании.
Генерируй реалистичные диалоги и реакции персонажей.
Отвечай от первого лица (Я/мне/меня), без перехода на "вы с изумлением" от третьего лица.
Учитывай контекст ситуации и отношения с игроками.
Будь краток и атмосферен (1-2 предложения).
Не повторяй дословно фразы игрока, реагируй по смыслу.
Не добавляй мета-пояснений про модель, правила или безопасность.{tone}"""

    def _fallback_react(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
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

    def react(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
        shared_context: Optional[dict] = None,
        npc_importance: str = "mass",
    ) -> dict:
        """Generate NPC reactions using router request."""
        prompt = self._build_prompt(location, actions, npc_memory, shared_context)
        capability = self._get_capability_for_npc(npc_importance)
        system_prompt = self._get_system_prompt()

        # Мета о том, какую модель роутер выберет под эту capability.
        model_key = self.router.select_model(capability)
        model_meta = {"key": model_key}
        try:
            pool = get_model_pool()
            cfg = pool.get_model_config(model_key) if pool else None
            if cfg:
                model_meta.update({
                    "name": cfg.name,
                    "provider": cfg.provider_type.value,
                    "path": cfg.path,
                    "context_size": cfg.context_size,
                    "temperature": cfg.temperature,
                })
        except Exception:
            pass

        try:
            response = self.router.request(
                capability=capability,
                prompt=prompt,
                system_prompt=system_prompt,
                params=GenerationParams(max_tokens=400),
            )
            return {
                "npc_reactions": [response],
                "npc_memory_updates": [prompt],
                "model": model_meta,
            }
        except Exception:
            return self._fallback_react(location, actions, npc_memory)
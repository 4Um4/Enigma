"""
DM Agent - Dungeon Master Narrative Layer

Uses capability-based routing to automatically select the best model.
"""

from typing import Optional

from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, Capability, get_router


class DmAgent:
    """
    Narrative DM layer with automatic model selection.
    
    Uses ModelRouter to request "narrative" capability.
    The router automatically selects the best model.
    """

    def __init__(self, router: Optional[ModelRouter] = None) -> None:
        self._router = router

    @property
    def router(self) -> ModelRouter:
        """Lazy initialization of router via global singleton."""
        if self._router is None:
            self._router = get_router()
        return self._router

    def narrate(
        self,
        location: str,
        actions: list[PlayerAction],
        rules_result: dict,
        npc_result: dict,
        world_result: dict,
        world_canon_exists: bool,
        context: Optional[dict] = None,
    ) -> dict:
        """
        Generate DM narrative using automatic model selection.
        
        The agent requests 'narrative' capability.
        Router automatically selects: qwen_7b (default) or qwen_9b (if available).
        """
        action_lines = " ".join([f"{a.player_name}: {a.action}." for a in actions])
        
        # Build prompt
        prompt = self._build_prompt(
            location=location,
            actions=action_lines,
            rules_result=rules_result,
            npc_result=npc_result,
            world_result=world_result,
            world_canon_exists=world_canon_exists,
            context=context,
        )
        
        # Get system prompt for narrative
        system_prompt = self._get_system_prompt()
        
        try:
            # Request via router - automatic model selection by capability
            dm_response = self.router.request(
                capability=Capability.NARRATIVE,
                prompt=prompt,
                system_prompt=system_prompt,
            )
            
            return {
                "dm_response": dm_response,
                "npc_reactions": npc_result.get("npc_reactions", []),
                "world_changes": world_result.get("world_events", []),
            }
        except Exception as e:
            print(f"DM Agent error: {e}, using fallback")
            return self._fallback_narrate(location, actions, rules_result, npc_result, world_result, world_canon_exists)

    def _build_prompt(
        self,
        location: str,
        actions: str,
        rules_result: dict,
        npc_result: dict,
        world_result: dict,
        world_canon_exists: bool,
        context: Optional[dict] = None,
    ) -> str:
        """Build narrative prompt."""
        context_str = ""
        if context:
            recent = context.get("recent_events", [])
            if recent:
                context_str = "Недавние события:\n" + "\n".join(f"- {e}" for e in recent[-3:]) + "\n\n"
        
        npc_reactions = npc_result.get("npc_reactions", [])
        npc_str = "\n".join(f"- {r}" for r in npc_reactions) if npc_reactions else "Нет реакций NPC"
        
        world_changes = world_result.get("world_events", [])
        world_str = "\n".join(f"- {w}" for w in world_changes) if world_changes else "Нет изменений мира"
        
        checks = rules_result.get("checks", [])
        rules_str = "\n".join(f"- {c.get('player', 'Unknown')}: {c.get('result', c.get('instruction', ''))}" for c in checks) if checks else "Нет проверок"
        
        return f"""Текущая локация: {location}

{context_str}Действия игроков:
{actions}

Результаты проверок правил:
{rules_str}

Реакции NPC:
{npc_str}

Изменения в мире:
{world_str}

Продолжи рассказ от лица Dungeon Master. Опиши что происходит, диалоги NPC, результаты действий. 
Не говори за игроков. Будь краток (1-3 предложения для простых действий).
В конце опиши текущую ситуацию, не задавай вопросов."""

    def _get_system_prompt(self) -> str:
        """Get system prompt for DM narrative."""
        return """Ты - Dungeon Master для D&D 5e кампании.
Веди叙事 от третьего лица, описывая мир и NPC.
Никогда не говори за игроков.
Будь краток и атмосферен.
Не повторяй предыдущий текст."""

    def _fallback_narrate(
        self,
        location: str,
        actions: list[PlayerAction],
        rules_result: dict,
        npc_result: dict,
        world_result: dict,
        world_canon_exists: bool,
    ) -> dict:
        """Fallback when LLM is unavailable."""
        action_lines = " ".join([f"{a.player_name}: {a.action}." for a in actions])
        if not world_canon_exists:
            return {
                "dm_response": (
                    f"Локация: {location}. Канон мира ещё не загружен. "
                    f"Заявленные действия: {action_lines}"
                ),
                "npc_reactions": ["NPC ждут уточнения канона мира."],
                "world_changes": ["Симуляция отложена до загрузки канона."],
            }

        return {
            "dm_response": (
                f"Локация: {location}. {action_lines} "
                f"Проверки: {rules_result['checks']}. "
                "Мир продолжает жить."
            ),
            "npc_reactions": npc_result.get("npc_reactions", []),
            "world_changes": world_result.get("world_events", []),
        }


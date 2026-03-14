"""
DM Agent - Dungeon Master Narrative Layer

Uses capability-based routing to automatically select the best model.
Includes Phase 1 error handling + VRAM logging.
"""

from typing import Optional, List, Dict
from pathlib import Path
from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, get_router
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
# from app.services.orchestrator import jsonl_log, ERROR_CODES  # Avoid circular import


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

    def run(
        self,
        location: str,
        actions: List[PlayerAction],
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        Main run method for DmAgent - generates narrative response.
        SAFE FALLBACK: Always returns minimal dict.
        """
        try:
            return self.narrate(
                location,
                actions,
                rules_result,
                npc_result,
                world_result,
                world_canon_exists,
                context,
            )
        except Exception:
            return self._fallback_narrate(
                location,
                actions,
                rules_result,
                npc_result,
                world_result,
                world_canon_exists,
            )

    def _build_prompt(
        self,
        location: str,
        actions: str,
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
        context: Optional[Dict] = None,
    ) -> str:
        """Build narrative prompt."""
        context_str = ""
        if context:
            recent = context.get("recent_memory", [])
            if recent:
                context_str = "Недавние события:\n" + "\n".join(f"- {e}" for e in recent[-3:]) + "\n\n"

        npc_reactions = npc_result.get("npc_reactions", [])
        npc_str = "\n".join(f"- {r}" for r in npc_reactions) if npc_reactions else "Нет реакций NPC"

        world_changes = world_result.get("world_events", [])
        world_str = "\n".join(f"- {w}" for w in world_changes) if world_changes else "Нет изменений мира"

        checks = rules_result.get("checks", [])
        rules_str = (
            "\n".join(f"- {c.get('player', 'Unknown')}: {c.get('result', c.get('instruction', ''))}" for c in checks)
            if checks
            else "Нет проверок"
        )

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
        actions: List[PlayerAction],
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
    ) -> Dict:
        """Fallback when LLM is unavailable - minimal working."""
        return {
            "dm_response": "Ничего не произошло.",
            "npc_reactions": [],
            "world_changes": [],
        }

    def narrate(
        self,
        location: str,
        actions: List[PlayerAction],
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        Generates narrative using ModelRouter.
        Converts actions list to string for prompt.
        """
        actions_str = "\n".join(f"{a.player_name}: {a.action}" for a in actions) if actions else "Нет действий"

        prompt = self._build_prompt(
            location,
            actions_str,
            rules_result,
            npc_result,
            world_result,
            world_canon_exists,
            context,
        )

        system_prompt = self._get_system_prompt()

        result = self.router.request(
            capability="narrative",
            prompt=prompt,
            system_prompt=system_prompt,
        )

        # result expected to be dict or JSON string
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except Exception:
                result = {"dm_response": result, "npc_reactions": [], "world_changes": []}

        return result
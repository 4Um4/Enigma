"""
NPC Agent - NPC Dialogue Generation

Uses capability-based routing for realistic NPC conversations.
Supports NPC Levels: major (important NPCs use npc_major model)
and mass (background NPCs use npc_mass model).

ФАЗА 3A: когда shared_context содержит npc_contexts (из Phase 3A NPC Psychology движков),
агент использует build_npc_prompt() систем-промпты вместо обезличенного дефолтного.
Это обеспечивает корректные имена NPC, психологию и поведение в ответах.
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

    Phase 3A: when shared_context["python_engines"]["npc_contexts"] is present,
    uses Phase 3A system prompts (built by build_npc_prompt) for each NPC.
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

    # ─────────────────────────────────────────────────────────────────────────
    # ФАЗА 3A: новый метод для Phase 3A промптов
    # ─────────────────────────────────────────────────────────────────────────

    def _get_phase3a_npc_contexts(self, shared_context: Optional[dict]) -> list:
        """
        Извлекает npc_contexts из shared_context.
        Проверяет два места:
          1. Верхний уровень shared_context["npc_contexts"]
             — так хранит routes_stream.py (python_engines там пуст)
          2. Внутри shared_context["python_engines"]["npc_contexts"]
             — так хранит orchestrator._run_python_engines (полный пайплайн)
        Если Phase 3A не запускалась — возвращает пустой список.
        """
        if not shared_context:
            return []
        # ИСПРАВЛЕНИЕ: сначала проверяем верхний уровень (stream-роут)
        top_level = shared_context.get("npc_contexts")
        if top_level:
            return top_level
        # Затем внутри python_engines (orchestrator)
        python_engines = shared_context.get("python_engines", {})
        if not isinstance(python_engines, dict):
            return []
        return python_engines.get("npc_contexts", [])

    def _build_phase3a_prompt(
        self,
        npc_context: dict,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
    ) -> tuple[str, str]:
        """
        Строит (system_prompt, user_prompt) из Phase 3A данных конкретного NPC.
        system_prompt — уже готов из build_npc_prompt() с именем, психологией, поведением.
        user_prompt — действие игрока.
        """
        # system_prompt — построен Phase 3A (содержит имя NPC, drives, state, behavior_hint)
        system_prompt = npc_context.get("system_prompt", self._get_system_prompt())

        # Добавляем hardcore-режим если включён
        if getattr(settings, "hardcore_mode", False):
            system_prompt += """

HARDCORE: разрешены грубость, мат, угрозы, мрачные детали, жестокость.
Не морализируй и не смягчай речь. Не "воспитывай" игрока."""

        action_lines = "\n".join(f"- {a.player_name}: {a.action}" for a in actions)
        user_prompt = f"""Действия игроков:\n{action_lines}\n\nОтветь кратко, от первого лица (1-2 предложения)."""

        return system_prompt, user_prompt

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
        """Get generic system prompt for NPC dialogue (fallback when no Phase 3A data)."""
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
        """
        Generate NPC reactions using router request.

        ФАЗА 3A: если shared_context содержит npc_contexts — использует
        Phase 3A system_prompt (с именем NPC, психологией, поведением).
        Иначе — дефолтный обезличенный промпт.
        """
        npc_contexts = self._get_phase3a_npc_contexts(shared_context)

        if npc_contexts:
            # ── ПУТЬ ФАЗА 3A: есть NPC с психологией ────────────────────────
            # Используем первый NPC из локации (самый важный по tier).
            # Сортируем: major > minor > mass
            tier_order = {"major": 0, "minor": 1, "mass": 2}
            sorted_contexts = sorted(
                npc_contexts,
                key=lambda c: tier_order.get(c.get("tier", "mass"), 2)
            )
            primary_ctx = sorted_contexts[0]

            # Capability по tier первого NPC
            primary_tier = primary_ctx.get("tier", "minor")
            capability = self._get_capability_for_npc(
                "major" if primary_tier == "major" else npc_importance
            )

            system_prompt, user_prompt = self._build_phase3a_prompt(
                primary_ctx, actions, npc_memory
            )

        else:
            # ── ПУТЬ ДЕФОЛТ: нет Phase 3A данных (fallback) ─────────────────
            capability    = self._get_capability_for_npc(npc_importance)
            system_prompt = self._get_system_prompt()
            user_prompt   = self._build_prompt(location, actions, npc_memory, shared_context)

        # Мета о том, какую модель роутер выберет под эту capability.
        model_key  = self.router.select_model(capability)
        model_meta = {"key": model_key}
        try:
            pool = get_model_pool()
            cfg  = pool.get_model_config(model_key) if pool else None
            if cfg:
                model_meta.update({
                    "name":         cfg.name,
                    "provider":     cfg.provider_type.value,
                    "path":         cfg.path,
                    "context_size": cfg.context_size,
                    "temperature":  cfg.temperature,
                })
        except Exception:
            pass

        try:
            response = self.router.request(
                capability=capability,
                prompt=user_prompt,
                system_prompt=system_prompt,
                params=GenerationParams(max_tokens=400),
            )
            return {
                "npc_reactions":      [response],
                "npc_memory_updates": [user_prompt],
                "model":              model_meta,
                # Передаём inner_thoughts для Debug Mode (если есть)
                "npc_inner_thoughts": [
                    {"npc": ctx["npc_name"], "thought": ctx.get("inner_thought", "")}
                    for ctx in npc_contexts
                ],
            }
        except Exception:
            return self._fallback_react(location, actions, npc_memory)
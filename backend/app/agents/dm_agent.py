# -*- coding: utf-8 -*-
"""
DM Agent - Dungeon Master Narrative Layer

Uses capability-based routing to automatically select the best model.
Includes Phase 1 error handling + VRAM logging.
"""

from typing import Optional, List, Dict, Generator
from pathlib import Path
from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, get_router
from app.services.llm.provider import GenerationParams
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
from app.core.config import settings
import json


class DmAgent:
    """
    Narrative DM layer with automatic model selection.
    Uses ModelRouter to request "narrative" capability.
    """

    def __init__(self, router: Optional[ModelRouter] = None) -> None:
        self._router = router

    @property
    def router(self) -> ModelRouter:
        if self._router is None:
            self._router = get_router()
        return self._router

    # ──────────────────────────────────────────────────────────────────────────
    # Основной метод (синхронный, для обычных запросов)
    # ──────────────────────────────────────────────────────────────────────────

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
        """Main run method. SAFE FALLBACK: всегда возвращает dict."""
        try:
            return self.narrate(
                location, actions, rules_result, npc_result,
                world_result, world_canon_exists, context,
            )
        except Exception:
            return self._fallback_narrate(
                location, actions, rules_result, npc_result,
                world_result, world_canon_exists,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Построение промпта — здесь основные изменения
    # ──────────────────────────────────────────────────────────────────────────

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
        context_str = ""
        if context:
            recent = context.get("recent_memory", [])
            if recent:
                context_str = "Недавние события:\n" + "\n".join(f"- {e}" for e in recent[-5:]) + "\n\n"

        npc_reactions = npc_result.get("npc_reactions", [])
        npc_str = "\n".join(f"- {r}" for r in npc_reactions) if npc_reactions else "Нет реакций NPC"

        world_changes = world_result.get("world_events", [])
        world_str = "\n".join(f"- {w}" for w in world_changes) if world_changes else "Нет изменений мира"

        checks = rules_result.get("checks", [])
        rules_str = (
            "\n".join(
                f"- {c.get('player', 'Unknown')}: {c.get('result', c.get('instruction', ''))}"
                for c in checks
            )
            if checks else "Нет проверок"
        )

        physics_warnings = ""
        python_engines_block = ""

        if context:
            # ──────────────────────────────
            # Блок physics_validation
            # ──────────────────────────────
            if context.get("physics_validation"):
                invalid = [v for v in context["physics_validation"] if not v["valid"]]
                if invalid:
                    physics_warnings = "Физические/логические ограничения сцены (ОБЯЗАТЕЛЬНО учитывай):\n"
                    for v in invalid:
                        physics_warnings += (
                            f"- Игрок пытался: {v['reason']}. "
                            f"Это невозможно потому что: {v.get('explanation', 'нарушение законов физики/логики игры')}. "
                            f"Предложи альтернативу: {v.get('alternative', 'другое действие')}\n"
                        )
                    physics_warnings += "\nТы обязан уважать эти ограничения и не допускать нарушения физики/логики.\n"

            # ──────────────────────────────
            # Блок python_engines — самый важный
            # ──────────────────────────────
            if context.get("python_engines"):
                engines = context["python_engines"]
                if engines:
                    python_engines_block = "Результаты вычислений и проверок (ОБЯЗАТЕЛЬНО используй эти данные в повествовании):\n"
                    for player_name, data in engines.items():
                        python_engines_block += f"Игрок {player_name}:\n"
                        if data.get("combat"):
                            c = data["combat"]
                            python_engines_block += (
                                f"- Атака: бросок {c.get('roll_str', '?')}, "
                                f"попадание: {'да' if c.get('hit') else 'нет'}, "
                                f"крит: {'да' if c.get('critical') else 'нет'}, "
                                f"урон: {c.get('damage_total', 0)} ({c.get('damage_str', '?')})\n"
                            )
                        if data.get("sandbox"):
                            s = data["sandbox"]
                            python_engines_block += (
                                f"- Действие типа {s.get('action_type', 'неизвестно')}: "
                                f"успех = {s.get('success', '?')}, "
                                f"результат = {s.get('result_description', 'нет описания')}\n"
                            )
                    python_engines_block += "\nИспользуй эти точные результаты в своём повествовании. Не придумывай другие значения.\n"

        return f"""Текущая локация: {location}

{context_str}
Действия игроков:
{actions}

Результаты проверок правил:
{rules_str}

Реакции NPC:
{npc_str}

Изменения в мире:
{world_str}

{physics_warnings}
{python_engines_block}

Продолжи рассказ от лица Dungeon Master. Не говори за игроков. 
Опиши что происходит, диалоги NPC, результаты действий. 
Обязательно учитывай данные из блоков "Физические/логические ограничения" и "Результаты вычислений и проверок" — они имеют приоритет.
Не говори за игроков. Будь краток (1-3 предложения для простых действий).
В конце опиши текущую ситуацию, не задавай вопросов.
"""

    def _get_system_prompt(self) -> str:
        tone = ""
        if getattr(settings, "hardcore_mode", False):
            tone = """

ТОН/РЕЖИМ: HARDCORE.
Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.
Не морализируй, не сглаживай и не "перевоспитывай" игрока.
Действия имеют последствия (социальные и физические), но без цензуры.
"""

        return f"""ВАЖНО: Отвечай ТОЛЬКО на Русском языке. Никакого английского или китайского.
ВАЖНО: Не показывай свои размышления. Только финальный ответ.

Ты — Мастер Подземелий D&D 5e. Ведёшь повествование от третьего лица.
Никогда не говори за игроков.
Будь атмосферен и краток (2-4 предложения).
Не повторяй текст промпта в ответе.{tone}"""

    # ──────────────────────────────────────────────────────────────────────────
    # Синхронная генерация
    # ──────────────────────────────────────────────────────────────────────────

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
        actions_str = (
            "\n".join(f"{a.player_name}: {a.action}" for a in actions)
            if actions else "Нет действий"
        )

        prompt = self._build_prompt(
            location, actions_str, rules_result, npc_result,
            world_result, world_canon_exists, context,
        )

        result = self.router.request(
            capability="narrative",
            prompt=prompt,
            system_prompt=self._get_system_prompt(),
            params=GenerationParams(max_tokens=1000),
        )

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = {"dm_response": result, "npc_reactions": [], "world_changes": []}

        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Streaming генерация — для SSE роута
    # ──────────────────────────────────────────────────────────────────────────

    async def stream_narrate(self, location, actions, rules_result, npc_result,
                             world_result, world_canon_exists, context=None):
        """
        Async streaming генерация для SSE роута.
        Загружает модель через ModelPool.get_model_async(), затем стримит токены.
        """
        actions_str = (
            "\n".join(f"{a.player_name}: {a.action}" for a in actions)
            if actions else "Нет действий"
        )
        prompt = self._build_prompt(
            location, actions_str, rules_result, npc_result,
            world_result, world_canon_exists, context,
        )
        system_prompt = self._get_system_prompt()

        provider = await self._get_provider_async("narrative")

        if provider is None or not hasattr(provider, "stream_tokens"):
            result = self.router.request(
                capability="narrative",
                prompt=prompt,
                system_prompt=system_prompt,
                params=GenerationParams(max_tokens=1000),
            )
            if isinstance(result, dict):
                yield result.get("dm_response", "")
            else:
                yield str(result)
            return

        import asyncio
        import threading

        q: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _producer():
            token_num = 0
            try:
                for token in provider.stream_tokens(
                    prompt=prompt,
                    params=GenerationParams(max_tokens=1000),
                    system_prompt=system_prompt,
                ):
                    token_num += 1
                    if token and len(token) > 24:
                        step = 12
                        for i in range(0, len(token), step):
                            asyncio.run_coroutine_threadsafe(q.put(token[i:i+step]), loop)
                    else:
                        asyncio.run_coroutine_threadsafe(q.put(token), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(q.put(f"\n[Ошибка стриминга: {e}]"), loop)
            finally:
                asyncio.run_coroutine_threadsafe(q.put(None), loop)

        threading.Thread(target=_producer, daemon=True).start()

        while True:
            item = await q.get()
            if item is None:
                break
            yield item

    async def _get_provider_async(self, capability: str):
        from app.services.llm.router import Capability, CAPABILITY_MODEL_PREFERENCES
        from app.services.llm.provider_manager import get_model_pool
    
        capability_obj = Capability(capability) if isinstance(capability, str) else capability
        preferred_keys = CAPABILITY_MODEL_PREFERENCES.get(capability_obj, [])
    
        pool = get_model_pool()
        if pool is None:
            return None
    
        for model_key in preferred_keys:
            if pool.is_model_available(model_key):
                model_provider = await pool.get_model_async(
                    model_key, 
                    agent="dm_narrative",
                    timeout_sec=60
                )
                if model_provider and model_provider.is_available():
                    return model_provider.provider
    
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Fallback
    # ──────────────────────────────────────────────────────────────────────────

    def _fallback_narrate(
        self,
        location: str,
        actions: List[PlayerAction],
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
    ) -> Dict:
        return {
            "dm_response": "Ничего не произошло.",
            "npc_reactions": [],
            "world_changes": [],
        }
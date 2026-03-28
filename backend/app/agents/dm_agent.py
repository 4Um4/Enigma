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


# ──────────────────────────────────────────────────────────────────────────────
# Стоп-токены Gemma-3: при появлении в стриме — немедленно останавливаем.
# <|im_start|> — самый опасный: вызывает генерацию текста промпта целиком.
# ──────────────────────────────────────────────────────────────────────────────
_GEMMA_STOP_TOKENS = [
    "<|file_separator|>",
    "<|end_of_turn|>",
    "<end_of_turn>",
    "<|im_end|>",
    "</|im_end|>",
    "<|im_start|>",      # главный виновник утечки промпта
    "</|im_start|>",
    "</s>",
    "<|endoftext|>",
    "<|file_end|>",
    "<|file_sep|>",
]


def _strip_stop_tokens(text: str) -> str:
    """Убирает стоп-токены из строки. Обрезает по первому вхождению."""
    for token in _GEMMA_STOP_TOKENS:
        idx = text.find(token)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def _has_stop_token(text: str) -> bool:
    return any(st in text for st in _GEMMA_STOP_TOKENS)


# ──────────────────────────────────────────────────────────────────────────────
# Фаза S: вспомогательная функция — SceneState → текст для DM промпта
# Дублирует логику SceneStateManager.get_scene_description() чтобы избежать
# циклического импорта. dm_agent не должен зависеть от scene_state_manager.
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# ПАТЧ для dm_agent.py — ФАЗА S.0
# Заменить функцию _build_scene_description() целиком.
#
# Изменения:
#   - Добавлен блок ПРОСТРАНСТВЕННЫЙ КОНТЕКСТ ИГРОКА
#   - Добавлен блок ПРАВИЛА РЕАКЦИЙ NPC
#   - _build_scene_description теперь делегирует в SceneStateManager
#     (убираем дублирование логики)
# ──────────────────────────────────────────────────────────────────────────────

def _build_scene_description(scene_state: dict) -> str:
    """
    Преобразует SceneState в текстовый блок для DM промпта.

    S.0: делегирует в SceneStateManager.get_scene_description() —
    там уже реализован полный блок включая player_target и правила реакций.

    Fallback: встроенная упрощённая версия если импорт недоступен.
    """
    if not scene_state:
        return ""

    # Пробуем использовать SceneStateManager — там полная S.0 логика
    try:
        from app.services.scene_state_manager import SceneStateManager
        return SceneStateManager.get_scene_description(scene_state)
    except Exception:
        pass

    # ── Fallback: упрощённая версия (совместимость) ───────────────────────────
    location_name = scene_state.get("location_name", scene_state.get("location_id", "?"))
    env           = scene_state.get("environment", {})
    objects       = scene_state.get("objects", {})
    npc_positions = scene_state.get("npc_positions", {})
    effects       = scene_state.get("active_effects", [])
    time_of_day   = env.get("time_of_day", "?")
    light         = env.get("light_level", "")
    noise         = env.get("noise_level", "")

    light_desc = {
        "dark": "темно", "very_dim": "почти темно", "dim": "тускло",
        "bright": "светло", "natural": "дневной свет",
    }.get(light, light)

    noise_desc = {
        "silent": "тихо", "low": "тихий фон",
        "moderate": "умеренный шум", "high": "шумно",
    }.get(noise, noise)

    state_map = {
        "intact": "цел", "damaged": "повреждён", "broken": "сломан",
        "lit": "горит", "unlit": "не горит", "burning": "горит",
        "open": "открыт", "closed_unlocked": "закрыт", "closed_locked": "заперт",
        "full": "полный", "empty": "пустой", "flowing": "течёт",
    }

    lines = [
        f"СОСТОЯНИЕ СЦЕНЫ — {location_name} | {time_of_day} | {light_desc} | {noise_desc}",
    ]

    if objects:
        parts = []
        for obj_id, obj in objects.items():
            name  = obj.get("name", obj_id)
            state = state_map.get(obj.get("state", ""), obj.get("state", ""))
            count = obj.get("count")
            cnt   = f"({count})" if count and count > 1 else ""
            parts.append(f"{name}{cnt}: {state}" if state else name)
        lines.append("Объекты: " + "; ".join(parts))

    if npc_positions:
        npc_parts = []
        for npc_id, pos in npc_positions.items():
            if pos.get("state") == "dead":
                continue
            p = pos.get("position", "")
            a = pos.get("activity", "")
            v = "" if pos.get("visible", True) else "(скрыт)"
            npc_parts.append(f"{npc_id} {v}: {p}, {a}".strip())
        if npc_parts:
            lines.append("NPC: " + "; ".join(npc_parts))

    if effects:
        lines.append("Эффекты: " + ", ".join(str(e) for e in effects))

    # S.0: player_target даже в fallback
    target_name = scene_state.get("player_target_npc_name")
    target_id   = scene_state.get("player_target_npc")
    player_pos  = scene_state.get("player_position")
    if player_pos:
        lines.append(f"Позиция игрока: {player_pos}")
    if target_name or target_id:
        name_str = target_name or target_id
        lines.append(f"Игрок обращается к: {name_str}")
        lines.append(
            f"ПРАВИЛО: только {name_str} отвечает игроку. Остальные NPC молчат."
        )

    lines.append("Упоминай ТОЛЬКО объекты и NPC из этого списка.")
    return "\n".join(lines)


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

        # Фаза S: SceneState — факты о мире. DM получает это первым.
        # Только объекты и NPC из этого блока реально существуют в сцене.
        scene_block = ""
        if context:
            scene_state = context.get("scene_state", {})
            if scene_state:
                try:
                    scene_block = _build_scene_description(scene_state) + "\n\n"
                except Exception:
                    pass

        # DM получает речь NPC как контекст-только-для-чтения —
        # чтобы его описание мира было СОГЛАСОВАНО с тем что NPC уже сказали.
        # Принцип: NPC говорят → DM описывает то что ПОСЛЕ слов NPC.
        # ВАЖНО: DM не пересказывает речь, но знает о ней.
        npc_reactions = npc_result.get("npc_reactions", [])
        npc_str = (
            "\n".join(f"- {r}" for r in npc_reactions)
            if npc_reactions else ""
        )
        npc_actions = npc_result.get("npc_actions", [])
        npc_actions_str = (
            "\n".join(f"- {a}" for a in npc_actions)
            if npc_actions else ""
        )

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
        npc_psychology_block = ""

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
                        # ИСПРАВЛЕНИЕ: npc_contexts хранится в python_engines в
                        # orchestrator._run_python_engines — это list, не dict.
                        # В stream-роуте python_engines пуст, но для надёжности
                        # пропускаем любые не-dict значения чтобы не было AttributeError.
                        if not isinstance(data, dict):
                            continue
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
                            success_str = "УСПЕХ" if s.get("success") else "ПРОВАЛ"
                            cons = s.get("consequences", {})
                            cons_str = ", ".join(
                                f"{k}={v}" for k, v in cons.items()
                            ) if cons else "нет последствий"
                            python_engines_block += (
                                f"- Действие типа {s.get('action_type', 'неизвестно')}: "
                                f"{success_str}. "
                                f"Последствия: {cons_str}.\n"
                                f"  ВАЖНО: если ПРОВАЛ — действие НЕ удалось физически. "
                                f"Не описывай его как успешное.\n"
                            )
                    python_engines_block += "\nИспользуй эти точные результаты в своём повествовании. Не придумывай другие значения.\n"

            # ──────────────────────────────
            # ФАЗА 3A: Психология NPC
            # ──────────────────────────────
            # npc_contexts хранится на верхнем уровне shared_context (stream-роут)
            # или внутри python_engines["npc_contexts"] (orchestrator).
            # DM получает подсказки о поведении NPC — чтобы повествование
            # совпадало с тем что рассчитали Python-движки.
            npc_ctxs = context.get("npc_contexts") or (
                context.get("python_engines", {}).get("npc_contexts", [])
                if isinstance(context.get("python_engines"), dict) else []
            )
            if npc_ctxs:
                npc_psychology_block = "Психологическое состояние NPC в локации (Python рассчитал — использовать в повествовании):\n"
                for ctx in npc_ctxs:
                    name  = ctx.get("npc_name", "NPC")
                    hint  = ctx.get("behavior_hint", "")
                    pstat = ctx.get("perceived_status", "")
                    tcat  = ctx.get("threat_category", "")
                    line  = f"- {name}: {hint}"
                    if pstat:
                        line += f" | Игрок воспринимается как: {pstat}"
                    if tcat:
                        line += f" | Уровень угрозы: {tcat}"
                    npc_psychology_block += line + "\n"
                npc_psychology_block += "Используй имена NPC из этого списка — не придумывай новые.\n"

                # ──────────────────────────────
        # S.4.2: ReactionPriority — кто реагирует первым
        # ──────────────────────────────
        reaction_block = ""
        if context:
            reaction_order = context.get("reaction_order", [])
            forced = context.get("forced_first_speaker")
            if reaction_order:
                reaction_block = "ПРАВИЛО РЕАКЦИЙ (Python рассчитал — обязательно соблюдай):\n"
                if forced:
                    forced_npc = next(
                        (r for r in reaction_order if r["npc_id"] == forced), None
                    )
                    forced_name = forced_npc["npc_name"] if forced_npc else forced
                    reaction_block += f"- {forced_name} РЕАГИРУЕТ ПЕРВЫМ — он не может промолчать.\n"
                for r in reaction_order:
                    threshold = r.get("threshold", "")
                    triggers  = ", ".join(r.get("triggers", []))
                    if threshold == "must_react":
                        label = "обязан вмешаться"
                    elif threshold == "will_react":
                        label = "реагирует"
                    else:
                        label = "замечает"
                    reaction_block += (
                        f"- {r['npc_name']}: {label}"
                        + (f" (причина: {triggers})" if triggers else "")
                        + "\n"
                    )
                reaction_block += "Максимум 3 реплики NPC за ход. Остальные NPC молчат.\n"

        return f"""{scene_block}Текущая локация: {location}

{context_str}
Действия игроков:
{actions}

Результаты проверок правил:
{rules_str}

Что NPC уже сказали игроку (КОНТЕКСТ — не повторяй это, используй для согласованности своего описания):
{npc_str if npc_str else "NPC не говорили ничего"}

Физические действия NPC (для описания мира):
{npc_actions_str if npc_actions_str else "NPC не предпринимают видимых физических действий"}

Изменения в мире:
{world_str}

{physics_warnings}
{python_engines_block}
{npc_psychology_block}
{reaction_block}
Продолжи рассказ от лица Dungeon Master. Не говори за игроков.
Опиши мир от второго лица ("ты видишь...", "ты чувствуешь...").

ЖЁСТКИЕ ПРАВИЛА — нарушение недопустимо:
1. ПРОВАЛ броска = действие физически НЕ произошло. Свеча осталась на месте. Дверь не открылась. Запрещено описывать провалившееся действие как успешное или частично успешное.
2. УСПЕХ броска = действие произошло. Опиши конкретный результат. Объект исчез со стола. NPC отреагировал на факт.
3. Реплики NPC уже показаны игроку — НЕ повторяй их, НЕ пересказывай. Описывай мир ПОСЛЕ их слов.
4. Используй ТОЛЬКО объекты и NPC из блока "СОСТОЯНИЕ СЦЕНЫ". Если объект не указан — его не существует.
5. Если NPC уже ронял поднос/кружки в этой сцене — он не роняет снова. Найди другую реакцию.
6. Психологическое состояние NPC из блока "Психология" — это факт, не рекомендация. Если NPC в состоянии "fearful" — он ведёт себя как напуганный, не как обычный.
7. Сцена должна РАЗВИВАТЬСЯ. Если игрок несколько раз совершает агрессивные действия — напряжение растёт, обстановка меняется, NPC эскалируют реакции.
8. Максимум 3 предложения. Не задавай вопросов.
"""

    def _get_system_prompt(self) -> str:
        """
        Загружает системный промпт из Promt_AI.json.
        Fallback: встроенный промпт если файл недоступен.
        """
        tone = ""
        if getattr(settings, "hardcore_mode", False):
            tone = """

ТОН/РЕЖИМ: HARDCORE.
Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.
Не морализируй, не сглаживай и не "перевоспитывай" игрока.
Действия имеют последствия (социальные и физические), но без цензуры.
"""
        # Пробуем загрузить из файла
        try:
            from app.services.prompt_loader import load_system_prompt
            from app.core.config import settings as s
            file_prompt = load_system_prompt(s.system_prompt_file)
            if file_prompt and len(file_prompt) > 20:
                return file_prompt + tone
        except Exception:
            pass

        # Встроенный fallback
        return f"""ВАЖНО: Отвечай ТОЛЬКО на Русском языке. Никакого английского или китайского.
ВАЖНО: Не показывай размышления. Только финальный ответ.
ВАЖНО: Никогда не генерируй теги <|im_start|>, <|im_end|>, </|im_end|>, <|file_separator|>.

Ты — Мастер Подземелий D&D 5e. Твоя задача: описывать МИР и его реакцию на действия игрока.

КТО ЧТО ДЕЛАЕТ:
- DM (ты): описываешь физический мир, окружение, последствия, действия NPC без слов
- NPC агент (отдельно): генерирует реплики NPC — ты их НЕ повторяешь

ТВОИ ПРАВИЛА:
- Веди от второго лица: "ты видишь", "ты чувствуешь", "перед тобой"
- Описывай только то что есть в блоке "СОСТОЯНИЕ СЦЕНЫ" — не придумывай объекты
- Результаты бросков из блока "Результаты вычислений" — закон. ПРОВАЛ = действие не случилось
- NPC реагируют РАЗНООБРАЗНО. Люся не роняет поднос каждый раз. У неё есть другие реакции: замирает, отворачивается, прижимается к стене, шепчет молитву, трясущимися руками протирает стол
- Сцена развивается линейно: каждое агрессивное действие УВЕЛИЧИВАЕТ напряжение. Не сбрасывай его
- Краткость: 2-3 предложения. Без вопросов в конце.
- Согласованность с NPC: если NPC сказал "я молчу" — DM не пишет что NPC кричит{tone}"""

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
            params=GenerationParams(max_tokens=220),
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
                params=GenerationParams(max_tokens=220),
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
            buffer = ""  # буфер для поимки стоп-токенов разбитых между чанками
            tail_len = max(len(st) for st in _GEMMA_STOP_TOKENS)
            try:
                for token in provider.stream_tokens(
                    prompt=prompt,
                    params=GenerationParams(max_tokens=220),
                    system_prompt=system_prompt,
                ):
                    if not token:
                        continue
                    token_num += 1
                    buffer += token

                    # Проверяем буфер на стоп-токены
                    if _has_stop_token(buffer):
                        # Обрезаем по первому стоп-токену, отправляем чистый остаток
                        clean = _strip_stop_tokens(buffer)
                        if clean:
                            asyncio.run_coroutine_threadsafe(q.put(clean), loop)
                        # Стоп-токен — завершаем стриминг немедленно
                        asyncio.run_coroutine_threadsafe(q.put(None), loop)
                        return

                    # Держим хвост на случай стоп-токена разбитого между чанками
                    if len(buffer) > tail_len:
                        to_send = buffer[:-tail_len]
                        buffer  = buffer[-tail_len:]
                        if to_send and len(to_send) > 24:
                            step = 12
                            for i in range(0, len(to_send), step):
                                asyncio.run_coroutine_threadsafe(q.put(to_send[i:i+step]), loop)
                        elif to_send:
                            asyncio.run_coroutine_threadsafe(q.put(to_send), loop)

                # Конец стрима — отправляем остаток буфера
                if buffer:
                    clean = _strip_stop_tokens(buffer)
                    if clean:
                        asyncio.run_coroutine_threadsafe(q.put(clean), loop)

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
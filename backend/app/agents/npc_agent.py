# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\npc_agent.py
# -*- coding: utf-8 -*-
"""
NPC Agent - NPC Dialogue Generation
ФАЗА S.0: добавлен пространственный контекст в промпт каждого NPC.
Убран хардкод имён из _resolve_active_npcs — теперь generic.
Добавлен _filter_npc_response — постфильтр галлюцинаций.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, Capability, get_router
from app.services.llm.provider import GenerationParams
from app.services.llm.provider_manager import get_model_pool
from app.core.config import settings


from pydantic import BaseModel, Field, ConfigDict

class NPCVerbalizationResponse(BaseModel):
    speech: str = Field(default="", max_length=2000)
    action: str = Field(default="", max_length=500)

    model_config = ConfigDict(extra="ignore")


class NpcAgent:
    """
    NPC agent with automatic model selection.
    Phase 3A: психология NPC через system_prompt из build_npc_prompt().
    Phase S.0: пространственный контекст сцены в каждом NPC промпте.
    """

    def __init__(self, router: Optional[ModelRouter] = None) -> None:
        self._router = router
        self._npc_context: dict = {}

    @property
    def router(self) -> ModelRouter:
        if self._router is None:
            self._router = get_router()
        return self._router

    def _get_capability_for_npc(self, npc_importance: Optional[str] = None) -> Capability:
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
        try:
            return self.react(location, actions, npc_memory, shared_context, npc_importance)
        except Exception:
            return self._fallback_react(location, actions, npc_memory)

    def speak_as(self, npc_name: str, context: str, player_action: str) -> str:
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
                params=GenerationParams(max_tokens=180),
            )
        except Exception as e:
            return f"{npc_name} молча смотрит на тебя."

    # ─────────────────────────────────────────────────────────────────────────
    # ФАЗА 3A: извлечение npc_contexts
    # ─────────────────────────────────────────────────────────────────────────

    def _get_phase3a_npc_contexts(self, shared_context: Optional[dict]) -> list:
        if not shared_context:
            return []
        top_level = shared_context.get("npc_contexts")
        if top_level:
            return top_level
        python_engines = shared_context.get("python_engines", {})
        if not isinstance(python_engines, dict):
            return []
        return python_engines.get("npc_contexts", [])

    # ─────────────────────────────────────────────────────────────────────────
    # ФАЗА S.0: пространственный блок для NPC промпта
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_npc_scene_block(
        npc_id: str,
        npc_name: str,
        scene_state: Optional[dict],
    ) -> str:
        """
        Строит пространственный блок для промпта конкретного NPC.
        Использует SceneStateManager.build_npc_context_block() если SceneState доступен.
        Fallback: пустая строка (не ломает систему).

        Этот блок помещается ПЕРВЫМ в system_prompt NPC — до психологии.
        """
        if not scene_state:
            return ""
        try:
            from app.services.scene_state_manager import SceneStateManager
            return SceneStateManager.build_npc_context_block(scene_state, npc_id, npc_name)
        except Exception:
            return ""

    # ─────────────────────────────────────────────────────────────────────────
    # ФАЗА S.0: постфильтр галлюцинаций
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _filter_npc_response(
        speech: str,
        action: str,
        trust_delta: int,
        stress_delta: int,
        speaker_npc_id: str,
        target_npc_id: Optional[str],
    ) -> tuple[str, str, int, int]:
        """
        S.0: Постфильтр — если игрок обращался к конкретному NPC,
        а модель сгенерировала ответ от другого персонажа — глушим.

        Принцип: Python решает кто молчит, LLM только озвучивает.

        Аргументы:
            speaker_npc_id — id NPC который сейчас обрабатывается
            target_npc_id  — id NPC к которому обращался игрок (из SceneState)

        Возвращает (speech, action, trust_delta, stress_delta) — либо оригинал,
        либо "молчит" если фильтр сработал.
        """
        # Если target не задан — все могут отвечать (broadcast или нет цели)
        if not target_npc_id:
            return speech, action, trust_delta, stress_delta

        # Если этот NPC является целью — пропускаем без изменений
        if speaker_npc_id == target_npc_id:
            return speech, action, trust_delta, stress_delta

        # NPC не является целью — молчит
        # trust/stress не меняются (игрок не взаимодействовал с ним)
        return "...", "молчит, разговор не к нему", 0, 0

    # ─────────────────────────────────────────────────────────────────────────
    # ФАЗА 3A: построение промпта для конкретного NPC
    # ─────────────────────────────────────────────────────────────────────────

    def _build_phase3a_prompt(
        self,
        npc_context: dict,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
        scene_state: Optional[dict] = None,
        working_memory: Optional[list[dict]] = None,
    ) -> tuple[str, str]:
        """
        УСИЛЕННАЯ версия для Working Memory (R1.2).
        Специально заточено под Gemma-12b-q4_k_m — модель теперь почти не плывёт по фактам.
        """
        npc_id   = npc_context.get("npc_id", "")
        npc_name = npc_context.get("npc_name", "NPC")

        # ── S.0: пространственный блок — ПЕРВЫМ в system_prompt ──────────────
        scene_block = self._build_npc_scene_block(npc_id, npc_name, scene_state)

        # ── Основной system_prompt из Phase 3A ────────────────────────────────
        base_system = npc_context.get("system_prompt", self._get_system_prompt())

        if scene_block:
            system_prompt = f"{scene_block}  {base_system}"
        else:
            system_prompt = base_system

        # Hardcore режим
        if getattr(settings, "hardcore_mode", True):
            system_prompt += """

HARDCORE: разрешены грубость, мат, угрозы, мрачные детали, жестокость.
Не морализируй и не смягчай речь. Не "воспитывай" игрока."""

        # ── Working Memory — САМЫЙ СИЛЬНЫЙ БЛОК (главное изменение) ───────────
        wm_str = ""
        if working_memory:
            wm_str = "  === ТВОЯ ПАМЯТЬ — ЖЕЛЕЗНЫЕ ФАКТЫ === "
            wm_str += "Ты обязан помнить ВСЁ, что говорил раньше. Это не может измениться.  "

            # Последние 10 событий (больше чем раньше), в обратном порядке — самое свежее сверху
            for entry in reversed(working_memory[-10:]):
                actor   = entry.get("actor", "?")
                content = entry.get("content", entry.get("action", "?"))
                if actor == npc_name:
                    wm_str += f"ТЫ РАНЬШЕ СКАЗАЛ: «{content}» "
                else:
                    wm_str += f"{actor}: «{content}» "

            wm_str += "ПРАВИЛО №1: Никогда не противоречи своим предыдущим словам выше."
            wm_str += "ПРАВИЛО №2: Если игрок пытается тебя запутать, изменить цену, количество или условия — жёстко поправляй его и повторяй ТОЧНО то, что ТЫ говорил раньше."
            wm_str += "ПРАВИЛО №3: Цифры и обещания — это святое. Не округляй, не меняй, не забывай."

        # ── Сессионная память (оставляем как было) ───────────────────────────
        recent_session = npc_context.get("recent_session", [])
        session_str = ""
        if recent_session:
            session_str = " Последнее что ты помнишь из этой сессии: "
            session_str += " ".join(f"  — {e}" for e in recent_session[-2:])
            session_str += " "

        action_lines = " ".join(f"- {a.player_name}: {a.action}" for a in actions)

        # S.0: если игрок НЕ обращается к этому NPC — напоминаем явно
        target_npc_id = scene_state.get("player_target_npc") if scene_state else None
        if target_npc_id and target_npc_id != npc_id:
            target_npc_name = scene_state.get("player_target_npc_name", "другому персонажу")
            address_reminder = (
                f" Игрок обращается к {target_npc_name}, НЕ к тебе. "
                f"Ответь: \"...\" (молчишь). "
            )
        else:
            address_reminder = ""

        # ── Финальный user_prompt ─────────────────────────────────────────────
        user_prompt = (
            f"{wm_str}"                     # ← теперь идёт САМЫМ ПЕРВЫМ
            f"{session_str}"
            f"Действия игроков: {action_lines} "
            f"{address_reminder} "
            f"Ответь кратко, от первого лица (1-2 предложения). "
            f"Используй строго валидный JSON. В числовых полях НЕ пиши знак +, только цифры или минус."
        )

        return system_prompt, user_prompt

    # ─────────────────────────────────────────────────────────────────────────
    # Стоп-токены и утилиты парсинга
    # ─────────────────────────────────────────────────────────────────────────

    _GEMMA_STOP_TOKENS = [
        "<|file_separator|>", "<|end_of_turn|>", "<end_of_turn>",
        "<|im_end|>", "<|im_start|>", "</|im_start|>",
        "</s>", "<|endoftext|>", "<|file_end|>", "<|file_sep|>",
    ]

    @staticmethod
    def _strip_stop_tokens(text: str) -> str:
        for token in NpcAgent._GEMMA_STOP_TOKENS:
            idx = text.find(token)
            if idx != -1:
                text = text[:idx]
        return text.strip()

    @staticmethod
    def _fix_json_numbers(text: str) -> str:
        import re
        return re.sub(r'(:\s*)\+(\d+)', r'\1\2', text)

    @staticmethod
    def _try_repair_json(text: str) -> dict:
        """Простой regex-ремонт JSON для старого парсера (_parse_npc_response)."""
        import re
        result: dict = {}

        # Извлекаем speech и action
        for field, pattern in [
            ("speech", r'"speech"\s*:\s*"((?:[^"\\]|\\.)*)"'),
            ("action", r'"action"\s*:\s*"((?:[^"\\]|\\.)*)"'),
        ]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                result[field] = m.group(1)

        # Извлекаем дельты только для старого парсера
        for field in ("trust_change", "stress_change"):
            m = re.search(rf'"{field}"\s*:\s*([+-]?\d+)', text)
            if m:
                result[field] = int(m.group(1))

        return result

    @staticmethod
    def _parse_npc_response(resp: str) -> tuple[str, str, int, int]:
        """Парсит полный ответ NPC со всеми дельтами (старый путь)."""
        clean = NpcAgent._strip_stop_tokens(resp.strip())

        # Удаление markdown fences
        if clean.startswith("```"):
            parts = clean.split("```")
            if len(parts) >= 2:
                inner = parts[1]
                if inner.startswith("json"):
                    inner = inner[4:].strip()
                else:
                    inner = inner.strip()
                clean = NpcAgent._strip_stop_tokens(inner)

        clean_fixed = NpcAgent._fix_json_numbers(clean)

        # Попытка 1: нормальный json.loads
        try:
            parsed = json.loads(clean_fixed)
            speech = str(parsed.get("speech", "")).strip()
            action = str(parsed.get("action", "")).strip()
            trust_delta = int(parsed.get("trust_change", 0))
            stress_delta = int(parsed.get("stress_change", 0))

            if not speech:
                speech = NpcAgent._strip_stop_tokens(resp)

            return speech, action, trust_delta, stress_delta
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        # Попытка 2: regex repair
        recovered = NpcAgent._try_repair_json(clean_fixed)
        if recovered.get("speech"):
            return (
                str(recovered.get("speech", "")).strip(),
                str(recovered.get("action", "")).strip(),
                int(recovered.get("trust_change", 0)),
                int(recovered.get("stress_change", 0)),
            )

        # Грубый fallback
        return NpcAgent._strip_stop_tokens(resp), "", 0, 0

    @staticmethod
    def _parse_r3_response(resp: str) -> tuple[str, str]:
        """
        R3-путь: парсит ответ через Pydantic-модель NPCVerbalizationResponse.
        
        Особенности:
        - trust_change и stress_change полностью игнорируются (даже если LLM их выводит)
        - Возвращает строго только (speech, action)
        - Приоритет: Pydantic → regex fallback → грубый fallback
        """
        # 1. Базовая очистка
        clean = NpcAgent._strip_stop_tokens(resp.strip())

        # 2. Удаление markdown-кода (```json ... ```)
        if clean.startswith("```"):
            parts = clean.split("```")
            if len(parts) >= 2:
                inner = parts[1]
                if inner.startswith("json"):
                    inner = inner[4:].strip()
                else:
                    inner = inner.strip()
                clean = NpcAgent._strip_stop_tokens(inner)

        # 3. Исправление распространённых ошибок JSON от LLM
        clean = NpcAgent._fix_json_numbers(clean)

        # 4. Попытка 1: строгий парсинг через Pydantic
        try:
            parsed = NPCVerbalizationResponse.model_validate_json(clean)
            return parsed.speech.strip(), parsed.action.strip()
        except Exception:
            pass

        # 5. Попытка 2: regex fallback (только speech и action)
        import re
        speech_match = re.search(
            r'"speech"\s*:\s*"((?:[^"\\]|\\.)*)"', clean, re.DOTALL
        )
        action_match = re.search(
            r'"action"\s*:\s*"((?:[^"\\]|\\.)*)"', clean, re.DOTALL
        )

        speech = speech_match.group(1).strip() if speech_match else ""
        action = action_match.group(1).strip() if action_match else ""

        # 6. Финальный fallback
        if not speech:
            speech = NpcAgent._strip_stop_tokens(resp)

        return speech, action

    # ─────────────────────────────────────────────────────────────────────────
    # ФАЗА S.0: _resolve_active_npcs — generic версия без хардкода имён
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_sleeping(ctx: dict, scene_state: Optional[dict]) -> bool:
        """Проверяет спит ли NPC по scene_state.npc_positions."""
        if not scene_state:
            return False
        npc_id = ctx.get("npc_id", "")
        pos = scene_state.get("npc_positions", {}).get(npc_id, {})
        activity = pos.get("activity", "").lower()
        return activity in {"sleeping", "спит", "sleep"}

    @staticmethod
    def _resolve_active_npcs(
        actions: list[PlayerAction],
        sorted_contexts: list[dict],
        scene_state: Optional[dict] = None,
    ) -> list[dict]:
        """
        Определяет каких NPC нужно вызывать на этом ходу.

        Порядок приоритетов (строго сверху вниз):
          0. Спящие NPC исключаются полностью (не могут говорить)
          1. Тихое/физическое действие → никто не отвечает
          2. S.0: player_target_npc задан Python → только этот NPC
          3. Broadcast-ключевые слова → все бодрствующие NPC
          4. Имена NPC в тексте → только упомянутые NPC
          5. Ролевые ключевые слова → NPC по роли
          6. Fallback → первый по tier среди бодрствующих
        """
        if not sorted_contexts:
            return []

        # ── Приоритет 0: убираем спящих ──────────────────────────────────────
        sorted_contexts = [
            ctx for ctx in sorted_contexts
            if not NpcAgent._is_sleeping(ctx, scene_state)
        ]

        if not sorted_contexts:
            return []

        full_text = " ".join(
            getattr(a, "action", "") for a in actions
        ).lower()

        # ── Приоритет 1: Тихое/физическое действие — никто не реагирует ─────
        # Проверяется ДО target, иначе sticky-target глушит этот фильтр.
        silent_keywords = [
            "осматриваюсь", "смотрю вокруг", "оглядываюсь", "изучаю комнату",
            "читаю", "жду молча", "сижу тихо", "наблюдаю",
            "осматриваю комнату", "тихо подхожу", "крадусь",
            "отношу", "кладу", "ложу", "несу",
        ]
        if any(kw in full_text for kw in silent_keywords):
            return []

        # ── Приоритет 2: Broadcast ────────────────────────────────────────────
        broadcast_keywords = [
            "всем", "господа", "люди", "слушайте",
            "кричу в зал", "обращаюсь к залу", "обращаюсь ко всем",
            "достаю оружие", "атакую всех", "на виду у всех",
            "поднимаю тост", "объявляю", "говорю, чтобы все",
        ]
        if any(kw in full_text for kw in broadcast_keywords):
            return sorted_contexts    

        # ── Приоритет 3: S.0 — target задан Python ───────────────────────────
        # Абсолютный приоритет среди речевых действий.
        if scene_state:
            target_id = scene_state.get("player_target_npc")
            if target_id:
                for ctx in sorted_contexts:
                    if ctx.get("npc_id") == target_id:
                        return [ctx]
                return []

        # ── Приоритет 4: Нет цели — молчание ─────────────────────────────────
        # Если Python не определил цель и это не broadcast —
        # DM опишет сцену, но NPC не говорят.
        # Fallback: первый по tier отвечает только на общую реплику без объекта.
        _OBJECT_HINTS = [
            "стол", "стул", "дверь", "окно", "бочк", "ящик",
            "огонь", "свеч", "пол", "стен", "потол",
        ]
        if any(hint in full_text for hint in _OBJECT_HINTS):
            return []

        # Общая реплика (приветствие, вопрос в воздух) — отвечает первый по tier
        return [sorted_contexts[0]]

    # ─────────────────────────────────────────────────────────────────────────
    # _build_prompt (fallback без Phase 3A)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
        shared_context: Optional[dict] = None,
    ) -> str:
        action_str = "".join(f"- {a.player_name}: {a.action}" for a in actions)
        memory_str = ""
        if npc_memory:
            last = npc_memory[-1].get("note") if isinstance(npc_memory[-1], dict) else None
            if last:
                memory_str += f"Контекст NPC: {last}"
        if shared_context:
            recent = shared_context.get("recent_memory", [])
            if recent:
                last_event = recent[-1]
                event_type = last_event.get("type", "event")
                memory_str += f"Недавнее событие: {event_type}"

        return f"""Локация: {location}
Действия игроков:
{action_str}
{memory_str}

Сгенерируй реакцию NPC на действия игроков.
Опиши диалоги и поведение персонажей.
Будь краток (1-2 предложения)."""

    def _get_system_prompt(self) -> str:
        tone = ""
        if getattr(settings, "hardcore_mode", False):
            tone = """

HARDCORE: разрешены грубость, мат, угрозы, мрачные детали, жестокость.
Не морализируй и не смягчай речь игрока/сцены. Не "воспитывай" игрока.
"""
        return f"""Ты - NPC в D&D 5e кампании.
Генерируй реалистичные диалоги и реакции персонажей.
Отвечай от первого лица (Я/мне/меня).
Учитывай контекст ситуации и отношения с игроками.
Будь краток и атмосферен (1-2 предложения).
Не повторяй дословно фразы игрока, реагируй по смыслу.
Не добавляй мета-пояснений.{tone}"""

    def _fallback_react(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
    ) -> dict:
        reactions = []
        memory_lines = []
        for action in actions:
            reactions.append(f"NPC в {location} реагируют на '{action.action}'.")
            memory_lines.append(f"{action.player_name}: {action.action}")
        if npc_memory:
            last = npc_memory[-1].get("note") if isinstance(npc_memory[-1], dict) else None
            if last:
                reactions.append(f"NPC помнят: {last}")
        return {
            "npc_reactions":      reactions,
            "npc_memory_updates": memory_lines,
            "npc_actions":        [],
            "npc_state_updates":  [],
            "npc_inner_thoughts": [],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # R3.1 — новый путь через VerbalizationContext
    # Вызывается вместо run() когда DecisionHub уже принял решение.
    # LLM получает только VerbalizationContext — не shared_context.
    # ─────────────────────────────────────────────────────────────────────────

    def run_from_context(
        self,
        contexts:    list,
        scene_state: Optional[dict] = None,
    ) -> dict:
        """
        R3-путь: NPC agent получает только VerbalizationContext.
        MASS NPC → шаблоны без LLM.
        Далёкие NPC → lazy verbalization, пропускаем.
        Dynamic token budget по intent.
        """
        from app.services.npc.verbalization_context import (
            VerbalizationContext,
            build_npc_prompt_from_context,
            get_mass_template,
            get_token_budget,
            should_verbalize,
            Intent,
        )
        from app.services.npc.npc_state import NPCTier

        all_reactions     = []
        all_actions       = []
        npc_state_updates = []

        for ctx in contexts:
            if not isinstance(ctx, VerbalizationContext):
                continue

            # IDLE/OBSERVE — молчат, без LLM
            if ctx.intent in (Intent.IDLE.value, Intent.OBSERVE.value):
                continue

            # Lazy verbalization — далёкие NPC не вербализуются
            if scene_state and not should_verbalize(
                ctx.npc_id, scene_state, ctx.intent
            ):
                continue

            # MASS NPC — шаблоны без LLM
            if ctx.tier == NPCTier.MASS.value:
                template = get_mass_template(ctx)
                if template:
                    all_actions.append(template)
                continue

            # MAJOR / MINOR — LLM с dynamic token budget
            max_tokens = get_token_budget(ctx.tier, ctx.intent)
            if max_tokens == 0:
                continue

            sys_p, usr_p = build_npc_prompt_from_context(ctx)

            try:
                resp = self.router.request(
                    capability=Capability.DIALOGUE,
                    prompt=usr_p,
                    system_prompt=sys_p,
                    params=GenerationParams(max_tokens=max_tokens),
                )
                # R3-путь: только speech и action — дельты не запрашиваем и не принимаем
                speech, action = self._parse_r3_response(resp)
                if action and action not in ("молчит, разговор не к нему", ""):
                    all_actions.append(f"{ctx.npc_name}: {action}")

            except Exception as e:
                logger.error(f"[VERBALIZE] LLM failed для {ctx.npc_id}: {e}")
                # Гарантированный fallback — NPC не исчезает из сцены
                from app.services.npc.verbalization_context import get_mass_template
                fallback = get_mass_template(ctx)
                if fallback:
                    all_actions.append(fallback)
                else:
                    # Последний резерв: intent как действие
                    all_actions.append(f"{ctx.npc_name} {ctx.intent}.")

        return {
            "npc_reactions":      all_reactions,
            "npc_actions":        all_actions,
            "npc_memory_updates": [],
            "npc_state_updates":  [],  # R3-путь: состояние меняет только StateApplicator
        }      

    # ─────────────────────────────────────────────────────────────────────────
    # react — основной метод
    # ─────────────────────────────────────────────────────────────────────────

    def react(
        self,
        location: str,
        actions: list[PlayerAction],
        npc_memory: Optional[list[dict]] = None,
        shared_context: Optional[dict] = None,
        npc_importance: str = "mass",
    ) -> dict:
        """
        Генерирует реакции NPC.

        S.0: передаёт scene_state в _build_phase3a_prompt и _resolve_active_npcs.
             Применяет _filter_npc_response для проверки что нужный NPC отвечает.
        """
        npc_contexts   = self._get_phase3a_npc_contexts(shared_context)
        recent_session = shared_context.get("recent_session", []) if shared_context else []

        scene_state   = shared_context.get("scene_state") if shared_context else None
        target_npc_id = (scene_state or {}).get("player_target_npc")


        # S.0: получаем SceneState для пространственного контекста
        scene_state    = shared_context.get("scene_state") if shared_context else None
        target_npc_id  = (scene_state or {}).get("player_target_npc")
        working_memory = shared_context.get("working_memory", []) if shared_context else []

        if npc_contexts:
            # ── ПУТЬ ФАЗА 3A: есть NPC с психологией ────────────────────────
            tier_order = {"major": 0, "minor": 1, "mass": 2}
            sorted_contexts = sorted(
                npc_contexts,
                key=lambda c: tier_order.get(c.get("tier", "mass"), 2)
            )

            # S.0: передаём scene_state в _resolve_active_npcs
            active_contexts = self._resolve_active_npcs(
                actions, sorted_contexts, scene_state=scene_state
            )

            if not active_contexts:
                return {
                    "npc_reactions":      [],
                    "npc_actions":        [],
                    "npc_memory_updates": [],
                    "npc_state_updates":  [],
                    "model":              {"key": "none"},
                    "npc_inner_thoughts": [
                        {"npc": ctx["npc_name"], "thought": ctx.get("inner_thought", "")}
                        for ctx in npc_contexts
                    ],
                }

            primary_tier = active_contexts[0].get("tier", "minor")
            capability   = self._get_capability_for_npc(
                "major" if primary_tier == "major" else npc_importance
            )
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

            all_reactions    = []
            all_actions      = []
            all_mem_updates  = []
            npc_state_updates = []

            # R3-путь: если есть verbalization_ctx — используем run_from_context
            r3_contexts = [
                ctx["verbalization_ctx"]
                for ctx in active_contexts
                if "verbalization_ctx" in ctx
            ]
            if r3_contexts:
                scene_state_for_r3 = shared_context.get("scene_state") if shared_context else None
                return self.run_from_context(r3_contexts, scene_state=scene_state_for_r3)
                
            for npc_ctx in active_contexts:
                npc_name    = npc_ctx.get("npc_name", "NPC")
                npc_id      = npc_ctx.get("npc_id", "")
                npc_tier    = npc_ctx.get("tier", "minor")
                npc_capability = self._get_capability_for_npc(
                    "major" if npc_tier == "major" else "mass"
                )

                npc_ctx_with_session = {**npc_ctx, "recent_session": recent_session}

                # R1.C1: передаём scene_state и working_memory в _build_phase3a_prompt
                sys_p, usr_p = self._build_phase3a_prompt(
                    npc_ctx_with_session, actions, npc_memory,
                    scene_state=scene_state,
                    working_memory=working_memory,
                )

                try:
                    resp = self.router.request(
                        capability=npc_capability,
                        prompt=usr_p,
                        system_prompt=sys_p,
                        params=GenerationParams(max_tokens=120),
                    )

                    speech, action, trust_delta, stress_delta = self._parse_npc_response(resp)

                    # S.0: постфильтр — если модель сгенерировала ответ не от того NPC
                    speech, action, trust_delta, stress_delta = self._filter_npc_response(
                        speech, action, trust_delta, stress_delta,
                        speaker_npc_id=npc_id,
                        target_npc_id=target_npc_id,
                    )

                    # Молчащий NPC не добавляется в реакции (только "..." не нужен игроку)
                    if speech and speech != "...":
                        all_reactions.append(f"{npc_name}: {speech}")
                    if action and action != "молчит, разговор не к нему":
                        all_actions.append(f"{npc_name}: {action}")

                    all_mem_updates.append(f"{npc_name}: {usr_p}")

                    if (trust_delta != 0 or stress_delta != 0) and npc_id:
                        npc_state_updates.append({
                            "npc_id":       npc_id,
                            "npc_name":     npc_name,
                            "trust_delta":  round(trust_delta / 100.0, 4),
                            "stress_delta": stress_delta,
                        })

                except Exception:
                    all_reactions.append(f"{npc_name} молча наблюдает.")

            return {
                "npc_reactions":      all_reactions,
                "npc_actions":        all_actions,
                "npc_memory_updates": all_mem_updates,
                "npc_state_updates":  npc_state_updates,
                "model":              model_meta,
                "npc_inner_thoughts": [
                    {"npc": ctx["npc_name"], "thought": ctx.get("inner_thought", "")}
                    for ctx in npc_contexts
                ],
            }

        else:
            # ── ПУТЬ ДЕФОЛТ: нет Phase 3A данных ────────────────────────────
            capability    = self._get_capability_for_npc(npc_importance)
            system_prompt = self._get_system_prompt()
            user_prompt   = self._build_prompt(location, actions, npc_memory, shared_context)

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
                    params=GenerationParams(max_tokens=180),
                )
                return {
                    "npc_reactions":      [response],
                    "npc_actions":        [],
                    "npc_memory_updates": [user_prompt],
                    "npc_state_updates":  [],
                    "model":              model_meta,
                    "npc_inner_thoughts": [],
                }
            except Exception:
                return self._fallback_react(location, actions, npc_memory)
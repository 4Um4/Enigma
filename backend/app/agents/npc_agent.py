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
from app.services.verbalization.verbalization_context import VerbalizationContext  # R3 path

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

    def _sync_request(self, *args, **kwargs):
        router = self._router if self._router else get_router()
        capability = kwargs.get("capability", args[0] if args else "dialogue")
        prompt = kwargs.get("prompt", args[1] if len(args) > 1 else "")
        params = kwargs.get("params", None)
        system_prompt = kwargs.get("system_prompt", None)
        print(f"[SYNC_REQ] capability={capability}, prompt_len={len(prompt)}")
        try:
            result = router._request_sync(capability, prompt, params, system_prompt)
            print(f"[SYNC_REQ] OK, result_len={len(result) if result else 0}")
            return result
        except Exception as e:
            print(f"[SYNC_REQ] FAILED: {type(e).__name__}: {e}")
            raise

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
        # R3-маршрутизация: если есть VerbalizationContext — минуем старый react()
        if shared_context:
            npc_contexts = shared_context.get("npc_contexts", [])
            r3_contexts = [
                ctx["verbalization_ctx"]
                for ctx in npc_contexts
                if isinstance(ctx.get("verbalization_ctx"), VerbalizationContext)
            ]
            if r3_contexts:
                scene_state = shared_context.get("scene_state")
                return self.run_from_context(r3_contexts, scene_state)

        # Fallback: R3 path недоступен — возвращаем пустой результат.
        # НЕ удалять: защита от случаев когда VerbalizationContext не собран.
        print("[WARN] NPC agent: R3 path unavailable, using fallback")
        return {
            "npc_reactions": [],
            "npc_actions": [],
            "npc_memory_updates": [],
            "npc_state_updates": [],
        }

    def speak_as(self, npc_name: str, context: str, player_action: str) -> str:
        prompt = f"""Ситуация: {context}
Действие игрока: {player_action}

Ответь от лица {npc_name}."""

        system_prompt = f"""Ты - {npc_name}, персонаж D&D 5e кампании.
Отвечай от первого лица, как персонаж.
Будь аутентичен: учитывай личность, мотивацию, настроение.
Не описывай действия - только говори."""

        try:
            return self._sync_request(
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
        from app.services.verbalization.verbalization_context import (
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
                print(f"[VERBALIZE-DROP] {getattr(ctx, 'npc_id', ctx)}: not VerbalizationContext, type={type(ctx).__name__}")
                continue

            # IDLE/OBSERVE — молчат, без LLM
            if ctx.intent in (Intent.IDLE.value, Intent.OBSERVE.value):
                print(f"[VERBALIZE-DROP] {ctx.npc_id}: intent={ctx.intent} (silent)")
                continue

            # Lazy verbalization — далёкие NPC не вербализуются
            if scene_state and not should_verbalize(
                ctx.npc_id, scene_state, ctx.intent
            ):
                # Диагностика: почему should_verbalize вернул False?
                _dist = scene_state.get("player_distances", {}).get(ctx.npc_id, "??")
                _tier = ctx.tier
                print(f"[VERBALIZE-DROP] {ctx.npc_id}: should_verbalize=False, dist={_dist}, tier={_tier}, intent={ctx.intent}")
                continue

            # MASS NPC — шаблоны без LLM
            if ctx.tier == NPCTier.MASS.value:
                template = get_mass_template(ctx)
                if template:
                    all_actions.append(template)
                print(f"[VERBALIZE-MASS] {ctx.npc_id}: template response")
                continue

            # MAJOR / MINOR — LLM с dynamic token budget
            max_tokens = get_token_budget(ctx.tier, ctx.intent)
            if max_tokens == 0:
                print(f"[VERBALIZE-DROP] {ctx.npc_id}: token_budget=0, tier={ctx.tier}, intent={ctx.intent}")
                continue

            print(f"[VERBALIZE] Building prompt for {ctx.npc_id}, tier={ctx.tier}, intent={ctx.intent}, tokens={max_tokens}")
            try:
                sys_p, usr_p = build_npc_prompt_from_context(ctx)
                print(f"[VERBALIZE] Prompt built OK, sys_p len={len(sys_p)}, usr_p len={len(usr_p)}")
            except Exception as e:
                print(f"[VERBALIZE] build_npc_prompt_from_context failed for {ctx.npc_id}: {e}")
                continue

            try:
                resp = self._sync_request(
                    capability=Capability.DIALOGUE,
                    prompt=usr_p,
                    system_prompt=sys_p,
                    params=GenerationParams(max_tokens=max_tokens),
                )
                print(f"[VERBALIZE] LLM response for {ctx.npc_id}: {resp[:50]}...")
                # R3-путь: только speech и action — дельты не запрашиваем и не принимаем
                speech, action = self._parse_r3_response(resp)
                print(f"[VERBALIZE] Parsed: speech='{speech[:30]}', action='{action[:30]}'")
                
                # Speech — реплика NPC (основная)
                if speech and speech not in ("...", ""):
                    line = f"{ctx.npc_name}: {speech}"
                    all_reactions.append(line)
                
                # Action — физическое действие (дополнительно)
                if action and action not in ("молчит, разговор не к нему", ""):
                    line = f"{ctx.npc_name}: {action}"
                    all_actions.append(line)

            except Exception as e:
                import traceback
                print(f"[VERBALIZE] LLM failed для {ctx.npc_id}: {e}")
                print(f"[VERBALIZE] Traceback: {traceback.format_exc()}")
                # Гарантированный fallback — NPC не исчезает из сцены
                from app.services.verbalization.verbalization_context import get_mass_template
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


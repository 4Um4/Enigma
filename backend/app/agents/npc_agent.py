# -*- coding: utf-8 -*-
"""
NPC Agent - NPC Dialogue Generation
ФАЗА S.0: добавлен пространственный контекст в промпт каждого NPC.
Убран хардкод имён из _resolve_active_npcs — теперь generic.
Добавлен _filter_npc_response — постфильтр галлюцинаций.
"""

import json
from typing import Optional

from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, Capability, get_router
from app.services.llm.provider import GenerationParams
from app.services.llm.provider_manager import get_model_pool
from app.core.config import settings





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
    ) -> tuple[str, str]:
        """
        Строит (system_prompt, user_prompt) из Phase 3A данных NPC.

        S.0: в начало system_prompt добавляется пространственный блок —
        NPC знает где стоит игрок, на каком расстоянии и к нему ли обращаются.
        """
        npc_id   = npc_context.get("npc_id", "")
        npc_name = npc_context.get("npc_name", "NPC")

        # ── S.0: пространственный блок — ПЕРВЫМ в system_prompt ──────────────
        scene_block = self._build_npc_scene_block(npc_id, npc_name, scene_state)

        # ── Основной system_prompt из Phase 3A ────────────────────────────────
        base_system = npc_context.get("system_prompt", self._get_system_prompt())

        # Собираем итоговый system_prompt: сцена → психология
        if scene_block:
            system_prompt = f"{scene_block}\n\n{base_system}"
        else:
            system_prompt = base_system

        # Hardcore режим
        if getattr(settings, "hardcore_mode", False):
            system_prompt += """

HARDCORE: разрешены грубость, мат, угрозы, мрачные детали, жестокость.
Не морализируй и не смягчай речь. Не "воспитывай" игрока."""

        # ── User prompt с сессионной памятью ──────────────────────────────────
        recent_session = npc_context.get("recent_session", [])
        session_str = ""
        if recent_session:
            session_str = "\nПоследнее что ты помнишь из этой сессии:\n"
            session_str += "\n".join(f"  — {e}" for e in recent_session[-2:])
            session_str += "\n"

        action_lines = "\n".join(f"- {a.player_name}: {a.action}" for a in actions)

        # S.0: если игрок НЕ обращается к этому NPC — напоминаем явно
        target_npc_id = scene_state.get("player_target_npc") if scene_state else None
        if target_npc_id and target_npc_id != npc_id:
            target_npc_name = scene_state.get("player_target_npc_name", "другому персонажу")
            address_reminder = (
                f"\nИгрок обращается к {target_npc_name}, НЕ к тебе. "
                f"Ответь: \"...\" (молчишь).\n"
            )
        else:
            address_reminder = ""

        user_prompt = (
            f"{session_str}"
            f"Действия игроков:\n{action_lines}\n"
            f"{address_reminder}\n"
            f"Ответь кратко, от первого лица (1-2 предложения).\n"
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
        import re
        result = {}
        for field, pattern in [
            ("speech", r'"speech"\s*:\s*"((?:[^"\\]|\\.)*)"'),
            ("action", r'"action"\s*:\s*"((?:[^"\\]|\\.)*)"'),
        ]:
            m = re.search(pattern, text)
            if m:
                result[field] = m.group(1)
        for field in ("trust_change", "stress_change"):
            m = re.search(rf'"{field}"\s*:\s*([+-]?\d+)', text)
            if m:
                result[field] = int(m.group(1))
        return result

    @staticmethod
    def _parse_npc_response(resp: str) -> tuple[str, str, int, int]:
        clean = NpcAgent._strip_stop_tokens(resp.strip())

        if clean.startswith("```"):
            parts = clean.split("```")
            if len(parts) >= 2:
                inner = parts[1]
                if inner.startswith("json"):
                    inner = inner[4:]
                clean = NpcAgent._strip_stop_tokens(inner.strip())

        clean_fixed = NpcAgent._fix_json_numbers(clean)

        try:
            parsed       = json.loads(clean_fixed)
            speech       = str(parsed.get("speech", "")).strip()
            action       = str(parsed.get("action", "")).strip()
            trust_delta  = int(parsed.get("trust_change", 0))
            stress_delta = int(parsed.get("stress_change", 0))
            if not speech:
                speech = NpcAgent._strip_stop_tokens(resp)
            return speech, action, trust_delta, stress_delta
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        recovered = NpcAgent._try_repair_json(clean_fixed)
        if recovered.get("speech"):
            return (
                str(recovered["speech"]).strip(),
                str(recovered.get("action", "")).strip(),
                int(recovered.get("trust_change", 0)),
                int(recovered.get("stress_change", 0)),
            )

        return NpcAgent._strip_stop_tokens(resp), "", 0, 0

    # ─────────────────────────────────────────────────────────────────────────
    # ФАЗА S.0: _resolve_active_npcs — generic версия без хардкода имён
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_active_npcs(
        actions: list[PlayerAction],
        sorted_contexts: list[dict],
        scene_state: Optional[dict] = None,
    ) -> list[dict]:
        """
        Определяет каких NPC нужно вызывать на этом ходу.

        S.0: Если SceneState содержит player_target_npc — используем его
        как приоритетный источник истины (Python посчитал → LLM озвучивает).

        Три сценария:
        1. SceneState.player_target_npc задан → только этот NPC отвечает
        2. Текст содержит broadcast-ключевые слова → все NPC реагируют
        3. Тихое действие (осмотр) → никто не отвечает
        4. Общее действие → первый по tier

        Generic: имена берутся из npc_context["npc_name"], не хардкодятся.
        """
        if not sorted_contexts:
            return []

        full_text = " ".join(
            getattr(a, "action", "") for a in actions
        ).lower()

        # ── Сценарий S.0: target задан Python (приоритет) ────────────────────
        if scene_state:
            target_id = scene_state.get("player_target_npc")
            if target_id:
                # Python уже определил цель — возвращаем только этого NPC
                for ctx in sorted_contexts:
                    if ctx.get("npc_id") == target_id:
                        return [ctx]
                # target_id есть, но NPC не в локации — fallback ниже

        # ── Сценарий 2: broadcast — обращение ко всем ────────────────────────
        broadcast_keywords = [
            "всем", "все", "господа", "люди", "слушайте", "внимание",
            "угрожаю всем", "кричу в зал", "обращаюсь к залу",
            "достаю оружие", "атакую всех", "на виду у всех",
        ]
        if any(kw in full_text for kw in broadcast_keywords):
            return sorted_contexts

        # ── Сценарий 3: тихое действие — NPC молчат ──────────────────────────
        silent_keywords = [
            "осматриваюсь", "смотрю вокруг", "оглядываюсь", "изучаю",
            "читаю", "слушаю", "жду", "иду к", "подхожу к", "сажусь",
            "выхожу", "вхожу", "осматриваю комнату",
        ]
        if any(kw in full_text for kw in silent_keywords):
            return []

        # ── Сценарий 4 (fallback): проверяем имена из контекста ──────────────
        # Generic: используем npc_name из данных, не хардкод
        def _get_name_forms(ctx: dict) -> list[str]:
            explicit = ctx.get("name_forms")
            if explicit:
                return [f.lower() for f in explicit]
            name = ctx.get("npc_name", "")
            n = name.lower()
            forms = [n]
            if len(n) > 3:
                forms.append(n[:-1])
            if len(n) > 4:
                forms.append(n[:-2])
                forms.append(n[:-3])
            if len(n) >= 4:
                forms.append(n[:4])
            if len(n) >= 5:
                forms.append(n[:5])
            return list(set(f for f in forms if len(f) >= 3))

        # Таблица ключевых слов по роли (из npc_id — универсальная)
        _ROLE_KEYWORDS: dict[str, list[str]] = {
            "tavern_keeper": ["хозяин", "трактирщик", "бармен", "хозяину", "трактирщику"],
            "innkeeper":     ["хозяин", "хозяйка", "трактирщик"],
            "maid":          ["служанка", "официантка", "девушка", "служанке"],
            "guard":         ["стражник", "охранник", "стражнику", "страж"],
            "merchant":      ["купец", "торговец", "купцу", "торговцу"],
            "thief":         ["вор", "незнакомец", "тень", "фигура"],
            "priest":        ["священник", "жрец"],
            "blacksmith":    ["кузнец", "кузнецу"],
            "farmer":        ["крестьянин", "фермер"],
            "noble":         ["лорд", "господин", "барон"],
        }

        def _get_role(npc_id: str) -> str:
            parts = npc_id.split("_")
            for length in range(len(parts) - 1, 0, -1):
                candidate = "_".join(parts[:length])
                if candidate in _ROLE_KEYWORDS:
                    return candidate
            return ""

        for ctx in sorted_contexts:
            npc_id   = ctx.get("npc_id", "")
            npc_name = ctx.get("npc_name", "")

            if any(form in full_text for form in _get_name_forms(ctx)):
                return [ctx]

            role = _get_role(npc_id)
            if role and any(kw in full_text for kw in _ROLE_KEYWORDS.get(role, [])):
                return [ctx]

        # Общее действие — отвечает первый по tier
        # Проверяем: игрок упомянул какую-то роль/имя которого нет в сцене?
        # Если да — никто не отвечает, DM сам скажет "кузнеца здесь нет"
        _ANY_ROLE_KEYWORDS = [kw for kws in _ROLE_KEYWORDS.values() for kw in kws]
        _NPC_NAMES = [ctx.get("npc_name", "").lower() for ctx in sorted_contexts]

        mentioned_unknown = (
            any(kw in full_text for kw in _ANY_ROLE_KEYWORDS) or
            # упомянуто имя из 4+ букв которого нет среди активных NPC
            any(
                word in full_text
                for word in full_text.split()
                if len(word) >= 4 and not any(word in name for name in _NPC_NAMES)
            )
        )
        # Только если явно упомянута роль/имя и никто не найден — молчим
        # Иначе (общая реплика без адресата) — отвечает первый
        if any(kw in full_text for kw in _ANY_ROLE_KEYWORDS):
            return []   # кузнец/священник/лорд — но их нет → DM объяснит

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
        action_str = "\n".join(f"- {a.player_name}: {a.action}" for a in actions)
        memory_str = ""
        if npc_memory:
            last = npc_memory[-1].get("note") if isinstance(npc_memory[-1], dict) else None
            if last:
                memory_str += f"\nКонтекст NPC: {last}"
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
        scene_state   = shared_context.get("scene_state") if shared_context else None
        target_npc_id = (scene_state or {}).get("player_target_npc")

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

            for npc_ctx in active_contexts:
                npc_name    = npc_ctx.get("npc_name", "NPC")
                npc_id      = npc_ctx.get("npc_id", "")
                npc_tier    = npc_ctx.get("tier", "minor")
                npc_capability = self._get_capability_for_npc(
                    "major" if npc_tier == "major" else "mass"
                )

                npc_ctx_with_session = {**npc_ctx, "recent_session": recent_session}

                # S.0: передаём scene_state в _build_phase3a_prompt
                sys_p, usr_p = self._build_phase3a_prompt(
                    npc_ctx_with_session, actions, npc_memory,
                    scene_state=scene_state,
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
"""
Файл: backend/app/services/input/llm_compressor_client.py
Назначение: Изоляция вызова LLM. Использует существующий абстрактный класс или делает прямой вызов.
Зависимости: httpx, domain.intent_profile
Основные сущности: LLMCompressorClient (Protocol), LlamaCppCompressorClient (реализация для локального сервера)

TODO: В будущем может потребоваться расширить LLMCompressorClient для поддержки нескольких моделей (например, облачные API), более сложных схем промптинга и адаптивного формата ответа (например, если модель поддерживает структурированные данные или требует постобработки). Но для MVP достаточно базового клиента для локального llama.cpp сервера с JSON Mode.

"""

import json
import logging
from typing import Any, Dict, Optional, Protocol, cast

logger = logging.getLogger(__name__)


class LLMCompressorClient(Protocol):
    """Интерфейс компрессора. LLM = Voice, но здесь она Semantic Parser."""

    async def compress_intent(
        self, raw_text: str, scene_context: Dict[str, Any],
        dialogue_session: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]: ...


class LlamaCppCompressorClient:
    """Реализация для локального llama.cpp сервера. Использует OpenAI-совместимый API."""

    def __init__(self, base_url: Optional[str] = None):
        # NEW-DLG-002 FIX: Использование settings.llama_cpp_server_url вместо хардкода.
        from app.core.config import settings
        self.base_url = base_url or settings.llama_cpp_server_url

    async def compress_intent(
        self, raw_text: str, scene_context: Dict[str, Any], dialogue_session: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        import asyncio
        return await asyncio.to_thread(self._sync_compress, raw_text, scene_context, dialogue_session)

    def _sync_compress(self, raw_text: str, scene_context: Dict[str, Any], dialogue_session: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Синхронная реализация через urllib (обходит баги прокси и httpx)."""
        import re
        import urllib.request

        system_prompt, user_prompt = self._build_prompts(raw_text, scene_context, dialogue_session)
        # Deterministic comprehension (вердикт Мастера, развилка (i)):
        # identical input → identical canonical output. temperature=0 —
        # comprehension не художественная генерация; seed — KernelRNG
        # (salt=prompt) — ТОТ ЖЕ прецедент, что _complete_via_server
        # (llama_cpp_provider:163-165), не второй механизм. Только этот
        # путь: DM/вербализация (temperature=0.9) не трогаются.
        from app.services.npc.kernel_rng import KernelRNG
        _seed = KernelRNG(tick=0, npc_id="intent_compressor", salt=user_prompt).randint(
            0, 2**31 - 1
        )
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "seed": _seed,
            "response_format": {"type": "json_object"} # Принудительный JSON Mode
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            # S97 FIX: Обход прокси (Throne), который рвёт соединения к localhost
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)

            # S203 FIX: Увеличен таймаут до 60 сек, т.к. qwen_7b на CPU может думать дольше 15 сек.
            with opener.open(req, timeout=60.0) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                content = resp_data["choices"][0]["message"]["content"]

                # Очистка от markdown разметки (Qwen любит оборачивать в ```json ... ```)
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)

                return cast(Dict[str, Any], json.loads(content))
        except json.JSONDecodeError as e:
            # S203 FIX: Логируем сырой ответ LLM, чтобы понять, почему парсинг падает.
            logger.error(f"[LLM_COMPRESSOR] JSONDecodeError: {e}. Raw content: {content if 'content' in locals() else 'N/A'}")
            return None
        except (urllib.error.URLError, KeyError, IndexError) as e:
            # L4: причина отказа видима на error-уровне (урок R7 — debug
            # прятал смерть LLM-слоя 12 ходов); тело HTTPError — диагноз сервера.
            _body = ""
            if isinstance(e, urllib.error.HTTPError):
                try:
                    _body = e.read().decode("utf-8", errors="replace")[:600]
                except Exception as read_error:
                    logger.debug(f"Failed to read HTTP error body: {read_error}")
            logger.error(
                f"[LLM_COMPRESSOR] request failed: {type(e).__name__} "
                f"code={getattr(e, 'code', '')} | SERVER BODY: {_body}"
            )
            return None
        except Exception as e:
            logger.error(f"[LLM_COMPRESSOR] Unexpected error: {e}")
            return None

    def _build_prompts(self, raw_text: str, scene_context: Dict[str, Any], dialogue_session: Optional[Any] = None) -> tuple[str, str]:
        # Извлекаем имена NPC для подсказки модели
        npc_names = []
        if isinstance(scene_context, dict):
            for pos_data in scene_context.get("npc_positions", {}).values():
                if isinstance(pos_data, dict) and pos_data.get("name"):
                    npc_names.append(pos_data["name"])

        names_hint = ", ".join(npc_names) if npc_names else "нет"

        system_prompt = f"""Ты — продвинутый семантический парсер. Переведи ввод игрока в строгий JSON, отражающий многомерную семантику высказывания.
Допустимые action: ["MOVE", "OBSERVE", "INTERACT", "ATTACK", "THREATEN", "PERSUADE", "FLIRT", "STEAL", "GIVE", "DIALOGUE", "UNCERTAIN"].
Если игрок говорит или спрашивает что-то (не угрожает и не флиртует), используй action = "DIALOGUE".
Если игрок угрожает (но не бьёт) — "THREATEN". Если бьёт или применяет силу — "ATTACK".
Допустимые speech_act: ["assert", "question", "request", "order", "offer", "promise", "threat", "apology", "compliment", "insult", "accusation", "greeting", "farewell", "continue", "clarify", "reject", "accept"].
- semantic_acts: массив ВСЕХ актов фразы по порядку. Допустимые type: "GREETING", "ASK_NAME", "ASK_IDENTITY", "ASK_LOCATION", "SELF_INTRODUCTION" (params: {{"name": "..."}}), "QUESTION" (params: {{"topic": "..."}}), "ASSERT" (params: {{"claim": "..."}}), "ORDER", "THREAT", "COMPLIMENT", "FAREWELL", "ASK_PROVENANCE" (params: {{"about": "о чём спрашивают происхождение"}}). ASK_PROVENANCE = вопрос о ПРОИСХОЖДЕНИИ знания/информации: кто сказал, откуда известно, кто сообщил, источник сведения и эквивалентные естественные формулировки. НЕ использовать для вопросов о том, кто что-то сделал с третьим лицом ("кто с ней разговаривал" — это QUESTION). Пример: "Кто тебе сказал, что я Мю?" -> acts: [{{"type": "ASK_PROVENANCE", "params": {{"about": "имя игрока"}}}}]. Для одиночного действия — один акт или [].
Допустимые social_intent и их жесткая связь с action и speech_act:
- "obtain_information": action="DIALOGUE", speech_act="QUESTION" или "ORDER". (Узнать секрет, правду, факт. Примеры: "что ты скрываешь", "в чем секрет", "расскажи мне правду").
- "obtain_cooperation": action="PERSUADE", speech_act="REQUEST" или "OFFER". (Договориться о помощи, сделке).
- "obtain_compliance": action="THREATEN", speech_act="THREAT" или "ORDER". (Заставить подчиниться через угрозу).
- "repair_relationship": action="DIALOGUE", speech_act="APOLOGY". (Помириться, извиниться).
- "build_rapport": action="DIALOGUE", speech_act="ASSERT" или "COMPLIMENT". (Сблизиться, дружеская беседа, нейтральный контакт).
- "intimidate": action="THREATEN" или "ATTACK", speech_act="THREAT" или "INSULT". (Запугать, унизить, угроза насилием. Примеры: "ты труп", "ты играешь с огнём", "я тебя уничтожу").
- "flirt": action="FLIRT" или "DIALOGUE", speech_act="COMPLIMENT". (Флирт, комплименты внешности, романтика. Примеры: "ты красивая", "ты мне нравишься", "не могу оторвать взгляд", "ты очаровательна", "мне с тобой так хорошо", "я думаю о тебе"). Любое выражение симпатии = "flirt".
- "comfort": action="DIALOGUE" или "GIVE", speech_act="ASSERT" или "PROMISE". (Утешить, поддержать в горе. Примеры: "всё будет хорошо", "не плачь", "я с тобой", "я помогу тебе", "давай я обниму тебя", "ты сильная", "твоя боль - моя боль"). Любая поддержка или забота = "comfort".
- "deceive": action="DIALOGUE", speech_act="ASSERT". (Солгать, обмануть).
- "confess": action="DIALOGUE", speech_act="ASSERT". (Признаться в чём-то).
- "provoke": action="DIALOGUE" или "ATTACK", speech_act="INSULT". (Спровоцировать на конфликт).
- "defend": action="DIALOGUE" или "ATTACK", speech_act="ASSERT". (Защитить кого-то).
- "neutral": action="DIALOGUE", speech_act="ASSERT". (Бытовая коммуникация).
Выбирай social_intent строго по смыслу. Выражение симпатии = "flirt", а не "build_rapport". Угрозы = "intimidate", а не "repair_relationship". Запрос секрета = "obtain_information", а не "neutral". Утешение и поддержка = "comfort", а не "obtain_cooperation" или "build_rapport".

# Few-Shot Examples (S203 §8.2.1-8.2.4)
Ввод: "ты такая красивая" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "compliment"}}
Ввод: "ты мне нравишься" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "compliment"}}
Ввод: "мне с тобой так хорошо" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "compliment"}}
Ввод: "я думаю о тебе постоянно" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "assert"}}
Ввод: "я счастлив, что встретил тебя" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "compliment"}}
Ввод: "можно я приглашу тебя на танец?" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "request"}}
Ввод: "я хочу узнать тебя ближе" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "request"}}
Ввод: "давай проведём вечер вместе" -> {{"action": "FLIRT", "social_intent": "flirt", "speech_act": "offer"}}
Ввод: "всё будет хорошо, не плачь" -> {{"action": "DIALOGUE", "social_intent": "comfort", "speech_act": "promise"}}
Ввод: "я с тобой, не бойся" -> {{"action": "DIALOGUE", "social_intent": "comfort", "speech_act": "assert"}}
Ввод: "ты не одна, я рядом" -> {{"action": "DIALOGUE", "social_intent": "comfort", "speech_act": "assert"}}
Ввод: "не извиняйся, ты ни в чём не виновата" -> {{"action": "DIALOGUE", "social_intent": "comfort", "speech_act": "assert"}}
Ввод: "мне жаль, что тебе так больно" -> {{"action": "DIALOGUE", "social_intent": "comfort", "speech_act": "apology"}}
Ввод: "я хочу, чтобы ты улыбалась" -> {{"action": "DIALOGUE", "social_intent": "comfort", "speech_act": "promise"}}
Ввод: "ты можешь опереться на моё плечо" -> {{"action": "DIALOGUE", "social_intent": "comfort", "speech_act": "offer"}}
Ввод: "я тебя уничтожу" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "threat"}}
Ввод: "ты труп" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "threat"}}
Ввод: "я знаю, где ты живёшь" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "threat"}}
Ввод: "ты ничего не значишь" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "insult"}}
Ввод: "ты играешь с огнём" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "threat"}}
Ввод: "я выпью твою кровь" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "threat"}}
Ввод: "не смей больше открывать рот" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "order"}}
Ввод: "ты ходишь по тонкому льду" -> {{"action": "THREATEN", "social_intent": "intimidate", "speech_act": "threat"}}
Ввод: "что ты скрываешь?" -> {{"action": "DIALOGUE", "social_intent": "obtain_information", "speech_act": "question"}}
Ввод: "признавайся, что у тебя за секрет?" -> {{"action": "DIALOGUE", "social_intent": "obtain_information", "speech_act": "order"}}
Ввод: "привет, как дела?" -> {{"action": "DIALOGUE", "social_intent": "build_rapport", "speech_act": "greeting"}}
Ввод: "Привет. Я Марко, а ты кто?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "GREETING"}}, {{"type": "SELF_INTRODUCTION", "params": {{"name": "Марко"}}}}, {{"type": "ASK_IDENTITY"}}], "speech_act": "question"}}
Ввод: "Я Мю." -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "SELF_INTRODUCTION", "params": {{"name": "Мю"}}}}], "speech_act": "assert"}}
Ввод: "Меня зовут Мю." -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "SELF_INTRODUCTION", "params": {{"name": "Мю"}}}}], "speech_act": "assert"}}
Ввод: "Привет, я Мю." -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "GREETING"}}, {{"type": "SELF_INTRODUCTION", "params": {{"name": "Мю"}}}}], "speech_act": "greeting"}}
Ввод: "Я — Мю." -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "SELF_INTRODUCTION", "params": {{"name": "Мю"}}}}], "speech_act": "assert"}}
Ввод: "Здравствуй, меня зовут Мю." -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "GREETING"}}, {{"type": "SELF_INTRODUCTION", "params": {{"name": "Мю"}}}}], "speech_act": "greeting"}}
Ввод: "Кто тебе сказал, что меня зовут Мю?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "ASK_PROVENANCE", "params": {{"about": "имя игрока"}}}}], "speech_act": "question"}}
Ввод: "Откуда ты знаешь, что я Мю?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "ASK_PROVENANCE", "params": {{"about": "имя игрока"}}}}], "speech_act": "question"}}
Ввод: "Кто разговаривал с Люсей?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "QUESTION", "params": {{"topic": "кто разговаривал с Люсей"}}}}], "speech_act": "question"}}
Ввод: "Я ищу Горана. Ты его сегодня видел?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "QUESTION", "params": {{"topic": "видел ли Горана"}}}}], "speech_act": "question"}}
Ввод: "ты молодец" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "COMPLIMENT"}}], "social_intent": "build_rapport", "speech_act": "compliment"}}
Ввод: "Я слуга этого дома десять лет." -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "ASSERT", "params": {{"claim": "Я слуга этого дома десять лет", "subject": "player", "topic": "occupation"}}}}], "speech_act": "assert"}}
Ввод: "Ты слуга этого дома?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "QUESTION", "params": {{"topic": "occupation", "target": "npc"}}}}], "speech_act": "question"}}
Ввод: "Ты ведь слуга этого дома, да?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "CONFIRMATION_SEEKING", "params": {{"topic": "occupation", "target": "npc"}}}}], "speech_act": "question"}}
Ввод: "ткни его ножом" -> {{"action": "ATTACK", "tool_reference": "нож", "physical_force": 0.9}}
Ввод: "ударь его палкой" -> {{"action": "ATTACK", "tool_reference": "палка", "physical_force": 0.6}}

Извлеки:
- action: канонический тип действия.
- actor: КТО совершает действие. Если игрок говорит о себе ("я подойду") — "player". Если приказывает NPC ("Торнин, отойди" или "пусть Торнин уйдёт") — имя NPC (например, "Торнин"). Доступные имена NPC: {names_hint}.
- target: к кому или к чему направлено действие (строка).
- speech_act: тип речевого акта (Searle).
- social_intent: истинная социальная цель.
- proposition: объект {{"subject_id": "...", "predicate": "stole|attacked|helped|asserts", "object_id": "...", "polarity": true|false}} — ТОЛЬКО если фраза содержит фактическое утверждение о мире (кто-то что-то сделал/украл/совершил). Для приказов, угроз, вопросов и действий — строго null. Не выдумывай proposition, если её нет во фразе.
- requested_outcome: что игрок хочет получить (строка).
- offered_outcome: что игрок предлагает (строка).
- condition: условие (строка).
- tool_reference: чем совершается действие (простая строка: "нож", "кулак", "палка"), иначе null.
- addressee: к кому обращена фраза (обращение/имя в начале: "Орм, не трогай её" -> "Орм"; "Скажи Тени..." -> "Тень"). Если обращения нет — null. ВАЖНО: addressee (кому сказано) ≠ target (над кем действие) ≠ actor (кто исполняет): "пусть Торнин уйдёт" -> addressee="Торнин", actor="Торнин", action связан с движением Торнина, не игрока.
- target_zone: ["HEAD", "TORSO", "ARMS", "LEGS", "GROIN", "UNDEFINED"].
- physical_force, emotional_charge, social_pressure: числа от 0.0 до 1.0.
- semantic: объект с ключами aggression, fear, shame, confidence, desperation (0.0-1.0).
- conversation_continuation: ["CONTINUE", "NEW_TOPIC", "RETURN_TO", "CLARIFY", null].

Если не уверен, установи action = "UNCERTAIN".
Верни ТОЛЬКО валидный JSON без markdown разметки."""

        # S200: Добавляем контекст активного диалога в промпт
        dialogue_context_str = ""
        if dialogue_session and not dialogue_session.is_empty:
            dialogue_context_str = f"\n\nТекущий диалог с {dialogue_session.partner_id}:\n"
            dialogue_context_str += f"- Topic: {dialogue_session.topic or 'не определена'}\n"
            if dialogue_session.buffer:
                last_turn = dialogue_session.buffer[-1]
                dialogue_context_str += f"- Последняя реплика ({last_turn.speaker}): {last_turn.text}\n"
            dialogue_context_str += "Если игрок пишет 'продолжай', 'ну?', 'и?', 'а что?' — интерпретируй как CONTINUE относительно последней реплики NPC.\n"

        # [DIAG-PROMPT] временный зонд (секция 2 директивы Мастера): состав дампа
        # scene_context по ключам — измерение ДО F-B, чтобы резать по фактам.
        _sect = {}
        if isinstance(scene_context, dict):
            for _k, _v in scene_context.items():
                try:
                    _sect[_k] = len(json.dumps(_v, ensure_ascii=False))
                except Exception:
                    _sect[_k] = -1
            _top = sorted(_sect.items(), key=lambda x: -x[1])[:12]
            print(f"[DIAG-PROMPT] keys={len(_sect)} chars_total={sum(v for v in _sect.values() if v > 0)} "
                  f"top12={_top}")
        else:
            print(f"[DIAG-PROMPT] scene_context type={type(scene_context).__name__} len={len(str(scene_context))}")  # type: ignore[unreachable]  # S313: runtime-гвард (cast лжёт на мусоре)


        # F-B (директива Understanding Layer, п.1): компактный контекст семантического
        # разбора вместо дампа мира. Замер [DIAG-PROMPT]: 49-50K chars из 50K user_prompt
        # — нерелевантный дамп (commitment_history/world_objects/geometry/epistemic);
        # семантике нужны только доступные адресаты (id+имя, SSOT имён —
        # scene_state["npc_positions"][npc_id].name). Диалог уже компактен отдельно.
        _compact_lines: list = []
        if isinstance(scene_context, dict):
            _loc = scene_context.get("location_id") or scene_context.get("location") or ""
            if _loc:
                _compact_lines.append(f"Локация: {_loc}")
            _npcs = scene_context.get("npc_positions", {})
            if isinstance(_npcs, dict):
                for _nid, _np in _npcs.items():
                    if not isinstance(_np, dict):
                        continue
                    _name = _np.get("name") or _np.get("display_name") or _nid
                    _compact_lines.append(f"- {_nid} ({_name})")
        _compact_ctx = "\n".join(_compact_lines) if _compact_lines else "нет"
        user_prompt = (
            f"Ввод: \"{raw_text}\"\n"
            f"Доступные персонажи (id — имя):\n{_compact_ctx}"
            f"{dialogue_context_str}"
        )

        return system_prompt, user_prompt

"""
Файл: backend/app/services/input/llm_compressor_client.py
Назначение: Изоляция вызова LLM. Использует существующий абстрактный класс или делает прямой вызов.
Зависимости: httpx, domain.intent_profile
Основные сущности: LLMCompressorClient (Protocol), LlamaCppCompressorClient (реализация для локального сервера)

TODO: В будущем может потребоваться расширить LLMCompressorClient для поддержки нескольких моделей (например, облачные API), более сложных схем промптинга и адаптивного формата ответа (например, если модель поддерживает структурированные данные или требует постобработки). Но для MVP достаточно базового клиента для локального llama.cpp сервера с JSON Mode.

"""

import json
import logging
import os
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

        # Явный импорт: urllib.request тянет urllib.error только сайд-эффектом —
        # анализаторы типа не видят, isinstance(e, HTTPError) не сужал тип.
        import urllib.error
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

        # content связан до try: JSONDecodeError-обработчик читает его легально
        # (присваивание внутри with гарантировано раньше любого json.loads).
        content = ""
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

                # [DET-TRACE] (вердикт Мастера, DEBT-INFERENCE-NONDET):
                # наблюдаемость identity запроса/ответа за env-флагом.
                # По умолчанию выключен — нулевой эффект на production.
                # Хэш — сырой ответ ДО markdown-чистки и JSON-парсинга:
                # расхождение det-замеров локализуется сервером, не парсером.
                if os.environ.get("ENIGMA_DET_TRACE") == "1":
                    import hashlib

                    print(
                        "[DET-TRACE] "
                        f"prompt_md5={hashlib.md5(user_prompt.encode('utf-8')).hexdigest()} "
                        f"seed={_seed} "
                        f"resp_md5={hashlib.md5(content.encode('utf-8')).hexdigest()}"
                    )

                # Очистка от markdown разметки (Qwen любит оборачивать в ```json ... ```)
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)

                return cast(Dict[str, Any], json.loads(content))
        except json.JSONDecodeError as e:
            # S203 FIX: Логируем сырой ответ LLM, чтобы понять, почему парсинг падает.
            # §1.3: content связан ДО try (см. инициализацию выше) — locals()
            # не нужен; пустая строка честно печатается как N/A.
            logger.error(f"[LLM_COMPRESSOR] JSONDecodeError: {e}. Raw content: {content or 'N/A'}")
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
            # §1.2: код статуса читается только у HTTPError — пустой
            # getattr-дефолт больше не маскирует отсутствие атрибута.
            _code = e.code if isinstance(e, urllib.error.HTTPError) else ""
            logger.error(
                f"[LLM_COMPRESSOR] request failed: {type(e).__name__} "
                f"code={_code} | SERVER BODY: {_body}"
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

        # RC8 вердикт (валидный тёплый A/B + контрбаланс): три few-shot-
        # строки имели ДОКАЗАННЫЙ отрицательный эффект (STATE-B: 0/27
        # ASK_PROVENANCE в 9 прогонах; STATE-A: 2-3/27 с воспроизводимой
        # генерализацией) — удалены из production (вердикт Мастера, V.1).
        # ENIGMA_RC8_STATE='B' восстанавливает легаси-состояние для
        # воспроизведения эксперимента (reports/RC8_DETERMINISM_RCA.md).
        # Новые примеры НЕ добавлять до закрытия unspecified-дефекта.
        _rc8_fewshot = ""

        # X2 (вердикт Мастера): инлайн-примеры в границе ASK_PROVENANCE/QUESTION
        # — дословные фразы probe-корпуса (AB-PROV[0] байт-в-байт; почти
        # GEN-3RD) — контаминация измерения; literal-suppression доказан RC8
        # и воспроизведён provclass_x2a/a2x (фраза-пример: A 0/2, X2 2/2).
        # ENIGMA_PROV_X2=1 → состояние X2: примеры убраны, граница не меняется.
        # X-clean (вердикт Мастера, второй GO): ASK_PROVENANCE извлекается из
        # строки-перечисления в собственную структурную строку контракта.
        # Гипотеза: семантика provenance доступна модели (QUESTION.topic =
        # source of knowledge), барьер — потеря типа в списке из 11 типов.
        # ENIGMA_PROV_XCLEAN=1 (приоритет над X2). Default = baseline (A).
        _prov_boundary_text = (
            "ASK_PROVENANCE = вопрос о ПРОИСХОЖДЕНИИ знания/информации: кто сказал, "
            "откуда известно, кто сообщил, источник сведения и эквивалентные естественные формулировки. "
            "НЕ использовать для вопросов о том, кто что-то сделал с третьим лицом"
        )
        _prov_enum_tail = (
            ', "ASK_PROVENANCE" (params: {"about": "о чём спрашивают происхождение"}). '
            + _prov_boundary_text
            + ' ("кто с ней разговаривал" — это QUESTION). '
            'Пример: "Кто тебе сказал, что я Мю?" -> acts: [{"type": "ASK_PROVENANCE", "params": {"about": "имя игрока"}}]'
        )
        _prov_class_block = ""
        if os.environ.get("ENIGMA_PROV_X2") == "1":
            _prov_enum_tail = ', "ASK_PROVENANCE" (params: {"about": "о чём спрашивают происхождение"}). ' + _prov_boundary_text
        if os.environ.get("ENIGMA_PROV_XCLEAN") == "1":
            _prov_enum_tail = ""
            _prov_class_block = (
                '\n- Допустимый type "ASK_PROVENANCE": вопрос об ИСТОЧНИКЕ ЗНАНИЯ СОБЕСЕДНИКА — '
                "кто ему это сообщил, откуда он узнал, каким источником располагает "
                '(params: {"about": "о чём спрашивают происхождение"}). '
                "ГРАНИЦА с QUESTION: вопрос о событиях, фактах или действиях третьих лиц в мире = QUESTION; "
                "вопрос о том, КАК/ОТКУДА собеседник узнал = ASK_PROVENANCE. "
                "Ответ на ASK_PROVENANCE раскрывает источник знания собеседника, а не факт мира."
            )
        # B (вердикт Мастера): база A + ОДНА контрастная пара на чужом контенте
        # в структурном блоке. Уроки серии: literal-suppression доказан дважды
        # (RC8, X2); XCLEAN показал риск выхолащивания topic-канала — topic-
        # насыщенность prov-групп обязательная метрика B. Пара обучает
        # ОТНОШЕНИЮ (источник знания собеседника vs событие мира), не
        # ключевым словам: один общий якорь («корабль»), различие чисто
        # реляционное. ENIGMA_PROV_B=1 (default OFF = baseline байт-неизменен).
        _prov_b_block = ""
        # B2 (вердикт Мастера, GO после закрытого det-check): ВТОРАЯ независимая
        # контрастная пара на другом реляционном паттерне provenance
        # (откуда-знаешь vs когда-случается), контент чужой корпусу и паре B
        # (гварды: «прилив», «расписание» вне корпуса; «корабль» вне B2-блока).
        # Сборка = база A + ТОЛЬКО эта пара (ENIGMA_PROV_B2 независим от
        # ENIGMA_PROV_B; пары никогда не сосуществуют в промпте) — одна
        # переменная относительно A. Гипотеза: каждый реляционный паттерн
        # требует своего контрастного якоря; ширина переноса = f(число паттернов).
        _prov_b2_block = ""
        if os.environ.get("ENIGMA_PROV_B2") == "1":
            _prov_b2_block = (
                "\n- Контрастная пара для границы классов: "
                '"Откуда ты знаешь расписание приливов?" — вопрос об ИСТОЧНИКЕ ЗНАНИЯ '
                'собеседника -> acts: [{"type": "ASK_PROVENANCE", "params": {"about": "расписании приливов"}}]; '
                '"Когда приходит прилив?" — вопрос о факте мира -> acts: [{"type": "QUESTION", "params": {"topic": "когда приходит прилив"}}]. '
                "Первый спрашивает, ОТКУДА собеседнику известно; второй — КОГДА происходит событие."
            )
        if os.environ.get("ENIGMA_PROV_B") == "1":
            _prov_b_block = (
                "\n- Контрастная пара для границы классов: "
                '"Кто тебе доложил о прибытии корабля?" — вопрос об ИСТОЧНИКЕ ЗНАНИЯ '
                'собеседника -> acts: [{"type": "ASK_PROVENANCE", "params": {"about": "прибытии корабля"}}]; '
                '"Кто разгружает корабль?" — вопрос о событии мира -> acts: [{"type": "QUESTION", "params": {"topic": "кто разгружает корабль"}}]. '
                "Первый спрашивает, ОТКУДА собеседнику известно; второй — КТО СОВЕРШАЕТ действие."
            )
        # Э0 semantic library (вердикт Мастера): семантическое знание модульно
        # на диске, активный промпт получает ограниченный срез. Production
        # source of truth остаётся inline (миграция — отдельный вердикт):
        # OFF (default) путь мёртв (import внутри ветки, замок test_semlib_off),
        # ON — модуль заменяет provenance-регион байт-в-байт состоянию B
        # (приёмка test_semlib_on). Prov-флаги при ON игнорируются: библиотека
        # единственный владелец региона. Router отсутствует by design (Э0-Э2):
        # шов будущего router'а — выбор модуля между list_modules/load_module.
        if os.environ.get("ENIGMA_SEM_LIB") == "1":
            from app.services.input.semantic_library import load_module
            _sem_mod = load_module("dialogue_provenance")
            _prov_enum_tail = _sem_mod.enum_tail
            _prov_class_block = ""
            _prov_b_block = _sem_mod.contrast_block
            _prov_b2_block = ""
        if os.environ.get("ENIGMA_RC8_STATE") == "B":
            _rc8_fewshot = (
                'Ввод: "Кто тебе сказал, что меня зовут Мю?" -> {"action": "DIALOGUE", "semantic_acts": [{"type": "ASK_PROVENANCE", "params": {"about": "имя игрока"}}], "speech_act": "question"}\n'
                'Ввод: "Откуда ты знаешь, что я Мю?" -> {"action": "DIALOGUE", "semantic_acts": [{"type": "ASK_PROVENANCE", "params": {"about": "имя игрока"}}], "speech_act": "question"}\n'
                'Ввод: "Кто разговаривал с Люсей?" -> {"action": "DIALOGUE", "semantic_acts": [{"type": "QUESTION", "params": {"topic": "кто разговаривал с Люсей"}}], "speech_act": "question"}\n'
            )

        system_prompt = f"""Ты — продвинутый семантический парсер. Переведи ввод игрока в строгий JSON, отражающий многомерную семантику высказывания.
Допустимые action: ["MOVE", "OBSERVE", "INTERACT", "ATTACK", "THREATEN", "PERSUADE", "FLIRT", "STEAL", "GIVE", "DIALOGUE", "UNCERTAIN"].
Если игрок говорит или спрашивает что-то (не угрожает и не флиртует), используй action = "DIALOGUE".
Если игрок угрожает (но не бьёт) — "THREATEN". Если бьёт или применяет силу — "ATTACK".
Допустимые speech_act: ["assert", "question", "request", "order", "offer", "promise", "threat", "apology", "compliment", "insult", "accusation", "greeting", "farewell", "continue", "clarify", "reject", "accept"].
- semantic_acts: массив ВСЕХ актов фразы по порядку. Допустимые type: "GREETING", "ASK_NAME", "ASK_IDENTITY", "ASK_LOCATION", "SELF_INTRODUCTION" (params: {{"name": "..."}}), "QUESTION" (params: {{"topic": "..."}}), "ASSERT" (params: {{"claim": "..."}}), "ORDER", "THREAT", "COMPLIMENT", "FAREWELL"{_prov_enum_tail}. Для одиночного действия — один акт или [].{_prov_class_block}{_prov_b_block}{_prov_b2_block}
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
{_rc8_fewshot}Ввод: "Я ищу Горана. Ты его сегодня видел?" -> {{"action": "DIALOGUE", "semantic_acts": [{{"type": "QUESTION", "params": {{"topic": "видел ли Горана"}}}}], "speech_act": "question"}}
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

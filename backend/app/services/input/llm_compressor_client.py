"""
Файл: backend/app/services/input/llm_compressor_client.py
Назначение: Изоляция вызова LLM. Использует существующий абстрактный класс или делает прямой вызов.
Зависимости: httpx, domain.intent_profile
Основные сущности: LLMCompressorClient (Protocol), LlamaCppCompressorClient (реализация для локального сервера)

TODO: В будущем может потребоваться расширить LLMCompressorClient для поддержки нескольких моделей (например, облачные API), более сложных схем промптинга и адаптивного формата ответа (например, если модель поддерживает структурированные данные или требует постобработки). Но для MVP достаточно базового клиента для локального llama.cpp сервера с JSON Mode.

"""

import json
import logging
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)


class LLMCompressorClient(Protocol):
    """Интерфейс компрессора. LLM = Voice, но здесь она Semantic Parser."""

    async def compress_intent(
        self, raw_text: str, scene_context: Dict[str, Any]
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
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
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

                return json.loads(content)
        except json.JSONDecodeError as e:
            # S203 FIX: Логируем сырой ответ LLM, чтобы понять, почему парсинг падает.
            logger.error(f"[LLM_COMPRESSOR] JSONDecodeError: {e}. Raw content: {content if 'content' in locals() else 'N/A'}")
            return None
        except (urllib.error.URLError, KeyError, IndexError) as e:
            logger.debug(f"LLM compressor request failed: {e}")
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

Извлеки:
- action: канонический тип действия.
- actor: КТО совершает действие. Если игрок говорит о себе ("я подойду") — "player". Если приказывает NPC ("Торнин, отойди" или "пусть Торнин уйдёт") — имя NPC (например, "Торнин"). Доступные имена NPC: {names_hint}.
- target: к кому или к чему направлено действие (строка).
- speech_act: тип речевого акта (Searle).
- social_intent: истинная социальная цель.
- proposition: объект {{"subject_id": "...", "predicate": "stole|attacked|helped|asserts", "object_id": "...", "polarity": true|false}} если есть утверждение о факте, иначе null.
- requested_outcome: что игрок хочет получить (строка).
- offered_outcome: что игрок предлагает (строка).
- condition: условие (строка).
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

        user_prompt = f"Ввод: \"{raw_text}\"\nКонтекст: {json.dumps(scene_context, ensure_ascii=False)}{dialogue_context_str}"

        return system_prompt, user_prompt

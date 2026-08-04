"""
Файл: backend/app/services/input/llm_compressor_client.py
Назначение: Изоляция вызова LLM. Использует существующий абстрактный класс или делает прямой вызов.
Зависимости: httpx, domain.intent_profile
Основные сущности: LLMCompressorClient (Protocol), LlamaCppCompressorClient (реализация для локального сервера)

TODO: В будущем может потребоваться расширить LLMCompressorClient для поддержки нескольких моделей (например, облачные API), более сложных схем промптинга и адаптивного формата ответа (например, если модель поддерживает структурированные данные или требует постобработки). Но для MVP достаточно базового клиента для локального llama.cpp сервера с JSON Mode.

"""

import json
from typing import Any, Dict, Optional, Protocol


class LLMCompressorClient(Protocol):
    """Интерфейс компрессора. LLM = Voice, но здесь она Semantic Parser."""

    async def compress_intent(
        self, raw_text: str, scene_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]: ...


class LlamaCppCompressorClient:
    """Реализация для локального llama.cpp сервера. Использует OpenAI-совместимый API."""

    def __init__(self, base_url: str = "http://127.0.0.1:8181"):
        self.base_url = base_url

    async def compress_intent(
        self, raw_text: str, scene_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        import asyncio
        return await asyncio.to_thread(self._sync_compress, raw_text, scene_context)

    def _sync_compress(self, raw_text: str, scene_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Синхронная реализация через urllib (обходит баги прокси и httpx)."""
        import re
        import urllib.request

        system_prompt, user_prompt = self._build_prompts(raw_text, scene_context)
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
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

            with opener.open(req, timeout=15) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                content = resp_data["choices"][0]["message"]["content"]

                # Очистка от markdown разметки (Qwen любит оборачивать в ```json ... ```)
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)

                return json.loads(content)
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as e:
            logger.debug(f"LLM compressor request failed: {e}")
            return None

    def _build_prompts(self, raw_text: str, scene_context: Dict[str, Any]) -> tuple[str, str]:
        # Извлекаем имена NPC для подсказки модели
        npc_names = []
        if isinstance(scene_context, dict):
            for pos_data in scene_context.get("npc_positions", {}).values():
                if isinstance(pos_data, dict) and pos_data.get("name"):
                    npc_names.append(pos_data["name"])

        names_hint = ", ".join(npc_names) if npc_names else "нет"

        system_prompt = f"""Ты — семантический парсер. Переведи ввод игрока в строгий JSON.
Допустимые action_types: ["MOVE", "OBSERVE", "INTERACT", "ATTACK", "THREATEN", "PERSUADE", "FLIRT", "STEAL", "GIVE", "UNCERTAIN"].
Извлеки:
- action_type: тип действия.
- actor_reference: КТО совершает действие. Если игрок говорит о себе ("я подойду") — "player". Если приказывает NPC ("Торнин, отойди" или "пусть Торнин уйдёт") — имя NPC (например, "Торнин"). Доступные имена NPC: {names_hint}.
- target_reference: к кому или к чему направлено действие (строка).
- target_zone: ["HEAD", "TORSO", "ARMS", "LEGS", "GROIN", "UNDEFINED"].
- physical_force, emotional_charge, social_pressure, commitment_level: числа от 0.0 до 1.0.
- semantic: объект с ключами aggression, fear, shame, confidence, desperation (0.0-1.0).
Если не уверен, установи action_type = "UNCERTAIN".
Верни ТОЛЬКО валидный JSON без markdown разметки."""

        user_prompt = f"Ввод: \"{raw_text}\"\nКонтекст: {json.dumps(scene_context, ensure_ascii=False)}"

        return system_prompt, user_prompt

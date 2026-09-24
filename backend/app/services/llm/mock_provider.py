"""
Mock LLM Provider
Возвращает предсказуемые ответы для прототипирования и тестов.
Не требует реального LLM сервера — всегда доступен.

path: /backend/app/services/llm/mock_provider.py
Назначение: Полноценный Mock провайдер для прототипирования и тестов — возвращает предсказуемые ответы без реального LLM
Зависимости: app.services.llm.provider
Основные сущности: MockProvider, MockConfig
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

from app.services.llm.provider import (
    GenerationParams,
    ProviderInfo,
    ProviderType,
    StreamingLlmProvider,
)


@dataclass
class MockConfig:
    """Настройки поведения Mock провайдера."""

    response_delay_sec: float = 0.1  # Имитация задержки сети
    simulate_streaming: bool = True  # Эмулировать по токенам или отдать сразу
    default_response: str = "[Mock] Действие выполнено. Мир реагирует."
    # Пул ответов для разнообразия
    response_pool: list[str] = field(
        default_factory=lambda: [
            "[Mock] Ты входишь в таверну. Запах жареного мяса наполняет воздух.",
            "[Mock] Гоблин выскакивает из-за угла, но спотыкается и падает.",
            "[Mock] Старый маг кивает тебе и показывает свиток с древними рунами.",
            "[Mock] Дверь заперта. Ты слышишь шорох за ней.",
            "[Mock] Торговец предлагает тебе зелье исцеления за 50 золотых.",
        ]
    )


class MockProvider(StreamingLlmProvider):
    """
    Mock провайдер для прототипирования.

    Используется когда:
    - LLM сервер недоступен
    - Нужно тестировать HTTP-слой без реальной генерации
    - Запуск в demo-режиме
    """

    def __init__(self, config: MockConfig | None = None) -> None:
        self._config = config or MockConfig()

    def complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> str:
        # Имитация задержки генерации
        time.sleep(self._config.response_delay_sec)

        # Если в промпте есть ключевые слова — контекстный ответ
        response = self._pick_response(prompt)
        return response

    def stream_complete(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> str:
        response = self._pick_response(prompt)

        if not self._config.simulate_streaming:
            # Отдаём весь текст сразу
            if callback:
                callback(response)
            return response

        # Эмулируем по токенам (по словам)
        full_text = ""
        words = response.split(" ")
        for word in words:
            chunk = word + " "
            full_text += chunk
            time.sleep(self._config.response_delay_sec / len(words))
            if callback:
                callback(chunk)

        return full_text.strip()

    def stream_tokens(
        self,
        prompt: str,
        params: GenerationParams | None = None,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        """Generator версия для SSE."""
        response = self._pick_response(prompt)

        if not self._config.simulate_streaming:
            yield response
            return

        words = response.split(" ")
        for word in words:
            yield word + " "
            time.sleep(self._config.response_delay_sec / max(len(words), 1))

    def _pick_response(self, prompt: str) -> str:
        """Выбирает ответ на основе контекста промпта.

        ВНИМАНИЕ: MockProvider возвращает ответы с префиксом '[Mock] ...'.
        ResponseValidator._contains_non_russian должен отклонять такие ответы
        (т.к. 'Mock' — английское слово). Если валидатор пропускает —
        MockProvider утекает в продакшен, что НЕДОПУСТИМО.
        """
        # BUG-DLG-CAUSAL-4.7.48 FIX: Использование settings.environment вместо os.getenv.
        from app.core.config import settings

        _env = settings.environment.lower()
        if _env == "production":
            # В продакшене MockProvider не должен отдавать ответы.
            # Возвращаем пустую строку → ResponseValidator._fallback("empty")
            # → игрок видит "Ничего не произошло." вместо "[Mock] ..."
            import logging

            logging.getLogger(__name__).error(
                "[MOCK_PROVIDER] MockProvider called in production! "
                "Falling back to empty response. "
                "Set ENIGMA_ENV=test or development to allow mock responses."
            )
            return ""

        prompt_lower = prompt.lower()

        # S269-ДЕТЕРМИНИЗМ (закрытие DEBT-MOCK из S213): выбор из пула —
        # по стабильному хешу промпта, не random.choice. Второй домен
        # пострадавших — DriftLab Mode E: ThreadPoolExecutor флапает
        # порядком mock-вызовов между ранами, общая random-последовательность
        # потребляется в разном порядке → MISMATCH при одинаковом seed.
        # Хеш промпта инвариантен к порядку вызовов. KernelRNG ядра
        # (ADR-O-301) не затронут — закон только для kernel layer,
        # mock остаётся вне симуляционного контура детерминизма.
        def _deterministic_pick(options: list[str]) -> str:
            # ADR-O-399 Iter2: hash(str) солёный PER-PROCESS (PYTHONHASHSEED) —
            # детерминизм внутри прогона, лотерея между процессами/сессиями.
            # Стабильный хеш (md5, §15-нейтральный: не time, не random) —
            # детерминирован между любыми процессами. Причина: DriftLab
            # канон L0'-vs-L1' дрейфовал между сессиями (2f30fe2d / 59315285 /
            # 63a5dd4f / 7a28bf7c при неизменном коде).
            import hashlib as _hl
            _idx = int(_hl.md5(prompt_lower.encode("utf-8")).hexdigest(), 16) % len(options)
            return options[_idx]

        # Простая эвристика по ключевым словам
        if any(w in prompt_lower for w in ["атак", "удар", "бьёт", "меч"]):
            return _deterministic_pick(
                [
                    "[Mock] Удар попадает! Цель получает урон.",
                    "[Mock] Атака промахивается — противник уклонился.",
                    "[Mock] Критический удар! Двойной урон!",
                ]
            )

        if any(w in prompt_lower for w in ["осмотр", "осмотреть", "осматрива"]):
            return _deterministic_pick(
                [
                    "[Mock] Ты осматриваешься: старые каменные стены, факелы, деревянный стол.",
                    "[Mock] В комнате видно: сундук в углу, потухший камин, старую карту на стену.",
                ]
            )

        if any(w in prompt_lower for w in ["говор", "сказал", "спросил", "отвеч"]):
            return _deterministic_pick(
                [
                    "[Mock] NPC задумчиво смотрит на тебя: 'Не знаю... может, стоит спросить у старосты.'",
                    "[Mock] 'За эту информацию придётся заплатить,' — процедил торговец.",
                ]
            )

        # Дефолт — из пула или статический
        return (
            _deterministic_pick(self._config.response_pool)
            if self._config.response_pool
            else self._config.default_response
        )

    def is_available(self) -> bool:
        """Mock ВСЕГДА доступен — это его смысл."""
        return True

    def get_info(self) -> ProviderInfo:
        return ProviderInfo(
            name="Mock Provider (prototype)",
            provider_type=ProviderType.MOCK,
            endpoint=None,
            model_name="mock-v1",
            is_available=True,
            context_size=4096,
            vram_mb=0,
        )

    def get_provider_type(self) -> ProviderType:
        return ProviderType.MOCK


# S269: модульный дефолт эндуранс-конфига. Лаборатория DriftLab задаёт
# delay=0/streaming=False для endurance-режима. Поведение по умолчанию
# не меняется (None → дефолтная MockConfig внутри MockProvider).
_default_endurance_config: MockConfig | None = None


def create_mock_provider(config: MockConfig | None = None) -> MockProvider:
    """Фабричная функция для создания Mock провайдера."""
    return MockProvider(config or _default_endurance_config)

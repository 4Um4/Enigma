"""
Запуск через backend: pytest backend/tests/test_intent_compressor.py
Тесты для IntentCompressor — модуля, который превращает текст игрока в структурированный Intent.
Покрывает как Fast Path (лемматизация + эвристики), так и Slow Path (вызов LLM). Проверяет корректность обработки, устойчивость к ошибкам и валидацию данных.

TODO: добавить тесты на edge cases, например, очень длинные команды, команды с нецензурной лексикой, команды на разных языках и т.д.

"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from backend.app.domain.intent_profile import ActionType, SemanticAmbiguity
from backend.app.services.input.intent_compressor import IntentCompressor


@pytest.fixture
def mock_llm_client():
    return AsyncMock()


@pytest.fixture
def compressor(mock_llm_client):
    return IntentCompressor(llm_client=mock_llm_client)


def test_fast_path_lemmatization(compressor, mock_llm_client):
    """Fast Path парсит MOVE через pymorphy3 лемматизацию без вызова LLM"""
    result = asyncio.run(compressor.compress("я медленно подхожу к нему", {}))

    assert result.action_type == ActionType.MOVE
    assert result.physical_force < 0.3  # "медленно" снижает физику
    assert result.ambiguity == SemanticAmbiguity.PARTIAL
    mock_llm_client.compress_intent.assert_not_called()


def test_slow_path_mock(compressor, mock_llm_client):
    """Slow Path корректно парсит сложный текст с замоканным LLM"""
    mock_llm_client.compress_intent.return_value = {
        "action_type": "ATTACK",
        "target_reference": "борко",
        "target_zone": "HEAD",
        "physical_force": 0.9,
        "emotional_charge": 0.8,
        "social_pressure": 0.1,
        "commitment_level": 1.0,
        "tool_reference": "кружка",
        "semantic": {"aggression": 0.9, "fear": 0.1, "shame": 0.0, "confidence": 0.8, "desperation": 0.2},
    }

    # Используем глагол, которого нет в Fast Path, чтобы гарантированно попасть в LLM
    result = asyncio.run(compressor.compress("я со всей дури оскорбляю борко кружкой по лицу", {}))

    assert result.action_type == ActionType.ATTACK
    assert result.target_reference == "борко"  # Строка, не ID!
    assert result.tool_reference == "кружка"
    assert result.physical_force == 0.9
    assert result.semantic.aggression == 0.9


def test_llm_failure(compressor, mock_llm_client):
    """При падении LLM система не крашится и не лжет (OBSERVE), а возвращает AMBIGUOUS"""
    mock_llm_client.compress_intent.return_value = None  # LLM сломалась

    # Используем глагол, которого нет в Fast Path
    result = asyncio.run(compressor.compress("я уничтожаю всех", {}))

    assert result.action_type == ActionType.UNCERTAIN
    assert result.ambiguity == SemanticAmbiguity.AMBIGUOUS
    assert result.confidence.action == 0.1


def test_dto_validation(compressor, mock_llm_client):
    """Неверные значения от LLM отсекаются Pydantic"""
    mock_llm_client.compress_intent.return_value = {
        "action_type": "ATTACK",
        "physical_force": 5.0,  # Нарушение ge=0.0, le=1.0
        "emotional_charge": "very_high",  # Не тот тип
    }

    # Используем глагол, которого нет в Fast Path
    result = asyncio.run(compressor.compress("я критикую его", {}))

    # Pydantic должен выкинуть ошибку валидации, уронив в except блок
    assert result.action_type == ActionType.UNCERTAIN
    assert result.ambiguity == SemanticAmbiguity.AMBIGUOUS

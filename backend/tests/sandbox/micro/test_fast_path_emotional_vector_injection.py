"""
path: backend/tests/sandbox/micro/test_fast_path_emotional_vector_injection.py
Назначение: Верификация ADR-088 (Fast path инжектит эмоциональный вектор для ATTACK)
Зависимости: app.services.input.intent_compressor, app.domain.intent_profile
Основные сущности: IntentCompressor, EmotionalVector

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_fast_path_emotional_vector_injection.py -v --tb=short; cd ..
"""

from unittest.mock import MagicMock

from app.domain.intent_profile import ActionType
from app.services.input.intent_compressor import IntentCompressor


def test_fast_path_emotional_vector_injection():
    """ДОКАЗЫВАЕТ: Fast path инжектит ненулевой EmotionalVector для ATTACK (ADR-088).

    Без этого NPC не испытывают агрессию при атаке — тихий каузальный сбой.
    Возврат дефолтного EmotionalVector() (aggression=0.0) для ATTACK запрещён.
    """
    # Мокаем LLM клиент, так как fast path работает без него
    mock_client = MagicMock()
    compressor = IntentCompressor(mock_client)

    # Вызываем fast path с текстом, содержащим леммы атаки
    result = compressor._fast_path_parse("атаковать врага ударить")

    assert result is not None, "Fast path не распознал намерение атаки"
    assert result.action_type == ActionType.ATTACK, f"Ожидался ATTACK, получен {result.action_type}"

    # ADR-088: Вектор эмоций НЕ должен быть нулевым для ATTACK
    assert result.semantic.aggression > 0.0, (
        f"ADR-088 Нарушено: EmotionalVector для ATTACK имеет нулевую агрессию (aggression={result.semantic.aggression})"
    )

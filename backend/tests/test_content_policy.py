# backend/tests/test_content_policy.py
"""
Тесты системы управления контентом (Content Policy & Voice Archetypes).
Проверяет:
1. Глобальный фильтр мата (ContentPolicy OFF vs EXPLICIT).
2. Загрузку VoiceArchetype из YAML и переопределение voice_profile в NPCProfileL0.

Запуск: cd backend; python -m pytest tests/test_content_policy.py -v -p no:cacheprovider; cd ..
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.core.config import settings
from app.core.content_policy import ContentPolicy, ContentLevel
from app.services.verbalization.dm_response_normalizer import DMResponseNormalizer

# --- Тест 1: Глобальный фильтр мата ---

def test_profanity_filter_blocks_when_off():
    """Если ContentPolicy OFF, мат заменяется на fallback."""
    # Создаём мок settings, у которого content_policy возвращает OFF
    mock_settings = MagicMock()
    mock_settings.content_policy = ContentPolicy.preset_off()
    
    # Патчим импорт settings внутри normalizer
    with patch("app.core.config.settings", mock_settings):
        text = "Иди ты нахуй, мудак!"
        filtered = DMResponseNormalizer._apply_content_policy_filter(text)
        assert "нахуй" not in filtered
        assert "мудак" not in filtered
        assert filtered in [
            "Происходит неловкое молчание.",
            "Собеседник замолкает, подбирая слова.",
            "В воздухе повисает напряжение."
        ]

def test_profanity_filter_allows_when_explicit():
    """Если ContentPolicy EXPLICIT, мат проходит."""
    mock_settings = MagicMock()
    mock_settings.content_policy = ContentPolicy.preset_explicit()
    
    with patch("app.core.config.settings", mock_settings):
        text = "Иди ты нахуй, мудак!"
        filtered = DMResponseNormalizer._apply_content_policy_filter(text)
        assert filtered == text

# --- Тест 2: Интеграция VoiceArchetype в NPC ---

def test_tornin_loads_gruff_veteran_archetype():
    """Проверяет, что npc_loader подменяет voice_profile Торнина на YAML из архетипа gruff_veteran."""
    from app.services.npc.npc_loader import load_npc_profiles_from_config
    
    profiles = load_npc_profiles_from_config()
    tornin = profiles.get("tavern_keeper_tornin")
    assert tornin is not None, "Торнин не найден в загруженных профилях"
    
    # Проверяем, что ID архетипа подхватился
    assert tornin.voice_archetype_id == "gruff_veteran"
    
    # Проверяем, что voice_profile взят из YAML (там есть ключевое слово "бывший солдат")
    assert "бывший солдат" in tornin.voice_profile
    # Убеждаемся, что это не тот текст, что был в JSON
    assert tornin.voice_profile != "Говоришь ровно, с лёгкой хрипотцой. Короткие предложения. Не объясняешься. Если не хочешь говорить — молчишь и утираешь стакан."

def test_shadow_loads_cold_professional_archetype():
    """Проверяет, что Тень получает холодный профиль."""
    from app.services.npc.npc_loader import load_npc_profiles_from_config
    
    profiles = load_npc_profiles_from_config()
    shadow = profiles.get("thief_shadow")
    assert shadow is not None, "Тень не найдена в загруженных профилях"
    
    assert shadow.voice_archetype_id == "cold_professional"
    assert "удар стилета" in shadow.voice_profile
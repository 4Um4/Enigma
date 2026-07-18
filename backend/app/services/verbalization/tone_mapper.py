"""
path: /project/backend/app/services/verbalization/tone_mapper.py
Назначение: Единая точка маппинга emotional_state (RU) в tone (EN) для TaskScheduler и Materializer. Защищает от Double Truth.
Зависимости: logging
Основные сущности: ToneMapper
"""

import logging

logger = logging.getLogger(__name__)

class ToneMapper:
    """Маппит русские emotional_state (из CommunicationIntent) в английские tone (для NpcDialogueSubscriber)."""

    _MAP = {
        "злость": "ANGRY",
        "страх": "FEARFUL",
        "паника": "PANIC",
        "радость": "FRIENDLY",
        "любопытство": "CURIOUS",
        "отвращение": "ANGRY",
        "удивление": "CURIOUS",
        "грусть": "SAD",
        "neutral": "NEUTRAL",
        "none": "NEUTRAL",
        "нейтрально": "NEUTRAL",
    }

    @staticmethod
    def map(emotional_state: str | None) -> str:
        """Возвращает tone. Если emotional_state отсутствует или неизвестен — логирует fallback и возвращает NEUTRAL."""
        if not emotional_state:
            logger.debug("[TONE_MAPPER] emotional_state is None/empty. Fallback to NEUTRAL.")
            return "NEUTRAL"
        
        _state_lower = emotional_state.lower()
        if _state_lower in ToneMapper._MAP:
            return ToneMapper._MAP[_state_lower]
        
        logger.warning(f"[TONE_MAPPER] Unknown emotional_state '{emotional_state}'. Fallback to NEUTRAL.")
        return "NEUTRAL"
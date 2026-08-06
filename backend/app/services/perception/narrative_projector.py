"""
path: /project/backend/app/services/perception/narrative_projector.py
Назначение: Эпистемический фильтр для реплик. Превращает сырые события в PerceivedNarrativeDTO.
Зависимости: app.domain.presentation, math
Основные сущности: NarrativeProjector
"""
import math
import logging
from typing import List, Dict, Any
from app.domain.presentation import (
    PerceivedNarrativeDTO, 
    PerceptionContext,
    AvatarPerceptionProfile
)
from app.services.perception.auditory_distortion_policy import AuditoryDistortionPolicy

logger = logging.getLogger(__name__)

# S159: Вынесены из хардкода в конфигурацию радиусов
PERCEPTION_CLEAR_RADIUS = 5.0
PERCEPTION_PARTIAL_RADIUS = 10.0
PERCEPTION_MAX_RADIUS = 15.0

class NarrativeProjector:
    """
    Инжектируется в GameLoop. Принимает чистый PerceptionContext и сырые диалоги.
    Не генерирует event_id (ожидает его в raw_dialogues).
    """
    def __init__(self):
        self._distortion = AuditoryDistortionPolicy()

    def project(
        self, 
        raw_dialogues: List[Dict], 
        context: PerceptionContext
    ) -> List[PerceivedNarrativeDTO]:
        if not raw_dialogues:
            return []

        narratives: List[PerceivedNarrativeDTO] = []
        p_x, p_y = context.player_position
        stability = context.avatar_profile.perceptual_stability

        for d in raw_dialogues:
            speaker_id = d.get("speaker_id")
            text = d.get("text", "")
            event_id = d.get("event_id", "") # Ожидаем event_id снаружи!
            
            dist = 999.0
            if speaker_id and speaker_id in context.speaker_positions:
                s_x, s_y = context.speaker_positions[speaker_id]
                dist = math.sqrt((p_x - s_x)**2 + (p_y - s_y)**2)

            if dist <= PERCEPTION_CLEAR_RADIUS:
                perception_certainty = 0.9 * stability
                auditory_clarity = 0.9 * stability
            elif dist <= PERCEPTION_PARTIAL_RADIUS:
                perception_certainty = 0.5 * stability
                auditory_clarity = 0.4 * stability
            elif dist <= PERCEPTION_MAX_RADIUS:
                perception_certainty = 0.2 * stability
                auditory_clarity = 0.1 * stability
            else:
                perception_certainty = 0.0
                auditory_clarity = 0.0

            visible_text = self._distortion.distort(text, auditory_clarity)

            narratives.append(PerceivedNarrativeDTO(
                event_id=event_id,
                speaker_id=speaker_id,
                visible_text=visible_text,
                perception_certainty=max(0.0, min(1.0, perception_certainty)),
                auditory_clarity=max(0.0, min(1.0, auditory_clarity)),
                delivery_type="NORMAL"
            ))

        return narratives
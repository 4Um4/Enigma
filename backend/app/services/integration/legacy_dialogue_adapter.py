"""
path: /project/backend/app/services/integration/legacy_dialogue_adapter.py
Назначение: Адаптер для обратной совместимости. Превращает PerceivedNarrativeDTO в старый dict для recent_dialogues.
Зависимости: app.domain.presentation
Основные сущности: LegacyDialogueAdapter
"""
from typing import List, Dict, Any
from app.domain.presentation import PerceivedNarrativeDTO
from app.domain.snapshot import RecentDialogueDTO

class LegacyDialogueAdapter:
    """
    Превращает новые PerceivedNarrativeDTO в старый формат RecentDialogueDTO,
    который сейчас ожидает фронтенд в recent_dialogues.
    """
    @staticmethod
    def to_legacy_dto(narratives: List[PerceivedNarrativeDTO]) -> List[RecentDialogueDTO]:
        result = []
        for n in narratives:
            result.append(RecentDialogueDTO(
                speaker_id=n.speaker_id or "unknown",
                text=n.visible_text,
                exposure=n.delivery_type.lower(),
                timestamp=0.0
            ))
        return result
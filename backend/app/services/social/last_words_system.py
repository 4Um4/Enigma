"""
Файл: backend/app/services/social/last_words_system.py
Назначение: Подбор цитаты на основе судьбы и отношений.
Зависимости: typing, app.models.last_words, app.models.fate, app.models.social_fabric
"""

from typing import Dict, Optional

from app.models.fate import FateOutcome
from app.models.last_words import LastWord, LastWordTone
from app.services.social.social_fabric_tracker import SocialFabricTracker


class LastWordsSystem:
    """Подбирает финальные реплики для NPC."""

    # База цитат (MVP)
    _QUOTES = {
        "maid_lusya": {
            FateOutcome.ESCAPE: "Спасибо. Я никогда не забуду, что ты сделал. Если я когда-нибудь вернусь... нет. Я не вернусь.",
            FateOutcome.DEATH: "(Её нашли в подвале. Она не сопротивлялась.)",
            FateOutcome.BROKEN: "Я не могу. Я больше не могу. Подвал... он всегда будет здесь. И я всегда буду здесь.",
            FateOutcome.LIBERATED: "Я свободна. Впервые за три года я дышу."
        },
        "thief_shadow": {
            FateOutcome.DEATH: "Гильдия не прощает. Ни предателей, ни палачей.",
            FateOutcome.BROKEN: "Ты полезный инструмент. Инструменты ломаются.",
            FateOutcome.LIBERATED: "Ты не полезный. Но ты честный. Это редкость."
        },
        "merchant_goran": {
            FateOutcome.DEATH: "(Его нашли в реке. У него осталась жена и двое детей.)",
            FateOutcome.LIBERATED: "Ты спас мне жизнь. Я не забуду. Если тебе когда-нибудь нужен шёлк... приходи.",
            FateOutcome.BROKEN: "Всё кончено. Гильдия заберёт всё. Моя семья... что будет с ними?"
        }
    }

    def get_last_word(
        self,
        npc_id: str,
        fate: Optional[FateOutcome],
        social_fabric: SocialFabricTracker
    ) -> Optional[LastWord]:
        """Возвращает финальную цитату, если она есть для данной судьбы."""
        if not fate:
            return None

        npc_quotes = self._QUOTES.get(npc_id, {})
        quote = npc_quotes.get(fate)

        if not quote:
            return None

        # Определяем тон на основе отношений к игроку
        snap = social_fabric.get_current(npc_id, "player")
        tone = LastWordTone.SILENT
        if snap:
            if snap.trust > 50:
                tone = LastWordTone.GRATEFUL
            elif snap.fear > 60:
                tone = LastWordTone.BITTER
            elif snap.trust < -40:
                tone = LastWordTone.BROKEN

        return LastWord(npc_id=npc_id, quote=quote, tone=tone)

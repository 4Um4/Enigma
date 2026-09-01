"""
Назначение: EMRL E1.2 — долговременный кристалл смысла; триплет + доверие + происхождение; распад confidence, не знания; retrieval_strength ≠ confidence
Зависимости: dataclasses, math
Основные сущности: MemoryCrystal
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MemoryCrystal:
    """EMRL E1.2: долговременное знание NPC — лёгкий кристалл смысла.

    ДОМЕН-РАЗДЕЛЕНИЕ (§13.3, прецедент ADR-O-305): это СЕМАНТИЧЕСКИЙ
    кристалл (memory-домен): «NPC знает факты о мире/агентах».
    Аффективный аналог — CrystallizedBelief (identity-домен, L2.5:
    «NPC боится/доверяет источнику», живой конвейер BeliefCrystallization).
    Пересечений полей нет, владельцы разные; склейка обоих следов —
    задача E2-консолидации через related_episodes (общий источник —
    эпизоды EventMemory).

    Отличия от EventMemory (эпизода):
    — эпизод хранит ЧТО СЛУЧИЛОСЬ, кристалл — ЧТО NPC ЗНАЕТ;
    — кристаллы не имеют стадийных зон (урок E1.1): единственный
      распадающийся параметр — confidence (уверенность), знание
      не удаляется никогда;
    — retrieval_strength (доступность) ≠ confidence (уверенность):
      припоминание растит доступность, НЕ истинность — ложный слух,
      часто вспоминаемый, остаётся доступным, но не становится
      «увереннее» (мандат, §о confidence).

    Идемпотентность происхождения (урок 9.6): origin_reference делает
    легальными два одинаковых триплета от разных источников («Игрок
    храбр» от Горана ≠ «Игрок храбр» от Люси) — они не схлопываются.
    """

    # Триплет знания
    subject: str          # "player"
    predicate: str        # "occupation"
    object: str           # "geologist"

    # Происхождение
    source: str           # npc_id, от которого знание получено
    origin_reference: str # дайджест источника (episode/consolidation)
    related_episodes: Tuple[str, ...] = ()  # id эпизодов-подтверждений

    # Доверие (два независимых измерения)
    confidence: float = 0.5          # 0..1 — уверенность в истинности
    retrieval_strength: float = 0.5  # 0..1 — доступность припоминания

    # Эмоциональная окраска знания
    emotional_weight: float = 0.0    # -1..+1

    # Время жизни
    last_reinforced: int = 0         # tick последнего подкрепления
    times_recalled: int = 0

    # Кто владеет кристаллом (нужно для PK таблицы; в DTO — для
    # самодостаточности round-trip)
    owner_id: str = ""
    campaign_id: str = ""

    def decayed(self, game_days: float = 1.0, rate: float = 0.005) -> "MemoryCrystal":
        """E1.2 semantic-decay: только confidence, только мультипликативно.

        Знание бессмертно: возвращается НОВЫЙ кристалл с меньшей
        уверенностью; subject/predicate/object нетронуты. Долгий
        горизон: при rate=0.005 и 30 днях confidence ×0.86 —
        столетняя история не обязана забываться в неделю.
        retrieval_strength НЕ распадается: доступность — функция
        припоминаний (times_recalled), не времени.
        """
        return MemoryCrystal(
            subject=self.subject,
            predicate=self.predicate,
            object=self.object,
            source=self.source,
            origin_reference=self.origin_reference,
            related_episodes=self.related_episodes,
            confidence=max(
                0.0, min(1.0, self.confidence * math.exp(-rate * game_days))
            ),
            retrieval_strength=self.retrieval_strength,
            emotional_weight=self.emotional_weight,
            last_reinforced=self.last_reinforced,
            times_recalled=self.times_recalled,
            owner_id=self.owner_id,
            campaign_id=self.campaign_id,
        )

    def recalled(self) -> "MemoryCrystal":
        """Припоминание: +доступность, БЕЗ изменения confidence.

        Механика активации: retrieval_strength → min(1.0, +0.1),
        times_recalled +1. Уверенность не трогаем — см. docstring класса.
        Подкрепление уверенности — только независимым свидетельством
        (consolidation в E2), не повторным припоминанием.
        """
        return MemoryCrystal(
            subject=self.subject,
            predicate=self.predicate,
            object=self.object,
            source=self.source,
            origin_reference=self.origin_reference,
            related_episodes=self.related_episodes,
            confidence=self.confidence,
            retrieval_strength=min(1.0, self.retrieval_strength + 0.1),
            emotional_weight=self.emotional_weight,
            last_reinforced=self.last_reinforced,
            times_recalled=self.times_recalled + 1,
            owner_id=self.owner_id,
            campaign_id=self.campaign_id,
        )

    def crystal_id(self) -> str:
        """Идентичность кристалла: триплет + происхождение (без confidence!)."""
        return f"{self.subject}:{self.predicate}:{self.origin_reference}"
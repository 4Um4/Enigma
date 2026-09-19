"""
Файл: backend/app/models/end_screen.py
Назначение: DTO для финального экрана результатов.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.models.cognitive_dissonance import Contradiction
from app.models.evaluation import EvaluationResult
from app.models.last_words import LastWord


@dataclass(frozen=True)
class NpcFateScreenData:
    """Данные о судьбе NPC для экрана результатов."""
    npc_id: str
    fate_outcome: str
    last_word: Optional[LastWord]

@dataclass(frozen=True)
class EndScreenData:
    """Полный набор данных для финального экрана (UI Layer)."""
    evaluation: EvaluationResult
    npc_fates: List[NpcFateScreenData]
    contradictions: List[Contradiction]
    verdict_text: str = ""
    fate_texts: List[str] = field(default_factory=list)
    relationship_texts: List[str] = field(default_factory=list)

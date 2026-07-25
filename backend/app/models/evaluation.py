"""
Файл: backend/app/models/evaluation.py
Назначение: Структура результата оценки игрока.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class SecretEvaluation:
    """Оценка одного секрета."""
    secret_id: str
    net_confidence: float       # -1.0..1.0 (signed epistemic confidence)
    was_correct: bool           # True если игрок был уверен и прав
    was_misidentified: bool     # True если игрок был уверен, но ошибался (FALSE вместо TRUE)
    discovery_methods: Tuple[str, ...] # Все методы, использованные для обнаружения

@dataclass(frozen=True)
class EvaluationResult:
    """Итоговый результат сравнения PlayerBeliefModel vs TruthState."""
    secrets_total: int
    secrets_identified: int      # Уверенно и правильно
    secrets_misidentified: int   # Уверенно и неправильно
    secrets_missed: int          # Не заметил (UNKNOWN или нет данных)

    # P7-08 FIX: Каузальные связи требуют отдельной модели (PlayerCausalModel).
    # Пока что мы не оцениваем их, чтобы не делать ложных эвристик.
    causal_links_total: int
    causal_links_identified: int

    methods_used: Dict[str, int] # {"dialogue": 5, "blackmail": 1}

    per_secret_results: List[SecretEvaluation]

    @property
    def score(self) -> int:
        """Итоговый счёт 0..100."""
        if self.secrets_total == 0:
            return 0
        raw = (self.secrets_identified * 10) - (self.secrets_misidentified * 5) + (self.causal_links_identified * 2)
        return max(0, min(100, raw))

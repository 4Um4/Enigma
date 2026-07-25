"""
Файл: backend/app/models/truth_state.py
Назначение: Неизменяемая доменная модель объективной истины квеста.
Зависимости: dataclasses, enum, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Set, Tuple


class RelationType(str, Enum):
    """Семантические типы связей между секретами."""
    CAUSES = "CAUSES"           # A является причиной B
    CONTRADICTS = "CONTRADICTS" # A противоречит B
    DEPENDS_ON = "DEPENDS_ON"   # A зависит от B
    REVEALS = "REVEALS"         # A раскрывает B
    CONCEALS = "CONCEALS"       # A скрывает B
    ENABLES = "ENABLES"         # A делает возможным B
    EXPLAINS = "EXPLAINS"       # A объясняет B

@dataclass(frozen=True)
class Secret:
    secret_id: str
    npc_id: str # Deprecated: использовать participants
    participants: Tuple[str, ...]
    category: str
    canonical_truth: str
    importance: float
    initial_holders: Tuple[str, ...]
    discovery_surface: Tuple[str, ...] # Как это можно обнаружить

@dataclass(frozen=True)
class TruthRelation:
    source_secret_id: str
    target_secret_id: str
    relation_type: RelationType
    strength: float

@dataclass(frozen=True)
class TruthState:
    """Полная карта правды мира. Доступна ТОЛЬКО EvaluationEngine."""
    secrets: Mapping[str, Secret] = field(default_factory=dict)
    relations: Tuple[TruthRelation, ...] = field(default_factory=tuple)

    def get_secret(self, secret_id: str) -> Secret:
        return self.secrets[secret_id]

    def get_relations_for(self, secret_id: str) -> List[TruthRelation]:
        return [r for r in self.relations if r.source_secret_id == secret_id or r.target_secret_id == secret_id]

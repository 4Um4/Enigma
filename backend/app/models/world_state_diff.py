"""
Файл: backend/app/models/world_state_diff.py
Назначение: Снапшот изменений мира для передачи в следующую кампанию.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class WorldContinuityMode(str, Enum):
    """Режим наследования мира между кампаниями."""
    ISOLATED = "isolated"     # Каждый забег — чистый мир (по умолчанию)
    PERSISTENT = "persistent" # Последствия переходят в следующую кампанию

@dataclass(frozen=True)
class WorldStateDiff:
    """Снапшот изменений мира (результат забега).
    Применяется к следующей кампании ТОЛЬКО если mode == PERSISTENT.
    """
    npc_fates: Dict[str, str]             # {npc_id: fate_outcome}
    relationship_changes: Dict[str, Dict[str, float]] # {npc_id: {"trust": -20, "fear": 30}}
    faction_alignments: Dict[str, float]  # {faction_id: alignment}
    secrets_exposed: Dict[str, bool]      # {secret_id: True/False}
    world_events: List[str]               # ["goran_killed", "lusya_escaped"]
    player_reputation: Dict[str, str]     # {faction_id: "ally"/"enemy"/"unknown"}

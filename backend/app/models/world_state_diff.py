"""
Файл: backend/app/models/world_state_diff.py
Назначение: Снапшот изменений мира для передачи в следующую кампанию.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

@dataclass(frozen=True)
class WorldStateDiff:
    """Строго типизированный порт причинных последствий между жизненными циклами мира.
    Применяется к следующей кампании ТОЛЬКО если mode == WorldContinuityMode.CONTINUOUS.
    """
    npc_fates: Dict[str, str]             # {npc_id: fate_outcome}
    faction_alignments: Dict[str, float]  # {faction_id: alignment}
    secrets_exposed: Dict[str, bool]      # {secret_id: True/False}
    world_events: List[str]               # ["goran_killed", "lusya_escaped"]
    player_reputation: Dict[str, str]     # {faction_id: "ally"/"enemy"/"unknown"}

"""
Файл: backend/app/contracts/interventions.py
Назначение: Внешний входной протокол системы. Ядро симуляции не знает источника данных.
Зависимости: стандартная библиотека Python.
Основные сущности: InterventionEven
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict

@dataclass(frozen=True)
class InterventionEvent:
    """Внешнее вмешательство в мир (TZ-08 v0.2).

    Ядро симуляции (TickOrchestrator) не знает 'player', 'CK successor' или 'world_scheduler'.
    Ядро обрабатывает interventions как недифференцированный data stream.
    Любая семантическая классификация переносится в downstream-слои.
    """
    source: str
    payload: Dict[str, Any]
    tick: int

    @classmethod
    def from_player_action(
        cls,
        action_text: str,
        player_name: str,
        tick: int,
        **kwargs
    ) -> "InterventionEvent":
        """Factory для player actions (backward compat для GameLoop)."""
        return cls(
            source="player",
            payload={"text": action_text, "player_name": player_name, **kwargs},
            tick=tick,
        )
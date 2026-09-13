# path: /project/backend/app/models/player_epistemic_state.py
"""
Файл: backend/app/models/player_epistemic_state.py
Назначение: P6 — PlayerEpistemicState: минимальный стейт уровней знания
    игрока (ТЗ-P6; НЕ PlayerCausalModel). Runtime между тиками;
    персистентность — P11 (вне P6).
Законы:
    - монотонность: только вверх (2->1 — вне MVP, CONTRADICTS "позже")
    - идемпотентность: повторный REVEAL не меняет уровень
Зависимости: app.domain.player_epistemics
Основные сущности: PlayerEpistemicState
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.domain.player_epistemics import (
    CLUE,
    IDENTIFIED,
    UNKNOWN,
    LevelChangeEvent,
    PlayerObservation,
    SurfaceEvent,
)


@dataclass
class PlayerEpistemicState:
    """Уровни 0/1/2 по секретам + наблюдения (SSOT игрок-петли)."""

    levels: dict = field(default_factory=dict)  # secret_id -> int (0/1/2)
    observations: List[PlayerObservation] = field(default_factory=list)

    def level(self, secret_id: str) -> int:
        """Текущий уровень (UNKNOWN, если секрета никогда не касались)."""
        return self.levels.get(secret_id, UNKNOWN)

    def raise_level(
        self, secret_id: str, to_level: int, source_event: SurfaceEvent
    ) -> Optional[LevelChangeEvent]:
        """Монотонный подъём уровня.

        Возвращает LevelChangeEvent ТОЛЬКО при реальном переходе
        (идемпотентность); to_level <= текущего -> None.
        """
        current = self.level(secret_id)
        if to_level <= current:
            return None
        if to_level not in (CLUE, IDENTIFIED):
            raise ValueError(
                f"[PLAYER_EPISTEMIC] недопустимый уровень: {to_level}"
            )
        self.levels[secret_id] = to_level
        return LevelChangeEvent(
            secret_id=secret_id,
            from_level=current,
            to_level=to_level,
            tick=source_event.tick,
            surface_kind=source_event.kind,
        )

    def add_observation(self, observation: PlayerObservation) -> None:
        self.observations.append(observation)

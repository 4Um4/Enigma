"""
Файл: backend/app/models/faction.py
Назначение: Состояние лояльности игрока к фракции.
Зависимости: dataclasses, typing
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactionAlignment:
    """Лояльность игрока к конкретной фракции."""
    faction_id: str
    alignment: float # -100..100 (отрицательный = враг, положительный = союзник)
    known_to_faction: bool # Знает ли фракция о действиях игрока

    def __post_init__(self) -> None:
        if not -100.0 <= self.alignment <= 100.0:
            raise ValueError("alignment must be in [-100, 100]")

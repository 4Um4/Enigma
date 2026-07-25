"""
Файл: backend/app/services/social/faction_alignment_tracker.py
Назначение: Отслеживание и обновление лояльности фракций.
Зависимости: typing, app.models.faction
"""

from typing import Dict, List, Optional

from app.models.faction import FactionAlignment


class FactionAlignmentTracker:
    """Отслеживает лояльность игрока к фракциям."""

    def __init__(self) -> None:
        self._alignments: Dict[str, FactionAlignment] = {}

    def set_initial(self, faction_id: str, alignment: float = 0.0, known: bool = False) -> None:
        """Устанавливает начальную лояльность."""
        if faction_id in self._alignments:
            raise ValueError(f"Initial alignment for {faction_id} already set.")
        self._alignments[faction_id] = FactionAlignment(
            faction_id=faction_id,
            alignment=alignment,
            known_to_faction=known
        )

    def apply_delta(self, faction_id: str, delta: float, known: bool = True) -> FactionAlignment:
        """Обновляет лояльность фракции на основе действия игрока."""
        current = self._alignments.get(faction_id)
        if not current:
            # Если фракция не инициализирована, создаём с нуля
            current = FactionAlignment(faction_id=faction_id, alignment=0.0, known_to_faction=False)

        new_alignment = max(-100.0, min(100.0, current.alignment + delta))

        # Если действие известно фракции, фракция теперь знает об игроке
        new_known = current.known_to_faction or known

        updated = FactionAlignment(
            faction_id=faction_id,
            alignment=new_alignment,
            known_to_faction=new_known
        )
        self._alignments[faction_id] = updated
        return updated

    def get_alignment(self, faction_id: str) -> Optional[FactionAlignment]:
        return self._alignments.get(faction_id)

    def get_all(self) -> List[FactionAlignment]:
        return list(self._alignments.values())

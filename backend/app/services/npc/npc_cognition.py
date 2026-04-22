# backend/app/services/npc/npc_cognition.py
"""
Утилиты анализа драйвов NPC.

Используется в psyche_engine.py для определения доминирующего драйва.
"""
from typing import Dict


def normalize_drives(drives: Dict[str, float]) -> Dict[str, float]:
    """Нормализует драйвы к сумме 1.0."""
    total = sum(drives.values())
    if total <= 0:
        return {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
    return {k: round(v / total, 4) for k, v in drives.items()}


def get_dominant_drive(drives: Dict[str, float]) -> str:
    """Возвращает ключ с максимальным значением."""
    return max(drives, key=drives.get)

"""
Файл: backend/app/services/social/social_fabric_tracker.py
Назначение: Отслеживание матрицы отношений и истории изменений.
Зависимости: typing, app.models.social_fabric
"""

from typing import Dict, List, Optional, Tuple

from app.models.social_fabric import RelationshipDelta, RelationshipSnapshot


class SocialFabricTracker:
    """Отслеживает матрицу NPC->NPC (и Player->NPC) отношений и их дельты."""

    def __init__(self) -> None:
        self._baseline: Dict[Tuple[str, str], RelationshipSnapshot] = {}
        self._current: Dict[Tuple[str, str], RelationshipSnapshot] = {}
        self._deltas: List[RelationshipDelta] = []

    def set_baseline(self, source_id: str, target_id: str, snapshot: RelationshipSnapshot) -> None:
        """Устанавливает базовое состояние. Выбрасывает ошибку при повторной установке."""
        key = (source_id, target_id)
        if key in self._baseline:
            raise ValueError(f"Baseline for {key} already exists and cannot be overwritten.")
        self._baseline[key] = snapshot
        self._current[key] = snapshot

    def get_current(self, source_id: str, target_id: str) -> Optional[RelationshipSnapshot]:
        return self._current.get((source_id, target_id))

    def apply_delta(
        self,
        tick: int,
        source_id: str,
        target_id: str,
        trust_delta: float = 0.0,
        fear_delta: float = 0.0,
        affection_delta: float = 0.0,
        cause: str = "unknown",
        description: str = ""
    ) -> RelationshipDelta:
        """Применяет изменение к отношениям и записывает в историю."""
        key = (source_id, target_id)
        current = self._current.get(key)

        new_trust = (current.trust if current else 0.0) + trust_delta
        new_fear = (current.fear if current else 0.0) + fear_delta
        new_affection = (current.affection if current else 0.0) + affection_delta

        # Clamp values
        new_trust = max(-100.0, min(100.0, new_trust))
        new_fear = max(0.0, min(100.0, new_fear))
        new_affection = max(-100.0, min(100.0, new_affection))

        # Сохраняем debt и respect из текущего состояния (они не меняются дельтами напрямую в MVP)
        debt = current.debt if current else 0.0
        respect = current.respect if current else 0.0

        updated_snapshot = RelationshipSnapshot(
            source_id=source_id,
            target_id=target_id,
            trust=new_trust,
            fear=new_fear,
            affection=new_affection,
            debt=debt,
            respect=respect
        )
        self._current[key] = updated_snapshot

        delta = RelationshipDelta(
            tick=tick,
            source_id=source_id,
            target_id=target_id,
            trust_delta=trust_delta,
            fear_delta=fear_delta,
            affection_delta=affection_delta,
            cause=cause,
            description=description
        )
        self._deltas.append(delta)
        return delta

    def get_all_deltas(self) -> List[RelationshipDelta]:
        return list(self._deltas)

    def get_deltas_for(self, source_id: str, target_id: str) -> List[RelationshipDelta]:
        return [d for d in self._deltas if d.source_id == source_id and d.target_id == target_id]

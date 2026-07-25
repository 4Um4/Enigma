"""
Файл: backend/app/services/player_cognition/observation_log.py
Назначение: Логирование и хранение наблюдений.
Зависимости: typing, app.models.observation
"""

from typing import Dict, List, Optional

from app.models.observation import EvidenceLink, EvidencePolarity, Observation, ObservationSourceType


class ObservationLog:
    """Лог сырых наблюдений игрока и их канонических связей (Evidence)."""

    def __init__(self) -> None:
        self._observations: List[Observation] = []
        self._evidence: List[EvidenceLink] = []
        self._next_id: int = 1

    def add(
        self,
        tick: int,
        observation_type: str,
        content: str,
        source_id: Optional[str] = None,
        source_type: ObservationSourceType = ObservationSourceType.UNKNOWN
    ) -> Observation:
        """Добавляет сырую наблюдение в лог."""
        obs = Observation(
            observation_id=self._next_id,
            tick=tick,
            observation_type=observation_type,
            source_id=source_id,
            source_type=source_type,
            content=content
        )
        self._observations.append(obs)
        self._next_id += 1
        return obs

    def add_evidence(self, observation_id: int, secret_id: str, evidence_strength: float, polarity: EvidencePolarity = EvidencePolarity.SUPPORTS) -> EvidenceLink:
        """Добавляет каноническую связь наблюдения с секретом."""
        if observation_id not in {o.observation_id for o in self._observations}:
            raise ValueError(f"Observation {observation_id} not found")
        link = EvidenceLink(
            observation_id=observation_id,
            secret_id=secret_id,
            evidence_strength=evidence_strength,
            polarity=polarity
        )
        self._evidence.append(link)
        return link

    def get_all(self) -> List[Observation]:
        """Возвращает все сырые наблюдения."""
        return list(self._observations)

    def get_for_source(self, source_id: str) -> List[Observation]:
        """Возвращает все наблюдения, связанные с конкретным источником (NPC, объектом)."""
        return [obs for obs in self._observations if obs.source_id == source_id]

    def get_evidence_for_secret(self, secret_id: str) -> List[EvidenceLink]:
        """Возвращает все доказательства, намекающие на конкретный секрет."""
        return [ev for ev in self._evidence if ev.secret_id == secret_id]

"""
Файл: backend/app/services/player_cognition/player_belief_model.py
Назначение: Построение и обновление убеждений игрока на основе EvidenceLink.
Зависимости: typing, app.models.player_belief, app.models.observation
"""

from typing import Dict, List, Optional, Tuple

from app.models.observation import EvidenceLink, EvidencePolarity, Observation
from app.models.player_belief import BeliefValue, PlayerBelief


class PlayerBeliefModel:
    """Реконструированная модель мира игрока. Строится неведомо для него."""

    def __init__(self) -> None:
        self._beliefs: Dict[str, PlayerBelief] = {}
        self._processed_evidence: set = set()
        self._processed_observations: Dict[str, set] = {} # secret_id -> set of obs_ids

    def update_from_evidence(self, observation: Observation, evidence: EvidenceLink) -> PlayerBelief:
        """Обновляет убеждение на основе нового доказательства. Идемпотентно."""
        secret_id = evidence.secret_id
        obs_id = observation.observation_id

        # Строгий ключ идемпотентности: (observation_id, secret_id, polarity)
        ev_key = (obs_id, secret_id, evidence.polarity)
        if ev_key in self._processed_evidence:
            return self._beliefs.get(secret_id)
        self._processed_evidence.add(ev_key)

        current = self._beliefs.get(secret_id)

        # Симметричное накопление масс
        new_support = current.support_mass if current else 0.0
        new_contradiction = current.contradiction_mass if current else 0.0

        if evidence.polarity == EvidencePolarity.SUPPORTS:
            new_support += evidence.evidence_strength
            new_supporting = (current.supporting_observations if current else ()) + (obs_id,)
            new_contradicting = current.contradicting_observations if current else ()
        else:
            new_contradiction += evidence.evidence_strength
            new_contradicting = (current.contradicting_observations if current else ()) + (obs_id,)
            new_supporting = current.supporting_observations if current else ()

        # Вычисляем net_score
        net_score = new_support - new_contradiction

        if net_score >= 0.8:
            new_value = BeliefValue.TRUE
        elif net_score <= -0.8:
            new_value = BeliefValue.FALSE
        else:
            new_value = BeliefValue.UNKNOWN

        updated_belief = PlayerBelief(
            proposition_id=secret_id,
            belief_value=new_value,
            support_mass=new_support,
            contradiction_mass=new_contradiction,
            supporting_observations=new_supporting,
            contradicting_observations=new_contradicting
        )
        self._beliefs[secret_id] = updated_belief
        return updated_belief

    def register_direct_evidence(self, secret_id: str, polarity: EvidencePolarity, strength: float, evidence_id: str) -> PlayerBelief:
        """Прямая установка доказательства (например, при шантаже игроком).
        Требует явный evidence_id для строгой идемпотентности.
        """
        current = self._beliefs.get(secret_id)

        # Строгий ключ идемпотентности на основе внешнего ID события/действия
        ev_key = (evidence_id, secret_id, polarity)
        if ev_key in self._processed_evidence:
            return current
        self._processed_evidence.add(ev_key)

        new_support = current.support_mass if current else 0.0
        new_contradiction = current.contradiction_mass if current else 0.0

        if polarity == EvidencePolarity.SUPPORTS:
            new_support += strength
        else:
            new_contradiction += strength

        net_score = new_support - new_contradiction

        if net_score >= 0.8:
            new_value = BeliefValue.TRUE
        elif net_score <= -0.8:
            new_value = BeliefValue.FALSE
        else:
            new_value = BeliefValue.UNKNOWN

        belief = PlayerBelief(
            proposition_id=secret_id,
            belief_value=new_value,
            support_mass=new_support,
            contradiction_mass=new_contradiction,
            supporting_observations=current.supporting_observations if current else (),
            contradicting_observations=current.contradicting_observations if current else ()
        )
        self._beliefs[secret_id] = belief
        return belief

    def get_confidence_for_secret(self, secret_id: str) -> float:
        """Возвращает net confidence (support - contradiction)."""
        belief = self._beliefs.get(secret_id)
        return belief.confidence if belief else 0.0

    def get_belief_for_secret(self, secret_id: str) -> Optional[PlayerBelief]:
        return self._beliefs.get(secret_id)

    def get_all_beliefs(self) -> List[PlayerBelief]:
        return list(self._beliefs.values())

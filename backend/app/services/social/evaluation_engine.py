"""
Файл: backend/app/services/social/evaluation_engine.py
Назначение: Сравнение убеждений с истиной.
Зависимости: typing, app.models.evaluation, app.models.truth_state, app.models.player_belief, app.models.observation
"""

from typing import Dict, List, Set

from app.models.evaluation import EvaluationResult, SecretEvaluation
from app.models.player_belief import BeliefValue
from app.models.truth_state import TruthState
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel


class EvaluationEngine:
    """Сравнивает PlayerBeliefModel с TruthState (Post-game only)."""

    def evaluate(
        self,
        truth: TruthState,
        beliefs: PlayerBeliefModel,
        observations: ObservationLog
    ) -> EvaluationResult:
        secrets_total = len(truth.secrets)
        secrets_identified = 0
        secrets_misidentified = 0
        secrets_missed = 0

        per_secret: List[SecretEvaluation] = []
        methods_used: Dict[str, int] = {}

        for secret_id, secret in truth.secrets.items():
            belief = beliefs.get_belief_for_secret(secret_id)
            confidence = belief.confidence if belief else 0.0

            # Собираем все методы, использованные для этого секрета
            ev_list = observations.get_evidence_for_secret(secret_id)
            methods: Set[str] = set()
            for ev in ev_list:
                obs = next((o for o in observations.get_all() if o.observation_id == ev.observation_id), None)
                if obs:
                    methods.add(obs.observation_type)
                    methods_used[obs.observation_type] = methods_used.get(obs.observation_type, 0) + 1

            was_correct = False
            was_misidentified = False

            if (secret_id in truth.discovered_secrets) or \
               (belief and belief.belief_value == BeliefValue.TRUE and confidence >= 0.8):
                secrets_identified += 1
                was_correct = True
            elif belief and belief.belief_value == BeliefValue.FALSE and confidence <= -0.8:
                secrets_misidentified += 1
                was_misidentified = True
            else:
                secrets_missed += 1

            per_secret.append(SecretEvaluation(
                secret_id=secret_id,
                net_confidence=confidence,
                was_correct=was_correct,
                was_misidentified=was_misidentified,
                discovery_methods=tuple(sorted(list(methods)))
            ))

        return EvaluationResult(
            secrets_total=secrets_total,
            secrets_identified=secrets_identified,
            secrets_misidentified=secrets_misidentified,
            secrets_missed=secrets_missed,
            causal_links_total=len(truth.relations),
            causal_links_identified=0, # Отложено до PlayerCausalModel
            methods_used=methods_used,
            per_secret_results=per_secret
        )

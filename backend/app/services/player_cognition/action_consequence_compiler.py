"""
Файл: backend/app/services/player_cognition/action_consequence_compiler.py
Назначение: Маршрутизация действия игрока во все слои симуляции.
Зависимости: typing, app.models.player_action, app.services.*
"""

from typing import Set

from app.models.observation import EvidencePolarity, ObservationSourceType
from app.models.player_action import ActionType, PlayerAction
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.social.social_fabric_tracker import SocialFabricTracker


class ActionConsequenceCompiler:
    """Единая точка распространения последствий действия.

    Связывает изолированные трекеры в единую каузальную цепь:
    Action -> Observation -> Evidence -> Belief -> SocialFabric
    """

    def __init__(
        self,
        observation_log: ObservationLog,
        belief_model: PlayerBeliefModel,
        social_fabric: SocialFabricTracker
    ) -> None:
        self._log = observation_log
        self._beliefs = belief_model
        self._fabric = social_fabric
        self._processed_actions: Set[str] = set()

    def process_action(self, action: PlayerAction) -> None:
        """Обрабатывает действие и обновляет все зависимые слои. Идемпотентно."""
        if action.action_id in self._processed_actions:
            return
        self._processed_actions.add(action.action_id)

        # 1. Формируем сыное наблюдение
        obs_content = action.description or f"{action.actor_id} совершил {action.action_type.value} к {action.target_id}"
        obs = self._log.add(
            tick=action.tick,
            observation_type=action.action_type.value,
            content=obs_content,
            source_id=action.target_id,
            source_type=ObservationSourceType.NPC
        )

        # 2. Обработка специфичных последствий
        if action.action_type == ActionType.BLACKMAIL and action.secret_id:
            # Единственный чистый путь: EvidenceLink -> update_from_evidence
            ev = self._log.add_evidence(
                observation_id=obs.observation_id,
                secret_id=action.secret_id,
                evidence_strength=1.0,
                polarity=EvidencePolarity.SUPPORTS
            )
            self._beliefs.update_from_evidence(obs, ev)

            self._fabric.apply_delta(
                tick=action.tick,
                source_id=action.target_id,
                target_id=action.actor_id,
                fear_delta=30.0,
                trust_delta=-30.0,
                cause=f"action:{action.action_type.value}",
                description=f"{action.target_id} боится {action.actor_id} после шантажа"
            )

        elif action.action_type == ActionType.HELP:
            self._fabric.apply_delta(
                tick=action.tick,
                source_id=action.target_id,
                target_id=action.actor_id,
                trust_delta=20.0,
                fear_delta=-10.0,
                cause=f"action:{action.action_type.value}",
                description=f"{action.target_id} благодарен {action.actor_id} за помощь"
            )

"""
Файл: backend/app/services/player_cognition/action_consequence_compiler.py
Назначение: Маршрутизация действия игрока во все слои симуляции.
Зависимости: typing, app.models.player_action, app.services.*
"""

from typing import Set, Optional, Any

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
        social_fabric: SocialFabricTracker,
        truth_state: Optional["TruthState"] = None,
        faction_tracker: Optional[Any] = None,
        relationship_store: Optional[Any] = None
    ) -> None:
        self._log = observation_log
        self._beliefs = belief_model
        self._fabric = social_fabric
        self._truth = truth_state
        self._faction_tracker = faction_tracker
        self._relationship_store = relationship_store
        self._campaign_id: Optional[str] = None
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

            # M-02 FIX: Отмечаем секрет как раскрытый
            if self._truth:
                self._truth.mark_discovered(action.secret_id)

            self._fabric.apply_delta(
                tick=action.tick,
                source_id=action.target_id,
                target_id=action.actor_id,
                fear_delta=30.0,
                trust_delta=-30.0,
                cause=f"action:{action.action_type.value}",
                description=f"{action.target_id} боится {action.actor_id} после шантажа"
            )
            # P2 FIX: Проброс дельты в SSOT ядра симуляции (RelationshipStore)
            if self._relationship_store and self._campaign_id:
                self._relationship_store.update(
                    campaign_id=self._campaign_id,
                    source=action.target_id,
                    target=action.actor_id,
                    delta={"fear": 30.0, "trust": -30.0}
                )
            
            # M-12 FIX: BLACKMAIL применяет delta к фракциям
            if self._faction_tracker:
                _faction_id = self._resolve_faction_id(action.target_id)
                if _faction_id:
                    self._faction_tracker.apply_delta(_faction_id, delta=-10.0, known=True)

        # M-07/M-08 FIX: DIALOGUE с secret_id тоже раскрывает секрет (без social_fabric delta)
        elif action.action_type == ActionType.DIALOGUE and action.secret_id:
            ev = self._log.add_evidence(
                observation_id=obs.observation_id,
                secret_id=action.secret_id,
                evidence_strength=0.5,  # dialogue = weaker than blackmail
                polarity=EvidencePolarity.SUPPORTS
            )
            self._beliefs.update_from_evidence(obs, ev)
            if self._truth:
                self._truth.mark_discovered(action.secret_id)

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
            # P2 FIX: Проброс дельты в SSOT ядра симуляции (RelationshipStore)
            if self._relationship_store and self._campaign_id:
                self._relationship_store.update(
                    campaign_id=self._campaign_id,
                    source=action.target_id,
                    target=action.actor_id,
                    delta={"trust": 20.0, "fear": -10.0}
                )
            # M-12 FIX: HELP применяет delta к фракциям
            if self._faction_tracker:
                _faction_id = self._resolve_faction_id(action.target_id)
                if _faction_id:
                    self._faction_tracker.apply_delta(_faction_id, delta=5.0, known=True)

    def _resolve_faction_id(self, target_id: str) -> Optional[str]:
        """M-12 FIX: Маппинг target_id NPC на канонический ID фракции."""
        _faction_map = {
            "guard": "городская_стража",
            "merchant": "торговая_гильдия",
            "thief": "гильдия_воров",
            "tavern_keeper": "таверна_серебряный_волк",
            "maid": "таверна_серебряный_волк"
        }
        _parts = target_id.split("_")
        if len(_parts) > 1:
            _role = _parts[0]
            return _faction_map.get(_role)
        return None
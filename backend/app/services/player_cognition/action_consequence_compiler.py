"""
Файл: backend/app/services/player_cognition/action_consequence_compiler.py
Назначение: Маршрутизация действия игрока во все слои симуляции.
Зависимости: typing, app.models.player_action, app.services.*
"""

import logging
from typing import TYPE_CHECKING, Any, Optional, Set

if TYPE_CHECKING:
    # SANATION-M1b.2.2: forward-ref Optional["TruthState"] жил без импорта
    # (F821, pre-existing) — TYPE_CHECKING-блок; рантайм не тронут.
    from app.models.truth_state import TruthState

from app.models.observation import EvidencePolarity, ObservationSourceType
from app.models.player_action import ActionType, PlayerAction
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.social.relationship_write_gate import RelationshipWriteGate
from app.services.social.social_fabric_tracker import SocialFabricTracker

logger = logging.getLogger(__name__)

# S211 (§18): порог уверенности для публичного обвинения. Калибруемый
# параметр (Calibration Laboratory). conf < порога → подозрение доступно,
# обвинение — нет.
_ACCUSE_CONFIDENCE_THRESHOLD: float = 0.5


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
        relationship_store: Optional[Any] = None,
        epistemic_resolver: Optional[Any] = None  # S211 (§18): гейт убеждений
    ) -> None:
        self._log = observation_log
        self._beliefs = belief_model
        self._fabric = social_fabric
        self._truth = truth_state
        self._faction_tracker = faction_tracker
        self._relationship_store = relationship_store
        # M1b.2.2 (ADR-O-371): писатель пяти скаляров переводится на
        # RelationshipWriteGate — единый write-маршрут (D2). Стор опционален
        # (DI): без стора гейта нет — охрана сайтов остаётся прежней
        # (if self._relationship_store ...). На cutover (M1b.4) гейт получит
        # v2-backend централизованно — компилятор повторно не мигрирует.
        self._write_gate = RelationshipWriteGate(relationship_store) if relationship_store else None
        # S211: EpistemicContextResolver над EpistemicStore — ЕДИНСТВЕННЫЙ
        # законный путь чтения убеждений игрока (Закон §18). PlayerBeliefModel
        # — legacy projection (DEBT-E1), в гейте НЕ участвует.
        self._epistemic_resolver = epistemic_resolver
        self._campaign_id: Optional[str] = None
        self._processed_actions: Set[str] = set()

    def set_epistemic_resolver(self, resolver: Any) -> None:
        """S211: late-binding инъекция резолвера (контроллер собирается
        раньше регистрации Epistemic Core в GameLoop — DI по прецеденту
        SocialSubscriber.set_social_engine_factory)."""
        self._epistemic_resolver = resolver

    def process_action(self, action: PlayerAction) -> Optional[str]:
        """Обрабатывает действие и обновляет все зависимые слои. Идемпотентно.

        S211: возвращает None при успехе ИЛИ строку-причину отклонения
        (эпистемический гейт). Вызывающие, игнорирующие возврат, не ломаются.
        """
        if action.action_id in self._processed_actions:
            return None
        self._processed_actions.add(action.action_id)

        # S211 (§18): эпистемический гейт. Обвинение — действие, опирающееся
        # на знание: без belief о субъекте (conf ≥ порога) игрок не знает,
        # КОГО и В ЧЁМ обвинять. Пустое обвинение онтологически невозможно.
        # Резолвер — единственный законный путь чтения убеждений игрока
        # (Закон §18); PlayerBeliefModel в гейте не участвует (DEBT-E1).
        if action.action_type == ActionType.ACCUSE:
            if self._epistemic_resolver is None:
                logger.warning(
                    "[ACC_GATE] EpistemicResolver не инжектирован — "
                    "ACCUSE без гейта (конфигурация GameLoop, см. §18)"
                )
            else:
                _conf = self._epistemic_resolver.get_confidence_for_subject(
                    "player", action.target_id
                )
                if _conf < _ACCUSE_CONFIDENCE_THRESHOLD:
                    _reason = (
                        f"epistemic gate: player belief о '{action.target_id}' "
                        f"conf={_conf:.2f} < {_ACCUSE_CONFIDENCE_THRESHOLD} — "
                        f"нет оснований для обвинения"
                    )
                    logger.info(f"[ACC_GATE] ACCUSE отклонено: {_reason}")
                    return _reason

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
            # P2 FIX: Проброс дельты в SSOT ядра симуляции (через WriteGate — M1b.2.2)
            if self._write_gate and self._campaign_id:
                self._write_gate.apply(
                    self._campaign_id,
                    action.target_id,
                    action.actor_id,
                    {"fear": 30.0, "trust": -30.0},
                    cause=f"action:{action.action_type.value}",
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
            # P2 FIX: Проброс дельты в SSOT ядра симуляции (через WriteGate — M1b.2.2)
            if self._write_gate and self._campaign_id:
                self._write_gate.apply(
                    self._campaign_id,
                    action.target_id,
                    action.actor_id,
                    {"trust": 20.0, "fear": -10.0},
                    cause=f"action:{action.action_type.value}",
                )
            # M-12 FIX: HELP применяет delta к фракциям
            if self._faction_tracker:
                _faction_id = self._resolve_faction_id(action.target_id)
                if _faction_id:
                    self._faction_tracker.apply_delta(_faction_id, delta=5.0, known=True)

        elif action.action_type == ActionType.ACCUSE:
            # S211: гейт уже пройден выше (иначе return был в нём). Публичное
            # обвинение: цель боится разоблачения, доверие к обвинителю
            # падает. TruthState НЕ трогаем: истинность обвинения решают
            # NPC-реакции (guard disposition REPORT и т.д.) — эмерджентно.
            self._fabric.apply_delta(
                tick=action.tick,
                source_id=action.target_id,
                target_id=action.actor_id,
                fear_delta=25.0,
                trust_delta=-15.0,
                cause=f"action:{action.action_type.value}",
                description=f"{action.target_id} обвинён {action.actor_id}"
            )
            if self._write_gate and self._campaign_id:
                self._write_gate.apply(
                    self._campaign_id,
                    action.target_id,
                    action.actor_id,
                    {"fear": 25.0, "trust": -15.0},
                    cause=f"action:{action.action_type.value}",
                )
            if self._faction_tracker:
                _faction_id = self._resolve_faction_id(action.target_id)
                if _faction_id:
                    self._faction_tracker.apply_delta(_faction_id, delta=-5.0, known=True)

        return None

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

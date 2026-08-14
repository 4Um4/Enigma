# backend/app/services/events/claim_event_subscriber.py
"""
path: /project/backend/app/services/events/claim_event_subscriber.py
Назначение: Адаптер между инфраструктурным событием (EventDTO) и эпистемической моделью (ClaimEvent).
Зависимости: app.domain.epistemology, app.services.events.event_bus
"""

import logging
from typing import Any, Optional
from app.domain.events import EventDTO
from app.domain.epistemology import ClaimEvent, Proposition, Predicate, SpeechAct
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore

logger = logging.getLogger(__name__)

class RelationshipReliabilityProvider:
    """
    S189: Адаптер RelationshipStore -> SourceReliabilityProvider (ADR-O-354).
    Возвращает trust (0.0-1.0) как базовую надёжность источника.
    """
    def __init__(self, relationship_store: Any, campaign_id: str):
        self._store = relationship_store
        self._campaign_id = campaign_id

    def get_reliability(self, observer: str, source: str, context: Optional[dict] = None) -> float:
        if not self._store:
            return 0.5 # Нейтральная надёжность при отсутствии SSOT
        
        # ADR-O-354: RelationshipStore.get_pair(campaign_id, observer, source) масштаб 0-100.
        # S189 FIX: Убран silent failure (ADR-O-308). Ошибка в RelationshipStore должна крашить тик.
        _pair_data = self._store.get_pair(self._campaign_id, observer, source) or {}
        _trust_100 = _pair_data.get("trust", 50.0)
        return max(0.0, min(1.0, _trust_100 / 100.0))

class ClaimEventSubscriber:
    """
    Слушает COMMUNICATION_CLAIM на EventBus.
    Преобразует EventDTO в ClaimEvent и передаёт в BeliefRevisionEngine.
    """
    def __init__(self, engine: BeliefRevisionEngine, store: EpistemicStore):
        self._engine = engine
        self._store = store

    def on_claim_event(self, event: Any) -> None:
        if not hasattr(event, 'payload'):
            logger.warning("[CLAIM_SUB] Event has no payload")
            return

        payload = event.payload
        prop_data = payload.get("proposition")
        if not prop_data:
            logger.warning("[CLAIM_SUB] No proposition in payload")
            return

        try:
            prop = Proposition(
                subject_id=prop_data.get("subject_id"),
                predicate=Predicate(prop_data.get("predicate")),
                object_id=prop_data.get("object_id"),
                polarity=prop_data.get("polarity", True)
            )

            claim = ClaimEvent(
                event_id=str(event.id),
                claim_id=payload.get("claim_id", str(event.id)),
                speaker_id=event.source,
                listener_id=payload.get("target_id"),
                proposition=prop,
                speech_act=SpeechAct(payload.get("speech_act", "assert")),
                tick=payload.get("tick", 0)
            )

            existing = self._store.get(claim.listener_id, prop)
            updated_record = self._engine.revise(claim.listener_id, claim, existing)
            self._store.upsert(updated_record)

        except Exception as e:
            logger.exception(f"[CLAIM_SUB] Failed to process claim event: {e}")
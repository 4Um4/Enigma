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

# S20x (ADR-O-357 enforcement): инлайн-провайдер reliability УДАЛЁН.
# Каноническая реализация: app/services/npc/trust_based_reliability_provider.py
# (TrustBasedReliabilityProvider). Подписчик — потребитель reliability,
# но не владелец формулы trust → reliability.

HEARING_RADIUS = 10.0

class ClaimEventSubscriber:
    """
    Слушает COMMUNICATION_CLAIM и NPC_SPOKE на EventBus.
    Преобразует EventDTO в ClaimEvent и передаёт в BeliefRevisionEngine.
    S192: Observation Divergence — фильтрует слушателей через пространственную мембрану (SpatialQueryService).
    S199 (Фаза 8.3): Поддержка игрока как наблюдателя (observer_id="player").
    """
    def __init__(
        self, 
        engine: BeliefRevisionEngine, 
        store: EpistemicStore,
        spatial_query_provider: Optional[Any] = None,
    ):
        self._engine = engine
        self._store = store
        self._get_spatial_query = spatial_query_provider

    def on_npc_spoke(self, event: Any) -> None:
        """
        Фаза 8.3: Детерминированный fallback для NPC_SPOKE.
        Если LLM не предоставила proposition, извлекает его из intent_type.
        """
        import dataclasses
        
        if not hasattr(event, 'payload'):
            return

        payload = event.payload
        # Если LLM уже предоставила proposition, COMMUNICATION_CLAIM обработает его.
        if payload.get("proposition"):
            return

        intent_type = payload.get("intent_type", "talk")
        target_id = payload.get("target_id")
        speaker_id = event.source

        # Маппинг интентов на пропозиции
        # subject_id — кто совершил действие, object_id — над кем/чем.
        prop = None
        if intent_type == "accuse" and target_id:
            # "Я обвиняю тебя в краже" -> target украл неизвестно что
            prop = Proposition(subject_id=target_id, predicate=Predicate.STOLE, object_id="unknown")
        elif intent_type == "praise" and target_id:
            # "Я хвалю тебя за помощь" -> target помог неизвестно кому
            prop = Proposition(subject_id=target_id, predicate=Predicate.HELPED, object_id="unknown")
        elif intent_type in ("intimidate", "attack") and target_id:
            # "Я угрожаю тебе" -> speaker напал на target
            prop = Proposition(subject_id=speaker_id, predicate=Predicate.ATTACKED, object_id=target_id)

        if prop:
            # Создаём НОВЫЙ payload и НОВЫЙ event, чтобы не мутировать frozen EventDTO
            new_payload = dict(payload)
            new_payload["proposition"] = {
                "subject_id": prop.subject_id,
                "predicate": prop.predicate.value,
                "object_id": prop.object_id,
                "polarity": True
            }
            new_payload.setdefault("claim_id", f"fallback-{event.id}")
            new_payload.setdefault("speech_act", "assert")
            
            # Создаём новый event с теми же полями, но новым payload
            new_event = dataclasses.replace(event, payload=new_payload)
            self.on_claim_event(new_event)

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

            # S192.1: Perception Membrane Hardening.
            # target_id — это семантический адресат, но физически услышать могут только те, кто в радиусе.
            # Телепатия (передача убеждений без физического контакта) запрещена.
            _listeners = set()

            # S202: Определяем источник звука. Если это атака, звук исходит от цели (удар).
            _origin_id = event.source
            _prop_data = payload.get("proposition")
            if _prop_data and _prop_data.get("predicate") == "attacked":
                _origin_id = payload.get("target_id", event.source)

            if self._get_spatial_query:
                _sq = self._get_spatial_query()
                if _sq:
                    _npc_positions = getattr(_sq, "_npc_positions", {})  # noqa: ENIGMA002
                    # S198: Если spatial_query пуст, fallback на target_id (гарантия детерминизма)
                    if not _npc_positions:
                        _primary_target = payload.get("target_id")
                        if _primary_target:
                            _listeners.add(_primary_target)
                    else:
                        for _nid in _npc_positions.keys():
                            # S199 (Фаза 8.3): Игрок больше не исключается — он полноправный наблюдатель.
                            if _nid == _origin_id:
                                continue
                            _dist = _sq.distance(_origin_id, _nid)
                            if _dist <= HEARING_RADIUS:
                                _listeners.add(_nid)
                        # S198: Явно проверяем target_id, даже если он отсутствует в _npc_positions
                        _primary_target = payload.get("target_id")
                        if _primary_target and _primary_target not in _listeners:
                            if _primary_target not in _npc_positions:
                                _listeners.add(_primary_target)
                            else:
                                _dist = _sq.distance(_origin_id, _primary_target)
                                if _dist <= HEARING_RADIUS:
                                    _listeners.add(_primary_target)
                else:
                    _primary_target = payload.get("target_id")
                    if _primary_target:
                        _listeners.add(_primary_target)
            else:
                _primary_target = payload.get("target_id")
                if _primary_target:
                    _listeners.add(_primary_target)

            for _listener_id in _listeners:
                # DEBT-R4 (S208): изоляция per-listener. Сбой ревизии одного
                # слушателя не должен молча убивать убеждения остальных
                # (класс инцидента S207: один битый элемент глушит хвост цикла).
                # Политика ARCH-017: Belief → degrade (продолжаем), но отказ
                # наблюдаем с идентификатором жертвы. Полная типизация ошибок
                # (PerceptionError-категории) — отдельная задача, не здесь.
                try:
                    claim = ClaimEvent(
                        event_id=str(event.id),
                        claim_id=payload.get("claim_id", str(event.id)),
                        speaker_id=event.source,
                        listener_id=_listener_id,
                        proposition=prop,
                        speech_act=SpeechAct(payload.get("speech_act", "assert")),
                        tick=payload.get("tick", 0)
                    )
                    existing = self._store.get(_listener_id, prop)
                    updated_record = self._engine.revise(_listener_id, claim, existing)
                    self._store.upsert(updated_record)
                except Exception as _listener_err:
                    logger.error(
                        f"[CLAIM_SUB] Belief revision failed: listener={_listener_id}, "
                        f"claim={payload.get('claim_id', event.id)}: {_listener_err}",
                        exc_info=True,
                    )

        except Exception as e:
            logger.exception(f"[CLAIM_SUB] Failed to process claim event: {e}")
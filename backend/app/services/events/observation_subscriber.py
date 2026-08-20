"""
path: backend/app/services/events/observation_subscriber.py
Назначение: Phase C (ADR-O-360) — второй канал поступления убеждений после
            testimony: прямое наблюдение мировых событий. Слушает THEFT,
            строит ClaimEvent(witness→witness) для агентов с LOS к источнику
            события. Пространственная мембрана — SpatialQueryService.visibility,
            НЕ event.radius (DEBT-R1).
Зависимости: app.domain.epistemology, app.domain.events, app.services.npc.*,
            app.services.spatial.spatial_query_service
Основные сущности: ObservationSubscriber, OBSERVABLE_EVENTS
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.domain.epistemology import ClaimEvent, Predicate, Proposition
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore

logger = logging.getLogger(__name__)

# ADR-O-360: дальность прямой видимости для наблюдения (калибруемый параметр,
# симметричен base_range="dim" из spatial_runtime.line_of_sight). ВАЖНО:
# SpatialQueryService.visibility() проверяет ТОЛЬКО стены (is_line_of_sight_clear),
# без дальности — поэтому мембрана наблюдения = visibility + distance.
# Полная унификация (light_level/density/danger) — ревизия ADR-O-360.
_OBSERVATION_SIGHT_RADIUS: float = 10.0

# События, наблюдаемые напрямую. Расширение списка — отдельной ревизией ADR-O-360
# (каждый новый EventType обязан иметь детерминированный маппинг на Predicate).
# ADR-O-360.
_OBSERVABLE_EVENT_PREDICATES: dict[str, Predicate] = {
    "theft": Predicate.STOLE,
}

# ObservationSubscriber сам себе testimony: повторное наблюдение того же
# события тем же агентом усиливает убеждение через same-source ветку движка
# (+0.9*0.2), а не дублирует его. Это позволяет не патчить BeliefRevisionEngine.


class ObservationSubscriber:
    """Phase C: WORLD EVENT → (LOS мембрана) → ClaimEvent(witness→witness) → Store.

    Эпистемические гарантии:
    - Truth Immutability: подписчик только читает событие, ничего не пишет в мир;
    - No Telepathy: убеждение получает только агент с visibility() == True;
    - Epistemic Isolation: подписчик не читает TruthState / RelationshipStore.
    """

    def __init__(
        self,
        engine: BeliefRevisionEngine,
        store: EpistemicStore,
        spatial_query_provider: Optional[Callable[[], Any]] = None,
        tick_provider: Optional[Callable[[], int]] = None,
    ) -> None:
        self._engine = engine
        self._store = store
        self._get_spatial_query = spatial_query_provider
        self._get_tick = tick_provider or (lambda: 0)

    def on_world_event(self, event: Any) -> None:
        """Точка входа EventBus. THEFT → убеждение свидетелей (player, STOLE, target)."""
        event_type = getattr(event, "type", None)
        if event_type is None:
            return

        predicate = _OBSERVABLE_EVENT_PREDICATES.get(event_type.lower())
        if predicate is None:
            return

        payload = getattr(event, "payload", None) or {}
        actor_id = getattr(event, "source", None)
        target_id = payload.get("target_id")
        if not actor_id or not target_id:
            logger.warning(
                f"[OBSERVATION_SUB] {event_type}: нет actor/target — наблюдение пропущено"
            )
            return

        witnesses = self._get_witnesses(actor_id)
        if not witnesses:
            return

        proposition = Proposition(
            subject_id=actor_id,
            predicate=predicate,
            object_id=target_id,
            polarity=True,
        )
        tick = self._get_tick()
        for witness_id in witnesses:
            claim = ClaimEvent(
                event_id=str(getattr(event, "id", "")),
                claim_id=f"observation-{getattr(event, 'id', '')}-{witness_id}",
                speaker_id=witness_id,
                listener_id=witness_id,
                proposition=proposition,
                tick=tick,
            )
            existing = self._store.get(witness_id, proposition)
            record = self._engine.revise(
                witness_id, claim, existing,
                reliability_context={"source_type": "direct_observation"},
            )
            self._store.upsert(record)
            logger.info(
                f"[OBSERVATION_SUB] {witness_id} наблюдал {actor_id} "
                f"{predicate.value} {target_id} (conf={record.confidence:.2f})"
            )

    def _get_witnesses(self, actor_id: str) -> list[str]:
        """LOS-мембрана. Актёр не свидетель себе (self-exclusion), player включён
        как агент (ADR-O-358, S200). Радиус события игнорируется (DEBT-R1)."""
        sq = self._get_spatial_query() if self._get_spatial_query else None
        if sq is None:
            logger.warning(
                "[OBSERVATION_SUB] SpatialQueryService недоступен — "
                "наблюдение невозможно (no telepathy, убеждение не создаётся)"
            )
            return []

        witnesses: list[str] = []
        positions = getattr(sq, "_npc_positions", {})
        for entity_id in sorted(positions):  # детерминизм итерации
            if entity_id == actor_id:
                continue
            try:
                _dist = sq.distance(entity_id, actor_id)
                if _dist > _OBSERVATION_SIGHT_RADIUS:
                    continue
                if sq.visibility(entity_id, actor_id):
                    witnesses.append(entity_id)
            except Exception as e:
                logger.warning(
                    f"[OBSERVATION_SUB] visibility({entity_id}, {actor_id}) failed: {e}"
                )
        return witnesses
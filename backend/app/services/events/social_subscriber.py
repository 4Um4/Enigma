"""
path: backend/app/services/events/social_subscriber.py
Назначение: Phase8Handler — социальная пропагация (Устав §5.1 + §3 Фаза 8)
Зависимости: domain.events.EventDTO, models.phase8.Phase8Context/Phase8Result, services.events.event_bus.EventBus
Основные сущности: SocialSubscriber (Phase8Handler)

Устав §5.1: EventBus.publish() — единственная точка входа событий.
SocialSubscriber подписан на шину, накапливает EventDTO.
Фаза 8: drain_events() + handle() — детерминированный drain-этап.
Шина для фактов, Фаза 8 для обработки. Никаких мета-событий.

propagate_social_rumors() — чистая функция, возвращает List[StateDeltas].
Оркестратор применяет дельты к all_npcs_raw в _apply_phase8_result().

- [ ] Phase 3B.4: поддержка асинхронной очереди для world_tick
- [ ] Phase 3E: расширение для FactionSystem (пропагация по фракциям)
- [ ] Логирование и метрики: сколько NPC затрагивает социальная пропагация, какие типы событий чаще всего влияют на социальные отношения
- [ ] Тесты: юнит-тесты для SocialSubscriber, интеграционные тесты с EventBus и SocialEngine
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context, Phase8Result
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.services.social.relationship_write_gate import RelationshipWriteGate

logger = logging.getLogger(__name__)

# Типы событий, влияющих на социальную пропагацию
_SOCIAL_EVENT_TYPES: list[EventType] = [
    EventType.PLAYER_INTERACTS,
    EventType.PLAYER_SPOKE,
    EventType.PLAYER_ATTACKED,
    EventType.PLAYER_ATTACKS,
    EventType.PLAYER_ATTACK,
    EventType.PLAYER_INSULTS,
    EventType.PLAYER_THREATENS,
    EventType.THEFT,
    EventType.HELP,
    EventType.INTIMIDATION,
    # V8-SOC-1 FIX: Добавлены события NPC↔NPC для социальных последствий
    EventType.ACTOR_ATTACKS,
    EventType.NPC_SPOKE,
    EventType.NPC_MOVED,
    EventType.NPC_PROXIMITY_CLOSE,
    EventType.NPC_PROXIMITY_LEAVE,
]


class SocialSubscriber:
    """Phase8Handler: социальная пропагация.

    Жизненный цикл:
      1. Шина → _on_event() накапливает EventDTO (Фазы 2/7)
      2. Оркестратор → drain_events() снимок + очистка (Фаза 8)
      3. Оркестратор → handle(events, ctx) → Phase8Result (Фаза 8)

    Чистая функция: propagate_social_rumors() возвращает List[StateDeltas].
    Оркестратор складывает дельты в delta_buffer → StateApplicator (фаза 10).
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._social_engine_factory: Callable | None = None
        self._social_tick: int = 0
        self._pending_events: List[EventDTO] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """Подписывается на все типы событий, влияющих на социальную пропагацию."""
        for et in _SOCIAL_EVENT_TYPES:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event: EventDTO) -> Optional[Dict[str, Any]]:
        """EventHandler: накапливает событие для обработки на Фазе 8."""
        self._pending_events.append(event)
        return None

    @property
    def name(self) -> str:
        return "social"

    def drain_events(self) -> List[EventDTO]:
        """Снимок буфера + очистка. Вызывается строго один раз за тик."""
        snapshot = list(self._pending_events)
        self._pending_events.clear()
        return snapshot

    def set_social_engine_factory(self, factory: Callable) -> None:
        """Устанавливает фабрику SocialEngine (DI)."""
        self._social_engine_factory = factory

    def handle(
        self,
        events: List[EventDTO],
        ctx: Phase8Context,
    ) -> Phase8Result:
        """ФАЗА 8: социальная пропагация накопленных событий.

        events — из drain_events(), может быть пустым.
        ctx — READ-ONLY.
        Возвращает Phase8Result(deltas) — оркестратор применяет.

        propagate_social_rumors() — чистая функция, возвращает List[StateDeltas].
        Оркестратор применяет дельты к all_npcs_raw через _apply_phase8_result().
        """
        if self._social_engine_factory is None:
            logger.debug("[SOCIAL_SUB] handle: нет social_engine_factory — пропускаем")
            return Phase8Result()

        if not events:
            logger.debug("[SOCIAL_SUB] handle: нет накопленных событий")
            return Phase8Result()

        from app.services.social.propagation import propagate_social_rumors

        # 8.1 FIX: Детерминированный fallback для трекинга отношений.
        # Если LLM не парсит семантику, NPC A и B всё равно должны влиять на отношения при разговоре.
        # Явная проверка атрибутов без скрытых дефолтов (§1.2 Silent Failure Eradication)
        if not hasattr(ctx.shared_context, "campaign_id"):
            # S116-fallback (tick_utils SimpleNamespace) — известно пустой
            # контекст idle/world-tick пути; не ошибка, debug.
            logger.debug(
                "[SOCIAL_SUBSCRIBER] S116-fallback shared_context (без campaign_id) "
               "— trust-fallback пропущен."
            )
        elif not hasattr(ctx.shared_context, "relationship_store"):
            logger.warning(
                "[SOCIAL_SUBSCRIBER] shared_context missing relationship_store. "
                "Social deltas skipped."
            )
        else:
            # M1b.2.1 (ADR-O-371): писатель переводится на RelationshipWriteGate —
            # единый write-маршрут (D2). Ленивая инъекция: гейт строится из
            # доступного стора, если точка сборки его ещё не пробросила; на
            # cutover (M1b.4) backend гейта меняется централизованно — подписчик
            # повторно не мигрирует. Дельты/направления НЕ меняются (механика).
            _gate = getattr(ctx.shared_context, "relationship_write_gate", None)
            _store = getattr(ctx.shared_context, "relationship_store", None)
            if _gate is None and _store is None:
                # M1b.2.1-fix: стор ещё не собран (lazy-сборка game_loop) —
                # детерминированный trust-fallback честно пропускается с
                # наблюдаемым логом (§1.2 Silent Failure Eradication).
                # Раньше здесь строился RelationshipWriteGate(None) →
                # "'NoneType' object has no attribute 'update'" каждый тик.
                logger.warning(
                    "[SOCIAL_SUBSCRIBER] relationship_store отсутствует (None) — "
                    "trust-fallback пропущен; social deltas (rumors) не затронуты."
                )
                # AUD-D2 FIX: раньше здесь НЕ было выхода — цикл for _ev ниже
                # выполнялся при _gate=None (индент-баг) → None.apply ERROR
                # на каждом живом событии. None-стор = честный skip, не полуконтур.
                self._social_engine = self._social_engine_factory(ctx.campaign_id)
                self._social_tick, deltas = propagate_social_rumors(
                    self._social_engine,
                    self._social_tick,
                    ctx.shared_context,
                    events=events,
                )
                _affected_ids = {d.npc_id for d in deltas if d.npc_id}
                return Phase8Result(
                    deltas=deltas,
                    socially_affected_npc_ids=_affected_ids,
                    events_processed=len(events),
                )
            else:
                if _gate is None:
                    _gate = RelationshipWriteGate(_store)
                _campaign_id = ctx.shared_context.campaign_id
            for _ev in events:
                if _ev.type == EventType.NPC_SPOKE.value:
                    _sp = _ev.source
                    _tg = _ev.payload.get("target_id")
                    # Phase 8.2: Детерминированный fallback для социальной семантики.
                    # gossip разрушает доверие к сплетнику (speaker).
                    # accuse повышает страх к обвиняемому (target).
                    # praise повышает доверие к хвалимому (target).
                    _intent = _ev.payload.get("intent_type", "talk")
                    _TRUST_DELTA = 0.5
                    _TARGET_TRUST_DELTA = 0.0
                    _TARGET_FEAR_DELTA = 0.0

                    if _intent == "gossip":
                        _TRUST_DELTA = -2.0
                    elif _intent == "praise":
                        _TARGET_TRUST_DELTA = 1.5
                    elif _intent == "accuse":
                        _TARGET_FEAR_DELTA = 1.0
                    if _sp and _tg and _sp != _tg:
                        try:
                            if _intent in ("intimidate", "attack"):
                                _gate.apply(_campaign_id, _sp, _tg, {"fear": 1.0}, cause=f"social_sub:{_intent}")
                            elif _intent == "gossip":
                                # Сплетни разрушают доверие ИГРОКА к сплетнику
                                _gate.apply(_campaign_id, "player", _sp, {"trust": _TRUST_DELTA}, cause="social_sub:gossip")
                            elif _intent == "praise":
                                # Хвала повышает доверие ИГРОКА к хвалимому
                                _gate.apply(_campaign_id, "player", _tg, {"trust": _TARGET_TRUST_DELTA}, cause="social_sub:praise")
                            elif _intent == "accuse":
                                # Обвинение повышает страх ИГРОКА к обвиняемому
                                _gate.apply(_campaign_id, "player", _tg, {"fear": _TARGET_FEAR_DELTA}, cause="social_sub:accuse")
                            else:
                                # Симуляция светской беседы — рост доверия игрока к спикеру
                                _gate.apply(_campaign_id, "player", _sp, {"trust": _TRUST_DELTA}, cause="social_sub:talk")
                        except Exception as _e:
                            logger.error(f"[SOCIAL_SUB] RelationshipStore fallback failed: {_e}")

        social_engine = self._social_engine_factory(ctx.campaign_id)
        self._social_tick, deltas = propagate_social_rumors(
            social_engine,
            self._social_tick,
            ctx.shared_context,
            events=events,
        )

        logger.debug(
            f"[SOCIAL_SUB] {len(events)} events "
            f"processed, social_tick={self._social_tick}, "
            f"deltas={len(deltas)}"
        )

        # Извлекаем затронутых NPC из дельт для синхронизации perception ∪ social
        _affected_ids = {d.npc_id for d in deltas if d.npc_id}

        return Phase8Result(
            deltas=deltas,
            socially_affected_npc_ids=_affected_ids,
            events_processed=len(events),
        )

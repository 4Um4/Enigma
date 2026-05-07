# backend/app/services/events/reaction_subscriber.py
"""
Phase 8: ReactionSubscriber — эмоциональные реакции наблюдателей на события.

Отличие от SocialSubscriber:
  SocialSubscriber → социальная пропагация (слухи, косвенное влияние)
  ReactionSubscriber → прямая эмоциональная реакция (стресс, страх, доверие)

Отличие от DecisionHub:
  DecisionHub → полный decision-цикл (Фаза 5) с LLM
  ReactionSubscriber → мгновенная рефлексивная реакция (Фаза 8) без LLM

Принцип: наблюдатель видит угрозу → стресс/страх растут, доверие падает.
Никакого «думания» — чистая формула на основе личности NPC и типа события.

Порядок в _handlers: perception → reaction → social
  perception: определяет КТО видит (perceiving_npc_ids)
  reaction: считает ПРЯМЫЕ эмоциональные дельты для наблюдателей
  social: распространяет слухи до тех, кто НЕ видел

path: backend/app/services/events/reaction_subscriber.py
Назначение: Phase8Handler — прямые эмоциональные реакции наблюдателей на события
Зависимости: app.models.phase8, app.models.state_delta, app.domain.events, app.domain.constants, app.services.events.event_types, app.services.events.event_bus
Основные сущности: ReactionSubscriber (Phase8Handler)

TODO:
- в будущем можно расширить реакцию, добавив не только стресс/страх/доверие, но и другие аспекты (напр. злость, симпатия) или более сложные формулы (напр. учитывать отношения между наблюдателем и источником). Но для MVP достаточно базовой тройки с простыми правилами.
- протестировать на реальных событиях из игры и отладить формулы, чтобы реакции были заметными, но не чрезмерными.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from app.domain.constants import ACTION_INTENSITY
from app.domain.events import EventDTO
from app.models.phase8 import Phase8Context, Phase8Result
from app.models.state_delta import DeltaDomain, EmotionPayload, SocialPayload, StateDeltas
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

# ── Типы событий, вызывающие прямые эмоциональные реакции ──────────────────
_REACTION_EVENT_TYPES: list[EventType] = [
    EventType.PLAYER_ATTACKS,
    EventType.PLAYER_ATTACK,
    EventType.PLAYER_ATTACKED,
    EventType.PLAYER_THREATENS,
    EventType.PLAYER_INSULTS,
    EventType.COMBAT,
    EventType.THEFT,
    EventType.INTIMIDATION,
    EventType.BETRAYAL,
    EventType.HELP,
    EventType.SAVED_LIFE,
    EventType.OBJECT_DESTROYED,
]

# ── Правила реакций: event_type.lower() → (stress_base, fear_base, trust_actor_base) ──
# stress_base: изменение стресса для среднего наблюдателя
# fear_base: изменение страха для среднего наблюдателя
# trust_actor_base: изменение доверия к источнику события (отрицательное = потеря)
_REACTION_RULES: dict[str, tuple[float, float, float]] = {
    "player_attacks":            (15.0, 10.0,  -8.0),
    "player_attack":             (15.0, 10.0,  -8.0),
    "player_attacked":           (20.0, 15.0, -12.0),
    "player_threatens":          (10.0,  8.0,  -4.0),
    "player_threatens_indirect": ( 7.0,  5.0,  -2.0),
    "player_insults":            ( 5.0,  2.0,  -3.0),
    "combat":                    (18.0, 12.0,  -6.0),
    "theft":                     ( 8.0,  3.0,  -7.0),
    "intimidation":             (12.0, 10.0,  -3.0),
    "betrayal":                 (15.0,  8.0, -12.0),
    "help":                     ( -3.0,  0.0,   5.0),
    "saved_life":               ( -5.0, -3.0,  10.0),
    "object_destroyed":         (  5.0,  3.0,   0.0),
}


def _get_event_intensity(event: EventDTO) -> float:
    """Интенсивность из payload или ACTION_INTENSITY fallback."""
    intensity = event.payload.get("intensity")
    if intensity is not None:
        return float(intensity)
    return ACTION_INTENSITY.get(event.type.lower(), 0.2)


def _compute_reaction_modifier(npc_dict: dict) -> float:
    """Модификатор реакции на основе личности NPC.

    Average NPC (stress=50, fear=0.25, willpower=50) → modifier ≈ 0.5
    Cowardly NPC (stress=70, fear=0.5, willpower=30) → modifier ≈ 1.0
    Brave NPC (stress=20, fear=0.1, willpower=80)    → modifier ≈ 0.2
    """
    psyche = npc_dict.get("psyche", {})
    stress = float(psyche.get("stress", 0.0))
    willpower = float(psyche.get("willpower", 50.0))
    drives = npc_dict.get("drives", {"fear": 0.25})
    fear_drive = float(drives.get("fear", 0.25))

    # composure_factor: стресс усиливает реакцию (на взводе)
    composure = 1.0 - min(stress, 100.0) / 100.0  # 0-1, 0 = max stress
    composure_factor = 0.5 + (1.0 - composure) * 0.5  # 0.5-1.0

    # fear_factor: высокая страх-тяга → сильнее реакция
    fear_factor = 0.5 + fear_drive * 2.0  # 0.5-2.5

    # willpower_factor: высокая воля → приглушает реакцию
    willpower_factor = 1.0 - willpower / 150.0  # 0.33-1.0

    return composure_factor * fear_factor * willpower_factor


def _is_npc_source(source: str, all_npcs_raw: list) -> bool:
    """Определяет, является ли источник события NPC (а не игроком)."""
    for npc in all_npcs_raw:
        npc_id = npc.get("id") or npc.get("npc_id")
        if npc_id and npc_id == source:
            return True
    return False


class ReactionSubscriber:
    """Phase8Handler: прямые эмоциональные реакции наблюдателей.

    Поток:
      1. EventBus доставляет событие → _on_event() накапливает
      2. Оркестратор → drain_events() снимок + очистка (Фаза 8)
      3. Оркестратор → handle(events, ctx) → Phase8Result (Фаза 8)

    Deltas маршрутизируются через delta_buffer → apply_batch (ADR-002).
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_events: list[EventDTO] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """Подписывается на типы событий, вызывающие эмоциональные реакции."""
        for et in _REACTION_EVENT_TYPES:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event: EventDTO) -> Optional[dict]:
        """EventHandler: накапливает событие для обработки на Фазе 8."""
        self._pending_events.append(event)
        return None

    @property
    def name(self) -> str:
        return "reaction"

    def drain_events(self) -> List[EventDTO]:
        """Снимок накопленных событий + очистка буфера."""
        snapshot = self._pending_events[:]
        self._pending_events.clear()
        return snapshot

    def handle(
        self,
        events: List[EventDTO],
        ctx: Phase8Context,
    ) -> Phase8Result:
        """ФАЗА 8: вычисляет эмоциональные реакции наблюдателей.

        events — из drain_events(), может быть пустым.
        ctx — READ-ONLY.
        Возвращает Phase8Result(deltas) — оркестратор маршрутизирует
        через delta_buffer → apply_batch.

        Использует perceiving_npcs из shared_context (установлен
        PerceptionSubscriber) или fallback на всех NPC.
        """
        if not events:
            return Phase8Result()

        # Определяем реагирующих NPC
        perceiving_ids = self._get_perceiving_ids(ctx)
        if not perceiving_ids:
            return Phase8Result()

        # Строим dict npc_id → npc_dict для быстрого доступа
        npc_by_id: dict[str, dict] = {}
        for npc in ctx.all_npcs_raw:
            npc_id = npc.get("id") or npc.get("npc_id")
            if npc_id:
                npc_by_id[npc_id] = npc

        deltas: list[StateDeltas] = []

        for event in events:
            rule_key = event.type.lower()
            rule = _REACTION_RULES.get(rule_key)
            if rule is None:
                continue

            stress_base, fear_base, trust_actor_base = rule
            intensity = _get_event_intensity(event)
            source = event.source

            # Определяем таргет для trust_delta
            source_is_npc = _is_npc_source(source, ctx.all_npcs_raw)
            trust_target_key = "social_target" if source_is_npc else "intent_target"
            trust_target_val = source if source_is_npc else "player"

            for npc_id in perceiving_ids:
                # Источник события не реагирует на собственное действие
                if npc_id == source:
                    continue

                npc_dict = npc_by_id.get(npc_id)
                if npc_dict is None:
                    continue

                modifier = _compute_reaction_modifier(npc_dict)

                # Вычисляем дельты
                stress_delta = round(stress_base * modifier * intensity, 2)
                fear_delta = round(fear_base * modifier * intensity, 2)
                trust_delta = round(trust_actor_base * modifier * intensity, 2)

                # Пропускаем нулевые дельты
                if stress_delta == 0.0 and fear_delta == 0.0 and trust_delta == 0.0:
                    continue

                # v2: Разделяем на EMOTION (stress) и SOCIAL (trust, fear)
                try:
                    # 1. Эмоциональная реакция (стресс)
                    if stress_delta != 0.0:
                        deltas.append(StateDeltas(
                            npc_id=npc_id,
                            # v1 backward compat
                            stress_delta=stress_delta,
                            # v2 domain-tagged payload
                            domain=DeltaDomain.EMOTION,
                            payload=EmotionPayload(stress_delta=stress_delta),
                            source="reaction",
                        ))

                    # 2. Социальная реакция (страх, доверие)
                    if fear_delta != 0.0 or trust_delta != 0.0:
                        social_kwargs = {
                            "npc_id": npc_id,
                            # v1 backward compat
                            "fear_delta": fear_delta,
                            "trust_delta": trust_delta,
                            # v2 domain-tagged payload
                            "domain": DeltaDomain.SOCIAL,
                            "payload": SocialPayload(fear_delta=fear_delta, trust_delta=trust_delta),
                            "source": "reaction",
                        }
                        if trust_delta != 0.0:
                            social_kwargs[trust_target_key] = trust_target_val # v1 compat
                            social_kwargs["target"] = trust_target_val           # v2 compat

                        deltas.append(StateDeltas(**social_kwargs))

                except ValueError as e:
                    # Невалидная дельта (конфликт таргетов) — логируем и пропускаем
                    logger.warning(
                        f"[REACTION_SUB] невалидная дельта для {npc_id}: {e}"
                    )

        if deltas:
            logger.debug(
                f"[REACTION_SUB] {len(events)} events, "
                f"{len(perceiving_ids)} perceivers, "
                f"{len(deltas)} deltas"
            )

        return Phase8Result(
            deltas=deltas,
            events_processed=len(events),
        )

    @staticmethod
    def _get_perceiving_ids(ctx: Phase8Context) -> set[str]:
        """Определяет список реагирующих NPC.

        Использует perceiving_npcs из shared_context (установлен
        PerceptionSubscriber в этом же тике) или fallback на всех NPC.
        """
        if ctx.shared_context is not None:
            perceiving_list = getattr(
                ctx.shared_context, "perceiving_npcs", None
            )
            # None = не установлен → fallback; [] = никто не увидел → пусто
            if perceiving_list is not None:
                return set(perceiving_list)

        # Fallback: все NPC из all_npcs_raw
        return {
            npc.get("id") or npc.get("npc_id")
            for npc in ctx.all_npcs_raw
            if npc.get("id") or npc.get("npc_id")
        }
from __future__ import annotations

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


import logging
from typing import Any, Dict, List, Optional

from app.domain.constants import ACTION_INTENSITY
from app.domain.events import EventDTO
from app.models.delta_payloads import (
    EmotionPayload,
    PerceptionPayload,
    PhysiologyPayload,
    SocialPayload,
)
from app.models.phase8 import Phase8Context, Phase8Result
from app.models.state_delta import DeltaDomain, StateDeltas
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
    "player_attacks": (15.0, 10.0, -8.0),
    "player_attack": (15.0, 10.0, -8.0),
    "player_attacked": (20.0, 15.0, -12.0),
    "player_threatens": (10.0, 8.0, -4.0),
    "player_threatens_indirect": (7.0, 5.0, -2.0),
    "player_insults": (5.0, 2.0, -3.0),
    "combat": (18.0, 12.0, -6.0),
    "theft": (8.0, 3.0, -7.0),
    "intimidation": (12.0, 10.0, -3.0),
    "betrayal": (15.0, 8.0, -12.0),
    "help": (-3.0, 0.0, 5.0),
    "saved_life": (-5.0, -3.0, 10.0),
    "object_destroyed": (5.0, 3.0, 0.0),
}


def _get_event_intensity(event: EventDTO) -> float:
    """Интенсивность из payload или ACTION_INTENSITY fallback."""
    intensity = event.payload.get("intensity")
    if intensity is not None:
        return float(intensity)
    return ACTION_INTENSITY.get(event.type.lower(), 0.2)


def _compute_reaction_modifier(npc_dict: Dict[str, Any]) -> float:
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


def _is_npc_source(source: str, all_npcs_raw: List[Any]) -> bool:
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

    def _on_event(self, event: EventDTO) -> Optional[Dict[str, Any]]:
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
            logger.warning(
                "[REACTION_SUB] handle() called with 0 events — no emotional reactions this tick"
            )
            return Phase8Result()

        logger.warning(
            f"[REACTION_SUB] handle() called with {len(events)} events types={[getattr(e, 'type', '?') for e in events[:3]]}"
        )

        # Извлекаем физический шок из материализованного Physical Layer (t)
        shock_by_npc: dict[str, float] = {}
        for delta in ctx.physical_deltas_materialized:
            if (
                delta.npc_id
                and delta.domain == DeltaDomain.PHYSIOLOGY
                and isinstance(delta.payload, PhysiologyPayload)
            ):
                imp = delta.payload.shock_impulse
                if imp > 0:
                    shock_by_npc[delta.npc_id] = max(
                        shock_by_npc.get(delta.npc_id, 0.0), imp
                    )

        # Определяем реагирующих NPC
        perceiving_ids = self._get_perceiving_ids(ctx)
        if not perceiving_ids:
            logger.warning(
                f"[REACTION_SUB] perceiving_ids EMPTY — no NPC to react. all_npcs_raw={len(ctx.all_npcs_raw) if ctx.all_npcs_raw else 0}"
            )
            return Phase8Result()
        logger.warning(
            f"[REACTION_SUB] perceiving_ids count={len(perceiving_ids)} ids={list(perceiving_ids)[:5]}"
        )

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

            # S115 FIX: Цель прямой угрозы/атаки получает threat_gradient_delta.
            # Без этого affective_load остаётся 0, и BreakProgressEngine не фиксирует давление.
            _event_target_id = event.payload.get("target_id")
            if _event_target_id and rule_key in (
                "player_threatens",
                "player_attacks",
                "player_attack",
            ):
                _threat_delta_target = 0.8 if rule_key == "player_threatens" else 0.6
                deltas.append(
                    StateDeltas(
                        npc_id=_event_target_id,
                        domain=DeltaDomain.PERCEPTION,
                        payload=PerceptionPayload(
                            threat_gradient_delta=round(_threat_delta_target, 3),
                        ),
                        source="reaction_perception_target",
                    )
                )

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

                # Вычисляем дельты (базовая реакция на событие)
                stress_delta = round(stress_base * modifier * intensity, 2)
                fear_delta = round(fear_base * modifier * intensity, 2)
                trust_delta = round(trust_actor_base * modifier * intensity, 2)

                # Каскад Force → Pain → Shock → Emotion (Приоритет 1)
                # Свой шок (цель) или эмпатический ужас от шока цели (свидетель)
                shock = shock_by_npc.get(npc_id, 0.0)
                if shock == 0.0:
                    target_id = event.payload.get("target_id")
                    if target_id and target_id != npc_id:
                        shock = shock_by_npc.get(target_id, 0.0)

                # CIR: Phase 8 (Reflex) лишена права генерировать эмоции (S-слой).
                # Она эмитит только причинные намёки (stress_delta, fear_delta) — M-слой.
                # Интерпретация стресса как "fear"/"panic" происходит исключительно в Phase 9 (Affective Pipeline).
                if shock > 0.0:
                    stress_delta += round(shock * 30.0 * modifier, 2)
                    fear_delta += round(shock * 15.0 * modifier, 2)

                # Пропускаем нулевые дельты
                if stress_delta == 0.0 and fear_delta == 0.0 and trust_delta == 0.0:
                    continue

                # ADR-123: Combat → Perception мост. Свидетели насилия получают threat_gradient_delta.
                # Без этого PerceptualKernel.threat_gradient = 0.0 после боя → fear=0.0.
                # Боль — это физиология. Угроза — это восприятие. Они независимы.
                _threat_delta = 0.0
                if shock > 0.0:
                    _threat_delta = min(0.5, shock * 2.0)  # Шок от удара → угроза
                elif rule_key in ("player_attacked", "player_attack", "combat"):
                    _threat_delta = 0.3 * intensity  # Свидетельство насилия → угроза

                if _threat_delta > 0.0:
                    deltas.append(
                        StateDeltas(
                            npc_id=npc_id,
                            domain=DeltaDomain.PERCEPTION,
                            payload=PerceptionPayload(
                                threat_gradient_delta=round(_threat_delta, 3),
                            ),
                            source="reaction_perception",
                        )
                    )

                # v2: Разделяем на EMOTION (stress) и SOCIAL (trust, fear)
                try:
                    # 1. Эмоциональная реакция (стресс + шок)
                    if stress_delta != 0.0:
                        deltas.append(
                            StateDeltas(
                                npc_id=npc_id,
                                # v1 backward compat
                                stress_delta=stress_delta,
                                # v2 domain-tagged payload
                                domain=DeltaDomain.EMOTION,
                                # CIR: Рефлекс передаёт только стресс (M-hint). Эмоция и интеграл вычисляются в Phase 9.
                                payload=EmotionPayload(
                                    stress_delta=stress_delta,
                                    emotion_tag=None,
                                    affective_load=None,
                                ),
                                source="reaction",
                            )
                        )

                    # 2. Социальная реакция (страх, доверие)
                    if fear_delta != 0.0 or trust_delta != 0.0:
                        social_kwargs = {
                            "npc_id": npc_id,
                            # v1 backward compat
                            "fear_delta": fear_delta,
                            "trust_delta": trust_delta,
                            # v2 domain-tagged payload
                            "domain": DeltaDomain.SOCIAL,
                            "payload": SocialPayload(
                                fear_delta=fear_delta, trust_delta=trust_delta
                            ),
                            "source": "reaction",
                        }
                        if trust_delta != 0.0:
                            social_kwargs[trust_target_key] = (
                                trust_target_val  # v1 compat
                            )
                            social_kwargs["target"] = trust_target_val  # v2 compat

                        deltas.append(StateDeltas(**social_kwargs))

                except ValueError as e:
                    # Невалидная дельта (конфликт таргетов) — логируем и пропускаем
                    logger.warning(
                        f"[REACTION_SUB] невалидная дельта для {npc_id}: {e}"
                    )

        if deltas:
            # ADR-116: Диагностика — какие дельты и emotion_tag генерируются
            _emo_deltas = [d for d in deltas if d.domain == DeltaDomain.EMOTION]
            _emo_tags = [getattr(d.payload, "emotion_tag", None) for d in _emo_deltas]
            logger.warning(
                f"[REACTION_SUB] {len(events)} events, "
                f"{len(perceiving_ids)} perceivers, "
                f"{len(deltas)} deltas, emotion_deltas={len(_emo_deltas)}, tags={_emo_tags}"
            )
        else:
            logger.warning(
                f"[REACTION_SUB] 0 deltas from {len(events)} events, {len(perceiving_ids)} perceivers, rule_key={events[0].type.lower() if events else 'NONE'}"
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
            perceiving_list = getattr(ctx.shared_context, "perceiving_npcs", None)
            # §ENIGMA-003: [] ≠ None. [] = валидная проекция "никто не увидел". None = сбой сбора.
            if perceiving_list is not None:
                return set(perceiving_list)  # Пустой список вернёт пустой set()

        # Fallback: все NPC из all_npcs_raw
        return {
            npc.get("id") or npc.get("npc_id")
            for npc in ctx.all_npcs_raw
            if npc.get("id") or npc.get("npc_id")
        }

from __future__ import annotations

# backend/app/services/npc/belief_transition_engine.py
"""
Write-path эпистемического слоя.

Единственный владелец записи в NPCState.beliefs.
Вызывается до DecisionHub.compute() — убеждения должны быть актуальны до решения.

Паттерн интеграции:
    apply_perception_memory(...)     ← фаза 3, запись в память
    BeliefTransitionEngine.integrate ← R7, запись в убеждения
    InterpretationEngine.compute(...)← фаза 3.1, cognitive distortion
    DecisionHub.compute(...)         ← решение
"""


import logging
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from app.models.npc_state import NPCState
    from app.services.npc.decision_hub import EventContext

from app.models.npc.beliefs import BeliefDelta, BeliefType

logger = logging.getLogger(__name__)

# Затухание сигнала по расстоянию (на метр теряется k)
_DISTANCE_DECAY_K: float = 0.12

# Коэффициент инерции убеждений (70% — старое, 30% — новое)
_BELIEF_INERTIA: float = 0.70

# Инерция убеждения о враждебности игрока чуть выше —
# негативный опыт помнится дольше нейтрального (ADR-049 принцип)
_HOSTILITY_INERTIA: float = 0.75

# Типы событий → рост угрозы
_THREAT_TYPES: frozenset = frozenset(
    {
        "player_attacks",
        "player_threatens",
        "player_cast_spell",
        "weapon_drawn",
        "combat_started",
    }
)

# Типы событий → снижение угрозы (медленнее роста)
_SAFE_TYPES: frozenset = frozenset(
    {
        "player_interacts",
        "player_helps",
        "player_trades",
        "idle",
        "npc_greets",
    }
)


# WRITE PATH 1/2: BeliefTransitionEngine → BeliefState
# Реактивный (R7): обновляет убеждения из текущего события per-tick.
# Второй writer — CoherenceBeliefAggregator (R8).
# Без правила мёрджа между ними. См. BeliefState docstring.
class BeliefTransitionEngine:
    """
    Обновляет NPCState.beliefs из EventContext.

    WRITE: только этот класс.
    READ: BeliefModifierResolver (следующий шаг, День 3).
    """

    def commit(
        self,
        state: "NPCState",
        event: "EventContext",
        current_tick: int,
    ) -> List["BeliefDelta"]:
        """
        Генерирует BeliefDelta из EventContext.
        Не мутирует state напрямую. StateApplicator применит дельту (SSOT).

        Формула убеждения:
            new = old * inertia + signal * (1 - inertia)
            signal = intensity * distance_factor

        Вызывать один раз за тик, до DecisionHub.
        """
        event_type_str: str = (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        )

        # Сигнал: интенсивность × затухание по расстоянию
        distance_factor = max(0.1, 1.0 - event.distance * _DISTANCE_DECAY_K)
        base_signal = round(event.intensity * distance_factor, 4)

        deltas: List[BeliefDelta] = []
        _d_danger = self._update_danger(
            state, event_type_str, base_signal, event.visible_threat_markers, current_tick
        )
        if _d_danger:
            deltas.append(_d_danger)

        # PLAYER_HOSTILE — только если источник события игрок
        if event.actor_id == "player":
            _d_hostile = self._update_player_hostile(
                state, event_type_str, base_signal, current_tick
            )
            if _d_hostile:
                deltas.append(_d_hostile)

        return deltas

    # ──────────────────────────────────────────────────────────────────────
    # Внутренние методы
    # ──────────────────────────────────────────────────────────────────────

    def _update_danger(
        self,
        state: "NPCState",
        event_type_str: str,
        base_signal: float,
        visible_markers: List[Any],
        tick: int,
    ) -> Optional[BeliefDelta]:
        """Обновить убеждение DANGER."""

        # Определить направление сигнала
        if event_type_str in _THREAT_TYPES:
            signal = base_signal
            confidence_delta = +0.10
        elif event_type_str in _SAFE_TYPES:
            # Снижение втрое медленнее роста — асимметрия страха
            signal = -base_signal * 0.33
            confidence_delta = -0.05
        elif visible_markers:
            # Fallback: видимые маркеры угрозы даже без известного типа
            signal = base_signal * 0.5
            confidence_delta = +0.05
        else:
            return None  # неизвестный тип без маркеров → не трогаем убеждение

        old = state.beliefs.get(BeliefType.DANGER)
        old_value = old.value if old else 0.0
        old_confidence = old.confidence if old else 0.5

        new_value = max(
            0.0,
            min(1.0, old_value * _BELIEF_INERTIA + signal * (1.0 - _BELIEF_INERTIA)),
        )
        new_confidence = max(0.1, min(1.0, old_confidence + confidence_delta))

        return BeliefDelta(
            belief_type=BeliefType.DANGER,
            old_value=old_value,
            new_value=round(new_value, 4),
            confidence=round(new_confidence, 4),
            source="perception",
            timestamp=tick,
        )

    def _update_player_hostile(
        self,
        state: "NPCState",
        event_type_str: str,
        base_signal: float,
        tick: int,
    ) -> Optional[BeliefDelta]:
        """Обновить убеждение PLAYER_HOSTILE."""

        if event_type_str in _THREAT_TYPES:
            signal = base_signal
        elif event_type_str in _SAFE_TYPES:
            signal = -base_signal * 0.2
        else:
            return None

        old = state.beliefs.get(BeliefType.PLAYER_HOSTILE)
        old_value = old.value if old else 0.0

        new_value = max(
            0.0,
            min(
                1.0,
                old_value * _HOSTILITY_INERTIA + signal * (1.0 - _HOSTILITY_INERTIA),
            ),
        )

        return BeliefDelta(
            belief_type=BeliefType.PLAYER_HOSTILE,
            old_value=old_value,
            new_value=round(new_value, 4),
            confidence=0.85,
            source="perception",
            timestamp=tick,
        )

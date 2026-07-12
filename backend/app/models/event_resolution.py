from __future__ import annotations
# backend/app/models/event_resolution.py
"""
EventResolutionResult — unified envelope для выхода из resolver.

ПРИНЦИП: ВСЁ что выходит из parser/resolver проходит через это.
Без этого — два разрозненных пути (verbal/physical) → разная обработка → баги.

Назначение: Unified envelope — всё что выходит из resolver проходит через это
Зависимости: typing, dataclasses (чистый слой)
Основные сущности: EventResolutionResult, StateChange, DecisionSignal, ReflexConstraint

Три канала (строго разделены):
  StateChanges    — физика (hp, conditions, wounds). Только данные, не визуал.
  SceneEvents     — сцена (кровь, стаггер, крик). Только визуал, не стейт.
  DecisionSignals — решение (constraints, biases). Только для DecisionHub.

ЗАПРЕЩЕНО:
  - Смешивать каналы (MicroEvent не меняет HP)
  - DecisionSignal не создаёт визуал
  - StateChange не идёт в DM промпт напрямую
"""


from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional


# ═════════════════════════════════════════════════════════
# КАНАЛ 1: STATE CHANGES (физика — только данные)
# ═════════════════════════════════════════════════════════


@dataclass(frozen=True)
class StateChange:
    """
    Атомарное изменение состояния NPC.
    НЕ визуальное — только числа для StateApplicator.

    Примеры:
      StateChange(target="maid_lusya", field="hp", delta=-12, source="sword_slash")
      StateChange(target="maid_lusya", field="threat.player", delta=15, source="attack")
    """

    target_id: str
    field: str  # "hp", "stress", "threat.{source}", "condition.{type}"
    delta: float
    source: str  # "damage", "bleeding", "condition_tick", "threat_accumulation"


# ═════════════════════════════════════════════════════════
# КАНАЛ 2: DECISION SIGNALS (решения — только для DecisionHub)
# ═════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ReflexConstraint:
    """
    Ограничение от рефлекса — NPC ограничен, но жив.

    НЕ блокирует полностью (это делает NPC "болванчиком").
    Ограничивает выбор через penalties и allowed_intents.

    Примеры:
      staggered: allowed=[IDLE, FLEE], penalty={ATTACK: -0.7}, max_movement=0
      stunned:  allowed=[IDLE], penalty={}, max_movement=0
      prone:    penalty={ATTACK: -0.5, FLEE: -0.3}, max_movement=0.3
    """

    allowed_intents: tuple[str, ...] = ()  # пусто = все разрешены
    penalties: tuple[tuple[str, float], ...] = ()  # (intent, penalty)
    max_movement: float = 1.0  # 0 = нельзя двигаться
    duration_ticks: int = 1  # сколько тиков длится

    def to_dict(self) -> Dict[str, object]:
        """Для сериализации и передачи в DecisionHub."""
        return {
            "allowed_intents": list(self.allowed_intents),
            "penalties": dict(self.penalties),
            "max_movement": self.max_movement,
            "duration_ticks": self.duration_ticks,
        }


@dataclass(frozen=True)
class DecisionSignal:
    """
    Сигнал для DecisionHub — ограничение или bias.
    НЕ создаёт визуал. НЕ меняет стейт напрямую.

    Примеры:
      DecisionSignal(target="maid_lusya", signal_type="constraint", constraint=ReflexConstraint(...))
      DecisionSignal(target="maid_lusya", signal_type="alert", bias={"FLEE": +0.3})
    """

    target_id: str
    signal_type: Literal["constraint", "bias", "alert"]
    constraint: Optional[ReflexConstraint] = None
    bias: tuple[tuple[str, float], ...] = ()  # (intent, modifier)


# ═════════════════════════════════════════════════════════
# КАНАЛ 3: SCENE EVENTS (визуал — только для DM/SceneContinuity)
# ═════════════════════════════════════════════════════════
# SceneEvents = существующий MicroEvent из reaction/micro_event.py
# НЕ дублируем — импортируем. MicroEvent уже frozen dataclass.


# ═════════════════════════════════════════════════════════
# UNIFIED ENVELOPE
# ═════════════════════════════════════════════════════════


@dataclass
class EventResolutionResult:
    """
    Unified envelope — единственный выход из resolver layer.

    Каждое действие игрока проходит через это:
      VERBAL  → type="verbal",  state_changes=[], scene_events=[], decision_signals=[]
      PHYSICAL → type="physical", все три канала заполнены

    WHY: Без этого envelope game_loop имеет if/else ветвление
         по типу события → разные пути обработки → баги.
    """

    type: Literal["verbal", "physical"]

    # Physical outcome (только при type="physical")
    # Определяется в models/physical.py — импортируем там где нужен
    physical_outcome: Optional[object] = None  # PhysicalOutcome (forward ref)

    # Три канала (строго разделены)
    state_changes: List[StateChange] = field(default_factory=list)
    decision_signals: List[DecisionSignal] = field(default_factory=list)
    # scene_events: List[MicroEvent] — добавляется в game_loop из ReflexResolver

    @property
    def has_physical(self) -> bool:
        return self.type == "physical" and self.physical_outcome is not None

    @property
    def has_constraints(self) -> bool:
        return any(s.signal_type == "constraint" for s in self.decision_signals)

    @property
    def has_state_impact(self) -> bool:
        return len(self.state_changes) > 0

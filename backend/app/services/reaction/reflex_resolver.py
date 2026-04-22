# backend/app/services/reaction/reflex_resolver.py
"""
ReflexResolver — мгновенная реакция на физический удар.

Позиция в pipeline:
    PhysicalOutcome → ReflexResolver → SceneEvents + DecisionSignals → StateApplicator

Назначение: Мгновенный рефлекс на физический удар — ДО DecisionHub
Зависимости: models/physical.py, reaction/micro_event.py, models/event_resolution.py
Основные сущности: ReflexResolver, ReflexResult

КРИТИЧЕСКОЕ ОТЛИЧИЕ от ReactionResolver:
    ReactionResolver (ШАГ 0.5) — ПОСЛЕ DecisionHub, осознанная реакция
    ReflexResolver (Шаг 3)      — ДО DecisionHub, рефлекс без мышления

ПРИНЦИПЫ:
  - НЕ думает. НЕ выбирает. Только рефлексы.
  - Генерирует SceneEvents (визуал) и DecisionSignals (constraints).
  - StateChanges НЕ генерирует — это делает StateApplicator.
  - ReflexConstraint ограничивает, но НЕ блокирует полностью.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from app.models.physical import (
    DamageType,
    PhysicalOutcome,
    WoundSeverity,
)
from app.models.event_resolution import DecisionSignal, ReflexConstraint
from app.services.reaction.micro_event import MicroEvent, MicroEventType


# ── Пороги рефлексов ──────────────────────────────────────────────────────

# Стаггер: отшатывание при достаточном уроне
_STAGGER_DAMAGE_THRESHOLD = 5
_STAGGER_BASE_PROBABILITY = 0.7

# Крик боли
_CRY_BASE_PROBABILITY = 0.8
_CRY_SUPPRESSED_BY_SEVERITY = 0.3  # при высокой severity шок — крик приглушён

# Кровь
_BLOOD_DAMAGE_THRESHOLD = 8
_BLOOD_CRITICAL_MULTIPLIER = 1.5  # крит = больше крови

# Выбить оружие
_WEAPON_DROP_DAMAGE_THRESHOLD = 12
_WEAPON_DROP_CRITICAL = True  # крит всегда выбивает

# Упасть
_FALL_DAMAGE_THRESHOLD = 15
_FALL_HP_FRACTION = 0.3  # или если урон > 30% от max_hp

# Дёрнуться (всегда при попадании)
_FLINCH_BASE_PROBABILITY = 0.9

# Маппинг DamageType → специфика рефлексов
_DAMAGE_REFLEX_MODIFIERS: Dict[DamageType, Dict[str, float]] = {
    DamageType.SLASHING: {"cry": 1.1, "blood": 1.3, "stagger": 0.9},
    DamageType.PIERCING: {"cry": 1.2, "blood": 1.1, "stagger": 0.8},
    DamageType.BLUDGEONING: {"cry": 0.9, "blood": 0.5, "stagger": 1.3},
    DamageType.FIRE: {"cry": 1.3, "blood": 0.2, "stagger": 1.0},
    DamageType.COLD: {"cry": 0.7, "blood": 0.1, "stagger": 0.7},
    DamageType.POISON: {"cry": 0.5, "blood": 0.3, "stagger": 0.3},
    DamageType.PSYCHIC: {"cry": 0.4, "blood": 0.0, "stagger": 0.5},
}


@dataclass
class ReflexResult:
    """
    Результат рефлекса — три канала строго разделены.
    
    scene_events → SceneContinuity + DM промпт (визуал)
    decision_signals → DecisionHub (constraints/biases)
    
    StateChanges НЕ здесь — их делает StateApplicator по PhysicalOutcome.
    """
    scene_events: List[MicroEvent] = field(default_factory=list)
    decision_signals: List[DecisionSignal] = field(default_factory=list)
    
    @property
    def has_constraint(self) -> bool:
        return any(s.signal_type == "constraint" for s in self.decision_signals)


class ReflexResolver:
    """
    Генерирует рефлексы на PhysicalOutcome.
    Чистый Python — не использует LLM.
    """
    
    def resolve(
        self,
        outcome: PhysicalOutcome,
        npc_id: str,
        current_hp: int = 0,
        max_hp: int = 0,
        distance: float = 0.0,
    ) -> ReflexResult:
        """
        Генерирует рефлекторные события и constraints.
        
        Args:
            outcome: Результат PhysicalResolver (hit, damage, type)
            npc_id: ID NPC получившего удар
            current_hp: Текущее HP (до урона)
            max_hp: Максимальное HP
            distance: Расстояние до атакующего
            
        Returns:
            ReflexResult с scene_events и decision_signals
        """
        if not outcome.hit:
            return ReflexResult()
        
        events: List[MicroEvent] = []
        signals: List[DecisionSignal] = []
        
        modifiers = _DAMAGE_REFLEX_MODIFIERS.get(outcome.damage_type, {})
        
        # ── 1. Флинч (всегда при попадании) ──
        p_flinch = _FLINCH_BASE_PROBABILITY * modifiers.get("stagger", 1.0)
        if random.random() < p_flinch:
            events.append(MicroEvent(
                event_type=MicroEventType.FLINCHED,
                npc_id=npc_id,
                trigger="hit",
                probability=round(p_flinch, 3),
                details={"damage": outcome.damage, "type": outcome.damage_type.value},
            ))
        
        # ── 2. Стаггер (при достаточном уроне) ──
        if outcome.damage >= _STAGGER_DAMAGE_THRESHOLD:
            p_stagger = _STAGGER_BASE_PROBABILITY * modifiers.get("stagger", 1.0)
            if outcome.critical:
                p_stagger = min(1.0, p_stagger + 0.3)
            if random.random() < p_stagger:
                events.append(MicroEvent(
                    event_type=MicroEventType.STAGGERED,
                    npc_id=npc_id,
                    trigger="heavy_hit",
                    probability=round(p_stagger, 3),
                    details={"damage": outcome.damage},
                ))
                # Стаггер → constraint на этот тик
                signals.append(DecisionSignal(
                    target_id=npc_id,
                    signal_type="constraint",
                    constraint=ReflexConstraint(
                        allowed_intents=("IDLE", "FLEE"),
                        penalties=(("ATTACK", -0.7), ("TALK", -0.5)),
                        max_movement=0.3,
                        duration_ticks=1,
                    ),
                ))
        
        # ── 3. Крик боли ──
        p_cry = _CRY_BASE_PROBABILITY * modifiers.get("cry", 1.0)
        # При тяжёлых ранах — шок, крик приглушён
        if outcome.wound_severity in (WoundSeverity.SEVERE, WoundSeverity.CRIPPLING):
            p_cry *= _CRY_SUPPRESSED_BY_SEVERITY
        if random.random() < p_cry:
            events.append(MicroEvent(
                event_type=MicroEventType.CRY_OF_PAIN,
                npc_id=npc_id,
                trigger="damage",
                probability=round(p_cry, 3),
                details={
                    "damage": outcome.damage,
                    "intensity": "muted" if p_cry < 0.5 else "normal",
                },
            ))
        
        # ── 4. Кровь ──
        if outcome.damage >= _BLOOD_DAMAGE_THRESHOLD:
            p_blood = 0.6 * modifiers.get("blood", 1.0)
            if outcome.critical:
                p_blood *= _BLOOD_CRITICAL_MULTIPLIER
            if random.random() < p_blood:
                events.append(MicroEvent(
                    event_type=MicroEventType.BLOOD_SPATTER,
                    npc_id=npc_id,
                    trigger="wound",
                    probability=round(p_blood, 3),
                    details={"damage_type": outcome.damage_type.value},
                ))
        
        # ── 5. Выбить оружие ──
        if outcome.damage >= _WEAPON_DROP_DAMAGE_THRESHOLD or (
            _WEAPON_DROP_CRITICAL and outcome.critical
        ):
            p_drop = 0.5 if outcome.critical else 0.25
            if random.random() < p_drop:
                events.append(MicroEvent(
                    event_type=MicroEventType.WEAPON_DROPPED_FORCE,
                    npc_id=npc_id,
                    trigger="impact",
                    probability=round(p_drop, 3),
                    details={"damage": outcome.damage},
                ))
        
        # ── 6. Упасть ──
        hp_fraction = outcome.damage / max_hp if max_hp > 0 else 0
        should_fall = (
            outcome.damage >= _FALL_DAMAGE_THRESHOLD
            or hp_fraction >= _FALL_HP_FRACTION
        )
        if should_fall:
            p_fall = 0.4 + 0.3 * hp_fraction  # больше урона → вероятнее падение
            if outcome.critical:
                p_fall = min(1.0, p_fall + 0.2)
            if random.random() < p_fall:
                events.append(MicroEvent(
                    event_type=MicroEventType.FELL_TO_GROUND,
                    npc_id=npc_id,
                    trigger="knockdown",
                    probability=round(p_fall, 3),
                    details={"damage": outcome.damage},
                ))
                # Падение → жёсткий constraint
                signals.append(DecisionSignal(
                    target_id=npc_id,
                    signal_type="constraint",
                    constraint=ReflexConstraint(
                        allowed_intents=("IDLE",),
                        penalties=(("ATTACK", -0.9), ("FLEE", -0.6)),
                        max_movement=0.0,
                        duration_ticks=2,  # на земле дольше
                    ),
                ))
        
        # ── 7. Alert signal (всегда при попадании) ──
        # DecisionHub получает bias к оборонительным интентам
        alert_bias: List[Tuple[str, float]] = [
            ("FLEE", 0.2 + 0.1 * hp_fraction),
            ("OBSERVE", 0.1),
        ]
        if outcome.damage > 10:
            alert_bias.append(("HELP", 0.15))
        signals.append(DecisionSignal(
            target_id=npc_id,
            signal_type="alert",
            bias=tuple(alert_bias),
        ))
        
        return ReflexResult(scene_events=events, decision_signals=signals)
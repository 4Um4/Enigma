# backend/app/services/npc/condition_engine.py
"""
ConditionEngine — тикер временных состояний NPC.

Назначение: Тикер conditions — работает ВСЕГДА, не только при PHYSICAL
Зависимости: models/physical.py, reaction/micro_event.py
Основные сущности: ConditionEngine

Позиция в pipeline:
    КАЖДЫЙ тик → ConditionEngine.tick() → StateChanges + SceneEvents

КРИТИЧЕСКОЕ ПРАВИЛО:
    ConditionEngine работает ВСЕГДА, не только при PHYSICAL событии.
    Иначе bleeding не тикает без боя → система "контекстная", а не постоянная.

Выход — два канала (строго разделены):
    StateChanges   → StateApplicator (hp decay, condition removal)
    SceneEvents    → SceneContinuity (кровь, визуал)

ЗАПРЕЩЕНО:
  - DecisionSignals (условия не решают за NPC — DecisionHub решает)
  - LLM
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from app.models.event_resolution import StateChange
from app.models.physical import Condition
from app.models.npc_state import NPCState
from app.services.reaction.micro_event import MicroEvent, MicroEventType

logger = logging.getLogger(__name__)

# ── Пороги для генерации SceneEvents ──────────────────────────────────────

# Bleeding: при каком severity генерировать визуал крови
_BLEED_VISUAL_THRESHOLD = 0.3

# Stun: минимальный severity для эффекта
_STUN_MIN_SEVERITY = 0.1

# Prone: всегда генерировать event если condition активна


class ConditionEngine:
    """
    Тикер conditions. Чистый Python, без состояния между вызовами.
    Вызывается для каждого NPC каждый тик.
    """
    
    def tick(
        self,
        state: NPCState,
        current_tick: int,
    ) -> Tuple[List[StateChange], List[MicroEvent]]:
        """
        Один тик для всех conditions NPC.
        
        Args:
            state: Текущее состояние NPC
            current_tick: Текущий тик мира
            
        Returns:
            (state_changes, scene_events) — два канала строго разделены
        """
        state_changes: List[StateChange] = []
        scene_events: List[MicroEvent] = []
        
        if not state.conditions:
            return state_changes, scene_events
        
        expired: List[str] = []
        
        for cond_type, cond in state.conditions.items():
            # Тик condition — возвращает False если истёк
            still_active = cond.tick()
            
            if not still_active:
                expired.append(cond_type)
                state_changes.append(StateChange(
                    target_id=state.npc_id,
                    field=f"condition.{cond_type}",
                    delta=0.0,
                    source="condition_expired",
                ))
                continue
            
            # ── Bleeding ──
            if cond_type == "bleeding" and cond.severity > 0.01:
                hp_loss = cond.severity * 2.0
                state_changes.append(StateChange(
                    target_id=state.npc_id,
                    field="hp",
                    delta=-round(hp_loss, 2),
                    source="bleeding_tick",
                ))
                
                # Визуал крови (не каждый тик — по порогу)
                if cond.severity >= _BLEED_VISUAL_THRESHOLD:
                    scene_events.append(MicroEvent(
                        event_type=MicroEventType.BLOOD_SPATTER,
                        npc_id=state.npc_id,
                        trigger="bleeding",
                        probability=round(cond.severity, 3),
                        details={"severity": round(cond.severity, 2), "ongoing": True},
                    ))
            
            # ── Stunned ──
            elif cond_type == "stunned" and cond.severity >= _STUN_MIN_SEVERITY:
                # Визуал — NPC оглушён (для DM промпта)
                scene_events.append(MicroEvent(
                    event_type=MicroEventType.POSTURE_CHANGED,
                    npc_id=state.npc_id,
                    trigger="stunned",
                    probability=round(cond.severity, 3),
                    details={"posture": "staggered", "severity": round(cond.severity, 2)},
                ))
            
            # ── Prone ──
            elif cond_type == "prone":
                scene_events.append(MicroEvent(
                    event_type=MicroEventType.FELL_TO_GROUND,
                    npc_id=state.npc_id,
                    trigger="prone",
                    probability=1.0,
                    details={"ongoing": True},
                ))
            
            # ── Burned ──
            elif cond_type == "burning" and cond.severity > 0.01:
                hp_loss = cond.severity * 1.5
                state_changes.append(StateChange(
                    target_id=state.npc_id,
                    field="hp",
                    delta=-round(hp_loss, 2),
                    source="burning_tick",
                ))
            
            # ── Poisoned ──
            elif cond_type == "poisoned" and cond.severity > 0.01:
                hp_loss = cond.severity * 1.0
                state_changes.append(StateChange(
                    target_id=state.npc_id,
                    field="hp",
                    delta=-round(hp_loss, 2),
                    source="poison_tick",
                ))
        
        # Лог expired
        if expired:
            logger.debug(
                f"[CONDITION] {state.npc_id}: expired {expired}, "
                f"remaining {list(state.conditions.keys())}"
            )
        
        return state_changes, scene_events
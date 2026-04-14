"""
path: /backend/app/services/reaction/reaction_rules.py
Назначение: Чистые Python правила генерации MicroEvents из DecisionResult + EventContext
Зависимости: decision_hub.py (DecisionResult, EventContext), micro_event.py
Основные сущности: compute_reaction_events(), _is_threat_event()

Правила генерации MicroEvents.
Чистый Python scorer — не использует LLM.

Формулы из ROAD_MAP:
  p_drop = (1 - composure) * activity_fragility
  attack + proximity → interaction_disrupted
"""
import random
from typing import List

from app.services.npc.decision_hub import DecisionResult, EventContext
from app.services.reaction.micro_event import MicroEvent, MicroEventType


# ── Пороги для триггеров ──────────────────────────────────────────────────────
_COMPOSURE_DROP_THRESHOLD = 0.4       # ниже — возможно уронить
_COMPOSURE_DISRUPT_THRESHOLD = 0.3    # ниже — прервать действие
_PROXIMITY_DISRUPT_M = 2.0            # метры — слишком близко для атаки

# ── Хрупкость активностей (насколько легко прервать) ───────────────────────────
_ACTIVITY_FRAGILITY: dict = {
    "serving": 0.8,       # поднос — легко уронить
    "working": 0.6,       # работа — средняя
    "talking": 0.3,       # разговор — сложно прервать физически
    "idle": 0.1,          # бездействие — нечего прерывать
    "guarding": 0.2,      # охрана — устойчивая
}
_ACTIVITY_FRAGILITY_DEFAULT = 0.4


def compute_reaction_events(
    decision: DecisionResult,
    event: EventContext,
    composure: float,
    hands_occupied: bool,
    current_activity: str,
) -> List[MicroEvent]:
    """
    Вычисляет микро-события на основе решения и контекста.
    
    Args:
        decision: Результат DecisionHub (intent, deltas, scores)
        event: Контекст события (event_type, intensity, distance)
        composure: Самообладание [0..1], выводится из state
        hands_occupied: Заняты ли руки NPC
        current_activity: Текущая активность из LifeEngine
        
    Returns:
        Список MicroEvent (может быть пустым — нет физической реакции)
    """
    events: List[MicroEvent] = []
    
    # Базовая проверка: только на угрозы и атаки генерируем реакции
    is_threat = _is_threat_event(event.event_type)
    is_attack = "attack" in event.event_type.lower()
    
    if not is_threat and not is_attack:
        return events
    
    # ── Правило 1: Уронить предмет ─────────────────────────────────────────
    # Условие: угроза + низкий composure + занятые руки
    if hands_occupied and composure < _COMPOSURE_DROP_THRESHOLD:
        fragility = _ACTIVITY_FRAGILITY.get(current_activity, _ACTIVITY_FRAGILITY_DEFAULT)
        p_drop = (1.0 - composure) * fragility
        p_drop = min(1.0, p_drop)
        
        if random.random() < p_drop:
            events.append(MicroEvent(
                event_type=MicroEventType.OBJECT_DROPPED,
                npc_id=decision.npc_id,
                trigger="threat" if is_threat else "attack",
                probability=round(p_drop, 3),
                details={"activity": current_activity},
            ))
    
    # ── Правило 2: Прервать взаимодействие ────────────────────────────────
    # Условие: атака + близость + низкий composure
    if is_attack and event.distance < _PROXIMITY_DISRUPT_M:
        if composure < _COMPOSURE_DISRUPT_THRESHOLD:
            events.append(MicroEvent(
                event_type=MicroEventType.INTERACTION_DISRUPTED,
                npc_id=decision.npc_id,
                trigger="attack_proximity",
                probability=round(1.0 - composure, 3),
                details={"distance": round(event.distance, 1)},
            ))
    
    # ── Правило 3: Сжать оружие/предмет при угрозе ────────────────────────
    # Условие: любая угроза + composure ниже комфортного
    if is_threat and composure < 0.7:
        events.append(MicroEvent(
            event_type=MicroEventType.GRIP_TIGHTENED,
            npc_id=decision.npc_id,
            trigger="threat",
            probability=round(0.7 + 0.3 * (1.0 - composure), 3),
            details={},
        ))
    
    return events


def _is_threat_event(event_type: str) -> bool:
    """Проверяет, является ли событие угрозой для NPC"""
    threat_keywords = ("threat", "attack", "insult", "intimidat", "violence")
    return any(kw in event_type.lower() for kw in threat_keywords)
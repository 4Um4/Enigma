from __future__ import annotations
# backend/app/services/memory/event_semantic_tagger.py
"""
Интерпретационный слой: EventContext → semantic tags.

ЕДИНСТВЕННОЕ место где event_type используется для социального смысла.
Всё downstream (EvidenceMapper, BeliefAggregator) работает только с semantic tags.

Принцип:
  event_type — механика ("player_attacks")
  semantic tag — социальный смысл ("social:aggression", "social:player_actor")

Масштабируемость:
  Добавить новый event_type — добавить строку в _EVENT_SEMANTIC_MAP.
  Логика агрегации не меняется.
"""

from typing import List, Dict, Any, Tuple


# ============================================================================
# Маппинг: event_type → frozenset semantic tags
# Единственное место в системе где event_type знается для social смысла.
# ============================================================================

_EVENT_SEMANTIC_MAP: dict[str, frozenset[str]] = {
    # Агрессия
    "player_attacks": frozenset({"social:aggression", "social:physical_harm"}),
    "player_threatens": frozenset({"social:aggression", "social:intimidation"}),
    "player_insults": frozenset({"social:aggression", "social:social_harm"}),
    "player_steals": frozenset({"social:aggression", "social:property_harm"}),
    "player_cast_spell": frozenset({"social:aggression", "social:unknown_threat"}),
    # Нейтральное
    "player_interacts": frozenset({"social:interaction"}),
    "player_used_item": frozenset({"social:interaction"}),
    "idle": frozenset({"social:neutral"}),
    # Благожелательное
    "player_helps": frozenset({"social:benevolence"}),
    "player_trades": frozenset({"social:transaction"}),
    # NPC-события
    "npc_killed": frozenset({"social:extreme_harm", "social:irreversible"}),
    "npc_breaks": frozenset({"social:submission"}),
    "npc_role_changed": frozenset({"social:role_shift"}),
    "npc_greets": frozenset({"social:interaction"}),
}

# Тег актора — добавляется если актор известен
_ACTOR_TAG_PLAYER = "social:player_actor"
_ACTOR_TAG_NPC = "social:npc_actor"

# Интенсивность
_INTENSITY_HIGH_TAG = "social:high_intensity"
_INTENSITY_HIGH_THRESH = 0.7


class EventSemanticTagger:
    """
    Конвертирует механическое событие в социальные теги.

    Stateless — создавать на каждый вызов или держать как singleton.
    """

    def tag(
        self,
        event_type: str,
        actor_id: str,
        intensity: float = 1.0,
    ) -> Tuple[str, ...]:
        """
        Вернуть semantic tags для данного события.

        Args:
            event_type: механический тип события (event.type)
            actor_id:   кто совершил (event.source)
            intensity:  интенсивность события (EventContext.intensity)

        Returns:
            Tuple[Any, ...] semantic tags — не содержат event_type напрямую
        """
        result: list[str] = []

        # 1. Семантика события
        semantic = _EVENT_SEMANTIC_MAP.get(event_type)
        if semantic:
            result.extend(semantic)
        # Неизвестный тип → не добавляем ничего (не блокируем систему)

        # 2. Тег актора
        if actor_id == "player":
            result.append(_ACTOR_TAG_PLAYER)
        elif actor_id:
            result.append(_ACTOR_TAG_NPC)

        # 3. Интенсивность
        if intensity >= _INTENSITY_HIGH_THRESH:
            result.append(_INTENSITY_HIGH_TAG)

        return tuple(result)

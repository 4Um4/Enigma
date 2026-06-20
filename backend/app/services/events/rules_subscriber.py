"""
path: backend/app/services/events/rules_subscriber.py
Назначение: Rules agent as PURE REDUCER. function(event, snapshot) → delta.
Зависимости: стандартная библиотека Python.
Основные сущности: RulesDelta, RulesSubscriber

АРХИТЕКТУРНЫЙ ПРИНЦИП (TZ-08 v0.2):
Rules = pure function (event, snapshot) → delta.
ЗАПРЕЩЕНО: mutation, запуск фаз, доступ к прошлому тику, cache, state.
"""
from __future__ import annotations
import logging
import hashlib
from typing import Any, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Таблицы D&D 5e (Перенесены из rules_agent.py) ─────────────────────────
_DC_BY_ACTION_TYPE: Dict[str, int] = {
    "COMBAT": 12, "SANDBOX_PHYSICAL": 12, "SANDBOX_SOCIAL": 14,
    "SANDBOX_MILD": 10, "ROMANCE": 14, "CAPTURE": 15,
    "FLEE": 12, "LIFE_CHOICE": 10, "EXPLORE": 0, "UNKNOWN": 12,
}
_ABILITY_BY_ACTION_TYPE: Dict[str, str] = {
    "COMBAT": "strength", "SANDBOX_PHYSICAL": "strength", "SANDBOX_SOCIAL": "charisma",
    "SANDBOX_MILD": "dexterity", "ROMANCE": "charisma", "CAPTURE": "strength",
    "FLEE": "dexterity", "LIFE_CHOICE": "wisdom", "EXPLORE": "perception", "UNKNOWN": "intelligence",
}
_SKILL_BY_ACTION_TYPE: Dict[str, str] = {
    "COMBAT": "Athletics", "SANDBOX_PHYSICAL": "Athletics", "SANDBOX_SOCIAL": "Persuasion",
    "SANDBOX_MILD": "Sleight of Hand", "ROMANCE": "Persuasion", "CAPTURE": "Athletics",
    "FLEE": "Acrobatics", "LIFE_CHOICE": "Insight", "EXPLORE": "Perception", "UNKNOWN": "Intelligence",
}
_NO_ROLL_TYPES = {"EXPLORE", "LIFE_CHOICE", "SANDBOX_MILD"}

@dataclass(frozen=True)
class RulesDelta:
    """Pure delta от RulesSubscriber. Применяется StateApplicator'ом, не здесь."""
    target_id: str
    action_type: str
    damage: float = 0.0
    success: bool = False
    dc: int = 0
    roll: int = 0
    checks: list = None  # Read-only metadata для DM-агента (post-state)

    def __post_init__(self):
        if self.checks is None:
            object.__setattr__(self, 'checks', [])

class RulesSubscriber:
    """PURE REDUCER. Rules = function(event, snapshot) → delta."""

    SUBSCRIBED_EVENTS = frozenset({
        "PLAYER_ATTACKED", "ACTOR_ATTACKS", "COMBAT",
        "player_attacks", "actor_attacks",
    })

    def __init__(self):
        pass # No state. Pure function container.

    def can_handle(self, event_type: str) -> bool:
        return event_type in self.SUBSCRIBED_EVENTS

    def handle(self, event: Any, snapshot: Dict[str, Any]) -> Optional[RulesDelta]:
        """PURE FUNCTION: event + snapshot → delta."""
        event_type = getattr(event, 'type', None) or event.get('type', '')
        if not self.can_handle(event_type):
            return None

        try:
            target_id = self._extract_target(event)
            if not target_id:
                return None

            target_npc = self._find_npc(target_id, snapshot.get('all_npcs_raw', []))
            if not target_npc:
                return None

            action_type = "COMBAT" # Базовый тип для боевых событий
            dc = _DC_BY_ACTION_TYPE.get(action_type, 12)
            
            # Детерминированный бросок d20 (seed from event id + tick)
            _event_id = getattr(event, 'id', '') or str(event.get('id', ''))
            _tick = snapshot.get('tick_number', 0)
            _seed = int(hashlib.sha256(f"{_event_id}:{_tick}".encode()).hexdigest(), 16) % 20 + 1
            roll = _seed

            success = roll >= dc
            damage = self._compute_damage(roll, dc) if success else 0.0

            # Формируем метаданные для DM (Read-only)
            check_meta = {
                "player": getattr(event, 'source', 'system'),
                "action": event_type,
                "action_type": action_type,
                "needs_roll": True,
                "dc": dc,
                "ability": _ABILITY_BY_ACTION_TYPE.get(action_type, "intelligence"),
                "skill": _SKILL_BY_ACTION_TYPE.get(action_type, "Intelligence"),
                "advantage": False,
                "disadvantage": False,
                "result": "успех" if success else "провал",
                "roll": roll,
            }

            delta = RulesDelta(
                target_id=target_id,
                action_type=action_type,
                damage=damage,
                success=success,
                dc=dc,
                roll=roll,
                checks=[check_meta],
            )
            logger.debug(f"[RULES_REDUCER] event={event_type} target={target_id} dc={dc} roll={roll} success={success} dmg={damage}")
            return delta

        except Exception as e:
            logger.error(f"[RULES_REDUCER] failed: {e}", exc_info=True)
            return None

    # ── Pure helper methods (read-only) ──────────────────────────────
    def _extract_target(self, event: Any) -> Optional[str]:
        if hasattr(event, 'payload'):
            return event.payload.get('target_id') or event.payload.get('target_reference')
        return event.get('target_id') or event.get('target_reference')

    def _find_npc(self, npc_id: str, npcs: list) -> Optional[Dict]:
        for npc in npcs:
            if npc.get('npc_id') == npc_id or npc.get('id') == npc_id:
                return npc
        return None

    def _compute_damage(self, roll: int, dc: int) -> float:
        base_damage = 4 # d8 average
        excess = max(0, roll - dc)
        return float(base_damage + excess)
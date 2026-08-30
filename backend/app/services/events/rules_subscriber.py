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

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Таблицы D&D 5e (Перенесены из rules_agent.py) ─────────────────────────
_DC_BY_ACTION_TYPE: Dict[str, int] = {
    "COMBAT": 12,
    "SANDBOX_PHYSICAL": 12,
    "SANDBOX_SOCIAL": 14,
    "SANDBOX_MILD": 10,
    "ROMANCE": 14,
    "CAPTURE": 15,
    "FLEE": 12,
    "LIFE_CHOICE": 10,
    "EXPLORE": 0,
    "UNKNOWN": 12,
}
_ABILITY_BY_ACTION_TYPE: Dict[str, str] = {
    "COMBAT": "strength",
    "SANDBOX_PHYSICAL": "strength",
    "SANDBOX_SOCIAL": "charisma",
    "SANDBOX_MILD": "dexterity",
    "ROMANCE": "charisma",
    "CAPTURE": "strength",
    "FLEE": "dexterity",
    "LIFE_CHOICE": "wisdom",
    "EXPLORE": "perception",
    "UNKNOWN": "intelligence",
}
_SKILL_BY_ACTION_TYPE: Dict[str, str] = {
    "COMBAT": "Athletics",
    "SANDBOX_PHYSICAL": "Athletics",
    "SANDBOX_SOCIAL": "Persuasion",
    "SANDBOX_MILD": "Sleight of Hand",
    "ROMANCE": "Persuasion",
    "CAPTURE": "Athletics",
    "FLEE": "Acrobatics",
    "LIFE_CHOICE": "Insight",
    "EXPLORE": "Perception",
    "UNKNOWN": "Intelligence",
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
    checks: List[Any] = None  # Read-only metadata для DM-агента (post-state)
    money_delta: float = 0.0  # БАГ 5 FIX: Дельта денег для TRADE/GIVE_MONEY

    def __post_init__(self):
        if self.checks is None:
            object.__setattr__(self, "checks", [])


class RulesSubscriber:
    """PURE REDUCER. Rules = function(event, snapshot) → delta."""

    SUBSCRIBED_EVENTS = frozenset(
        {
            "PLAYER_ATTACKED",
            "ACTOR_ATTACKS",
            "COMBAT",
            "player_attacks",
            "actor_attacks",
            "player_interacts",
            "PLAYER_INTERACTS",
        }
    )

    # Эвристики для социальных действий (без LLM)
    _TRUST_POSITIVE_ACTIONS = {"комплимент", "сказать", "поговорить", "помочь"}
    _ATTRACTION_ACTIONS = {"комплимент", "сказать"}
    _GIVE_MONEY_ACTIONS = {"деньги", "отдать", "заплатить"}
    _TRADE_ACTIONS = {"купить", "торгов", "сделка", "эль", "пиво"}

    def __init__(self):
        pass  # No state. Pure function container.

    def can_handle(self, event_type: str) -> bool:
        return event_type in self.SUBSCRIBED_EVENTS

    def handle(self, event: Any, snapshot: Dict[str, Any]) -> Optional[RulesDelta]:
        """PURE FUNCTION: event + snapshot → delta."""
        event_type = getattr(event, "type", None) or event.get("type", "")  # noqa: ENIGMA002
        if not self.can_handle(event_type):
            return None

        try:
            target_id = self._extract_target(event)

            # SHI-FIX TRADE: Fallback на трактирщика для "купить" без явной цели
            if not target_id:
                _raw_input = snapshot.get("raw_input", "").lower()
                if any(w in _raw_input for w in self._TRADE_ACTIONS):
                    for _n in snapshot.get("all_npcs_raw", []):
                        _arch = str(_n.get("_archetype", "")).lower()
                        if _arch in (
                            "tavern_keeper",
                            "merchant",
                            "bartender",
                            "innkeeper",
                        ):
                            target_id = _n.get("npc_id") or _n.get("id")
                            logger.warning(
                                f"[RULES_TRADE_FALLBACK] no explicit target, resolved to tavern_keeper: {target_id}"
                            )
                            break
            if not target_id:
                return None

            # SHI-FIX: Маршрутизация социальных действий
            if event_type in ("player_interacts", "PLAYER_INTERACTS"):
                return self._handle_social(event, target_id, snapshot)

            target_npc = self._find_npc(target_id, snapshot.get("all_npcs_raw", []))
            if not target_npc:
                return None

            action_type = "COMBAT"  # Базовый тип для боевых событий
            dc = _DC_BY_ACTION_TYPE.get(action_type, 12)

            # Детерминированный бросок d20 (seed from event id + tick)
            _event_id = getattr(event, "id", "") or str(event.get("id", ""))  # noqa: ENIGMA002
            _tick = snapshot.get("tick_number", 0)
            _seed = (
                int(hashlib.sha256(f"{_event_id}:{_tick}".encode()).hexdigest(), 16)
                % 20
                + 1
            )
            roll = _seed

            success = roll >= dc
            damage = self._compute_damage(roll, dc) if success else 0.0

            # Формируем метаданные для DM (Read-only)
            check_meta = {
                "player": getattr(event, "source", "system"),
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
            logger.debug(
                f"[RULES_REDUCER] event={event_type} target={target_id} dc={dc} roll={roll} success={success} dmg={damage}"
            )
            return delta

        except Exception as e:
            logger.error(f"[RULES_REDUCER] failed: {e}", exc_info=True)
            return None

    def _handle_social(
        self, event: Any, target_id: str, snapshot: Dict[str, Any]
    ) -> Optional[RulesDelta]:
        """Обработка социальных действий (SOCIAL/LOVE/TRADE) без LLM."""
        _raw_input = snapshot.get("raw_input", "").lower()
        _semantic_action = event.payload.get("semantic_action", "")

        # Если Fast Path не распознал действие, используем эвристики
        if not _semantic_action or _semantic_action == "UNCERTAIN":
            if any(w in _raw_input for w in self._TRUST_POSITIVE_ACTIONS):
                _semantic_action = "COMPLIMENT"
            elif any(w in _raw_input for w in self._GIVE_MONEY_ACTIONS):
                _semantic_action = "GIVE_MONEY"
            elif any(w in _raw_input for w in self._TRADE_ACTIONS):
                _semantic_action = "TRADE"
            else:
                _semantic_action = "INTERACT"

        trust_delta = 0.0
        attraction_delta = 0.0
        money_delta = 0.0

        if _semantic_action == "COMPLIMENT":
            trust_delta = 2.0
            attraction_delta = 1.0
        elif _semantic_action == "GIVE_MONEY":
            trust_delta = 5.0
            money_delta = -5.0
        elif _semantic_action == "TRADE":
            _player_npc = next(
                (
                    n
                    for n in snapshot.get("all_npcs_raw", [])
                    if n.get("npc_id") == "player" or n.get("id") == "player"
                ),
                None,
            )
            if _player_npc:
                _bs = _player_npc.setdefault("body_state", {})
                _current_money = float(_bs.get("money", 0))
                if _current_money >= 5.0:
                    money_delta = -5.0
                    logger.warning(
                        f"[RULES_TRADE] player spent 5.0G, remaining: {_current_money - 5.0}G"
                    )

        if trust_delta > 0 or attraction_delta > 0:
            _rel_store = snapshot.get("relationship_store")
            _campaign_id = snapshot.get("campaign_id")
            if _rel_store and _campaign_id:
                # M1b.2.6 (ADR-O-371; ТЗ-RE-01 §8.6 «зеркальный комплимент
                # заменяется направленной семантикой»; вердикт Мастера —
                # semantic gate, не миграция): ОДНА направленная запись
                # player→target. СТОП-условия: зеркальная target→player
                # удалена (комплимент игрока меняет отношение ИГРОКА к цели —
                # мнение цели о игроке формируется её собственным восприятием,
                # не автозеркалом); кэш-хирургия attraction/trust удалена —
                # кэш есть read-проекция стора (P1 ARCH), его наполняет
                # StateApplicator-гидратация, не подписчик (обходной путь
                # вокруг SSOT закрыт; M1b.3 доведёт fallback-чтения DecisionHub).
                from app.services.social.relationship_write_gate import (
                    RelationshipWriteGate,
                )

                RelationshipWriteGate(_rel_store).apply(
                    _campaign_id,
                    "player",
                    target_id,
                    {"trust": trust_delta, "attraction": attraction_delta},
                    cause=f"rules:compliment:{_semantic_action}",
                )

        return RulesDelta(
            target_id=target_id,
            action_type="SANDBOX_SOCIAL",
            success=True,
            checks=[{"type": "persuasion", "dc": 14, "roll": 15, "success": True}],
            money_delta=money_delta,
        )

    # ── Pure helper methods (read-only) ──────────────────────────────
    def _extract_target(self, event: Any) -> Optional[str]:
        if hasattr(event, "payload"):
            return event.payload.get("target_id") or event.payload.get(
                "target_reference"
            )
        return event.get("target_id") or event.get("target_reference")

    def _find_npc(self, npc_id: str, npcs: List[Any]) -> Optional[Dict]:
        for npc in npcs:
            if npc.get("npc_id") == npc_id or npc.get("id") == npc_id:
                return npc
        return None

    def _compute_damage(self, roll: int, dc: int) -> float:
        base_damage = 4  # d8 average
        excess = max(0, roll - dc)
        return float(base_damage + excess)

# backend/app/services/action/processor.py
#
# Шаг 4 рефакторинга: Единый пайплайн одного хода.
# Вырезан из orchestrator.run_turn() и stream_turn().
#
# Входные данные : список PlayerAction + контекст (campaign_id, location)
# Выходные данные: ProcessingResult (classification + physics_validation)
#
# orchestrator больше не знает ни про classifier, ни про validator напрямую —
# он только вызывает processor.process() и читает результат.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.services.action_classifier import classifier, ActionType
from app.services.game.physics_validator import validator
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import GameEvent, EventType
from app.services.simulation.world_state import get_world_state

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Структуры результата
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ActionResult:
    """Результат обработки одного действия одного игрока."""
    player_name:        str
    action_text:        str
    action_type:        str          # ActionType.value (строка)
    agents_needed:      List[str]
    flags:              Dict[str, Any]
    physics_valid:      bool
    physics_reason:     Optional[str] = None
    physics_alternative: Optional[str] = None


@dataclass
class ProcessingResult:
    """
    Итог пайплайна для всего хода (все игроки).

    classification      — список dict'ов, идентичных тому, что раньше
                          писалось в shared_context["classification"]
    physics_validation  — список dict'ов только для заблокированных действий,
                          идентично shared_context["physics_validation"]
    action_results      — типизированные данные на каждое действие
    """
    classification:     List[Dict[str, Any]] = field(default_factory=list)
    physics_validation: List[Dict[str, Any]] = field(default_factory=list)
    action_results:     List[ActionResult]   = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Процессор
# ─────────────────────────────────────────────────────────────────────────────

class ActionProcessor:
    """
    Единый пайплайн обработки хода:
        1. Action Classifier  → ActionType + agents_needed + flags
        2. Physics Validator  → valid / reason / alternative

    Не знает ни про LLM-агентов, ни про память, ни про SceneState.
    Принимает get_character_dict_func снаружи (dependency injection),
    чтобы не зависеть от CharacterService напрямую.
    """

# Маппинг ActionType → EventType
    _ACTION_TO_EVENT: Dict[str, EventType] = {
        "COMBAT":            EventType.PLAYER_ATTACKED,
        "SANDBOX_PHYSICAL":  EventType.OBJECT_CHANGED,
        "SANDBOX_SOCIAL":    EventType.PLAYER_SPOKE,
        "SANDBOX_MILD":      EventType.PLAYER_SPOKE,
        "SOCIAL":            EventType.PLAYER_SPOKE,
        "SOCIAL_MASS":       EventType.PLAYER_SPOKE,
        "EXPLORE":           EventType.PLAYER_MOVED,
        "ROMANCE":           EventType.PLAYER_SPOKE,
        "CAPTURE":           EventType.PLAYER_ATTACKED,
        "FLEE":              EventType.PLAYER_MOVED,
        "CRAFT_USE":         EventType.PLAYER_USED_ITEM,
    }

    def _publish_event(
        self,
        action_result: "ActionResult",
        location: str,
        scene_state: Optional[Dict] = None,
    ) -> None:
        """
        A.3: Публикует GameEvent в EventBus после успешного affordance check.
        Вызывается только если physics_valid=True.
        Принцип: невозможное не публикуется — NPC никогда не видят несуществующего.
        """
        try:
            event_type = self._ACTION_TO_EVENT.get(
                action_result.action_type, EventType.PLAYER_SPOKE
            )
            radius = 15.0 if action_result.action_type in (
                "COMBAT", "SANDBOX_PHYSICAL", "CAPTURE"
            ) else 5.0

            event = GameEvent(
                event_type  = event_type,
                actor_id    = action_result.player_name,
                location    = location,
                parameters  = {
                    "action_text": action_result.action_text[:120],
                    "action_type": action_result.action_type,
                },
                radius      = radius,
            )

            bus     = get_event_bus()
            results = bus.publish(event)

            # Точка A: записываем в WorldState для Token Budget
            get_world_state().record_event(event.to_dict())

            logger.info(
                f"[PROCESSOR→EVENTBUS] {event_type.name} "
                f"от {action_result.player_name!r} "
                f"radius={radius}м → {len(results)} обработчиков"
            )
        except Exception as e:
            logger.error(f"[PROCESSOR] EventBus publish failed: {e}")

    def process(
        self,
        actions: list,
        campaign_id: str,
        location: str,
        get_character_dict_func: Callable[[str, str], Dict[str, Any]],
        npc_importance: Optional[Dict] = None,
    ) -> ProcessingResult:
        """
        Параметры
        ---------
        actions                 : список PlayerAction (схема из schemas.py)
        campaign_id             : нужен для загрузки character sheet
        location                : текущая локация (передаётся в physics)
        get_character_dict_func : callable(campaign_id, player_name) → dict
        npc_importance          : dict {npc_id: importance} для classifier
        """
        npc_importance = npc_importance or {}
        result = ProcessingResult()

        for action_item in actions:
            action_text = getattr(
                action_item, "action",
                getattr(action_item, "description", str(action_item))
            )
            player_name = action_item.player_name

            # ── 1. Классификация ──────────────────────────────────────────
            act_type = classifier.classify(action_text)
            agents_needed, flags = classifier.get_required_agents(
                act_type,
                npc_present=bool(npc_importance),
            )

            classification_entry: Dict[str, Any] = {
                "player":       player_name,
                "type":         act_type.value,
                "agents":       agents_needed,
                "flags":        flags,
                "text_preview": (
                    action_text[:80] + "..."
                    if len(action_text) > 80
                    else action_text
                ),
            }
            result.classification.append(classification_entry)

            # ── 2. Физический валидатор ───────────────────────────────────
            char_sheet = get_character_dict_func(campaign_id, player_name)
            validation = validator.validate(
                action=action_text,
                character=char_sheet,
                game_state={"location": location},
            )

            physics_valid       = validation.valid
            physics_reason      = None
            physics_alternative = None

            if not physics_valid:
                physics_reason      = validation.reason
                physics_alternative = validation.alternative
                result.physics_validation.append({
                    "player":      player_name,
                    "valid":       False,
                    "reason":      physics_reason,
                    "alternative": physics_alternative,
                })
                logger.warning(
                    f"[PROCESSOR] BLOCKED '{player_name}': {physics_reason}"
                )

            # A.3: публикуем в EventBus если физически возможно
            # (affordance check пройден — NPC могут реагировать)
            action_res_tmp = ActionResult(
                player_name         = player_name,
                action_text         = action_text,
                action_type         = act_type.value,
                agents_needed       = agents_needed,
                flags               = flags,
                physics_valid       = physics_valid,
                physics_reason      = physics_reason,
                physics_alternative = physics_alternative,
            )
            if physics_valid:
                self._publish_event(action_res_tmp, location)

            # ── Combined ──────────────────────────────────────────────────
            result.action_results.append(action_res_tmp)

        logger.info(
            f"[PROCESSOR] Обработано {len(result.action_results)} действий: "
            f"{[r.action_type for r in result.action_results]}"
        )
        return result
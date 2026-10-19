"""
ENIGMA SELF-HEALING (Level 5): Startup Schema Validation (ADR-O-426 D70).

Рефактор D70: функция возвращает List[str] ошибок; решение (блокировать
ли старт) принимает старт-гейт (app.core.startup_gate.run_startup_gate),
а не эта функция. Устраняет COV-D70: «non-blocking warning» →
блокирующий отказ через старт-гейт.

Логирование — на стороне вызова (старт-гейт логирует перед raise).
"""
import logging
from typing import Any, List

logger = logging.getLogger(__name__)


def validate_all_schemas(game_loop: Any = None) -> List[str]:
    """Валидирует NPC configs, TruthState, EventBus при старте.

    ADR-O-426 / D70: возвращает список ошибок. Решение (блокировать ли
    старт) принимает старт-гейт (app.core.startup_gate), а не эта функция.
    Логирование — на стороне вызова.

    Аргументы:
        game_loop: опционально; если передан — проверяются TruthState
            и подписчики TICK_COMPLETED (M-03/N2 regression guard).

    Возвращает:
        List[str] ошибок (пустой = валидно).
    """
    errors: List[str] = []

    # 1. NPC Configs (N9: schedule × activity_map consistency)
    try:
        from app.services.npc.npc_loader import load_npcs_merged

        npcs = load_npcs_merged()
        if not npcs:
            errors.append("No NPCs loaded from config/npc/individuals/")
        for npc in npcs:
            npc_id = npc.get("id", npc.get("npc_id", "unknown"))
            schedule = npc.get("schedule", {})
            activity_map = npc.get("activity_map", {})
            for time_range, activity in schedule.items():
                if activity not in activity_map:
                    errors.append(
                        f"NPC {npc_id}: schedule has '{activity}' at {time_range}, "
                        f"but activity_map has no entry. N9 not fixed."
                    )
    except Exception as e:
        errors.append(f"NPC configs validation crashed: {e}")

    # 2. TruthState & MVP Pipeline (if game_loop is available)
    if game_loop:
        mvp = getattr(game_loop, "mvp_controller", None)  # noqa: ENIGMA002
        if mvp is None:
            logger.warning("[SCHEMA] mvp_controller is None — MVP features disabled (N1).")
        else:
            ts = getattr(mvp, "truth_state", None)  # noqa: ENIGMA002
            if ts is None:
                logger.warning("[SCHEMA] TruthState failed to load (is None) — MVP features disabled.")
            elif len(ts.secrets) == 0:
                logger.warning("[SCHEMA] TruthState loaded with 0 secrets — MVP might be incomplete.")

            # N2: TICK_COMPLETED subscription
            try:
                from app.services.events.event_bus import get_event_bus
                from app.services.events.event_types import EventType

                _bus = get_event_bus()
                # Поле называется _handlers (event_bus.py:50), НЕ _subscribers.
                # Ключ — строковое значение enum: EventType.TICK_COMPLETED.value.
                # Пустой default — валидное состояние (нет шины/хэндлеров);
                # отсутствие подписчиков ниже отражается в errors явно (не silent).
                _handlers = getattr(_bus, "_handlers", {})  # noqa: ENIGMA002
                subs = _handlers.get(EventType.TICK_COMPLETED.value, [])  # noqa: ENIGMA002
                if len(subs) == 0:
                    errors.append("No subscribers for TICK_COMPLETED — M-03/N2 regression")
            except Exception as e:
                errors.append(f"EventBus validation failed: {e}")

    return errors

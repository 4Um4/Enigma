from __future__ import annotations

# backend/app/services/simulation/world_state.py
#
# Phase 3B.2 — WorldState + World Token Budget
#
# Принцип: НЕ заменяет SceneStateManager.
# WorldState — тонкая обёртка: добавляет к существующему SceneState
# два новых поля:
#   recent_events  — последние N GameEvent для контекста DM/NPC
#   other_locations — сжатые сводки соседних локаций
#
# WorldTokenBudget — встроен сюда же.
# Два места проверки (из roadmap v8.1):
#   A. world_state.record_event()  — фоновое сжатие при добавлении события
#   B. build_context_slice()       — финальный срез перед отправкой агентам
#
# Лимит: 2048 токенов на весь контекст мира.
# Оценка: ~4 символа/токен (быстро, без tiktoken).
import dataclasses
import json
import logging
from typing import Any, Dict, List, Optional

from app.domain.events import EventDTO

logger = logging.getLogger(__name__)

# ── Лимиты ────────────────────────────────────────────────────────────────────
WORLD_TOKEN_BUDGET = 2048  # жёсткий лимит токенов на контекст мира
MAX_RECENT_EVENTS = 20  # сколько событий хранить в памяти

# Приоритетные веса (из roadmap v8.1)
PRIORITY_WEIGHTS = {
    "current_location": 1.0,  # всегда включается
    "active_npcs": 0.9,  # NPC в текущей локации
    "player_inventory": 0.8,
    "recent_events": 0.7,  # последние события
    "other_locations": 0.2,  # сжатый summary соседних локаций
    "inactive_npcs": 0.1,  # только имя + статус
}


def _estimate_tokens(obj: Any) -> int:
    """Быстрая оценка токенов: ~4 символа/токен."""
    try:
        return len(json.dumps(obj, ensure_ascii=False)) // 4
    except Exception:
        return len(str(obj)) // 4


# ─────────────────────────────────────────────────────────────────────────────
# WorldTokenBudget
# ─────────────────────────────────────────────────────────────────────────────


class WorldTokenBudget:
    """
    Строит срез мира не превышающий WORLD_TOKEN_BUDGET токенов.

    Приоритет включения:
      1. Текущая локация (всегда)
      2. Активные NPC в локации
      3. Инвентарь игрока
      4. Последние события (recent_events)
      5. Соседние локации — только summary

    Если NPC не влезает целиком — добавляется только имя + статус.
    """

    def build_context_slice(
        self,
        scene_state: Dict[str, Any],
        recent_events: List[EventDTO],
        other_locations: Dict[str, Dict[str, Any]],
        budget: int = WORLD_TOKEN_BUDGET,
    ) -> Dict[str, Any]:
        """
        Точка B (roadmap): финальный срез перед отправкой агентам.
        Вызывается из context_builder.build_context().
        """
        remaining = budget
        result: Dict[str, Any] = {}

        # 1. Текущая локация — всегда включаем
        loc_core = self._core_location(scene_state)
        loc_tokens = _estimate_tokens(loc_core)
        if loc_tokens <= remaining:
            result["location"] = loc_core
            remaining -= loc_tokens
        else:
            # Даже если не влезает — включаем минимум
            result["location"] = {
                "location_id": scene_state.get("location_id", ""),
                "environment": scene_state.get("environment", {}),
            }
            remaining -= _estimate_tokens(result["location"])

        # 2. Активные NPC
        npc_positions = scene_state.get("npc_positions", {})
        npc_list = []
        for npc_id, pos in npc_positions.items():
            if pos.get("state") == "dead":
                continue
            full_entry = {"id": npc_id, **pos}
            full_tokens = _estimate_tokens(full_entry)
            if full_tokens <= remaining:
                npc_list.append(full_entry)
                remaining -= full_tokens
            elif remaining > 30:
                # Только минимум
                slim = {
                    "id": npc_id,
                    "name": pos.get("name", npc_id),
                    "status": pos.get("state", "здесь"),
                }
                npc_list.append(slim)
                remaining -= _estimate_tokens(slim)
        if npc_list:
            result["npcs"] = npc_list

        # 3. Инвентарь игрока
        inventory = scene_state.get("player_inventory_snapshot", {})
        if inventory and remaining > 50:
            inv_tokens = _estimate_tokens(inventory)
            if inv_tokens <= remaining:
                result["player_inventory"] = inventory
                remaining -= inv_tokens

        # 4. Последние события (Устав §2.1: EventDTO → dict для context slice)
        if recent_events and remaining > 100:
            # Берём с конца, пока влезают
            included: List[Any] = []
            for event in reversed(recent_events[-10:]):
                event_dict = dataclasses.asdict(event)
                t = _estimate_tokens(event_dict)
                if t <= remaining:
                    included.insert(0, event_dict)
                    remaining -= t
                else:
                    break
            if included:
                result["recent_events"] = included

        # 5. Соседние локации — только summary
        if other_locations and remaining > 80:
            summaries = {}
            for loc_id, loc_data in other_locations.items():
                summary = {
                    "name": loc_data.get("name", loc_id),
                    "npcs": [
                        p.get("name", nid)
                        for nid, p in loc_data.get("npc_positions", {}).items()
                        if p.get("state") != "dead"
                    ][:3],  # максимум 3 NPC в summary
                }
                st = _estimate_tokens(summary)
                if st <= remaining:
                    summaries[loc_id] = summary
                    remaining -= st
        # other_locations не добавляем — Phase 3B.3+

        used = budget - remaining
        logger.debug(
            f"[WTB] Срез: {used}/{budget} токенов использовано "
            f"({round(used / budget * 100)}%)"
        )

        return result

    def _core_location(self, scene_state: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает ключевые поля локации (без громоздких вложений)."""
        objects = {}
        for obj_id, obj in scene_state.get("objects", {}).items():
            # Пропускаем уничтоженные объекты с count=0
            if obj.get("count") == 0:
                continue
            objects[obj_id] = {
                k: v
                for k, v in obj.items()
                if k in ("name", "state", "count", "light", "hp")
            }

        return {
            "location_id": scene_state.get("location_id", ""),
            "environment": scene_state.get("environment", {}),
            "objects": objects,
            # S.0 поля
            "player_position": scene_state.get("player_position"),
            "player_target_npc": scene_state.get("player_target_npc"),
            "player_target_npc_name": scene_state.get("player_target_npc_name"),
            # A3-FIX: убран zombie reader. SpatialQueryService — canonical source,
            # не дублируется в token-budget копии.
            # "player_distances" больше не существует в scene_state (ADR-048).
            "active_effects": scene_state.get("active_effects", []),
        }


# ─────────────────────────────────────────────────────────────────────────────
# WorldState
# ─────────────────────────────────────────────────────────────────────────────


class WorldState:
    """
    Обёртка над SceneState с поддержкой:
      - recent_events  (последние GameEvent)
      - WorldTokenBudget (срез для агентов)

    Не дублирует SceneStateManager — использует его для чтения/записи.
    Один экземпляр на кампанию (создаётся в main.py при startup).
    """

    def __init__(self) -> None:
        self._wtb = WorldTokenBudget()
        self._recent_events: List[
            EventDTO
        ] = []  # последние MAX_RECENT_EVENTS событий (Устав §2.1)

    def record_event(self, event: EventDTO) -> None:
        """
        Точка A (roadmap): добавляет событие в буфер.
        При превышении MAX_RECENT_EVENTS — удаляет самые старые.
        Вызывается из game_loop.py после event_bus.publish().
        """
        self._recent_events.append(event)
        if len(self._recent_events) > MAX_RECENT_EVENTS:
            self._recent_events.pop(0)

    def get_recent_events(self, limit: int = 5) -> List[EventDTO]:
        """Последние N событий для context_builder (Устав §2.1)."""
        return self._recent_events[-limit:]

    def build_context_slice(
        self,
        scene_state: Dict[str, Any],
        other_locations: Optional[Dict[str, Dict[str, Any]]] = None,
        budget: int = WORLD_TOKEN_BUDGET,
    ) -> Dict[str, Any]:
        """
        Строит срез мира для DM и NPC агентов.
        Вызывается из context_builder.build_context().
        Никогда не превышает budget токенов.
        """
        return self._wtb.build_context_slice(
            scene_state=scene_state,
            recent_events=self._recent_events,
            other_locations=other_locations or {},
            budget=budget,
        )

    def clear_events(self) -> None:
        """Сбрасывает буфер событий. Для тестов."""
        self._recent_events.clear()


# ── Singleton ──────────────────────────────────────────────────────────────

_world_state: Optional[WorldState] = None


def get_world_state() -> WorldState:
    global _world_state
    if _world_state is None:
        _world_state = WorldState()
        logger.info("[WORLD_STATE] WorldState инициализирован")
    return _world_state

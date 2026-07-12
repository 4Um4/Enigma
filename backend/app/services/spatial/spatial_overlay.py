from __future__ import annotations
from typing import Any, Dict, List, Optional
# backend/app/services/spatial/spatial_overlay.py
# Назначение: Динамическое состояние сцены (SpatialOverlay)
# Инициализируется из scene_state каждый тик. Не мутирует граф.
# Методы: build_overlay_from_scene, try_reserve_node
# Зависимости: app.models.spatial_contracts
"""
TODO:
- Возможно, добавить методы для обновления других аспектов оверлея (например, открытие дверей, изменение освещения) в зависимости от событий в сцене
- В будущем можно добавить поддержку многоязычных описаний узлов и эффектов, что может потребовать более сложной логики в RoleResolver и при построении оверлея
- Возможно, добавить кэширование оверлея для оптимизации, если построение будет слишком дорогим, с механизмом инвалидации при изменении scene_state
- В try_reserve_node можно добавить логику для обработки конфликтов при URGENT, например, уведомление текущего держателя узла или попытку найти альтернативный путь
"""


import logging

from app.models.spatial_contracts import SpatialOverlay

logger = logging.getLogger(__name__)


def build_overlay_from_scene(scene_state: Dict[str, Any]) -> SpatialOverlay:
    """Строит SpatialOverlay из текущего scene_state.

    Читает: npc_positions (reserved), active_effects (risk, light),
    spatial_overlay (прямые данные если есть).
    """
    overlay = SpatialOverlay()

    # ── Прямые данные из scene_state (если кто-то уже записал) ────────
    raw = scene_state.get("spatial_overlay", {})
    if isinstance(raw, dict):
        overlay.blocked_nodes = set(raw.get("blocked_nodes", []))
        overlay.open_doors = set(raw.get("open_doors", []))
        overlay.crowd_density = raw.get("crowd_density", {})
        overlay.risk_zones = raw.get("risk_zones", {})
        overlay.light_levels = raw.get("light_levels", {})

    # ── Резервация: NPC стоит на узле → узел занят ───────────────────
    npc_positions = scene_state.get("npc_positions", {})
    for npc_id, entry in npc_positions.items():
        pos = entry.get("position", "")
        if pos and entry.get("visible", True):
            overlay.reserved_nodes[pos] = npc_id

    # ── Плотность: количество NPC на одном узле ──────────────────────
    node_npc_count: dict[str, int] = {}
    for npc_id, entry in npc_positions.items():
        pos = entry.get("position", "")
        if pos:
            node_npc_count[pos] = node_npc_count.get(pos, 0) + 1
    for node_id, count in node_npc_count.items():
        # Нормализация: 1 NPC = 0.2, 5+ = 1.0
        overlay.crowd_density.setdefault(node_id, min(count * 0.2, 1.0))

    # ── Освещение из environment ─────────────────────────────────────
    env = scene_state.get("environment", {})
    light = env.get("light_level", "")
    if light == "bright":
        overlay._global_light = 1.0
    elif light == "dim":
        overlay._global_light = 0.5
    elif light == "dark":
        overlay._global_light = 0.1

    return overlay


def try_reserve_node(
    overlay: SpatialOverlay,
    node_id: str,
    npc_id: str,
    urgency: str = "normal",
) -> bool:
    """Пытается зарезервировать узел для NPC.

    Возвращает True если:
    - Узел свободен
    - Узел уже зарезервирован этим же NPC
    - urgency == "urgent" (снижает штраф, но не ломает логику)

    Возвращает False если узел занят другим NPC.
    """
    current_holder = overlay.reserved_nodes.get(node_id)
    if current_holder is None:
        # Свободен — резервируем
        overlay.reserved_nodes[node_id] = npc_id
        return True
    if current_holder == npc_id:
        # Уже занят этим NPC — ок
        return True
    # Занят другим NPC
    if urgency == "urgent":
        # URGENT: снижаем штраф, но не выкидываем другого NPC
        # Возвращаем True, но с предупреждением
        logger.debug(
            f"[OVERLAY] {npc_id} запрашивает занятый узел {node_id} "
            f"(владелец: {current_holder}) с urgency=URGENT — допущено"
        )
        return True
    return False

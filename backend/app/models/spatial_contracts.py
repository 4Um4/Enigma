from __future__ import annotations

# backend/app/models/spatial_contracts.py
# Назначение: Контракты SpatialService v1.2 — типы, Enum, dataclass
# Трёхслойная модель: Геометрия (x,y) → Топология (zone_id/level) → Семантика (role/tags)
# Зависимости: stdlib only
# Основные сущности: NodeRole, Urgency, NodeRef, SpatialOverlay, NPCPathState

"""
- Возможно, добавить дополнительные поля в NodeRef для поддержки будущих фич (например, size, capacity, etc.)
- В SpatialOverlay можно добавить методы для удобного обновления состояния (например, блокировка узла, открытие двери, установка плотности толпы)
- В NPCPathState можно добавить поле для хранения предыдущего пути, чтобы при инвалидации кэша можно было сравнить новый путь с предыдущим и принять решение о необходимости пересчёта
- В будущем можно добавить поддержку многоязычных ролей и тегов, что может потребовать более сложной логики в RoleResolver
"""


from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

# ── Семантика: роли узлов ────────────────────────────────────────────


class NodeRole(Enum):
    """Семантическая роль узла. Определяет поведение NPC при поиске цели."""

    BAR = "bar"  # Стойка, место обслуживания (для гостей)
    BED = "bed"  # Кровать, место сна
    ENTRANCE = "entrance"  # Вход, дверь, ворота
    TABLE = "table"  # Стол, место приёма пищи/работы
    WORKBENCH = "workbench"  # Верстак, кузня, рабочее место
    MARKET = "market"  # Рынок, прилавок, торговля
    TRANSITION = "transition"  # Лестницы, двери, люки, порталы
    BOUNDARY = "boundary"  # Выход из чанка в соседний (ДОЛГ 6.2)

    # ADR-O-326: Функциональные роли (рабочие станции)
    GUARD_POST = "guard_post"           # Караульня (где стоит стражник на дежурстве)
    DARK_CORNER = "dark_corner"         # Тёмный угол (где прячется вор)
    SERVING_STATION = "serving_station" # Точка обслуживания (где служанка раздаёт еду)
    KITCHEN_COUNTER = "kitchen_counter" # Кухонная стойка (где готовят/протирают)
    INN_DESK = "inn_desk"               # Стойка трактирщика (где встречают гостей)

    DEFAULT = "default"  # Узел без явной роли


class Urgency(Enum):
    """Срочность навигации. Модифицирует веса скоринга, НЕ игнорирует мир."""

    NORMAL = "normal"  # Обычное перемещение
    URGENT = "urgent"  # FLEE, combat escape, критическая потребность


# ── Геометрия + Топология + Семантика в одной структуре ──────────────


@dataclass(frozen=True)
class NodeRef:
    """Неизменяемая ссылка на узел пространственного графа.

    Слои:
    - Геометрия: x, y — абсолютные мировые координаты (от 0,0)
    - Топология: zone_id (= location_id), level (ground/basement/floor_2)
    - Семантика: role, tags

    node_id — канонический: "location_id:editor_id"
    """

    node_id: str
    role: NodeRole
    tags: List[str]
    x: float  # АБСОЛЮТНАЯ мировая координата
    y: float  # АБСОЛЮТНАЯ мировая координата
    zone_id: str  # Топология: всегда = location_id
    level: Optional[str] = None  # Вертикальность: ground, basement, floor_2

    @property
    def xy(self) -> Tuple[float, float]:
        return (self.x, self.y)


# ── Динамическое состояние сцены ─────────────────────────────────────


@dataclass
class SpatialOverlay:
    """Динамическое состояние сцены. Не сериализуется в граф.

    Живёт в TickBuffer/scene_state. Мутируется оркестратором, НЕ SpatialService.
    SpatialService только читает overlay при скоринге и pathfinding.
    """

    blocked_nodes: Set[str] = field(default_factory=set)
    open_doors: Set[str] = field(default_factory=set)
    crowd_density: Dict[str, float] = field(default_factory=dict)  # node_id → 0.0–1.0
    risk_zones: Dict[str, float] = field(default_factory=dict)  # node_id → 0.0–1.0
    light_levels: Dict[str, float] = field(default_factory=dict)  # node_id → 0.0–1.0
    reserved_nodes: Dict[str, str] = field(default_factory=dict)  # node_id → npc_id

    def compute_hash(self) -> str:
        """Детерминированный хэш для инвалидации кэша путей."""
        import hashlib

        parts = [
            ";".join(sorted(self.blocked_nodes)),
            ";".join(sorted(self.open_doors)),
            ";".join(f"{k}:{v:.2f}" for k, v in sorted(self.crowd_density.items())),
            ";".join(f"{k}:{v:.2f}" for k, v in sorted(self.risk_zones.items())),
            ";".join(f"{k}:{v:.2f}" for k, v in sorted(self.light_levels.items())),
            ";".join(f"{k}:{v}" for k, v in sorted(self.reserved_nodes.items())),
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Состояние пути NPC (хранится ВНЕ SpatialService) ─────────────────


@dataclass
class NPCPathState:
    """Хранится в NPCState/MovementEngine, НЕ в SpatialService.

    SpatialService вычисляет путь один раз. NPC шагает по active_path.
    Пересчёт только при: смене intent, инвалидации overlay, блокировке пути.
    """

    active_path: List[NodeRef] = field(default_factory=list)
    path_index: int = 0
    target_node: Optional[NodeRef] = None
    overlay_hash_at_compute: str = ""

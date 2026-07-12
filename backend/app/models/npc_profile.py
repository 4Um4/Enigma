from __future__ import annotations

# backend/app/models/npc_profile.py
"""
Целевая архитектура данных NPC (To-Be).
Разделение на 4 слоя для обеспечения масштабируемости и предсказуемости.

Назначение: Единый источник правды для структуры данных NPC (Целевая архитектура L0-L1-L2).
Зависимости: typing, app.services.npc.npc_state (для Enum'ов)
Основные сущности: NPCProfileL0, SpatialSnapshotR4

L0 (Profile) — Immutable. Шаблон из JSON.
L1 (Identity) — Медленная динамика. Кристаллизованные черты (ResonanceEngine).
L2 (State) — Быстрая динамика. Текущий тик (DecisionHub/StateApplicator).
R4 (Spatial) — Эфемерный срез. Существует только внутри одного тика.
"""


from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# Импорты Enum'ов из моделей


# --- СЛОЙ L0: ШАБЛОН (IMMUTABLE) ---


@dataclass(frozen=True)
class InventoryProfile:
    """Правила генерации инвентаря, не конкретный список."""

    possible_items: Dict[str, float] = field(
        default_factory=dict
    )  # item_id -> spawn_chance
    min_gold: int = 0
    max_gold: int = 0
    conditional_items: Dict[str, str] = field(
        default_factory=dict
    )  # condition -> item_id


@dataclass(frozen=True)
class PsycheBase:
    """Базовые характеристики психики (из JSON)."""

    willpower: int
    breakpoint: int
    loyalty_base: int = 50  # Переименовано из loyalty_true для ясности


@dataclass(frozen=True)
class NPCProfileL0:
    """
    L0 Core Profile. Загружается из config/npc/ один раз.
    NEVER CHANGES во время кампании.
    """

    id: str
    name: str
    tier: str  # "mass", "minor", "major"
    drives_base: Dict[str, float]  # control, significance, fear, desire
    psyche_base: PsycheBase
    voice_profile: str
    backstory: str = ""
    # Режиссёрская подсказка — instructions для LLM
    author_notes: str = ""
    inventory_rules: Optional[InventoryProfile] = None
    gender: str = (
        "male"  # "male", "female", "other" — для гендерных окончаний в narrative
    )
    # v2.2 Spatial Ontology: Архетип профессии. Инъектируется из _archetype при загрузке.
    # L1 Bridge: В будущем заменит _archetype на core.compliance_bias
    archetype: str = "commoner"  # "maid", "guard", "thief", "tavern_keeper" и т.д.
    # P1 FIX: Жизненный проект (конкретная цель). Меняется при достижении/провале.
    goal: str = ""
    # P1-3 v3.0: Ось идентичности (Core Orientation). Не меняемая базовая жизненная направленность.
    # Меняется только через кризис идентичности (падение confidence ниже 0.2 и перестройка убеждений).
    core_orientation: str = "survival"  # family_builder, wealth_creator, warrior, etc.


# --- СЛОЙ L1: ИДЕНТИЧНОСТЬ (MEDIAN DYNAMICS) ---


@dataclass
class SpatialSnapshotR4:
    """
    R4 Spatial Snapshot. Существует только в рамках одного тика (SceneState).
    Уничтожается после обработки события.
    """

    location_id: str = "unknown"
    local_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # X, Y, Z
    standing_on_object: Optional[str] = None  # "barrel_01"
    environment_mods: Dict[str, float] = field(
        default_factory=dict
    )  # stability_mod, visibility_mod

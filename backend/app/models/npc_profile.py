# backend/app/models/npc_profile.py
"""
Целевая архитектура данных NPC (To-Be).
Разделение на 4 слоя для обеспечения масштабируемости и предсказуемости.

Назначение: Единый источник правды для структуры данных NPC (Целевая архитектура L0-L1-L2).
Зависимости: typing, app.services.npc.npc_state (для Enum'ов)
Основные сущности: NPCProfileL0, NPCIdentityL1, NPCStateL2, SpatialSnapshotR4

L0 (Profile) — Immutable. Шаблон из JSON.
L1 (Identity) — Медленная динамика. Кристаллизованные черты (ResonanceEngine).
L2 (State) — Быстрая динамика. Текущий тик (DecisionHub/StateApplicator).
R4 (Spatial) — Эфемерный срез. Существует только внутри одного тика.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# Импорты Enum'ов из текущей системы (чтобы не ломать то, что работает)
try:
    from app.services.npc.npc_state import EmotionTag, Intent, WillState, BehaviorMaskState
except ImportError:
    BehaviorMaskState = str  # Заглушка, если модуль еще не готов


# --- СЛОЙ L0: ШАБЛОН (IMMUTABLE) ---

@dataclass(frozen=True)
class InventoryProfile:
    """Правила генерации инвентаря, не конкретный список."""
    possible_items: Dict[str, float] = field(default_factory=dict)  # item_id -> spawn_chance
    min_gold: int = 0
    max_gold: int = 0
    conditional_items: Dict[str, str] = field(default_factory=dict)  # condition -> item_id


@dataclass(frozen=True)
class PsycheBase:
    """Базовые характеристики психики (из JSON)."""
    willpower: int
    breakpoint: int
    loyalty_base: int = 50  # Переименовано из loyalty_true для ясности


@dataclass(frozen=True)
class NPCProfileL0:
    """
    L0 Core Profile. Загружается из major_npcs.json один раз.
    NEVER CHANGES во время кампании.
    """
    id: str
    name: str
    tier: str  # "mass", "minor", "major"
    drives_base: Dict[str, float]  # control, significance, fear, desire
    psyche_base: PsycheBase
    voice_profile: str
    backstory: str = ""
    inventory_rules: Optional[InventoryProfile] = None


# --- СЛОЙ L1: ИДЕНТИЧНОСТЬ (MEDIAN DYNAMICS) ---

@dataclass
class NPCIdentityL1:
    """
    L1 Identity. Кристаллизованная личность.
    Меняется очень медленно (раз в сотни тиков) через ResonanceEngine.
    Сохраняется в campaign_state, но не в шаблоне.
    """
    traits: Dict[str, float] = field(default_factory=dict)  # "distrust_player": 0.85
    formed_at_day: int = 0


# --- СЛОЙ L2: СОСТОЯНИЕ (FAST DYNAMICS) ---

@dataclass
class NPCStateL2:
    """
    L2 State. Динамическое состояние.
    Меняется каждый тик через StateApplicator.
    ВНИМАНИЕ: Здесь строго Enum'ы. Строки генерируются только в VerbalizationContext (R3).
    """
    npc_id: str = ""  # Ссылка на L0 Profile для логирования и сериализации
    stress: float = 0.0
    emotion: EmotionTag = EmotionTag.NEUTRAL
    will_state: WillState = WillState.FREE
    intent: Intent = Intent.IDLE
    intent_target: Optional[str] = None
    
    relationship_cache: Dict[str, float] = field(default_factory=dict)  # target_id -> value
    trauma_markers: Set[str] = field(default_factory=set)
    
    # --- ДИНАМИЧЕСКИЕ ТРЕЙТЫ ---
    # Накапливаются от событий (например, "suspicious": 0.8).
    # Затухают каждый тик (decay). Относятся к L2, так как меняются быстро.
    active_traits: Dict[str, float] = field(default_factory=dict)
    
    # --- СИСТЕМА СЛОМА (R8) ---
    # Быстрые динамики (метры слома). Меняются каждый тик через StateApplicator.
    # При критических значениях триггерят медленные изменения в NPCIdentityL1.
    identity_integrity: float = 1.0      # 1.0 = цел, 0.0 = сломлен
    pressure_resistance: float = 1.0     # Буфер сопротивления давлению
    resentment: float = 0.0              # Затаенная обида (накопительная)
    dependency: float = 0.0              # Зависимость (от игрока/вещества)
    
    # TODO: временное поле для обратной совместимости, будет удалено
    behavior_mask: Optional[BehaviorMaskState] = None


# --- СЛОЙ R4: ПРОСТРАНСТВО (EPHEMERAL) ---

@dataclass
class SpatialSnapshotR4:
    """
    R4 Spatial Snapshot. Существует только в рамках одного тика (SceneState).
    Уничтожается после обработки события.
    """
    location_id: str = "unknown"
    local_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # X, Y, Z
    standing_on_object: Optional[str] = None  # "barrel_01"
    environment_mods: Dict[str, float] = field(default_factory=dict)  # stability_mod, visibility_mod
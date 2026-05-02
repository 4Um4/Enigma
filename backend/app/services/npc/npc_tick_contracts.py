"""
Контракты NPC фазы тика — Input/Buffer/Services.

Вариант C: оркестратор разрешает зависимости ДО вызова,
фаза получает 3 явных контракта, мутирует только Buffer.

path: backend/app/services/npc/npc_tick_contracts.py
Назначение: Три явных контракта для NPC фазы тика. Input/Buffer/Services — никаких dict-мешков.
Зависимости: npc_state, decision_hub, domain/events
Основные сущности: NpcTickInput, NpcTickBuffer, NpcTickServices
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.services.npc.decision_hub import EventContext

# Сопоставление intent → activity для scene_state
_INTENT_TO_ACTIVITY = {
    "COMBAT":     "fighting",
    "FLEE":       "fleeing",
    "TALK":       "talking",
    "OBSERVE":    "observing",
    "HELP":       "helping",
    "INTIMIDATE": "intimidating",
    "IDLE":       "",  # пустая строка → не перезаписываем дефолт
}


@dataclass(frozen=True)
class NpcTickInput:
    """Данные для NPC фазы — только чтение."""
    campaign_id: str
    location: str
    scene_state: dict
    player_target_id: Optional[str]
    hub_event: EventContext
    is_session_start: bool
    action_type: str
    raw_input: str
    current_tick: int
    all_npcs_raw: list  # Список legacy-dict NPC (shared reference — legacy мутации)
    nearby_npcs: list   # Из dm_result.scene_context.nearby_npcs
    scene_continuity: Any  # SceneContinuity или None
    spatial_events: list   # Для социальных триггеров (ревность по proximity)
    line_of_sight: dict    # Из dm_result.scene_context.line_of_sight


@dataclass
class NpcTickBuffer:
    """Накопитель результатов NPC фазы — только запись."""
    dirty_npcs: set = field(default_factory=set)
    npc_contexts: list = field(default_factory=list)
    max_npc_stress: float = 0.0
    # Activity overrides — оркестратор применит в scene_state ПОСЛЕ фазы
    activity_overrides: Dict[str, str] = field(default_factory=dict)
    # CommunicationIntent для Фазы 6 — публикация через оркестратор (Устав §5.1)
    communication_intents: list = field(default_factory=list)
    # MovementIntent — реактивное движение NPC (APPROACH, FLEE и др.)
    # Оркестратор передаёт в MovementEngine → SceneChange → apply_changes
    movement_intents: list = field(default_factory=list)
    # DEPRECATED: published_events — нарушает §5.1 (публикация внутри pipeline).
    # Удалить после миграции всех потребителей на communication_intents через Фазу 6.
    published_events: list = field(default_factory=list)


@dataclass(frozen=True)
class NpcTickServices:
    """Сервисы, разрешённые оркестратором ДО вызова фазы."""
    memory_manager: Any
    relationship_store: Any
    social_engine: Optional[Any]
    reputation_engine: Optional[Any]
    economic_profiles: Dict[str, Any]
    event_bus: Any = None  # Фаза 6-7: IntentEventAdapter → EventBus (§3.3)
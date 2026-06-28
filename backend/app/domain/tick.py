# path: backend/app/domain/tick.py
"""
Назначение: DTO результата тика — пересекает границу orchestrator → API → frontend
Зависимости: dataclasses, typing, domain.snapshot
Основные сущности: TickResultDTO
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Tuple

from app.domain.snapshot import WorldSnapshotDTO

# TZ-09: Execution Pipeline Collapse.
# TickState — пассивный контракт снимка каузальности (Causal Snapshot).
# Защита от мутаций обеспечивается на границе сборки (в Orchestrator) через frozen().

def frozen(x: Any) -> Any:
    """Рекурсивная структурная заморозка: list → tuple. dict остаётся dict (для pickle)."""
    if isinstance(x, list):
        return tuple(frozen(v) for v in x)
    if isinstance(x, dict):
        return {k: frozen(v) for k, v in x.items()}
    return x

def create_tick_state(
    *,
    tick_id: int,
    campaign_id: str,
    scene_state: dict,
    all_npcs_raw: list,
    effective_drives_map: dict,
    interventions: list,
    pe_modifiers_map: Optional[dict] = None,
    hub_event: Optional[Any] = None,
    player_target_id: Optional[str] = None,
    action_type: str = "idle",
    raw_input: str = "",
    is_session_start: bool = False,
    nearby_npcs: Optional[list] = None,
    line_of_sight: Optional[dict] = None,
    scene_continuity: Optional[Any] = None,
    spatial_events: Optional[list] = None,
    drf_tick_id: int = -1,
) -> "TickState":
    """Фабрика TickState. Замораживает данные на границе сборки (Orchestrator)."""
    return TickState(
        tick_id=tick_id,
        campaign_id=campaign_id,
        scene_state=frozen(scene_state),
        all_npcs_raw=tuple(map(frozen, all_npcs_raw)),
        effective_drives_map=frozen(effective_drives_map),
        interventions=tuple(interventions),
        pe_modifiers_map=frozen(pe_modifiers_map) if pe_modifiers_map else {},
        hub_event=hub_event,
        player_target_id=player_target_id,
        action_type=action_type,
        raw_input=raw_input,
        is_session_start=is_session_start,
        nearby_npcs=tuple(map(frozen, nearby_npcs)) if nearby_npcs else (),
        line_of_sight=frozen(line_of_sight) if line_of_sight else {},
        scene_continuity=scene_continuity,
        spatial_events=tuple(spatial_events) if spatial_events else (),
        drf_tick_id=drf_tick_id,
    )

@dataclass(frozen=True)
class TickState:
    """Пассивный иммутабельный снимок состояния мира для передачи в редюсер.
    
    Содержит ВСЕ необходимые данные для вычисления мутаций. 
    Никаких внешних контекстов (DMContext) не требуется.
    """
    tick_id: int
    campaign_id: str
    scene_state: Any                             # MappingProxyType
    all_npcs_raw: Tuple[Any, ...]                # Tuple of MappingProxyType
    effective_drives_map: Any                    # MappingProxyType
    interventions: Tuple[Any, ...]               # Tuple
    pe_modifiers_map: Any                        # MappingProxyType (S-93: Active Inference)
    # Поля игрока (заполняются из interventions, если source="player")
    hub_event: Optional[Any] = None
    player_target_id: Optional[str] = None
    action_type: str = "idle"
    raw_input: str = ""
    is_session_start: bool = False
    nearby_npcs: Tuple[Any, ...] = ()             # Tuple of MappingProxyType
    line_of_sight: Any = field(default_factory=dict)  # MappingProxyType
    scene_continuity: Optional[Any] = None
    spatial_events: Tuple[Any, ...] = ()
    drf_tick_id: int = -1

@dataclass(frozen=True)
class TickMutation:
    """Чистый результат работы NpcTickPipeline. Возвращает только дельты и намерения."""
    npc_deltas: List[Any]                 # List[StateDelta]
    communication_intents: List[Any]      # List[CommunicationIntent]
    movement_intents: List[Any]           # List[MovementIntent]


@dataclass(frozen=True)
class TickResultDTO:
    """Результат одного тика мира.
    
    Пересекает границу TickOrchestrator → API layer.
    Содержит только то, что нужно API для ответа клиенту.
    """
    status: str                           # "ok" | "no_scene" | "error"
    changes_count: int = 0
    significant_events: List[dict] = field(default_factory=list)
    world_snapshot: Optional[WorldSnapshotDTO] = None
    error: Optional[str] = None
    # ADR-075: Строго типизированный транспорт Эмбодимента через каузальную границу API.
    # None по умолчанию (нет конфликта = нет моторного сопротивления).
    will_conflict_data: Optional[dict] = None
    # TZ-08 v0.2: Narrative Projection. Данные для LLM-генерации, вычисленные ядром.
    # Формируются в любом тике (idle/player) на основе State+Decision.
    npc_contexts: list = field(default_factory=list)
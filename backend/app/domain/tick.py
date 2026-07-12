"""
Назначение: DTO результата тика — пересекает границу orchestrator → API → frontend
Зависимости: dataclasses, typing, domain.snapshot
Основные сущности: TickResultDTO
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    scene_state: Dict[str, Any],
    all_npcs_raw: List[Any],
    effective_drives_map: Dict[str, Any],
    interventions: List[Any],
    pe_modifiers_map: Optional[Dict[str, Any]] = None,
    hub_event: Optional[Any] = None,
    player_target_id: Optional[str] = None,
    action_type: str = "idle",
    raw_input: str = "",
    is_session_start: bool = False,
    nearby_npcs: Optional[List[Any]] = None,
    line_of_sight: Optional[Dict[str, Any]] = None,
    scene_continuity: Optional[Any] = None,
    spatial_events: Optional[List[Any]] = None,
    drf_tick_id: int = -1,
    # TZ-10: Preloaded Data (Strangulation Pattern)
    memory_weights_map: Optional[Dict[str, Any]] = None,
    narrative_cache_map: Optional[Dict[str, Any]] = None,
    social_modifiers_map: Optional[Dict[str, Any]] = None,
    reputation_modifiers_map: Optional[Dict[str, Any]] = None,
    economic_profiles_map: Optional[Dict[str, Any]] = None,
    crystallized_beliefs_map: Optional[Dict[str, Any]] = None,
    identity_traits_map: Optional[Dict[str, Any]] = None,
    # Read-only services (не выполняют I/O, безопасны для редюсера)
    relationship_store: Optional[Any] = None,
    spatial_service: Optional[Any] = None,
    spatial_query: Optional[Any] = None,
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
        memory_weights_map=frozen(memory_weights_map) if memory_weights_map else {},
        narrative_cache_map=frozen(narrative_cache_map) if narrative_cache_map else {},
        social_modifiers_map=frozen(social_modifiers_map)
        if social_modifiers_map
        else {},
        reputation_modifiers_map=frozen(reputation_modifiers_map)
        if reputation_modifiers_map
        else {},
        economic_profiles_map=frozen(economic_profiles_map)
        if economic_profiles_map
        else {},
        crystallized_beliefs_map=frozen(crystallized_beliefs_map)
        if crystallized_beliefs_map
        else {},
        identity_traits_map=frozen(identity_traits_map) if identity_traits_map else {},
        relationship_store=relationship_store,
        spatial_service=spatial_service,
        spatial_query=spatial_query,
    )


@dataclass(frozen=True)
class TickState:
    """Пассивный иммутабельный снимок состояния мира для передачи в редюсер.

    Содержит ВСЕ необходимые данные для вычисления мутаций.
    Никаких внешних контекстов (DMContext) не требуется.
    TZ-10: svc устранён, все данные preloaded в TickState.
    """

    tick_id: int
    campaign_id: str
    scene_state: Any  # MappingProxyType
    all_npcs_raw: Tuple[Any, ...]  # Tuple of MappingProxyType
    effective_drives_map: Any  # MappingProxyType
    interventions: Tuple[Any, ...]  # Tuple
    pe_modifiers_map: Any  # MappingProxyType (S-93: Active Inference)
    # Поля игрока (заполняются из interventions, если source="player")
    hub_event: Optional[Any] = None
    player_target_id: Optional[str] = None
    action_type: str = "idle"
    raw_input: str = ""
    is_session_start: bool = False
    nearby_npcs: Tuple[Any, ...] = ()  # Tuple of MappingProxyType
    line_of_sight: Any = field(default_factory=dict)  # MappingProxyType
    scene_continuity: Optional[Any] = None
    spatial_events: Tuple[Any, ...] = ()
    drf_tick_id: int = -1

    # TZ-10: Preloaded Data (загружаются Orchestrator ДО вызова run)
    memory_weights_map: Any = field(
        default_factory=dict
    )  # MappingProxyType: npc_id -> weights
    narrative_cache_map: Any = field(
        default_factory=dict
    )  # MappingProxyType: npc_id -> cache
    social_modifiers_map: Any = field(
        default_factory=dict
    )  # MappingProxyType: npc_id -> social_mods
    reputation_modifiers_map: Any = field(
        default_factory=dict
    )  # MappingProxyType: npc_id -> rep_mod
    economic_profiles_map: Any = field(
        default_factory=dict
    )  # MappingProxyType: npc_id -> eco_profile
    crystallized_beliefs_map: Any = field(
        default_factory=dict
    )  # MappingProxyType: npc_id -> beliefs
    identity_traits_map: Any = field(
        default_factory=dict
    )  # MappingProxyType: npc_id -> traits

    # Read-only services (не выполняют I/O, безопасны для редюсера)
    relationship_store: Optional[Any] = None
    spatial_service: Optional[Any] = None
    spatial_query: Optional[Any] = None


@dataclass(frozen=True)
class TickMutation:
    """Чистый результат работы NpcTickPipeline. Возвращает только дельты и намерения.

    TZ-10: Expanded with deferred mutations (l1_events, memory_events).
    """

    npc_deltas: List[Any]  # List[StateDelta]
    communication_intents: List[Any]  # List[CommunicationIntent]
    movement_intents: List[Any]  # List[MovementIntent]
    l1_drift_events: List[Any] = field(default_factory=list)  # List[TraitDriftEvent]
    memory_events: List[Any] = field(default_factory=list)  # List[EventDTO]


@dataclass(frozen=True)
class TickResultDTO:
    """Результат одного тика мира.

    Пересекает границу TickOrchestrator → API layer.
    Содержит только то, что нужно API для ответа клиенту.
    """

    status: str  # "ok" | "no_scene" | "error"
    changes_count: int = 0
    significant_events: List[Dict[str, Any]] = field(default_factory=list)
    world_snapshot: Optional[WorldSnapshotDTO] = None
    error: Optional[str] = None
    # ADR-075: Строго типизированный транспорт Эмбодимента через каузальную границу API.
    # None по умолчанию (нет конфликта = нет моторного сопротивления).
    will_conflict_data: Optional[Dict[str, Any]] = None
    # TZ-08 v0.2: Narrative Projection. Данные для LLM-генерации, вычисленные ядром.
    # Формируются в любом тике (idle/player) на основе State+Decision.
    npc_contexts: List[Dict[str, Any]] = field(default_factory=list)
    # Sprint P9: Список строк фактов для DMContractBuilder
    observed_facts: List[str] = field(default_factory=list)
    # S83.1 FIX: Возвращаем мутированный снимок состояния из ядра (deepcopy из create_tick_context)
    final_scene_state: Optional[Dict[str, Any]] = None

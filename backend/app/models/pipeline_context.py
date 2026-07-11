# -*- coding: utf-8 -*-
"""
pipeline_context.py — единый источник правды для структуры shared_context.

Убирает лотерею с опечатками в ключах.
Любой ключ, отсутствующий здесь — архитектурное нарушение.

path: /backend/app/models/pipeline_context.py
Назначение: Строгая типизация контекста пайплайна (замена голого Dict[str, Any])
Зависимости: typing.Any
Основные сущности: PipelineContext
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.will import IntentResolution

# TODO: после миграции domain — раскомментировать
# from app.domain.communication import CommunicationIntent
# from app.domain.events import EventDTO


@dataclass
class PipelineContext:
    """Строго типизированный контекст, проходящий через весь game_loop."""
    
    # ── Идентификаторы (из context_builder) ───────────────────────
    campaign_id:          str
    world_id:             str
    location:             str
    
    # ── Состояние мира ─────────────────────────────────────────────
    scene_state:          Dict[str, Any]
    player_state:         Dict[str, Any]
    world_context_slice:  Dict[str, Any]   = field(default_factory=dict)
    
    # ── Результаты Python-движков (из context_builder) ────────────
    python_engines:       Dict[str, Any]   = field(default_factory=dict)
    combat_data:          Dict[str, Any]   = field(default_factory=dict)  # Фаза 8: исход боя для DM (pain, shock, injuries)
    all_npcs_raw_snapshot: Any    = None  # Фаза 9: полный снимок NPC state (description, title)
    npc_contexts:         List[Any]   = field(default_factory=list)
    recent_session:       List[Any]   = field(default_factory=list)
    recent_memory:        List[Any]   = field(default_factory=list)
    reaction_order:       List[Any]   = field(default_factory=list)
    forced_first_speaker: str | None = None
    
    # ── Время ──────────────────────────────────────────────────────
    game_time_seconds:    int    = 0
    current_tick:         int    = 0
    
    # ── Игрок и его действие ───────────────────────────────────────
    player:               Dict[str, Any]   = field(default_factory=dict)
    player_markers:       List[Any]   = field(default_factory=list)
    player_target_id:     str    = ""
    player_target_name:   str    = ""
    action_type:          str    = ""
    recent_player_actions:List[Any]   = field(default_factory=list)
    intent_resolution:    Optional[IntentResolution] = None # ADR-032: Результат шлюза воли
    will_conflict_data:   Optional[dict[str, Any]] = None  # ADR-034: Артефакты конфликта воли (для UI Спринт 26)
    
    # ── NPC и их реакции ───────────────────────────────────────────
    active_npc_ids:       List[Any]   = field(default_factory=list)
    perceiving_npcs:      List[Any]   = field(default_factory=list)
    npc_arrivals:         List[Any]   = field(default_factory=list)
    npc_recent_speech:    List[Any]   = field(default_factory=list)
    character_filter:     Dict[str, Any]   = field(default_factory=dict)
    
    # ── Пространственные и социальные события ──────────────────────
    spatial_query:        Any    = None  # ADR-121: SpatialQueryService — ADR-048 Authoritative Spatial Spine
    spatial_events:       List[Any]   = field(default_factory=list)
    scene_events:         List[Any]   = field(default_factory=list)
    social_propagation:   List[Any]   = field(default_factory=list)
    
    # ── Фронты и давление ──────────────────────────────────────────
    front_description:    str    = ""
    front_type:           str    = ""
    world_pressure:       float  = 0.0
    
    # ── Наблюдение (The Fool: только видимые симптомы, не внутренние состояния) ──
    player_perception:    Any    = None  # Фаза 9: peripheral_cues, embodied_traces
    
    # ── Сложные объекты (будут строго типизированы на следующих шагах) 
    dm_result:            Any    = None
    scene_continuity:     Any    = None
    world_tick_result:    Any    = None
    
    # ── Domain объекты (ФАЗА миграции, пока None) ─────────────────
    # TODO: заменить dm_result / scene_continuity / world_tick_result
    #       на строгие domain-типы после внедрения TickOrchestrator.
    # communication_intent: Optional[CommunicationIntent] = None
    # events:               List[Any][EventDTO]               = field(default_factory=list)
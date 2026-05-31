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
from typing import Any, Optional

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
    scene_state:          dict
    player_state:         dict
    world_context_slice:  dict   = field(default_factory=dict)
    
    # ── Результаты Python-движков (из context_builder) ────────────
    python_engines:       dict   = field(default_factory=dict)
    npc_contexts:         list   = field(default_factory=list)
    recent_session:       list   = field(default_factory=list)
    recent_memory:        list   = field(default_factory=list)
    reaction_order:       list   = field(default_factory=list)
    forced_first_speaker: str | None = None
    
    # ── Время ──────────────────────────────────────────────────────
    game_time_seconds:    int    = 0
    current_tick:         int    = 0
    
    # ── Игрок и его действие ───────────────────────────────────────
    player:               dict   = field(default_factory=dict)
    player_markers:       list   = field(default_factory=list)
    player_target_id:     str    = ""
    player_target_name:   str    = ""
    action_type:          str    = ""
    recent_player_actions:list   = field(default_factory=list)
    intent_resolution:    Optional[IntentResolution] = None # ADR-032: Результат шлюза воли
    will_conflict_data:   Optional[dict[str, Any]] = None  # ADR-034: Артефакты конфликта воли (для UI Спринт 26)
    
    # ── NPC и их реакции ───────────────────────────────────────────
    active_npc_ids:       list   = field(default_factory=list)
    perceiving_npcs:      list   = field(default_factory=list)
    npc_arrivals:         list   = field(default_factory=list)
    npc_recent_speech:    list   = field(default_factory=list)
    character_filter:     dict   = field(default_factory=dict)
    
    # ── Пространственные и социальные события ──────────────────────
    spatial_events:       list   = field(default_factory=list)
    scene_events:         list   = field(default_factory=list)
    social_propagation:   list   = field(default_factory=list)
    
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
    # events:               list[EventDTO]               = field(default_factory=list)
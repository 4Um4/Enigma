# -*- coding: utf-8 -*-
"""
TickOrchestrator — единая точка входа для тика мира.

Строгая последовательность фаз из Архитектурного Устава §3.
Ни один сервис не вызывает другой напрямую — всё через фазы.

path: backend/app/services/tick_orchestrator.py
Назначение: Единая точка входа для тика мира. 10 фаз из Архитектурного Устава (§3).
Зависимости: domain.tick, services.events.event_bus, services.npc.life_engine, services.memory.memory_manager, services.integration.world_snapshot_builder
Основные сущности: TickOrchestrator, _TickContext

ФАЗА 0: Simulation (LifeEngine — чистый Python, без LLM)
ФАЗА 1: Input (сбор событий из внешних источников)
ФАЗА 2: EventBus (первичная волна — spatial events)
ФАЗА 3: Memory Phase (MemoryManager.apply для затронутых NPC)
ФАЗА 4: Pre-Decision (TopicExtractor → тема для каждого NPC)
ФАЗА 5: Decision (DecisionHub → CommunicationIntent)
ФАЗА 6: Post-Decision (IntentEventAdapter → EventDTO)
ФАЗА 8: Handlers (детерминированный drain: drain_events + handle → Phase8Result)
ФАЗА 9: Integration (WorldSnapshotBuilder → WorldSnapshotDTO)
ФАЗА 10: Persistence (atomic commit через PersistencePort)
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Union

from pathlib import Path
from enum import Enum

from app.domain.tick import TickResultDTO
from app.domain.intent import IntentDTO
from app.models.state_delta import DeltaDomain, StateDeltas
from app.models.cfrm import EventBuffer, ClusterOccupancy

from app.services.scene_change import SceneChange, ChangeType

class ReductionPolicy(Enum):
    """Политика редукции дельт при агрегации"""
    ADDITIVE = "additive"
    BOUNDED_ADDITIVE = "bounded_additive"
    OVERWRITE = "overwrite"
    PHYSICS_COMPOSITE = "physics_composite"

DELTA_POLICY_REGISTRY = {
    DeltaDomain.SOCIAL: ReductionPolicy.ADDITIVE,
    DeltaDomain.EMOTION: ReductionPolicy.BOUNDED_ADDITIVE,
    DeltaDomain.REPUTATION: ReductionPolicy.ADDITIVE,
    DeltaDomain.IDENTITY: ReductionPolicy.OVERWRITE,
    DeltaDomain.PHYSIOLOGY: ReductionPolicy.PHYSICS_COMPOSITE,
}
from app.services.events.event_types import EventType
from app.services.npc.life_engine import get_life_engine
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from app.services.npc.topic_extractor import extract_topic
from app.services.events.event_bus import get_event_bus
from app.services.will import resolve_intent_pressure, compute_willpower
from app.models.phase8 import Phase8Context, Phase8Handler, Phase8Result
# P2: PerceptionSubscriber мертв. Восприятие теперь вычисляется LocalCausalSolver
from app.services.cfrm.local_causal_solver import LocalCausalSolver
from app.models.cfrm import PhenomenologicalState, PsychologicalPressure
from app.models.delta_payloads import EmotionPayload, PerceptionPayload
from app.models.will import IntentPressureProfile, WillResponseDTO, WillState
from app.models.state_delta import StateDeltas, DeltaDomain
from app.services.events.reaction_subscriber import ReactionSubscriber
from app.services.events.social_subscriber import SocialSubscriber
from app.services.combat.combat_subscriber import CombatSubscriber
from app.services.events.intent_event_adapter import IntentEventAdapter
from app.services.spatial.spatial_service import SpatialService
from app.services.spatial.spatial_event_detector import (
    SpatialEventDetector,
    _npc_positions_snapshot,
)
from app.services.spatial.transit_tracker import TransitTracker
# SpatialService v1.2 заменяет location_graph. Прямой импорт запрещён контрактом.
from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder

logger = logging.getLogger(__name__)

class DRFBus:
    """Dynamic Recompression Field Bus: единая шина причинных напряжений тика.
    Системы пишут сюда претензии (emit), наблюдатель читает и схлопывает (drain).
    """
    def __init__(self):
        self.stream: list[dict] = []

    def emit(self, claim: dict):
        self.stream.append(claim)

    def drain(self) -> list[dict]:
        data = self.stream
        self.stream = []
        return data

@dataclass
class DRFExecutionContext:
    """Scoped causal ledger: привязка претензий к tick+npc frame.
    Pipeline получает drf_ctx, а не голый drf_bus.
    Claim автоматически наследует npc_id и tick_id из контекста.
    """
    tick_id: int
    bus: Any  # DRFBus — разделяемая шина тика
    npc_id: Optional[str] = None  # None = frame-level (pre-loop)

    def for_npc(self, npc_id: str) -> 'DRFExecutionContext':
        """Создаёт scoped контекст для конкретного NPC (тот же bus, тот же tick)."""
        return DRFExecutionContext(tick_id=self.tick_id, npc_id=npc_id, bus=self.bus)

    def emit(self, claim: dict):
        """Испускает претензию с авто-привязкой npc_id и tick_id."""
        _enriched = {**claim}
        if self.npc_id and "target_npc" not in _enriched:
            _enriched["target_npc"] = self.npc_id
        _enriched["tick_id"] = self.tick_id
        if self.npc_id:
            _enriched["npc_id"] = self.npc_id
        self.bus.emit(_enriched)
        print(f"[DRF_EMIT_BUS] bus_id={id(self.bus)} stream_size={len(self.bus.stream)} npc={self.npc_id} tick={self.tick_id}")

    def drain(self) -> list[dict]:
        """Схлопывает шину — делегирует bus. Вызывать только на frame-level."""
        return self.bus.drain()

# ── DRF Causal Scoring Weights (ДОЛГ 4.2) ──────────────────────────
# Давление определяет допустимость намерений, не только приоритет.
# Аддитивный скоринг: final = base + Σ(energy × weight × alignment)
_DRF_PRESSURE_WEIGHTS = {
    "SURVIVAL": 0.15,   # Критическое (flee) — радикальный бонус
    "SOCIAL":   0.10,   # Социальное (approach) — средний бонус
    "ROUTINE":  0.02,   # Рутина (schedule) — минимальный
}
_DRF_ALIGNED   = 1.0   # claim vector совпадает с intent reason — полный вес
_DRF_MISALIGNED = 0.3  # частичное давление при несовпадении вектора

@dataclass
class _TickContext:
    """Внутренний контекст тика — живёт только внутри execute()."""
    campaign_id: str
    scene_state: dict
    tick_number: int
    # Слой 4: позиции NPC ДО тика (для детекции переходов)
    old_npc_positions: dict = field(default_factory=dict)
    # Фаза 0: изменения от LifeEngine
    scene_changes: list = field(default_factory=list)
    # Фаза 2: spatial events для Phase 3 (memory)
    phase_2_events: list = field(default_factory=list)
    # Фаза 4: извлечённые темы для каждого NPC (npc_id → topic)
    npc_topics: dict = field(default_factory=dict)
    # Фаза 5: CommunicationIntent для каждого NPC (пока пустой — legacy pipeline)
    communication_intents: list = field(default_factory=list)
    # Фаза 5: решения DecisionHub
    decision_events: list = field(default_factory=list)
    # Фаза 9: финальный снимок
    world_snapshot: Optional[Any] = None
    # Player turn: данные от DM-фазы (если есть — пропускаем фазы 0-2)
    dm_ctx: Optional["DMContextDTO"] = None
    # Player turn: сервисы для legacy pipeline (передаёт npc_orchestration)
    npc_services: Optional[Any] = None
    # Player turn: результат legacy pipeline
    player_result: Optional[TickPlayerResultDTO] = None
    # Player turn: контекст GameLoop для фаз 7-10 (Устав §3 — единая последовательность)
    shared_context: Any = None
    actions: list = field(default_factory=list)
    player_intent: Optional["IntentDTO"] = None # ADR-031: Канонический интент
    player_pressure: Optional["IntentPressureProfile"] = None # ADR-031 Fix: Вектор давления из Фазы 1
    rules_result: Dict[str, Any] = field(default_factory=dict)
    r3_direct_mode: bool = True
    # Фаза 10: данные для коммита (мостируются из TickBuffer GameLoop)
    all_npcs_raw: list = field(default_factory=list)
    dirty_npcs: set = field(default_factory=set)
    wt_dirty: bool = False
    prop_dirty: bool = False
    max_npc_stress: float = 0.0
    # Фаза 10: данные для атомарного коммита
    npc_states: list[dict] = field(default_factory=list)
    # tick_events: все события тика для аудита (decision_events + spatial + handlers)
    tick_events: list[dict] | None = None
    # Фаза 0.5: буфер idle-дельт (social decay, reputation decay)
    delta_buffer: list = field(default_factory=list)
    # ── CFRM Layer 1 & P1: Причинная физика мира ──────────────────────
    event_buffer: EventBuffer = field(default_factory=EventBuffer)
    cluster_occupancy: ClusterOccupancy = field(default_factory=ClusterOccupancy)
    # DRF: Unified Causal Bus — единая память причинных напряжений тика.
    drf_bus: DRFBus = field(default_factory=DRFBus)


# ── Мостовые DTO для player turn (P1.1b) ──────────────────────────────
# TODO: удалить после замены HubEventContext на EventDTO

@dataclass(frozen=True)
class DMContextDTO:
    """Мост: DM-интерпретация → TickOrchestrator."""
    hub_event: Any
    nearby_npcs: list
    line_of_sight: dict
    scene_continuity: Any
    action_type: str
    player_target_id: str
    spatial_events: list
    raw_input: str
    is_session_start: bool
    current_tick: int = 0
    all_npcs_raw: list = field(default_factory=list)


@dataclass
class TickPlayerResultDTO:
    """Результат NPC-тика для player turn."""
    status: str = "ok"
    error: Optional[str] = None
    npc_contexts: list = field(default_factory=list)
    snapshot: Optional[dict] = None
    events: List[Any] = field(default_factory=list)
    dirty_npcs: set = field(default_factory=set)
    activity_overrides: Dict[str, str] = field(default_factory=dict)
    max_npc_stress: float = 0.0
    # MovementIntent — реактивное движение NPC (APPROACH и др.)
    # Оркестратор передаёт в MovementEngine → SceneChange → apply_changes
    movement_intents: list = field(default_factory=list)
    # Результат _phase_finalize (R3 frame, npc_reactions, npc_actions) —
    # доступен только если execute() прошёл фазы 8-10 (Устав §3)
    finalize_result: Optional[dict] = None


class TickOrchestrator:
    """
    Оркестратор тика мира.
    
    НЕ содержит бизнес-логику — только порядок вызовов фаз.
    Каждая фаза — отдельный сервис из services/.
    """

    def __init__(self, scene_manager=None, memory_manager=None, event_bus=None) -> None:
        self._scene_manager = scene_manager
        # DI: внешние сервисы (GameLoop передаёт свои инстансы)
        self._memory_manager = memory_manager
        self._event_bus = event_bus
        # Ленивая инициализация для оставшихся
        self._life_engine = None
        self._snapshot_builder = None
        self._transit_tracker = None
        self._spatial_service = None  # ADR-029: Инъекция для CFRM ClusterGraph
        # P1.1f: Social propagation — состояние тика переносим с GameLoop
        self._social_engine_factory: Any = None  # callable(campaign_id) → SocialEngine
        # §5.1 подписчики EventBus
        # P2: PerceptionSubscriber удален. Восприятие перенесено в LocalCausalSolver (Фаза 9)
        self._reaction_sub: ReactionSubscriber = ReactionSubscriber(self._get_event_bus())
        self._social_sub: SocialSubscriber = SocialSubscriber(self._get_event_bus())
        self._combat_sub: CombatSubscriber = CombatSubscriber(self._get_event_bus())
        
        # CFRM P2: Каузальный солвер и интерпретатор феноменологии
        self._causal_solver = LocalCausalSolver()
        # Фаза 0.5: time-driven idle-обработчики
        self._idle_handlers: list = []
        # StateApplicator для apply_batch (единый мутатор)
        self._state_applicator: Any = None
        # ReputationEngine для reputation decay
        self._reputation_engine: Any = None
        # DRF: Instance-level causal bus — переживает execute() / execute_player_finalize()
        self._drf_bus: DRFBus = DRFBus()

    def _get_life_engine(self):
        if self._life_engine is None:
            self._life_engine = get_life_engine()
        return self._life_engine

    def get_current_tick(self, campaign_id: str) -> int:
        """Единый источник тика — TemporalEngine (Устав §3).
        
        Публичный фасад для GameLoop и API routes.
        """
        return self._get_life_engine().get_current_tick(campaign_id)

    def _resolve_spatial_service(self, ctx: "_TickContext") -> Optional["SpatialService"]:
        """ADR-048: Единственный легитимный способ получить SpatialService.
        Приоритет: Инъекция GameLoop -> Аварийная сборка (с предупреждением).
        Кэш не используется для подмены отсутствующего сервиса в новом контексте.
        """
        # 1. Авторитетный источник: передан через NpcTickServices из npc_orchestration
        if ctx.npc_services and hasattr(ctx.npc_services, 'spatial_service') and ctx.npc_services.spatial_service:
            self._spatial_service = ctx.npc_services.spatial_service
            return self._spatial_service

        # 1.5. Кэш текущего тика: tick_player_turn уже резолвил сервис,
        # но execute_player_finalize создаёт новый _TickContext без npc_services (ADR-065).
        # Переиспользуем уже установленный сервис вместо аварийной сборки.
        if self._spatial_service:
            return self._spatial_service

        # 2. Аварийная сборка из scene_state (если GameLoop не пробросил сервис)
        _loc_id = ctx.scene_state.get("location_id", "")
        if _loc_id:
            try:
                logger.warning(f"[SPATIAL_AUTHORITY] ADR-048 VIOLATION: SpatialService собран вручную для {_loc_id}. GameLoop не пробросил сервис!")
                self._spatial_service = SpatialService.build_for_location(
                    campaign_id=ctx.campaign_id,
                    location_id=_loc_id,
                    scene_state=ctx.scene_state,
                )
                return self._spatial_service
            except Exception as e:
                logger.error(f"[SPATIAL_AUTHORITY] Crash during emergency build: {type(e).__name__}: {e}")
                return None
            
        return None

    def _get_memory_manager(self):
        if self._memory_manager is None:
            raise RuntimeError("MemoryManager не внедрён — передайте через конструктор")
        return self._memory_manager

    def _get_event_bus(self):
        if self._event_bus is None:
            self._event_bus = get_event_bus()
        return self._event_bus

    def _get_snapshot_builder(self):
        if self._snapshot_builder is None:
            self._snapshot_builder = WorldSnapshotBuilder()
        return self._snapshot_builder

    def _get_transit_tracker(self):
        if self._transit_tracker is None:
            self._transit_tracker = TransitTracker()
        return self._transit_tracker

    def set_social_engine_factory(self, factory: Any) -> None:
        """Внедряет фабрику SocialEngine (DI)."""
        self._social_engine_factory = factory
        # Передаём фабрику в SocialSubscriber
        if self._social_sub is not None:
            self._social_sub.set_social_engine_factory(factory)

    def set_state_applicator(self, applicator: Any) -> None:
        """Внедряет StateApplicator (DI) — единый мутатор для apply_batch."""
        self._state_applicator = applicator

    def set_reputation_engine(self, engine: Any) -> None:
        """Внедряет ReputationEngine (DI) для reputation decay."""
        self._reputation_engine = engine

    def add_idle_handler(self, handler: Any) -> None:
        """Добавляет IdleTickHandler для Фазы 0.5 (DI)."""
        self._idle_handlers.append(handler)

    # ── CFRM Layer 1: Spatial Index ─────────────────────────────────────

    def _rebuild_cluster_occupancy(self, ctx: _TickContext) -> None:
        """Восстанавливает индекс присутствия NPC в кластерах из scene_state.
        
        Вызывается на старте каждого тика. Маппит макро-зону (position)
        каждого NPC на канонический ClusterID.
        """
        start_time = time.perf_counter()
            
        # Сброс индекса для устранения ghost-сущностей (cache invalidation)
        ctx.cluster_occupancy = ClusterOccupancy()
        
        npc_positions = ctx.scene_state.get("npc_positions", {})
        location_id = ctx.scene_state.get("location_id", "")
        
        for npc_id, data in npc_positions.items():
            raw_node = data.get("position")
            if not raw_node:
                continue
            
            # Нормализация до канонического ClusterID (format: "location_id:node_id")
            if ":" in str(raw_node) or not location_id:
                cluster_id = str(raw_node)
            else:
                cluster_id = f"{location_id}:{raw_node}"
                
            ctx.cluster_occupancy.update_entity(npc_id, cluster_id)
            
        # Верификация: все NPC из all_npcs_raw должны быть в индексе
        if hasattr(ctx, 'all_npcs_raw') and ctx.all_npcs_raw:
            indexed_ids = set(ctx.cluster_occupancy.entity_to_cluster.keys())
            raw_ids = {npc.get("npc_id") for npc in ctx.all_npcs_raw if npc.get("npc_id")}
            if missing_in_index := raw_ids - indexed_ids:
                logger.warning(f"[CFRM] ClusterOccupancy: NPC в all_npcs_raw, но нет в npc_positions: {missing_in_index}")
                
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"[CFRM] ClusterOccupancy rebuild: {len(npc_positions)} entities in {elapsed_ms:.2f}ms")
            
        # Игрок — тоже наблюдатель в причинном пузыре
        if player_data := npc_positions.get("player"):
            if raw_player_node := player_data.get("position"):
                if ":" in str(raw_player_node) or not location_id:
                    p_cluster = str(raw_player_node)
                else:
                    p_cluster = f"{location_id}:{raw_player_node}"
                ctx.cluster_occupancy.update_entity("player", p_cluster)

    def execute(
        self,
        campaign_id: str,
        scene_state: dict,
        tick_number: int = 0,
        dm_ctx: Optional["DMContextDTO"] = None,
        npc_services: Optional[Any] = None,
        spatial_service: Optional[Any] = None, # ADR-048: Инъекция от GameLoop
    ) -> Union[TickResultDTO, TickPlayerResultDTO]:
        """Единственная точка входа для тика мира.

        Два режима:
        - idle (dm_ctx=None): полный 10-фазовый цикл без игрока
        - player (dm_ctx=...): фазы 3-6 через legacy pipeline, без 8-10
        """
        if scene_state is None:
            return TickResultDTO(status="no_scene")

        # ADR-048: Приоритет инъекции от GameLoop. Если нет — аварийная сборка.
        if spatial_service:
            self._spatial_service = spatial_service

        # DRF: Сброс шины на начало тика (один bus на весь lifecycle: execute + finalize)
        self._drf_bus.stream.clear()
        print(f"[DRF_BUS_RESET] bus_id={id(self._drf_bus)} tick={tick_number}")
        ctx = _TickContext(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=tick_number,
            dm_ctx=dm_ctx,
            npc_services=npc_services,
            drf_bus=self._drf_bus,  # Instance-level bus — не создаём новый!
        )

        # CFRM P2: Восстанавливаем пространственный индекс кластеров ДО привязки моста
        self._rebuild_cluster_occupancy(ctx)

        # CFRM P2: Мост деобъективации — превращение объективных событий в возмущения поля
        event_bus = self._get_event_bus()
        
        def _deobjectify_event(event: 'EventDTO') -> None:
            """Трансформирует EventDTO в FieldDisturbance на основе контекста тика."""
            import logging
            from app.models.cfrm import classify_event, FieldDisturbance, CausalAxis, DisturbanceVector
            
            result = classify_event(event.type)
            axis = result.axis
            
            # Логирование эпистемической неопределённости (событие на границе или неизвестно)
            if result.confidence < 0.5:
                logging.warning(f"[CFRM] classify_event: {event.type} -> {axis.value} (confidence={result.confidence}, source={result.source.value})")
            
            # Определяем кластер происхождения (кто вышел из строя реальности?)
            origin_cluster = ctx.cluster_occupancy.get_cluster(event.source) or "world:unknown"
            
            # Инференс векторов возмущения на основе типа события
            vectors = []
            if axis == CausalAxis.PHYSICAL:
                vectors.append(DisturbanceVector.KINETIC)
                vectors.append(DisturbanceVector.ACOUSTIC)
                if event.type in ("PLAYER_ATTACKS", "PLAYER_ATTACKED", "NPC_ATTACKED"):
                    vectors.append(DisturbanceVector.MATTER)
            elif axis == CausalAxis.COGNITIVE:
                vectors.append(DisturbanceVector.BEHAVIORAL)
            elif axis == CausalAxis.SOCIAL:
                vectors.append(DisturbanceVector.ACOUSTIC)
                vectors.append(DisturbanceVector.BEHAVIORAL)

            # Вычисляем базовую магнитуду возмущения
            magnitude = event.payload.get("intensity", 0.5)
            
            disturbance = FieldDisturbance(
                origin_cluster=origin_cluster,
                disturbance_type=axis,
                magnitude=magnitude,
                vectors=tuple(vectors),
                source_entity=event.source
            )
            ctx.event_buffer.add(disturbance, axis)

        event_bus.attach_cfrm_bridge(_deobjectify_event)

        try:
            if dm_ctx is not None:
                # Player turn: фазы 5-6 (decision + post-decision)
                # Фазы 8-10 выполняются через execute_player_finalize() ПОСЛЕ Rules agent,
                # потому что Rules — асинхронный и требует npc_contexts (Устав §3)
                self._phase_5_player_decision(ctx)
                self._phase_6_post_decision(ctx)
            else:
                # Idle tick: полный 10-фазовый цикл
                self._snapshot_positions_before(ctx)
                self._phase_0_simulation(ctx)
                self._phase_0_5_idle_services(ctx)
                self._phase_1_input(ctx)
                self._phase_2_event_bus_primary(ctx)
                self._phase_3_memory(ctx)
                self._phase_4_pre_decision(ctx)
                self._phase_5_decision(ctx)
                self._phase_6_post_decision(ctx)
                self._phase_8_drain_secondary(ctx)
                self._phase_9_integration(ctx)
                self._phase_10_persistence(ctx)

        except Exception as e:
            logger.error(f"[TICK_ORCH] Ошибка в тике {campaign_id}: {e}", exc_info=True)
            if dm_ctx is not None:
                return TickPlayerResultDTO(status="error", error=str(e))
            return TickResultDTO(status="error", error=str(e))
        finally:
            # CFRM P2: Гарантированно отключаем мост деобъективации в конце тика
            event_bus.detach_cfrm_bridge()

        if dm_ctx is not None:
            return ctx.player_result
        return TickResultDTO(
            status="ok",
            changes_count=len(ctx.scene_changes),
            significant_events=ctx.decision_events,
            world_snapshot=ctx.world_snapshot,
        )

    # ── Player Turn (тонкая обёртка) ────────────────────────────────

    def tick_player_turn(
        self,
        campaign_id: str,
        location: str,
        scene_state: dict,
        dm_ctx: DMContextDTO,
        npc_services: Any,
    ) -> TickPlayerResultDTO:
        """Player turn делегирует в execute() — единственная точка входа."""
        # execute() при dm_ctx возвращает TickPlayerResultDTO
        return self.execute(  # type: ignore[return-value]
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=dm_ctx.current_tick,
            dm_ctx=dm_ctx,
            npc_services=npc_services,
        )

    # ── Player Turn: decision через legacy pipeline ───────────────────

    def _phase_5_player_decision(self, ctx: _TickContext) -> None:
        """Player turn: делегирует в run_npc_pipeline (topic, DecisionHub, StateApplicator).

        Фазы 0-2 уже выполнены в _run_pipeline (DM, EventBus, CharacterFilter).
        Фазы 8-10 выполнит _run_pipeline (finalize, commit).
        Здесь — только decision + state mutation + IntentEventAdapter.
        """
        dm = ctx.dm_ctx
        _dm_npcs = len(dm.all_npcs_raw) if dm and dm.all_npcs_raw else 0
        logger.warning(f"[PHASE_5_PLAYER] ENTER: nearby_npcs={len(dm.nearby_npcs) if dm and dm.nearby_npcs else 0}, dm.all_npcs_raw={_dm_npcs}")
        from app.services.npc.npc_tick_contracts import NpcTickInput, NpcTickBuffer
        from app.services.npc.npc_tick_pipeline import run_npc_pipeline
        # DRF: Создаём frame context с привязкой к tick (npc_id привяжется в loop)
        _drf_ctx = DRFExecutionContext(tick_id=ctx.tick_number, bus=ctx.drf_bus)
        _pl = getattr(dm.hub_event, 'payload', '<NO_PAYLOAD>') if dm.hub_event else '<NO_HUB_EVENT>'
        logger.debug(f"[ARCHAE-TICK] hub_event id={id(dm.hub_event) if dm.hub_event else 0} payload={_pl} event_type={getattr(dm.hub_event, 'event_type', 'NO_TYPE')}")
        npc_input = NpcTickInput(
            campaign_id=ctx.campaign_id,
            location=ctx.scene_state.get("location_id", ""),
            scene_state=ctx.scene_state,
            player_target_id=dm.player_target_id,
            hub_event=dm.hub_event,
            is_session_start=dm.is_session_start,
            action_type=dm.action_type,
            raw_input=dm.raw_input,
            current_tick=dm.current_tick,
            all_npcs_raw=dm.all_npcs_raw,
            nearby_npcs=dm.nearby_npcs,
            scene_continuity=dm.scene_continuity,
            spatial_events=dm.spatial_events,
            line_of_sight=dm.line_of_sight,
        )

        npc_buffer = NpcTickBuffer()
        npc_buffer = run_npc_pipeline(npc_input, npc_buffer, ctx.npc_services, drf_ctx=_drf_ctx)

        # CommunicationIntents из pipeline → Фаза 6 (Устав §5.1)
        if npc_buffer.communication_intents:
            ctx.communication_intents = npc_buffer.communication_intents

        print(f"[TICK_PLAYER_INTENT] npc_buffer.movement_intents={npc_buffer.movement_intents} count={len(npc_buffer.movement_intents)}")
        ctx.player_result = TickPlayerResultDTO(
            npc_contexts=npc_buffer.npc_contexts,
            dirty_npcs=npc_buffer.dirty_npcs,
            activity_overrides=npc_buffer.activity_overrides,
            max_npc_stress=npc_buffer.max_npc_stress,
            movement_intents=npc_buffer.movement_intents,
        )

    # ── Player Turn: фазы 8-10 (после Rules agent) ──────────────────

    def execute_player_finalize(
        self,
        player_result: TickPlayerResultDTO,
        tick_buffer: Any,
        shared_context: Any,
        actions: list,
        campaign_id: str,
        rules_result: Dict[str, Any],
        r3_direct_mode: bool = True,
    ) -> TickPlayerResultDTO:
        """Фазы 8-10 для player turn — вызывается ПОСЛЕ Rules agent.

        Rules agent асинхронный и требует npc_contexts, поэтому
        выполняется между tick_player_turn (фазы 5-6) и этим методом.
        Устав §3: одна последовательность, один коммит.
        """
        # Создаём внутренний контекст с данными из GameLoop
          # ADR-031 Fix: Проброс вектора давления из Фазы 1
        _intent_res = shared_context.intent_resolution
        _ss_ref = shared_context.scene_state
        if not _ss_ref:
            logger.error(f"[SCENE_IDENTITY] shared_context.scene_state is {type(_ss_ref).__name__}! Creating orphan dict — traversals will be lost!")
        ctx = _TickContext(
            campaign_id=campaign_id, # ПОЧИНКА: Берем из аргумента, а не из location_id!
            scene_state=_ss_ref or {},
            tick_number=shared_context.current_tick or 0,
            dm_ctx=None,  # уже обработан в tick_player_turn
            shared_context=shared_context,
            # Мостируем данные из GameLoop TickBuffer
            all_npcs_raw=tick_buffer.all_npcs_raw if tick_buffer else [],
            player_intent=_intent_res.original_intent if _intent_res else None,
            player_pressure=_intent_res.pressure_profile if _intent_res else None,
            player_result=player_result,  # FIX: Без этого ctx.player_result=None → return None → краш finalize_result
            dirty_npcs=tick_buffer.dirty_npcs if tick_buffer else set(),
            wt_dirty=getattr(tick_buffer, 'wt_dirty', False),
            prop_dirty=getattr(tick_buffer, 'prop_dirty', False),
            max_npc_stress=getattr(tick_buffer, 'max_npc_stress', 0.0),
            drf_bus=self._drf_bus,  # DRF: Тот же bus, что в execute() — не создаём новый!
                        )
        
        # ADR-034 FIX: Исполнение Фазы 1 (WillpowerGate) для хода Игрока.
        # Без этого Интент Игрока пролетает мимо Воли, и Аватар покорно соглашается на всё.
        if ctx.player_intent:
            self._phase_1_input(ctx)

        # ADR-042 Fix: Инъекция актуального NPC state для DirectiveInterpretationSubscriber.
        # При ходе игрока Фаза 0 (_phase_0_simulation) пропускается, 
        # из-за чего ctx.all_npcs_raw остаётся пустым и Труба Воли обрывается (DIRECTIVE_NO_STATE).
        _life_engine = self._get_life_engine()
        if _life_engine:
            ctx.npc_states = _life_engine.get_npc_states(ctx.campaign_id)
            # ЗАЩИТА ОТ ЗАТИРАНИЯ: LifeEngine возвращает [] если tick() не вызывался.
            # Нельзя убивать загруженных NPC из-за пустого кэша.
            # ADR-O-112: Сохраняем инъекцию Аватара игрока из GameLoop при перезаписи.
            if ctx.npc_states:
                _player_entry = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
                ctx.all_npcs_raw = ctx.npc_states
                if _player_entry:
                    ctx.all_npcs_raw = [n for n in ctx.all_npcs_raw if n.get("npc_id") != "player"]
                    ctx.all_npcs_raw.append(_player_entry)
            
            # ADR-064 Fix: Fallback на DMContextDTO, так как LifeEngine возвращает []
            # при холодном кэше (ход игрока до idle-тика). Каузальная труба Воли не должна обрываться.
            if not ctx.all_npcs_raw and ctx.dm_ctx and ctx.dm_ctx.all_npcs_raw:
                ctx.all_npcs_raw = ctx.dm_ctx.all_npcs_raw
                logger.info("[CAUSALITY] all_npcs_raw загружен из dm_ctx (LifeEngine кэш пуст).")

            # NPIC NORMALIZATION GATE: Устранение State Starvation (NCC).
            # Любой NPC без body_state получает BODY_STATE_DISABLED.
            # Это гарантирует: агент существует физически (как инертное тело),
            # а не как "логический призрак" с социальными весами и нулевой физиологией.
            if ctx.all_npcs_raw:
                from app.models.npc_state import BODY_STATE_DISABLED
                for _npc in ctx.all_npcs_raw:
                    _bs = _npc.get("body_state")
                    if not _bs:  # None или пустой dict
                        _npc["body_state"] = BODY_STATE_DISABLED
                        logger.warning(f"[NPIC_NORMALIZE] NPC '{_npc.get('npc_id', '?')}' missing body_state. Injected DISABLED sentinel.")

        # ADR-035: Перехват пространственных команд в R3 Direct Path.
        # Если Слой 1 распознал MOVE, а пайплайн NPC пропустил это, создаем SceneChange напрямую.
        # S28 Debug: Проверка каузального шлюза
        _intent_res_debug = getattr(ctx.shared_context, 'intent_resolution', None) if ctx.shared_context else None
        logger.warning(f"[S28_GATE] shared_context exists: {ctx.shared_context is not None}, intent_resolution: {_intent_res_debug is not None}")
        if _intent_res_debug:
            _params_debug = _intent_res_debug.original_intent.parameters if _intent_res_debug.original_intent else None
            logger.warning(f"[S28_GATE] params exists: {_params_debug is not None}, data: {_params_debug}")

        if ctx.shared_context and hasattr(ctx.shared_context, 'intent_resolution') and ctx.shared_context.intent_resolution:
            _intent_res = ctx.shared_context.intent_resolution
            _params = _intent_res.original_intent.parameters if _intent_res.original_intent else None
            
            # Безопасное извлечение семантики (это DTO, не dict)
            _sem_action = getattr(_params, 'semantic_action', None) if _params else None
            _sem_target = getattr(_params, 'target_reference', None) if _params else None
            
            logger.warning(f"[S28_CHECK] sem_action={_sem_action}, sem_target={_sem_target}")
            if _sem_action == "MOVE" and _sem_target:
                _target_ref = _sem_target.lower()
                
                # ADR-O: Проверяем, является ли цель NPC. "Восток" — это не NPC.
                _is_npc_target = any(
                    _target_ref in n.get("name", "").lower() or _target_ref in n.get("npc_id", "").lower()
                    for n in ctx.all_npcs_raw
                ) if ctx.all_npcs_raw else False

                if _is_npc_target:
                    # Приказ NPC. Маршрутизируем в DirectiveInterpretationSubscriber.
                    logger.warning(f"[CAUSALITY] Semantic action MOVE detected for NPC '{_target_ref}'. Routing to DirectiveInterpretationSubscriber.")
                    
                    # S28: Замыкание контура. Вызов обработчика давления власти
                    try:
                        import types
                        from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber
                        # Передаем ID цели напрямую! Слой 2 уже резолвил имя.
                        _target_id = getattr(_params, 'target_id', None)
                        _directive_payload = {
                            "semantic_action": _sem_action, 
                            "target_reference": _target_ref,
                            "target_id": _target_id, # Пробрасываем ID
                            "social_pressure": 0.8
                        }
                        _mock_event = types.SimpleNamespace(payload=_directive_payload)
                        # Читаем NPC из _TickContext, куда они проброшены из GameLoop (TickBuffer)
                        # ADR-049: Передача актуальных NPC данных вместо пустого списка
                        _directive_deltas = DirectiveInterpretationSubscriber().handle(_mock_event, ctx.all_npcs_raw)
                        if _directive_deltas:
                            ctx.delta_buffer.extend(_directive_deltas)
                            # COGNITIVE OVERLAY: Применяем дельты НЕМЕДЛЕННО к raw state,
                            # чтобы DecisionHub (Фаза 5) видел актуальное давление, а не T-1
                            for delta in _directive_deltas:
                                _npc_id = delta.npc_id
                                _npc_state = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _npc_id), None)
                                if not _npc_state:
                                    continue
                                # Инжект директивы в PerceptualKernel
                                if hasattr(delta.payload, 'recent_directive_data') and delta.payload.recent_directive_data:
                                    _npc_state.setdefault("perceptual_kernel", {})["recent_directive"] = delta.payload.recent_directive_data
                                # Инжект эмоционального давления (stress, fear)
                                if hasattr(delta.payload, 'stress_delta') and delta.payload.stress_delta != 0:
                                    _npc_state.setdefault("emotion", {})["stress"] = _npc_state.get("emotion", {}).get("stress", 0.0) + delta.payload.stress_delta
                                if hasattr(delta.payload, 'fear_delta') and delta.payload.fear_delta != 0:
                                    _npc_state.setdefault("social_stats", {})["fear_of_player"] = _npc_state.get("social_stats", {}).get("fear_of_player", 0.1) + delta.payload.fear_delta
                                # GAP1 FIX: Темпоральная симметрия. Критический шок инжектится так же мгновенно, как директива.
                                # Слово не должно лететь быстрее Топора. Бессознательное тело = нокаут сейчас, не в следующем тике.
                                if hasattr(delta.payload, 'shock_impulse') and getattr(delta.payload, 'shock_impulse', 0.0) > 0.5:
                                    _npc_state.setdefault("body_state", {})["shock_impulse"] = getattr(_npc_state.get("body_state", {}), "shock_impulse", 0.0) + delta.payload.shock_impulse
                                    _npc_state.setdefault("body_state", {})["consciousness"] = max(0.0, 1.0 - delta.payload.shock_impulse)
                            logger.warning(f"[COGNITIVE_OVERLAY] Applied {len(_directive_deltas)} directive deltas to NPC raw state for DecisionHub.")
                    except Exception as e:
                        logger.error(f"[CAUSALITY_CRASH] DirectiveInterpretationSubscriber failed: {e}", exc_info=True)
                else:
                    logger.info(f"[CAUSALITY] MOVE target '{_target_ref}' is not an NPC. Treating as player spatial action.")

        # ADR-035: Обработка реактивных перемещений (MovementIntents)
        # В player turn LifeEngine не вызывается, поэтому MovementEngine нужно вызвать вручную
        _mi = ctx.player_result.movement_intents if ctx.player_result else None
        print(f"[MOVEMENT_INTENT_CHECK] player_result={ctx.player_result is not None} movement_intents={_mi} count={len(_mi) if _mi else 0}")
        if ctx.player_result and ctx.player_result.movement_intents:
            from app.services.spatial.movement_engine import MovementEngine
            _spatial_svc = self._resolve_spatial_service(ctx)
            print(f"[MOVEMENT_DEBUG] spatial_svc={_spatial_svc is not None} scene_manager={self._scene_manager is not None}")
            if _spatial_svc:
                me = MovementEngine()
                me.set_spatial_service(_spatial_svc)
                _tick = self.get_current_tick(ctx.campaign_id)
                print(f"[MOVEMENT_DEBUG] Calling process_intents with {len(ctx.player_result.movement_intents)} intents, tick={_tick}")
                # ДОЛГ 4.2: Causal Scoring Overlay — аддитивный скоринг давления
                self._apply_drf_scoring_overlay(ctx.player_result.movement_intents, ctx)
                changes = me.process_intents(
                    ctx.player_result.movement_intents, _tick,
                    ctx.scene_state.get("npc_positions", {}),
                    campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
                )
                print(f"[MOVEMENT_DEBUG] process_intents returned {len(changes)} changes")
                for _di, _ch in enumerate(changes):
                    print(f"[SCENE_CHANGE_DIAG] idx={_di} field={getattr(_ch, 'field', '?')} target={getattr(_ch, 'target', '?')} value={getattr(_ch, 'value', '?')}")
                # DIAGNOSTIC: Как SceneChange объекты выглядят?
                for _di, _ch in enumerate(changes):
                    print(f"[SCENE_CHANGE_DIAG] idx={_di} field={getattr(_ch, 'field', '?')} target={getattr(_ch, 'target', '?')} value={getattr(_ch, 'value', '?')}")
                logger.debug(f"[PIPELINE][MOVEMENT] changes={len(changes)} scene_manager={self._scene_manager is not None}")
                if changes and self._scene_manager:
                    self._scene_manager.apply_changes(ctx.campaign_id, changes, ctx.scene_state)
                    logger.warning(f"[PLAYER_TURN] Applied {len(changes)} reactive movement changes")
                    print(f"[TRAV_CHECK_P1] after_apply_changes: id(ctx.scene_state)={id(ctx.scene_state)} active_traversals={list(ctx.scene_state.get('active_traversals', {}).keys())}")
                elif changes and not self._scene_manager:
                    logger.error("[PIPELINE][MOVEMENT] CRITICAL: scene_manager is None! Changes lost!")
            else:
                logger.error("[SPATIAL_AUTHORITY] SpatialService отсутствует, реактивное движение заблокировано.")

        # Фаза 0.5: время не останавливается (decay = всегда)
        self._phase_0_5_idle_services(ctx)

        # ── ФИКС P0: Передать npc_contexts из player_result в shared_context ──
        # Без этого build_r3_dm_frame() видит пустой npc_contexts → "NPC не предпринимают значимых действий"
        if ctx.player_result:
            _pr = ctx.player_result
            if getattr(_pr, 'npc_contexts', None):
                ctx.shared_context.npc_contexts = _pr.npc_contexts
                logger.warning(f"[P0_FIX] npc_contexts transferred: {len(_pr.npc_contexts)} contexts")
            # Создать человекочитаемое описание действий NPC для DM контракта
            if getattr(_pr, 'movement_intents', None):
                _npc_names = {n.get("npc_id"): n.get("name", n.get("npc_id", "???"))
                              for n in ctx.all_npcs_raw if isinstance(n, dict)} if ctx.all_npcs_raw else {}
                _summary = []
                for _mi in _pr.movement_intents:
                    _nid = getattr(_mi, 'npc_id', None) or getattr(_mi, 'npc', None) or '???'
                    _iname = _npc_names.get(_nid, _nid)
                    _itype = str(getattr(_mi, 'intent', getattr(_mi, 'intent_type', '')))
                    if 'reactive:flee' in _itype:
                        _summary.append(f"{_iname} в страхе отступает")
                    elif 'micro_flee' in _itype:
                        _summary.append(f"{_iname} отшатывается")
                    elif 'reactive:approach' in _itype:
                        _summary.append(f"{_iname} приближается")
                    elif 'flee' in _itype:
                        _summary.append(f"{_iname} отступает")
                    elif 'approach' in _itype:
                        _summary.append(f"{_iname} приближается")
                    else:
                        _summary.append(f"{_iname}: {_itype}")
                if _summary:
                    ctx.shared_context.npc_movement_summary = _summary
                    logger.warning(f"[P0_FIX] npc_movement_summary: {_summary}")

        # Фазы 8→9→10 — единая последовательность (Устав §3)
        # Диагностика: проверяем pending до drain
        self._phase_8_player_handlers(ctx)
        self._phase_9_player_integration(ctx)
        self._phase_10_player_persistence(ctx)

        # Perception pipeline для action tick (тот же что idle tick)
        # Без этого action response не содержит player_perception → cues_received=0
        # ADR-092: Perception pipeline для action tick
        if ctx.scene_state and ctx.all_npcs_raw:
            if not hasattr(self, '_manifest_svc'):
                from app.services.perception.behavior_manifestation_service import BehaviorManifestationService
                from app.services.perception.phenomenology_projection_service import PhenomenologyProjectionService
                self._manifest_svc = BehaviorManifestationService()
                self._project_svc = PhenomenologyProjectionService()
            
            _traces = self._manifest_svc.produce_traces(ctx.scene_state, all_npcs_raw=ctx.all_npcs_raw)
            _player_perception = self._project_svc.project(_traces, ctx.scene_state, tick=ctx.tick_number)
            
            # Сохраняем для __init__.py snapshot builder
            if ctx.shared_context:
                ctx.shared_context.player_perception = _player_perception
                ctx.shared_context.all_npcs_raw_snapshot = ctx.all_npcs_raw

        # Возвращаем обновлённый результат (с finalize_result)
        # SCENE_IDENTITY: проверяем, что scene_state не потерян между фазами
        _final_traversals = list(ctx.scene_state.get("active_traversals", {}).keys()) if ctx.scene_state else []
        if _final_traversals:
            logger.warning(f"[SCENE_IDENTITY] finalize exits with traversals: {_final_traversals} id={id(ctx.scene_state)}")
        return ctx.player_result

    # ── Player Turn: finalize + commit ─────────────────────────────────

    def _phase_finalize(
        self,
        tick_ctx: Any,  # TickBuffer — lazy import чтобы избежать циклической зависимости
        actions: list,
        shared_context: Any,
        campaign_id: str,
        rules_result: Dict[str, Any],
        r3_direct_mode: bool = True,
    ) -> dict:
        """ФАЗА 7-8: R3 frame + NPC state + memory + working memory + decay.

        Перенесено из finalize_phase.py — TickOrchestrator владеет логикой.
        Использует внедрённые memory_manager вместо game_loop.
        Lazy-импорты чтобы избежать циклической зависимости с game_loop/.
        """
        # R3 Direct Mode: DecisionResult → SceneOutcome → DMFrame
        if r3_direct_mode:
            from app.services.scene.r3_direct_builder import build_r3_dm_frame
            npc_result = build_r3_dm_frame(shared_context, actions, rules_result)
        else:
            npc_result = {}

        # Применяем trust/stress дельты к NPC state
        from app.services.game_loop.npc_state_helpers import apply_npc_state_updates
        if npc_state_updates := npc_result.get("npc_state_updates", []):
            apply_npc_state_updates(
                self._get_memory_manager(), npc_state_updates,
                npc_dicts=tick_ctx.all_npcs_raw, campaign_id=campaign_id,
            )

        # Working Memory: ответы NPC → STM + L2
        from app.services.memory.working_memory_tick import write_npc_reactions_to_memory
        write_npc_reactions_to_memory(
            self._get_memory_manager(),
            npc_result.get("npc_reactions", []),
            tick_ctx.all_npcs_raw,
            campaign_id,
        )

        # Decay через TemporalContext — единое расписание (Устав §8)
        from app.services.memory.working_memory_tick import run_decay_and_resonance
        _temporal = self._get_life_engine().get_temporal_context(campaign_id)
        run_decay_and_resonance(
            self._get_memory_manager(), campaign_id, _temporal,
            shared_context.active_npc_ids,
        )
        # Фиксируем выполнение decay, чтобы счётчик сбросился
        if _temporal.should_run_memory_decay:
            self._get_life_engine().mark_decay_executed(campaign_id)

        return npc_result

    # ── Слой 4: подготовка ────────────────────────────────────────────

    def _snapshot_positions_before(self, ctx: _TickContext) -> None:
        """Снимок позиций NPC ДО тика — для SpatialEventDetector (Слой 4).
        Также продвигает TransitTracker (NPC в пути двигаются на 1 шаг).
        """
        ctx.old_npc_positions = _npc_positions_snapshot(ctx.scene_state)

        # ADR-0010: TransitTracker ампутирован из макро-пайплайна.
        # Макро-движение теперь — Semantic Relocation (атомарный переход).
        # Микро-движение (steering) будет реализовано в LocalSteeringLayer.

    # ── ФАЗЫ ──────────────────────────────────────────────────────────

    def _phase_0_simulation(self, ctx: _TickContext) -> None:
        """LifeEngine: need-driven, schedule, random events. Чистый Python.
        
        Применяет изменения сразу — phase 5 (Decision) должен видеть свежий state.
        Передаёт TransitTracker в MovementEngine для регистрации новых путей.
        """
        engine = self._get_life_engine()
        runtime_path = self._get_npc_runtime_path(ctx.campaign_id)
        # ADR-0010: TransitTracker больше не передаётся в LifeEngine/MovementEngine
        
        # ADR-048: Авторитетный SpatialService берется из единого резолвера
        _spatial_svc = self._resolve_spatial_service(ctx)
        if _spatial_svc:
            engine.set_spatial_service(_spatial_svc)
        
        # DRF: Инъекция единой причинной шины в LifeEngine
        engine.set_claim_bus(ctx.drf_bus)
        print(f"[DRF_BIND_LIFE] bus_id={id(ctx.drf_bus)}")
        changes, life_intents = engine.tick(ctx.campaign_id, ctx.scene_state, runtime_path=runtime_path)
        ctx.scene_changes = changes or []
        # Заполняем полные стейты для фаз 3-6, 10 (Устав §3.1)
        ctx.npc_states = engine.get_npc_states(ctx.campaign_id)
        # ADR-002: Единый мутатор работает с all_npcs_raw. В idle-пути это те же данные, что и npc_states
        ctx.all_npcs_raw = ctx.npc_states
        if changes and self._scene_manager:
            self._scene_manager.apply_changes(ctx.campaign_id, changes, ctx.scene_state)
            logger.debug(f"[TICK_ORCH] Фаза 0: {len(changes)} cognitive changes от LifeEngine")
        
        # ADR-049: LifeEngine De-godification. Замыкание контура локомоции.
        # Намерения расписания обрабатываются через MovementEngine, порождая TraversalState.
        if life_intents:
            # DRF: Претензии уже собраны напрямую в ctx.claim_field через Side-Channel Bus
            from app.services.spatial.movement_engine import MovementEngine
            _loc_id = ctx.scene_state.get("location_id", "")
            if _loc_id and _spatial_svc:
                me = MovementEngine()
                me.set_spatial_service(_spatial_svc)
                spatial_changes = me.process_intents(
                    life_intents, tick=ctx.tick_number,
                    npc_positions=ctx.scene_state.get("npc_positions", {}),
                    campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
                )
                if spatial_changes and self._scene_manager:
                    self._scene_manager.apply_changes(ctx.campaign_id, spatial_changes, ctx.scene_state)
                    logger.info(f"[TICK_ORCH] Фаза 0: {len(spatial_changes)} spatial changes from {len(life_intents)} LifeEngine intents")

        # ADR-019: Фаза 0.75 — Authoritative Traversal Lifecycle.
        # Бэкенд не интерполирует пиксели, но владеет жизненным циклом перемещения.
        self._process_traversals(ctx)

    def _process_traversals(self, ctx: _TickContext) -> None:
        """Фаза 0.75: Authoritative Traversal Lifecycle (STL Phase 1).
        Traversal НЕ мутирует мир напрямую. 
        При завершении он генерирует SceneChange (факт перемещения) и маркирует статус.
        Единый Spatial Commit (apply_changes) схлопнет реальность позже.
        """
        traversals = ctx.scene_state.get("active_traversals", {})
        if not traversals:
            return
            
        current_tick = ctx.scene_state.get("tick", 0)
        completion_changes = []
        
        for npc_id, trav in list(traversals.items()):
            if trav.get("status") != "MOVING":
                continue
            
            started_tick = trav.get("started_tick", 0)
            duration_ticks = trav.get("duration_ticks", 1)
            expected_arrival_tick = started_tick + duration_ticks
            
            if current_tick >= expected_arrival_tick:
                # STL: Транзит завершён. Генерируем финальный факт перемещения.
                target_node = trav.get("target_node")
                wp = trav.get("path_waypoints", [])
                
                # Факт 1: Каузальная позиция обновлена
                completion_changes.append(SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="position",
                    value=target_node,
                    cause="traversal_complete",
                    tick=current_tick
                ))
                
                # Факт 2: Визуальная позиция (финальная точка маршрута)
                if len(wp) >= 2:
                    completion_changes.append(SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=npc_id,
                        field="local_position",
                        value={"x": wp[-1][0], "y": wp[-1][1]},
                        cause="traversal_complete",
                        tick=current_tick
                    ))
                
                # STL: Удаление запрещено. Меняем статус на COMPLETED.
                trav["status"] = "COMPLETED"
                logger.debug(f"[TRAVERSAL] Lifecycle complete: npc={npc_id} arrived at {target_node}. SceneChanges emitted.")
        
        # STL: Схлопываем реальность через единый commit-point
        if completion_changes and self._scene_manager:
            self._scene_manager.apply_changes(ctx.campaign_id, completion_changes, ctx.scene_state)
            logger.info(f"[STL_COMMIT] Traversal completion: {len(completion_changes)} changes applied")

    def _phase_1_input(self, ctx: _TickContext) -> None:
        """Фильтрация воли игрока через WillpowerGate (ADR-031).
        
        Если интент угрожает идентичности аватара — возникает конфликт воли.
        """
        # БЕЗУСЛОВНАЯ ДИАГНОСТИКА: Вызывается ли метод вообще?
        import sys
        print(f"[WILL_TRACE_UNCONDITIONAL] _phase_1_input CALLED. Has intent: {ctx.player_intent is not None}", file=sys.stderr, flush=True)
        
        if not ctx.player_intent:
            return # Idle-тик или нет ввода от игрока

        intent = ctx.player_intent
        _sem_action = getattr(intent, 'parameters', None) and intent.parameters.semantic_action or getattr(intent, 'action', 'UNKNOWN')
        _sem_target = getattr(intent, 'target', 'UNKNOWN')  # ADR-125: DTO.target_id deprecated. Truth is in intent.target
        logger.warning(f"[WILL_TRACE] 1. Intent action: '{_sem_action}', target: '{_sem_target}', NPCs in raw: {len(ctx.all_npcs_raw)}")
        
        # Извлекаем снапшот аватара из симуляции
        player_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
        
        if not player_dict:
            logger.error(f"[WILL_TRACE] FAIL: Аватар 'player' НЕ НАЙДЕН в all_npcs_raw (len={len(ctx.all_npc_raw)}). Воля отключена!")
            self._publish_player_intent(ctx, intent)
            return
            
        logger.warning(f"[WILL_TRACE] 2. Avatar found. Psyche: {player_dict.get('psyche', {})}")

        # 1. Вектор давления берется из результата Фазы 1 (Единая точка вычисления)
        # Повторный вызов resolve_intent_pressure ЗАПРЕЩЕН (каузальная integrity)
        pressure = ctx.player_pressure or resolve_intent_pressure(intent)
        psyche = player_dict.get("psyche", {})
        
        # 2. Affect Resonance Scan (Искажение интерпретации реальности)
        # Травма - это не бафф, это искажение. Resonance -> Distortion -> Will.
        from app.services.affect import scan_affective_resonance, distort_pressure
        from app.models.affect import AffectiveImprint
        imprints = tuple(AffectiveImprint(**imp) for imp in player_dict.get("affective_imprints", []))
        
        # TODO: Передать PsychologicalPressure и PerceivedPhenomenon от CFRM P2, когда LocalCausalSolver будет генерировать их для хода игрока
        resonance = scan_affective_resonance(intent, None, None, imprints)
        distorted_pressure = distort_pressure(pressure, resonance, psyche)
        
        # 3. Вычисление реакции аватара (Cumulative Strain Model на искаженном давлении)
        will_response = compute_willpower(distorted_pressure, psyche)

        # ДИАГНОСТИКА: Почему нет конфликта?
        logger.warning(f"[WILL_TRACE] 2. Pressure: identity={pressure.identity_deviation:.2f}, humiliation={pressure.humiliation:.2f}")
        logger.warning(f"[WILL_TRACE] 3. Will state: {will_response.state.value}, Resistance: {will_response.resistance:.2f}")

        # 4. Маршрутизация исходов
        if resonance.trigger_strength > 0.1:
            logger.info(f"[AFFECT] Resonance detected: strength={resonance.trigger_strength:.2f}, bias={resonance.dominant_bias.value}, triggered={resonance.triggered_imprints}")
            
        if will_response.state in (WillState.COMPLY, WillState.RELUCTANT, WillState.CONDITIONED):
            # Аватар подчиняется (возможно, с неохотой или привыканием)
            self._publish_player_intent(ctx, intent)
            
            # Фиксация урона идентичности
            if will_response.identity_damage > 0:
                from app.models.delta_payloads import IdentityPayload
                ctx.delta_buffer.append(StateDeltas(
                    npc_id="player",
                    domain=DeltaDomain.IDENTITY,
                    target="player",
                    payload=IdentityPayload(identity_integrity_delta=-will_response.identity_damage)
                ))

            # ADR-039 FIX: Если Аватар подчинился неохотно (RELUCTANT+) или получил урон — 
            # это каузальное событие Воли. Пишем в ОБЕ трубы: DeltaBuffer (для NPC/истории) и shared_context (для API Игрока)
            if will_response.state != WillState.COMPLY or will_response.identity_damage > 0:
                from app.models.delta_payloads import WillConflictPayload
                ctx.delta_buffer.append(StateDeltas(
                    npc_id="player",
                    domain=DeltaDomain.WILL,
                    target="player",
                    payload=WillConflictPayload(
                        state=will_response.state.value,
                        resistance=will_response.resistance,
                        embodied_vector=will_response.embodied_vector.value if will_response.embodied_vector else None,
                        identity_damage=will_response.identity_damage
                    )
                ))
                from app.services.will import get_embodied_impulse_text
                ctx.shared_context.will_conflict_data = {
                    "original_intent": getattr(intent, 'parameters', None) and intent.parameters.semantic_action or getattr(intent, 'action', "UNKNOWN"),
                    "state": will_response.state.value,
                    "resistance": will_response.resistance,
                    "embodied_vector": will_response.embodied_vector.value if will_response.embodied_vector else None,
                    "counter_offer_text": get_embodied_impulse_text(will_response.embodied_vector) if will_response.embodied_vector else None
                }
                logger.info(f"[WILL] Conflict data written: state={will_response.state.value}, R={will_response.resistance:.2f}")
        else:
            # Аватар сопротивляется. Действие блокируется, публикуется WILL_CONFLICT
            logger.info(f"[WILL] Аватар сопротивляется! State={will_response.state.value}, R={will_response.resistance:.2f}")
            from app.domain.events import EventDTO
            from app.models.delta_payloads import WillConflictPayload
            
            # Генерируем структурный конфликт Воли через DeltaBuffer
            ctx.delta_buffer.append(StateDeltas(
                npc_id="player",
                domain=DeltaDomain.WILL,
                target="player",
                payload=WillConflictPayload(
                    state=will_response.state.value,
                    resistance=will_response.resistance,
                    embodied_vector=will_response.embodied_vector.value if will_response.embodied_vector else None,
                    identity_damage=will_response.identity_damage
                )
            ))
            
            # Восстанавливаем запись в shared_context для API ответа
            from app.services.will import get_embodied_impulse_text
            ctx.shared_context.will_conflict_data = {
                "original_intent": getattr(intent, 'parameters', None) and intent.parameters.semantic_action or getattr(intent, 'action', "UNKNOWN"),
                "state": will_response.state.value,
                "resistance": will_response.resistance,
                "embodied_vector": will_response.embodied_vector.value if will_response.embodied_vector else None,
                "counter_offer_text": get_embodied_impulse_text(will_response.embodied_vector) if will_response.embodied_vector else None
            }
            
            # Публикуем событие блокировки для других систем (DM, NPC реакция)
            get_event_bus().publish(EventDTO.create(
                event_type=EventType.WILL_CONFLICT.value,
                source="player",
                payload={"state": will_response.state.value, "resistance": will_response.resistance}
            ))
            
            # Эмоциональный отклик аватара на давление
            if will_response.fear_delta > 0:
                ctx.delta_buffer.append(StateDeltas(
                    npc_id="player",
                    domain=DeltaDomain.EMOTION,
                    target="player",
                    payload=EmotionPayload(stress_delta=will_response.fear_delta * 50, emotion_tag="fear")
                ))

        # ADR-036: Affective Conditioning (Sensitization & New Trauma)
        # Аватар учится через боль. Травма укрепляется при подавлении воли.
        if will_response.identity_damage > 0 or resonance.trigger_strength > 0.1:
            from app.services.affect import apply_conditioning
            from dataclasses import asdict
            current_game_time = ctx.scene_state.get("game_time_seconds", 0)
            updated_imprints = apply_conditioning(imprints, resonance, will_response, intent, current_game_time)
            player_dict["affective_imprints"] = [asdict(imp) for imp in updated_imprints]

    def _publish_player_intent(self, ctx: _TickContext, intent: IntentDTO) -> None:
        """Публикация разрешенного намерения игрока в шину."""
        _evt_map = {
            "attack": EventType.PLAYER_ATTACKS,
            "player_attacks": EventType.PLAYER_ATTACKS,
        }
        _act = getattr(intent, 'action', "") or ""
        _resolved_type = _evt_map.get(_act, EventType.PLAYER_INTERACTS)
        from app.domain.events import EventDTO
        get_event_bus().publish(EventDTO.create(
            event_type=_resolved_type.value,
            source="player",
            payload={"action": _act, "target": getattr(intent, 'target', "") or ""}
        ))

    def _phase_2_event_bus_primary(self, ctx: _TickContext) -> None:
        """Первая волна EventBus: пространственные события от MovementEngine (Слой 4).
        
        SpatialEventDetector сравнивает позиции до/после фазы 0
        и публикует NPC_MOVED, NPC_PROXIMITY_CLOSE, NPC_PROXIMITY_LEAVE.
        """
        if not ctx.old_npc_positions:
            return
        detector = SpatialEventDetector()
        if _spatial_events := detector.detect_and_publish(
            old_positions=ctx.old_npc_positions,
            new_scene_state=ctx.scene_state,
        ):
            ctx.phase_2_events.extend(_spatial_events)
            logger.debug(f"[TICK_ORCH] Фаза 2: {len(_spatial_events)} spatial events")

    def _phase_3_memory(self, ctx: _TickContext) -> None:
        """MemoryProcessor: обновляет NPCState ДО принятия решения (Устав §3.1).
        
        Для каждого spatial event из Phase 2 — находит затронутых NPC,
        конвертирует dict → NPCState, вызывает MemoryManager.apply().
        Пишет в STM + SQLite. narrative_cache синхронизируется обратно
        в npc_dict через NPCState.write_to_legacy (Устав §3.1).
        """
        if not ctx.phase_2_events:
            return

        mm = self._get_memory_manager()
        from app.models.npc_state import NPCState
        processed = 0

        for event in ctx.phase_2_events:
            for npc_id in self._resolve_affected_npcs(event):
                npc_dict = next(
                    (n for n in ctx.npc_states if n.get("id") == npc_id),
                    None,
                )
                if not npc_dict:
                    continue

                npc_state = load_l2_state_from_runtime_dict(npc_dict)
                # apply() ищет npc_id в payload — инжектим
                new_payload = {**event.payload, "npc_id": npc_id}
                new_event = replace(event, payload=new_payload)

                _sq = getattr(ctx.npc_services, 'spatial_query', None) if ctx.npc_services else None
                mm.apply(new_event, npc_state, campaign_id=ctx.campaign_id, spatial_query=_sq)
                # Мост обратно: apply() обновил narrative_cache на NPCState,
                # но Фаза 5 пересоздаёт NPCState из npc_dict (Устав §3.1)
                NPCState.write_to_legacy(npc_state, npc_dict)
                processed += 1

        logger.debug(f"[TICK_ORCH] Фаза 3: {processed} memory updates")

    @staticmethod
    def _resolve_affected_npcs(event) -> list[str]:
        """Определяет список NPC затронутых событием."""
        affected: list[str] = []
        etype = event.type

        if etype == EventType.NPC_MOVED.value:
            affected.append(event.source)
        elif etype in (
            EventType.NPC_PROXIMITY_CLOSE.value,
            EventType.NPC_PROXIMITY_LEAVE.value,
        ):
            affected.extend(
                (event.payload.get("npc_a", ""), event.payload.get("npc_b", ""))
            )

        return [n for n in affected if n]

    def _phase_4_pre_decision(self, ctx: _TickContext) -> None:
        """TopicExtractor: извлекает тему для каждого NPC (Устав §3.2).
        
        Приоритет источников темы:
        1. Spatial event затронувший NPC (конкретный контекст)
        2. STM буфер NPC (последние реплики)
        3. Фоллбэк "наблюдение" (никогда не пустой — Устав §3.2)
        """
        mm = self._get_memory_manager()

        for npc_dict in ctx.npc_states:
            npc_id = npc_dict.get("id")
            if not npc_id:
                continue

            topic = ""
            stm_text = ""

            # 1. Проверяем spatial events затронувшие этого NPC
            for event in ctx.phase_2_events:
                affected = self._resolve_affected_npcs(event)
                if npc_id in affected:
                    topic = extract_topic(
                        event_type=event.type,
                        raw_input=event.payload.get("to_node", ""),
                    )
                    break  # первый подошедший event достаточно

            # 2. Фоллбэк на STM
            if not topic:
                stm_text = mm.get_stm_prompt_block(ctx.campaign_id, npc_id)
                if stm_text.strip():
                    topic = extract_topic(
                        event_type="idle",
                        raw_input=stm_text,
                    )

            # 3. Жёсткий фоллбэк — тема НЕ может быть пустой (Устав §3.2)
            if not topic:
                topic = "наблюдение"

            ctx.npc_topics[npc_id] = topic

        logger.debug(f"[TICK_ORCH] Фаза 4: {len(ctx.npc_topics)} topics извлечено")

    def _phase_5_decision(self, ctx: _TickContext) -> None:
        """DecisionHub: создаёт CommunicationIntent для каждого NPC.
        
        Idle path теперь использует тот же набор параметров что player path:
        identity, drive_modifiers, cognitive_distortion, topic (Устав §3.1).
        CommunicationIntents передаются в Фазу 6 для публикации (Устав §3.3).
        """
        logger.warning(f"[PHASE_5] ENTER: is_player={ctx.is_player_turn if hasattr(ctx, 'is_player_turn') else '?'}, npc_states={len(ctx.npc_states) if hasattr(ctx, 'npc_states') else '?'}")
        engine = self._get_life_engine()
        
        # Собираем identity L1 для каждого NPC — кристаллизованные черты личности
        mm = self._get_memory_manager()
        identities: dict[str, dict[str, float]] = {}
        for npc_dict in ctx.npc_states:
            if npc_id := npc_dict.get("id"):
                if traits := mm.get_identity_traits(ctx.campaign_id, npc_id):
                    identities[npc_id] = traits
        
        decision_dicts, communication_intents, movement_intents = engine.tick_decisions(
            ctx.campaign_id, ctx.scene_state,
            topics=ctx.npc_topics, identities=identities,
        )
        ctx.decision_events = decision_dicts or []
        ctx.communication_intents = communication_intents or []
        if decision_dicts:
            logger.debug(f"[TICK_ORCH] Фаза 5: {len(decision_dicts)} decisions, {len(communication_intents)} intents")

        # Каузальный мост: когнитивные решения → пространственное движение
        if movement_intents:
            from app.services.spatial.movement_engine import MovementEngine
            from app.domain.movement import MacroMovementGoal, LocalSteeringGoal
            
            # ADR-060.1: Арбитраж LOD0/LOD1 ДО исполнения. 
            # Гарантирует, что LOD0 (уклонение) не убивает LOD1 (маршрут).
            # Порядок: LOD1 (Macro) выполняется первым, LOD0 (Micro) корректирует позицию.
            _merged_intents = []
            _per_npc = {}
            for i in movement_intents:
                _nid = getattr(i, 'npc_id', None)
                if _nid: _per_npc.setdefault(_nid, []).append(i)
                else: _merged_intents.append(i) # Без npc_id — сразу на исполнение
                
            for _nid, _intents in _per_npc.items():
                if len(_intents) > 1:
                    # Сортируем: Macro (LOD1) идет первым, Micro (LOD0) корректирует
                    _intents.sort(key=lambda x: isinstance(x, LocalSteeringGoal))
                _merged_intents.extend(_intents)
            
            _spatial_svc = self._resolve_spatial_service(ctx)
            if _spatial_svc:
                # ДОЛГ 4.2: Causal Scoring Overlay — аддитивный скоринг давления
                self._apply_drf_scoring_overlay(_merged_intents, ctx)
                
                me = MovementEngine()
                me.set_spatial_service(_spatial_svc)
                spatial_changes = me.process_intents(
                    _merged_intents, tick=ctx.tick_number,
                    npc_positions=ctx.scene_state.get("npc_positions", {}),
                    campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
                )
                if spatial_changes and self._scene_manager:
                    self._scene_manager.apply_changes(ctx.campaign_id, spatial_changes, ctx.scene_state)
                if spatial_changes:
                    logger.info(f"[CAUSAL_BRIDGE] Фаза 5: {len(spatial_changes)} spatial changes from {len(movement_intents)} cognitive intents")
            else:
                logger.error("[SPATIAL_AUTHORITY] SpatialService отсутствует, движение решений заблокировано.")

    def _phase_6_post_decision(self, ctx: _TickContext) -> None:
        """IntentEventAdapter: CommunicationIntent → EventDTO (Устав §3.3).
        
        Единственная легальная точка CommunicationIntent → EventDTO.
        Когда Phase 5 начнёт производить CommunicationIntent — провода уже готовы.
        """
        if not ctx.communication_intents:
            return

        bus = get_event_bus()
        adapter = IntentEventAdapter()
        converted = 0

        for intent in ctx.communication_intents:
            event = adapter.to_event(intent)
            bus.publish(event)
            converted += 1

        logger.debug(f"[TICK_ORCH] Фаза 6: {converted} intents → EventDTO")

    # ── Player Turn: фазы 8-10 (Устав §3 — единая последовательность) ──

    def _phase_8_player_handlers(self, ctx: _TickContext) -> None:
        """Player turn: Фаза 8 — делегирует в _phase_8_drain_secondary().

        Единая точка обработки для обоих путей (idle + player).
        """
        self._phase_8_drain_secondary(ctx)

    def _phase_9_player_integration(self, ctx: _TickContext) -> None:
        """Player turn: R3 frame + NPC state + memory + decay (Устав §9 — Integration).

        Делегирует в _phase_finalize, сохраняет результат в player_result.
        Также запускает аффективный pipeline (ADR-049) для player turn.
        """
        if ctx.shared_context is None:
            return

        # S75-FIX: Delta Reconciliation — применяем decay-дельты до affective pipeline.
        # Аналогично _phase_9_integration: без этого _run_affective_pipeline
        # читает stale affective_load/threat_gradient и перезаписывает decay.
        if ctx.delta_buffer and self._state_applicator:
            _aggregated = self._aggregate_deltas(ctx.delta_buffer)
            if _aggregated:
                self._state_applicator.apply_batch(
                    _aggregated, ctx.all_npcs_raw, ctx.campaign_id
                )
            ctx.delta_buffer.clear()

        _finalize = self._phase_finalize(
            ctx, ctx.actions, ctx.shared_context, ctx.campaign_id,
            ctx.rules_result, ctx.r3_direct_mode,
        )

        # Сохраняем для возврата из execute()
        if ctx.player_result is not None:
            ctx.player_result.finalize_result = _finalize

        # ADR-049: Аффективный pipeline для player turn
        # Без этого эмоции NPC замораживаются между ходами игрока
        self._run_affective_pipeline(ctx)

    def _phase_10_player_persistence(self, ctx: _TickContext) -> None:
        """Player turn: atomic commit (Устав §10 — Persistence).

        Единственная точка коммита за тик (Устав §4.2.1).
        """
        # DRF Observer: Схлопываем и логируем поле причинных напряжений ПЕРЕД коммитом
        print(f"[DRF_DRAIN_BUS] bus_id={id(ctx.drf_bus)} stream_size={len(ctx.drf_bus.stream)}")
        _claims = ctx.drf_bus.drain()
        if _claims:
            from collections import defaultdict
            _npc_claims = defaultdict(list)
            for c in _claims:
                _npc_claims[c.get("target_npc", "unknown")].append(f"{c.get('pressure_type', '?')}:{c.get('vector', '?')}({c.get('energy', 0.0):.1f})")
            for npc, claims_str in _npc_claims.items():
                print(f"[DRF_FIELD] npc={npc} pressures={claims_str}")
        else:
            print("[DRF_FIELD] claim_field is EMPTY this tick")
            
        if ctx.shared_context is None:
            return

        # Flush: применяем все накопленные idle-дельты через единый мутатор
        if ctx.delta_buffer:
            _aggregated = self._aggregate_deltas(ctx.delta_buffer)
            if _aggregated and self._state_applicator:
                self._state_applicator.apply_batch(
                    _aggregated, ctx.all_npcs_raw, ctx.campaign_id
                )
                ctx.delta_buffer.clear()

        if ctx.dirty_npcs or ctx.wt_dirty or ctx.prop_dirty:
            self._scene_manager.commit(
                campaign_id=ctx.campaign_id,
                scene_state=ctx.shared_context.scene_state,
                npc_dicts=ctx.all_npcs_raw,
            )
            _sources: list[str] = []
            if ctx.dirty_npcs:
                _sources.append(f"npc={len(ctx.dirty_npcs)}")
            if ctx.wt_dirty:
                _sources.append("world_tick")
            if ctx.prop_dirty:
                _sources.append("social")
            logger.warning(f"[COMMIT] single commit: {', '.join(_sources)}")

        # ADR-117: Синхронизация LifeEngine кэша с мутированными данными.
        # Без этого affective_load, emotion, body_state теряются между тиками —
        # каждый player turn загружает свежий статический конфиг.
        if ctx.all_npcs_raw:
            engine = self._get_life_engine()
            engine.update_cache(ctx.campaign_id, ctx.all_npcs_raw)

    # ── Фаза 0.5: Time-driven idle-сервисы (ВСЕГДА, время не останавливается) ──

    def _phase_0_5_idle_services(self, ctx: _TickContext) -> None:
        """Time-driven decay: social drift, reputation drift, affective decay.

        Выполняется КАЖДЫЙ тик (idle + player path).
        Время идёт непрерывно — эксплойты через движение исключены.
        Дельты собираются в ctx.delta_buffer → apply_batch() в Фазе 10.
        """
        # ADR-002: Время не останавливается. Каждый тик продвигает часы на GAME_TICK_INTERVAL_SECONDS
        self._advance_idle_time(ctx)
        
        # ADR-036: Affective Decay (Leaky Integrator для памяти)
        # Травмы затухают со временем, если не подкрепляются.
        from app.services.affect import decay_affective_imprints
        from app.models.affect import AffectiveImprint
        from dataclasses import asdict
        
        _current_time = ctx.scene_state.get("game_time_seconds", 0)
        for npc_dict in ctx.all_npcs_raw:
            imp_dicts = npc_dict.get("affective_imprints", [])
            if not imp_dicts: continue
            try:
                imprints = tuple(AffectiveImprint(**imp) for imp in imp_dicts)
                # delta_time берем из константы интервала тика (5 сек)
                decayed = decay_affective_imprints(imprints, 5.0, _current_time)
                npc_dict["affective_imprints"] = [asdict(d) for d in decayed]
            except Exception as e:
                # Инвариант 3: Аффективный decay — критический процесс, не debug
                logger.warning(f"[AFFECT_DECAY] Failed for {npc_dict.get('npc_id')}: {e}")

        if not self._idle_handlers:
            return

        current_tick = self._get_life_engine().get_current_tick(ctx.campaign_id)
        snapshots = self._build_npc_snapshots(ctx.all_npcs_raw)

        # S73-DIAG: Проверка призрачного decay (мёртвая ли психика в snapshot?)
        if snapshots:
            _sample = snapshots[0]
            print(f"[AFF_DEBUG] handlers={[type(h).__name__ for h in self._idle_handlers]} aff_load={_sample.get('affective_load', '<MISSING>')} emo={_sample.get('emotion', '<MISSING>')}")

        for handler in self._idle_handlers:
            try:
                deltas = handler.handle(snapshots, ctx.campaign_id, current_tick)
            except Exception as e:
                logger.error(
                    f"[PHASE_0.5] {handler.name} handle() failed: {e}. "
                    f"Deltas lost this tick."
                )
                continue

            if deltas:
                ctx.delta_buffer.extend(deltas)

        # S75-R1.1 FIX: Perceptual Decay (Rule 38, ADR-122).
        # threat_gradient, uncertainty, anomaly_score затухают в idle-тиках.
        # Без этого _run_affective_pipeline (Фаза 9) пересчитывает affective_load
        # из устаревшего PK, перезаписывая честный декей из AffectiveDecayHandler.
        # Результат: Вечный Двигатель Страха (maid_lusya: 1.00/fearful навсегда).
        _PERCEPTUAL_DECAY = {"threat_gradient": 0.05, "uncertainty": 0.03, "anomaly_score": 0.02}
        for npc_dict in ctx.all_npcs_raw:
            pk = npc_dict.get("perceptual_kernel")
            if pk and isinstance(pk, dict):
                for _key, _rate in _PERCEPTUAL_DECAY.items():
                    if _key in pk:
                        pk[_key] = max(0.0, float(pk[_key]) - _rate)

        # S75-R1 FIX: Cache Desync (Техзадание S75).
        # Синхронизация LifeEngine cache с применёнными idle-дельтами.
        # Хотя Фаза 10 тоже вызывает update_cache, этот вызов гарантирует,
        # что кэш обновлён ДО Фазы 9, предотвращая расхождение истин.
        if ctx.all_npcs_raw:
            engine = self._get_life_engine()
            engine.update_cache(ctx.campaign_id, ctx.all_npcs_raw)

    def _advance_idle_time(self, ctx: _TickContext) -> None:
        """Продвигает игровое время на GAME_TICK_INTERVAL_SECONDS (ADR-002: время не останавливается).
        Работает даже если shared_context=None (idle-путь), читая время из scene_state.
        """
        from app.core.constants import GAME_TICK_INTERVAL_SECONDS
        from app.core.calendar import Calendar

        current_seconds = 0
        # Приоритетный источник: shared_context (аккумулирует дни/годы)
        if ctx.shared_context is not None and hasattr(ctx.shared_context, 'game_time_seconds') and ctx.shared_context.game_time_seconds:
            current_seconds = ctx.shared_context.game_time_seconds
        else:
            # Fallback: legacy time_of_day в scene_state (теряет день/год, но часы идут)
            _env_time = ctx.scene_state.get("environment", {}).get("time_of_day", "07:00")
            current_seconds = Calendar.parse_hhmm(_env_time)

        new_seconds = Calendar.advance(current_seconds, GAME_TICK_INTERVAL_SECONDS)

        # Обновляем оба источника данных
        if ctx.shared_context is not None and hasattr(ctx.shared_context, 'game_time_seconds'):
            ctx.shared_context.game_time_seconds = new_seconds

        # Сохраняем абсолютное время в scene_state для персистенции и фронтенда
        ctx.scene_state["game_time_seconds"] = new_seconds
        new_hhmm = Calendar.format_time(new_seconds)
        ctx.scene_state.setdefault("environment", {})["time_of_day"] = new_hhmm

    @staticmethod
    def _build_npc_snapshots(all_npcs_raw: list) -> list:
        """Проецирует all_npcs_raw → List[NPCStateSnapshot] для handlers.

        Handlers работают только с контрактом, не с внутренностями scene_state.

        Маппинг данных:
          social_stats.trust         → relationship_cache["player"]["trust"] (0-100)
          social_stats.fear_of_player → relationship_cache["player"]["fear"]
          psyche.loyalty_true        → base_values["player"] (базовое доверие к игроку)
          status_profile.faction_rank → faction_affiliations (ключи фракций)

        NPC-to-NPC связи обогащаются через _enrich_with_social_relations() при загрузке.
        После обогащения relationship_cache содержит записи NPC→NPC из village_relations.json.
        Player entry гарантированно добавляется из social_stats (даже при наличии NPC→NPC записей).
        """
        from app.models.idle_tick import NPCStateSnapshot

        snapshots = []
        for npc in all_npcs_raw:
            if not isinstance(npc, dict):
                continue

            npc_id = npc.get("id", "")
            psyche = npc.get("psyche", {})
            ss = npc.get("social_stats", {})

            # relationship_cache: вложенный формат {target: {trust, fear, ...}}
            # SocialDecayHandler ожидает: {target: {trust, fear, base_trust}}
            existing_rc = npc.get("relationship_cache", {})
            if isinstance(existing_rc, dict) and any(
                isinstance(v, dict) for v in existing_rc.values()
            ):
                # Уже во вложенном формате — берём как основу (shallow copy)
                relationship_cache = dict(existing_rc)
            else:
                # Маппинг social_stats (player-facing плоский) → вложенный формат
                relationship_cache = {}

            # Гарантируем player entry из social_stats
            # (после обогащения NPC→NPC, relationship_cache может существовать
            # без player entry — social_stats.trust/fear_of_player заполняют его)
            _player_trust = float(ss.get("trust", 0.0))
            _player_fear = float(ss.get("fear_of_player", 0.0))
            _player_debt = float(ss.get("debt", 0.0))
            if "player" not in relationship_cache and (_player_trust != 0.0 or _player_fear != 0.0 or _player_debt != 0.0):
                relationship_cache["player"] = {
                    "trust": _player_trust,
                    "fear": _player_fear,
                    "debt": _player_debt,
                }

            # base_values: базовые значения для drift-расчёта
            # SocialDecayHandler: base_vals.get(target, rel_data.get("base_trust", current))
            existing_bv = npc.get("base_values", {})
            base_values = dict(existing_bv) if existing_bv else {}  # shallow copy

            # Гарантируем player base из loyalty_true
            # (после обогащения NPC→NPC, base_values может существовать
            # без player entry — psyche.loyalty_true заполняет его)
            if "player" not in base_values:
                _loyalty = float(psyche.get("loyalty_true", 50.0))
                base_values["player"] = _loyalty

            # faction_affiliations: список фракций для ReputationDecayHandler
            if existing_fa := npc.get("faction_affiliations", []):
                faction_affiliations = existing_fa
            else:
                # Извлекаем из status_profile.faction_rank
                _faction_rank = npc.get("status_profile", {}).get("faction_rank", {})
                faction_affiliations = list(_faction_rank.keys())

            # --- Physiology Domain: Body LOD Macro ---
            # Мастер Тай: body_profile (статика) + body_state (рантайм) → Snapshot
            # НЕ вычислять effective values здесь! Хранить базу и модификаторы отдельно.
            body_profile = npc.get("body_profile", {})
            body_state = npc.get("body_state", {})
            
            _max_hp = float(body_profile.get("max_hp", 100.0))
            _current_hp = float(body_state.get("current_hp", _max_hp))
            
            _base_abilities = body_profile.get("abilities", {})
            _modifiers = body_state.get("modifiers", {})
            _statuses = body_state.get("statuses", [])
            
            # Мастер Тай: Injuries должны группироваться по zone, а не плоским списком
            _raw_injuries = body_state.get("injuries", [])
            injuries_by_zone: Dict[str, list] = {}
            for inj in _raw_injuries:
                zone = inj.get("target_zone", "unknown")
                if zone not in injuries_by_zone:
                    injuries_by_zone[zone] = []
                injuries_by_zone[zone].append(inj)
            
            # --- Affective Domain: Psyche LOD Macro (S74) ---
            # Разум получает время. Интеграл и эмоция проецируются в idle-слой.
            _affective_load = float(npc.get("affective_load", 0.0))
            _emotion = str(npc.get("emotion", "neutral") or "neutral")

            snapshots.append(NPCStateSnapshot(
                npc_id=npc_id,
                stress=float(psyche.get("stress", 0.0)),
                relationship_cache=relationship_cache,
                base_values=base_values,
                faction_affiliations=faction_affiliations,
                # Physiology
                hp=_current_hp,
                max_hp=_max_hp,
                pain=float(body_state.get("pain", 0.0)),
                fatigue=float(body_state.get("fatigue", 0.0)),
                blood_loss=float(body_state.get("blood_loss", 0.0)),
                consciousness=float(body_state.get("consciousness", 1.0)),
                shock_impulse=float(body_state.get("shock_impulse", 0.0)),
                life_status=str(body_state.get("life_status", "ALIVE")),
                injuries_by_zone=injuries_by_zone,
                base_abilities=_base_abilities,
                modifiers=_modifiers,
                statuses=_statuses,
                # Affective (S74: Temporal Mind)
                affective_load=_affective_load,
                emotion=_emotion,
            ))
        return snapshots

    @staticmethod
    def _aggregate_deltas(deltas: list) -> list:
        """Domain Reduction Semantics Layer (DRSL): редукция по законам физики доменов.
        
        Мастер Тай: система не различала коммутативные и некоммутативные эффекты.
        Бухгалтерия (Social) ≠ Физика (Physiology). 
        
        PHYSICS_COMPOSITE (Physiology) обходит merge — это инъекции энергии в тело,
        они обрабатываются ImpactEngine/StateApplicator как эволюция состояния, а не сумма.
        """
        from app.models.delta_payloads import (
            SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload
        )

        def _reduce_additive(p1, p2):
            """Сливает два payload для ADDITIVE/BOUNDED_ADDITIVE доменов."""
            if p1 is None: return p2
            if p2 is None: return p1
            if type(p1) != type(p2): return p2 

            if isinstance(p1, SocialPayload):
                return SocialPayload(
                    trust_delta=p1.trust_delta + p2.trust_delta,
                    fear_delta=p1.fear_delta + p2.fear_delta,
                    affection_delta=p1.affection_delta + p2.affection_delta,
                    debt_delta=p1.debt_delta + p2.debt_delta,
                )
            if isinstance(p1, EmotionPayload):
                return EmotionPayload(
                    stress_delta=p1.stress_delta + p2.stress_delta,
                    emotion_delta=p1.emotion_delta + p2.emotion_delta,
                    # Для тегов/травм — последний ненулевой выигрывает
                    emotion_tag=p2.emotion_tag if p2.emotion_tag is not None else p1.emotion_tag,
                    new_trauma=p2.new_trauma if p2.new_trauma is not None else p1.new_trauma,
                    # ADR-117: affective_load — последний ненулевой выигрывает
                    # Без этого мёрж дропает affective_load → prev=0.000 каждый тик
                    affective_load=p2.affective_load if p2.affective_load is not None else p1.affective_load,
                )
            if isinstance(p1, ReputationPayload):
                return ReputationPayload(
                    reputation_delta=p1.reputation_delta + p2.reputation_delta
                )
            if isinstance(p1, IdentityPayload):
                # OVERWRITE: для воли — последний выигрывает, для чисел — сумма
                return IdentityPayload(
                    identity_integrity_delta=p1.identity_integrity_delta + p2.identity_integrity_delta,
                    pressure_resistance_delta=p1.pressure_resistance_delta + p2.pressure_resistance_delta,
                    will_state_override=p2.will_state_override if p2.will_state_override is not None else p1.will_state_override,
                )
            if isinstance(p1, PerceptionPayload):
                # ADDITIVE: threat/uncertainty/anomaly — суммируются (decay + CFRM)
                return PerceptionPayload(
                    threat_gradient_delta=p1.threat_gradient_delta + p2.threat_gradient_delta,
                    uncertainty_delta=p1.uncertainty_delta + p2.uncertainty_delta,
                    anomaly_score_delta=p1.anomaly_score_delta + p2.anomaly_score_delta,
                )
            return p2

        # Разделение потоков: Физика (PHYSICS_COMPOSITE) обходит merge
        physics_deltas = []
        algebraic_deltas = []

        for d in deltas:
            if not isinstance(d, StateDeltas):
                continue

            policy = DELTA_POLICY_REGISTRY.get(d.domain, ReductionPolicy.ADDITIVE)
            
            if policy == ReductionPolicy.PHYSICS_COMPOSITE:
                # Тело — инерционная система. Дельты передаются как отдельные 
                # инъекции энергии, не суммируются здесь.
                physics_deltas.append(d)
            else:
                algebraic_deltas.append(d)

        # Бухгалтерская редукция (ADDITIVE / BOUNDED_ADDITIVE / OVERWRITE)
        groups: dict[tuple, StateDeltas] = {}

        for d in algebraic_deltas:
            # Формируем ключ группировки
            if d.domain is not None:
                key = (d.npc_id, d.domain, d.target)
            else:
                # Легаси v1 фолбэк (пока потребители не мигрированы)
                key = (d.npc_id, None, d.intent_target or d.social_target or d.faction_id)

            if key in groups:
                existing = groups[key]
                policy = DELTA_POLICY_REGISTRY.get(d.domain, ReductionPolicy.ADDITIVE)
                
                if policy == ReductionPolicy.OVERWRITE and d.domain == DeltaDomain.IDENTITY:
                    # OVERWRITE: для Identity воли — последний выигрывает, для чисел — сумма
                    existing.identity_integrity_delta += d.identity_integrity_delta
                    existing.pressure_resistance_delta += d.pressure_resistance_delta
                    if d.will_state_override is not None:
                        existing.will_state_override = d.will_state_override
                else:
                    # ADDITIVE / BOUNDED_ADDITIVE: суммируем v1 поля
                    existing.stress_delta += d.stress_delta
                    existing.emotion_delta += d.emotion_delta
                    existing.trust_delta += d.trust_delta
                    existing.fear_delta += d.fear_delta
                    existing.reputation_delta += d.reputation_delta
                    existing.identity_integrity_delta += d.identity_integrity_delta
                    existing.pressure_resistance_delta += d.pressure_resistance_delta
                    
                    # v1 trait_updates — merge
                    for k, v in d.trait_updates.items():
                        existing.trait_updates[k] = existing.trait_updates.get(k, 0.0) + v
                
                # v1 маршрутизация — дополняем если в existing пусто
                if d.intent_target is not None: existing.intent_target = d.intent_target
                if d.social_target is not None: existing.social_target = d.social_target
                if d.faction_id is not None: existing.faction_id = d.faction_id
                
                # source: берём последний ненулевой
                if d.source != "unknown":
                    existing.source = d.source
                
                # v1 теги — последний выигрывает
                if d.emotion_tag is not None:
                    existing.emotion_tag = d.emotion_tag
                if d.new_trauma is not None:
                    existing.new_trauma = d.new_trauma
                if d.will_state_override is not None:
                    existing.will_state_override = d.will_state_override

                # v2 payload merge (алгебраическая редукция)
                existing.payload = _reduce_additive(existing.payload, d.payload)
            else:
                groups[key] = d

        # Слияние: алгебраические (свернутые) + физические (как есть, без merge)
        _result = list(groups.values()) + physics_deltas
        if physics_deltas:
            logger.debug(f"[AGGREGATE] algebraic={len(groups.values())} physics={len(physics_deltas)} physics_domains={[d.domain for d in physics_deltas[:3]]}")
        return _result

    def _phase_8_drain_secondary(self, ctx: _TickContext) -> None:
        """ФАЗА 8: Layered Reduction (Causal Depth Model).

        Шина для фактов (Фазы 2/7), Фаза 8 для обработки.
        Порядок слоёв: Perception → Physical (Combat) → Cognitive (Reaction) → Social.
        Physical слой материализуется перед Cognitive для соблюдения причинности
        без нарушения порядка исполнения (Мастер Тай: Dual Buffer Causal Model).
        """
        # 1. Perception Layer — УДАЛЕН. Вычисляется в Фазе 9 через LocalCausalSolver.
        
        # 2. Physical Layer (Combat: вычисление урона, генерация shock_impulse)
        combat_result = self._execute_phase8_handler(ctx, self._combat_sub)

        # ADR-O-112 DIAG: Проверяем, что CombatSubscriber вернул
        if combat_result:
            logger.debug(f"[DIAG_PHASE8] combat_result: deltas={len(combat_result.deltas or [])} missed={len(getattr(combat_result, 'missed_targets', []))}")
        else:
            logger.debug(f"[DIAG_PHASE8] combat_result=None — CombatSubscriber вернул пустой результат")

        # Извлекаем combat summary для DM (pain, shock, injuries, misses)
        if combat_result and ctx.shared_context is not None:
            from app.models.delta_payloads import PhysiologyPayload
            from app.models.state_delta import DeltaDomain
            _combat_data = {}
            for d in (combat_result.deltas or []):
                if d.domain == DeltaDomain.PHYSIOLOGY and d.payload and isinstance(d.payload, PhysiologyPayload):
                    _target = d.npc_id or d.target or "unknown"
                    _combat_data[_target] = {
                        "pain_delta": d.payload.pain_delta,
                        "blood_loss_delta": d.payload.blood_loss_delta,
                        "shock_impulse": d.payload.shock_impulse,
                        "injuries": [{"zone": i.target_zone, "severity": i.structural_damage, "damage_type": i.damage_type} for i in d.payload.add_injuries] if d.payload.add_injuries else []
                    }
            # Промахи по расстоянию — DM должен знать что атака не достигла цели
            _missed = getattr(combat_result, 'missed_targets', [])
            for _miss in _missed:
                _combat_data[_miss["npc_id"]] = {"miss": True, "distance": _miss["distance"], "max_range": _miss["max_range"]}
            if _combat_data:
                ctx.shared_context.combat_data = _combat_data
                logger.debug(f"[DIAG_PHASE8] combat_data targets={list(_combat_data.keys())} data={_combat_data}")
            else:
                logger.debug(f"[DIAG_PHASE8] combat_data EMPTY — no PhysiologyPayload in deltas")

        # Материализация Physical Layer: иммутабельный снимок для Cognitive слоя
        physical_deltas_tuple: Tuple[StateDeltas, ...] = ()
        if combat_result and combat_result.deltas:
            physical_deltas_tuple = tuple(combat_result.deltas)

        # 3. Cognitive Layer (Reaction: чтение shock_impulse, генерация страха/паники)
        self._execute_phase8_handler(
            ctx, self._reaction_sub, physical_deltas_materialized=physical_deltas_tuple
        )

        # 4. Social Layer (Social: распространение слухов)
        self._execute_phase8_handler(
            ctx, self._social_sub, physical_deltas_materialized=physical_deltas_tuple
        )

        # Flush: применяем все накопленные дельты (Phase 0.5 + Phase 8)
        # через единый мутатор → Phase 9 видит обновлённое состояние (ADR-002)
        if ctx.delta_buffer:
            _aggregated = self._aggregate_deltas(ctx.delta_buffer)
            if _aggregated and self._state_applicator:
                self._state_applicator.apply_batch(
                    _aggregated, ctx.all_npcs_raw, ctx.campaign_id
                )
                ctx.delta_buffer.clear()

    def _execute_phase8_handler(
        self,
        ctx: _TickContext,
        handler: Phase8Handler,
        physical_deltas_materialized: Tuple[StateDeltas, ...] = (),
    ) -> Optional[Phase8Result]:
        """Исполняет один обработчик Фазы 8 с изолированным контекстом."""
        # ADR-O-112 DIAG: Проверяем, есть ли накопленные события до drain
        if handler.name == "combat":
            _pending = getattr(handler, '_pending_events', [])
            logger.debug(f"[DIAG_PHASE8] combat_sub pending_events={len(_pending)} types={[getattr(e, 'type', '?') for e in _pending[:3]]}")
        events = handler.drain_events()
        if handler.name == "combat" and not events:
            logger.debug(f"[DIAG_PHASE8] combat_sub DRAINED 0 events — _pending was={len(_pending)}")
        _handler_name = getattr(handler, '__class__', type(handler)).__name__
        if events:
            logger.debug(f"[PHASE8_DRAIN] handler={_handler_name} events={len(events)} types={[getattr(e, 'type', '?') for e in events[:3]]}")
        if not events:
            return None

        _npc_contexts = (
            ctx.player_result.npc_contexts
            if ctx.player_result is not None
            else []
        )
        try:
            phase8_ctx = Phase8Context(
                all_npcs_raw=ctx.all_npcs_raw,
                all_npc_contexts=_npc_contexts,
                shared_context=ctx.shared_context,
                campaign_id=ctx.campaign_id,
                tick_ctx=ctx,
                physical_deltas_materialized=physical_deltas_materialized,
            )
        except Exception as _ctx_err:
            # Инвариант 3: Наблюдаемость отказа — CDS должен видеть крахи Phase8
            logger.warning(
                f"[PIPELINE][CRITICAL] phase=8_ctx handler={_handler_name} "
                f"error={type(_ctx_err).__name__}: {_ctx_err}"
            )
            return None

        try:
            result = handler.handle(events, phase8_ctx)
        except Exception as e:
            # Инвариант 3: Safeguard не = молчание. Крах виден CDS.
            logger.warning(
                f"[PHASE8_CRASH] handler={handler.name} error={type(e).__name__}: {e}"
            )
            logger.error(
                f"[PHASE_8] {handler.name} handle() failed: {e}. "
                f"Events lost this tick."
            )
            return None

        # Применяем Phase8Result к _TickContext
        self._apply_phase8_result(ctx, result, handler.name)
        return result

    def _apply_phase8_result(
        self,
        ctx: _TickContext,
        result: Phase8Result,
        handler_name: str,
    ) -> None:
        """Применяет Phase8Result к _TickContext.

        perception → фильтр npc_contexts + perceiving_npcs
        social → deltas применяются к all_npcs_raw
        deltas с npc_id → применение к конкретному NPC
        """
        # Perception: фильтруем NPC контексты
        if result.perceiving_npc_ids is not None and ctx.shared_context is not None:
            _all_ctxs = (
                ctx.player_result.npc_contexts
                if ctx.player_result is not None
                else []
            )
            _filtered = [
                c for c in _all_ctxs
                if c.get("npc_id") in result.perceiving_npc_ids
            ]
            ctx.shared_context.npc_contexts = _filtered
            ctx.shared_context.perceiving_npcs = list(result.perceiving_npc_ids)

        # Deltas: маршрутизация через delta_buffer → apply_batch (ADR-002 единый мутатор)
        # Прямая мутация all_npcs_raw запрещена — все дельты идут через единый путь
        if result.deltas:
            ctx.delta_buffer.extend(result.deltas)
            ctx.prop_dirty = True
            logger.debug(
                f"[PHASE_8] {handler_name}: {len(result.deltas)} deltas "
                f"routed to delta_buffer"
            )

        # Legacy: prop_dirty от старых обработчиков (совместимость)
        if result.prop_dirty:
            ctx.prop_dirty = True

    def _phase_9_integration(self, ctx: _TickContext) -> None:
        """CFRM P2: Вычисление локальной реальности + WorldSnapshotBuilder."""
        
        # S75-FIX: Delta Reconciliation — применяем накопленные decay-дельты
        # к all_npcs_raw ДО того, как аффективный пайплайн прочитает состояние.
        # Без этого Phase 9 читает устаревшие affective_load и threat_gradient,
        # перекалькулирует их из stale-данных и перезаписывает честный decay.
        # Результат: "вечный двигатель страха" (maid_lusya: 1.00/fearful навсегда).
        if ctx.delta_buffer and self._state_applicator:
            _aggregated = self._aggregate_deltas(ctx.delta_buffer)
            if _aggregated:
                self._state_applicator.apply_batch(
                    _aggregated, ctx.all_npcs_raw, ctx.campaign_id
                )
            ctx.delta_buffer.clear()
        
        # --- CFRM P2: 3-фазный редюсер и интерпретация давления ---
        # ADR-116: Диагностика входа в CFRM P2
        _cfrm_enter = bool(ctx.event_buffer and ctx.cluster_occupancy and ctx.all_npcs_raw)
        if not _cfrm_enter:
            logger.warning(f"[CFRM_P2_SKIP] evbuf={bool(ctx.event_buffer)} occ={bool(ctx.cluster_occupancy)} raw={bool(ctx.all_npcs_raw)}")
        if _cfrm_enter:
            if not self._spatial_service:
                logger.warning(f"[CFRM_P2_SKIP] spatial_service is None — affective pipeline disabled")
            cluster_graph = self._spatial_service.build_cluster_graph() if self._spatial_service else None
            if cluster_graph is None and self._spatial_service:
                logger.warning(f"[CFRM_P2_SKIP] build_cluster_graph() returned None")
            if cluster_graph:
                # Вычисление феноменологической реальности для каждого NPC
                phenomena_states = self._causal_solver.solve(
                    event_buffer=ctx.event_buffer,
                    cluster_graph=cluster_graph,
                    occupancy=ctx.cluster_occupancy,
                    all_npcs_raw=ctx.all_npcs_raw
                )
                
                # ADR-116: Диагностика phenomena_states
                _ph_count = len(phenomena_states) if phenomena_states else 0
                _ph_threats = {eid: round(getattr(ps, 'threat_level', 0), 2) for eid, ps in (phenomena_states or {}).items()} if _ph_count else {}
                logger.warning(f"[CFRM_P2] phenomena_count={_ph_count} threats={_ph_threats}")
                
                # Интерпретация: Превращение локальной истины в обновление восприятия (ADR-O)
                for entity_id, p_state in phenomena_states.items():
                    # S72 / §ENIGMA-S72: CFRM = сырой сенсор, не интерпретатор.
                    # Убраны фиксированные множители (×40, ×20, ×10) — движок больше не решает,
                    # насколько это страшно. Личность решает через drives_base (I2).
                    # Убран dominant_emotion_hint — движок не назначает эмоцию до личности.
                    # PhenomenologicalState.threat_level уже 0-1 — передаём как есть.
                    pressure = PsychologicalPressure(
                        fear=p_state.threat_level,
                        uncertainty=p_state.anomaly_score,
                        aggression_trigger=0.0  # S72: агрессия не выводится из угрозы автоматически
                    )
                    
                    # S72: PerceptionPayload получает сырые сигналы, не интерпретированные движком.
                    # Нормализация к 0-1 происходит на уровне PhenomenologicalState (источник),
                    # а не на уровне движка (посредник).
                    perception_payload = PerceptionPayload(
                        threat_gradient_delta=pressure.fear,
                        uncertainty_delta=pressure.uncertainty,
                        anomaly_score_delta=p_state.anomaly_score * 0.5,
                        dominant_emotion_hint=None  # S72: эмоция назначается Affective Pipeline, не движком
                    )
                    
                    # Perception delta — только если возмущение значимое
                    # (слабые дельты не мутируют PK, но всё ещё кормят аффективный pipeline ниже)
                    if p_state.threat_level >= 0.1 or p_state.visible_blood:
                        delta = StateDeltas(
                            npc_id=entity_id,
                            domain=DeltaDomain.PERCEPTION,
                            target="player",
                            payload=perception_payload,
                            source="cfrm_solver"
                        )
                        ctx.delta_buffer.append(delta)
                    
                    # ADR-O: Affective Pressure Pipeline (Perception -> Pressure -> Emotion)
                    # Вычисляем давление на основе проекции ядра (T-1 + delta T)
                    if npc_raw := next(
                        (
                            n
                            for n in ctx.all_npcs_raw
                            if n.get("npc_id") == entity_id
                        ),
                        None,
                    ):
                        from app.services.affective.affective_integrator import integrate_affective_pressure
                        from app.services.affective.emotion_transition import resolve_emotion_transition, THRESHOLD_ANXIOUS, THRESHOLD_FEARFUL, THRESHOLD_PANIC
                        from app.models.npc_state import PerceptualKernel
                        
                        # ADR-116: psyche для affective pipeline — fear из drives, willpower из psyche
                        # БЫЛО: npc_raw.get("psyche", {}).get("drives_base", {}) — всегда {} (drives_base нет внутри psyche)
                        _drives_raw = npc_raw.get("drives", {})
                        _psyche_raw = npc_raw.get("psyche", {})
                        psyche = {
                            "fear": _drives_raw.get("fear", 0.25),
                            "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
                        }
                        pk_dict = npc_raw.get("perceptual_kernel", {})
                        # ADR-116: Диагностика входа в affective pipeline
                        logger.debug(f"[AFFECTIVE_ENTRY] npc={entity_id} fear={psyche['fear']:.2f} will={psyche['willpower']:.2f}")
                        
                        # Легковесная проекция: старое ядро + текущая дельта (clamping 0.0-1.0)
                        projected_kernel = PerceptualKernel(
                            threat_gradient=min(1.0, max(0.0, pk_dict.get("threat_gradient", 0.0) + perception_payload.threat_gradient_delta)),
                            uncertainty=min(1.0, max(0.0, pk_dict.get("uncertainty", 0.0) + perception_payload.uncertainty_delta)),
                            anomaly_score=min(1.0, max(0.0, pk_dict.get("anomaly_score", 0.0) + perception_payload.anomaly_score_delta)),
                            compliance_bias=pk_dict.get("compliance_bias", 0.0),
                            aggression_inhibition=pk_dict.get("aggression_inhibition", 0.0),
                            initiative_suppression=pk_dict.get("initiative_suppression", 0.0)
                        )
                        
                        # ТЗ EMBODIED UI: Генерация ProjectionFrame (T+0)
                        from app.domain.perception import ProjectionFrame
                        if projected_kernel.threat_gradient > 0.05 or projected_kernel.initiative_suppression > 0.2:
                            signal = "avoid_gaze" if projected_kernel.threat_gradient > 0.5 else ("freeze" if projected_kernel.initiative_suppression > 0.7 else "calm")
                            _projection_frames.append(ProjectionFrame(
                                entity_id=entity_id,
                                threat=projected_kernel.threat_gradient,
                                suppression=projected_kernel.initiative_suppression,
                                salience=max(projected_kernel.threat_gradient, projected_kernel.initiative_suppression),
                                embodied_signal=signal,
                                expires_tick=ctx.tick_number + 3
                            ))

                        # ADR-049: Интеграция аффективного давления (Страх = интеграл угрозы по времени)
                        current_load = npc_raw.get("affective_load", 0.0)
                        new_load = integrate_affective_pressure(projected_kernel, current_load, psyche)
                        
                        # S74: Anti-DOUBLE TRUTH BOOTSTRAP УБИТ.
                        # Этот блок создавал "вечный двигатель страха": эмоция удерживала интеграл
                        # от затухания, а интеграл удерживал эмоцию. В S74/S75 поле первично,
                        # тег вторичен. Если нагрузка падает ниже порога, эмоция ДОЛЖНА
                        # коллапсировать, а не подтягивать физику под себя.
                        
                        # ADR-049: Фазовый переход эмоции при пересечении порога
                        emotion_payload = resolve_emotion_transition(new_load, current_load, psyche)
                        
                        # §ENIGMA-DUAL-CIRCUIT: Sustaining Loop УБИТ (S73).
                        # Эмоция не удерживается искусственно при высоком load.
                        # Если EmotionTransition не дал фазового перехода — эмоция = neutral.
                        # Это обнажает честную динамику для диагностики S73-R1.
                        
                        if emotion_payload:
                            # Передаем новое значение интеграла в Applicator для сохранения в NPCState
                            from dataclasses import replace
                            emotion_payload = replace(emotion_payload, affective_load=new_load)
                            
                            # ADR-116: Диагностика эмоционального пайплайна
                            logger.debug(f"[AFFECTIVE] npc={entity_id} load={new_load:.3f} prev={current_load:.3f} tag={emotion_payload.emotion_tag}")
                            
                            emotion_delta = StateDeltas(
                                npc_id=entity_id,
                                domain=DeltaDomain.EMOTION,
                                target="player",
                                payload=emotion_payload,
                                source="affective_pipeline"
                            )
                            ctx.delta_buffer.append(emotion_delta)

        # WorldSnapshotBuilder: собирает WorldSnapshotDTO из финального state
        # ADR-035: Трансляция стейта аватара в феноменологическую проекцию
        from app.services.presentation.avatar_presentation_assembler import assemble_avatar_presentation
        player_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
        _avatar_projection = assemble_avatar_presentation(player_dict) if player_dict else None

        # ТЗ EMBODIED UI PERCEPTION: Правильный пайплайн T+0
        from app.domain.perception import ProjectionFrame
        from app.services.perception.perceptual_attention_service import PerceptualAttentionService
        from app.services.perception.phenomenology_projection_service import PhenomenologyProjectionService
        from app.domain.snapshot import AvatarStateDTO
        
        # Безопасная инициализация фреймов (создаются в CFRM блоке выше)
        if '_projection_frames' not in locals():
            _projection_frames: List[ProjectionFrame] = []

        # The Fool v2: BehaviorManifestation (Фаза 8.5) + Phenomenology Projection (Фаза 9)
        from app.services.perception.behavior_manifestation_service import BehaviorManifestationService
        from app.services.perception.phenomenology_projection_service import PhenomenologyProjectionService
        from app.domain.snapshot import AvatarStateDTO, PlayerPerceptionDTO
        if not hasattr(self, '_manifest_svc'):
            self._manifest_svc = BehaviorManifestationService()
            self._project_svc = PhenomenologyProjectionService()
            self._attention_svc = PerceptualAttentionService()
            
        # Шаг 1: Моторные следы (Тело -> Наблюдение)
        _traces = self._manifest_svc.produce_traces(ctx.scene_state, all_npcs_raw=ctx.all_npcs_raw)
        
        # Шаг 2: Трансляция следов в смыслы (без телепатии) + Диафрагма внимания
        _player_perception = self._project_svc.project(_traces, ctx.scene_state, tick=ctx.tick_number)
        
        logger.debug(f"[PERCEPTION_PIPELINE] T+0 SUCCESS: Traces={len(_traces)} | Cues={len(_player_perception.active_perceptions)}")

        builder = self._get_snapshot_builder()
        ctx.world_snapshot = builder.build(
            scene_state=ctx.scene_state,
            tick=ctx.tick_number,
            avatar_state=_avatar_projection,
            all_npcs_raw=ctx.all_npcs_raw, # ADR-037: Передаем сырые данные для Ambient Phenomenology
            player_perception=_player_perception, # ТЗ EMBODIED UI: Передаем наблюдения игрока
        )

    def _run_affective_pipeline(self, ctx: _TickContext) -> None:
        """ADR-049: Аффективный аккумулятор — накопление давления и фазовый переход эмоций.
        
        Вызывается из ОБЕИХ путей (idle + player turn).
        Без этого affective_load не растёт при player turn → emotion=NEUTRAL → _emotion_modifier()=0.0.
        """
        if not ctx.all_npcs_raw:
            logger.debug("[AFFECTIVE_PLAYER] SKIP: all_npcs_raw is empty")
            return

        from app.services.affective.affective_integrator import integrate_affective_pressure
        from app.services.affective.emotion_transition import resolve_emotion_transition, THRESHOLD_ANXIOUS, THRESHOLD_FEARFUL, THRESHOLD_PANIC
        from app.models.npc_state import PerceptualKernel
        from app.models.delta_payloads import EmotionPayload, PerceptionPayload
        from app.models.state_delta import StateDeltas, DeltaDomain
        from dataclasses import replace as dataclass_replace

        logger.debug(f"[AFFECTIVE_PLAYER] ENTER: npc_count={len(ctx.all_npcs_raw)}")
        for npc_raw in ctx.all_npcs_raw:
            entity_id = npc_raw.get("npc_id") or npc_raw.get("id")
            if not entity_id or entity_id == "player":
                continue  # Игрок не проходит аффективный pipeline

            pk_dict = npc_raw.get("perceptual_kernel", {})
            _drives_raw = npc_raw.get("drives", {})
            _psyche_raw = npc_raw.get("psyche", {})

            # S72: Drives Base как Линза Реальности.
            # Веса восприятия определяются личностью, не хардкодом движка.
            # fear → вес угрозы, control → вес неопределённости, significance → вес аномалии.
            _drive_fear = _drives_raw.get("fear", 0.25)
            _drive_control = _drives_raw.get("control", 0.25)
            _drive_significance = _drives_raw.get("significance", 0.25)

            psyche = {
                "fear": _drive_fear,
                "control": _drive_control,
                "significance": _drive_significance,
                "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
            }

            # Проекция ядра: текущее состояние (без delta — delta уже применена в idle tick)
            projected_kernel = PerceptualKernel(
                threat_gradient=pk_dict.get("threat_gradient", 0.0),
                uncertainty=pk_dict.get("uncertainty", 0.0),
                anomaly_score=pk_dict.get("anomaly_score", 0.0),
                compliance_bias=pk_dict.get("compliance_bias", 0.0),
                aggression_inhibition=pk_dict.get("aggression_inhibition", 0.0),
                initiative_suppression=pk_dict.get("initiative_suppression", 0.0),
            )

            _body = npc_raw.get("body_state", {})
            _pain_f = float(_body.get("pain", 0.0)) / 100.0 * 0.3 if _body else 0.0
            _shock_f = float(_body.get("shock_impulse", 0.0)) * 0.4 if _body else 0.0

            # S73-DIAG: Проверка очага аффекта. Видит ли пайплайн боль от удара?
            if entity_id in ("thief_shadow", "guard_borko"):
                print(f"[AFF_SOURCE] npc={entity_id} pain_raw={_body.get('pain', 0.0)} shock_raw={_body.get('shock_impulse', 0.0)} prev_aff={npc_raw.get('affective_load', 0.0)} emo={npc_raw.get('emotion', '?')}")

            # S72-FIX: Устранение двойного счёта аффективного аккумулятора.
            # Баг: current_load вычислялся из PK (мгновенная проекция), 
            # а incoming внутри интегратора добавлял тот же сигнал.
            # Результат: new_load = 2 × (threat × fear) - recovery → квантизация.
            # Фикс: current_load = предыдущий интеграл из сохранённого состояния.
            _prev_affective = npc_raw.get("affective_load", None)
            if _prev_affective is not None and float(_prev_affective) > 0.0:
                current_load = float(_prev_affective)
            else:
                # Fallback: мгновенная проекция (для первого тика или если ADR-122 убил сериализацию)
                current_load = min(1.0,
                    projected_kernel.threat_gradient * _drive_fear +
                    projected_kernel.uncertainty * _drive_control +
                    projected_kernel.anomaly_score * _drive_significance +
                    _pain_f + _shock_f
                )

            # Физиология — мгновенный сигнал, передаётся через psyche
            psyche = {
                "fear": _drive_fear,
                "control": _drive_control,
                "significance": _drive_significance,
                "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
                "pain": _pain_f,
                "shock": _shock_f,
            }

            new_load = integrate_affective_pressure(projected_kernel, current_load, psyche)

            # S72-FIX: Эпистемический потолок. affective_load не может превышать 1.0.
            # Без этого аккумулятор переполняется при высоком threat + высокий fear_drive.
            # Runtime-доказательство: maid_lusya load=1.332 при threat=1.0, fear=0.45.
            new_load = min(1.0, new_load)

            # §ENIGMA-DUAL-CIRCUIT: AFFECTIVE_BOOT УБИТ.
            # Бутстрап создавал "вечный двигатель страха": рефлекс ставил эмоцию,
            # бутстрап подтягивал интеграл до порога эмоции, интеграл держал эмоцию,
            # бутстрап снова подтягивал. Интеграл не мог затухнуть.
            # Фикс: Разделение контуров. Интеграл (load) — честная память.
            # Рефлекс (emotion_tag) — быстрая реакция. DecisionHub использует оба
            # через _emotion_modifier. Искусственная синхронизация НЕ НУЖНА.
            pass  # Потолок и для bootstrap

            emotion_payload = resolve_emotion_transition(new_load, current_load, psyche)

            # S73-DIAG: Вычислен ли new_load и почему он теряется?
            if entity_id in ("thief_shadow", "guard_borko"):
                print(f"[AFF_RESULT] npc={entity_id} current={current_load:.3f} new={new_load:.3f} has_transition={emotion_payload is not None}")

            # §ENIGMA-DUAL-CIRCUIT (S74-FIX): Разделение памяти и интерпретации.
            # Интеграл ОБЯЗАН сохраняться при каждом изменении, даже если эмоция
            # не пересекла порог (Phase-Gate Bug). Без этого нагрузка навечно зависает в 0.0.
            if emotion_payload is None and abs(new_load - current_load) > 0.001:
                _current_tag = npc_raw.get("emotion", "neutral") or "neutral"
                emotion_payload = EmotionPayload(
                    stress_delta=0.0,
                    emotion_delta=0.0,
                    emotion_tag=_current_tag,
                    affective_load=new_load,
                )

            if emotion_payload:
                emotion_payload = dataclass_replace(emotion_payload, affective_load=new_load)
                logger.debug(f"[AFFECTIVE_PLAYER] npc={entity_id} load={new_load:.3f} prev={current_load:.3f} tag={emotion_payload.emotion_tag}")
                ctx.delta_buffer.append(StateDeltas(
                    npc_id=entity_id,
                    domain=DeltaDomain.EMOTION,
                    target="player",
                    payload=emotion_payload,
                    source="affective_pipeline_player"
                ))

            # S73-L0: Epistemic Trace (Log-only instrumentation).
            # Фиксируем субъективную проекцию реальности NPC для анализа RSI (Reality Split Index).
            # Не влияет на симуляцию. Позволяет CDS измерять расхождение интерпретаций.
            # S73-DIAG: Отслеживание источника эмоции для диагностики конкуренции контуров
            _e_tag = emotion_payload.emotion_tag if emotion_payload else (npc_raw.get("emotion", "neutral") or "neutral")
            _e_src = "TRANSITION" if emotion_payload else "NONE"
            _prev_src = "saved" if (_prev_affective is not None and float(_prev_affective) > 0.0) else "pk"
            _incoming_val = (
                projected_kernel.threat_gradient * _drive_fear +
                projected_kernel.uncertainty * _drive_control +
                projected_kernel.anomaly_score * _drive_significance +
                _pain_f + _shock_f
            )
            logger.info(
                f"[EPISTEMIC_TRACE] npc={entity_id} "
                f"threat={projected_kernel.threat_gradient:.3f} "
                f"unc={projected_kernel.uncertainty:.3f} "
                f"anom={projected_kernel.anomaly_score:.3f} "
                f"drives=[f={_drive_fear:.2f},c={_drive_control:.2f},s={_drive_significance:.2f}] "
                f"pain={_pain_f:.3f} shock={_shock_f:.3f} "
                f"prev={current_load:.3f}<{_prev_src}> inc={_incoming_val:.3f} "
                f"load={new_load:.3f} emotion={_e_tag} src={_e_src}"
            )

    def _phase_10_persistence(self, ctx: _TickContext) -> None:
        """Atomic commit: SQLite (runtime truth) + YAML (для человека).

        Единственная точка сохранения за тик (Устав §4.2.1).
        Делегирует в SceneStateManager.commit(), который вызывает PersistencePort.atomic_commit().
        """
        # DRF Observer: Схлопываем поле причинных напряжений ПЕРЕД коммитом
        print(f"[DRF_DRAIN_BUS] bus_id={id(ctx.drf_bus)} stream_size={len(ctx.drf_bus.stream)}")
        _claims = ctx.drf_bus.drain()
        if _claims:
            from collections import defaultdict
            _npc_claims = defaultdict(list)
            for c in _claims:
                _npc_claims[c.get("target_npc", c.get("npc_id", "unknown"))].append(f"{c.get('pressure_type', '?')}:{c.get('vector', '?')}({c.get('energy', 0.0):.1f})")
            for npc, claims_str in _npc_claims.items():
                print(f"[DRF_FIELD] npc={npc} pressures={claims_str}")
        else:
            print("[DRF_FIELD] claim_field is EMPTY this tick")

        if self._scene_manager is None:
            logger.warning("[TICK_ORCH] Фаза 10: нет scene_manager — коммит пропущен")
            return

        # Flush: применяем все накопленные idle-дельты через единый мутатор
        if ctx.delta_buffer:
            _aggregated = self._aggregate_deltas(ctx.delta_buffer)
            if _aggregated and self._state_applicator:
                self._state_applicator.apply_batch(
                    _aggregated, ctx.all_npcs_raw, ctx.campaign_id
                )
                ctx.delta_buffer.clear()

        # ADR-117: Синхронизация LifeEngine кэша с мутированными данными
        if ctx.all_npcs_raw:
            engine = self._get_life_engine()
            engine.update_cache(ctx.campaign_id, ctx.all_npcs_raw)

        # Собираем события тика для аудита
        ctx.tick_events = ctx.decision_events  # TODO: расширить spatial + handler events

        saved = self._scene_manager.commit(
            campaign_id=ctx.campaign_id,
            scene_state=ctx.scene_state,
            npc_dicts=ctx.npc_states,
        )

        if saved > 0:
            logger.debug(f"[TICK_ORCH] Фаза 10: commit OK ({saved} подсистем)")
        else:
            logger.warning("[TICK_ORCH] Фаза 10: commit вернул 0 — данные не сохранены")

    # ── ДОЛГ 4.2: Causal Scoring Overlay ─────────────────────────────
    # Аддитивный скоринг: DRF давление влияет на приоритет интентов как поле сил.
    # Viability veto (SURVIVAL ⟂ ROUTINE) — НЕ ЗДЕСЬ. Это конфликт мотиваций,
    # он должен решаться ДО генерации интента, в DecisionHub (ДОЛГ 4.3).
    # MovementEngine — актюатор, а не арбитр жизнеспособности.

    def _apply_drf_scoring_overlay(self, intents: list, ctx: _TickContext) -> None:
        """Аддитивный скоринг: final_priority = base + Σ(claim.energy × weight × alignment).

        Единый overlay для idle и player путей.
        DRF — поле сил, не ярлык. Давление модулирует приоритет, не заменяет его.
        """
        _claims = ctx.drf_bus.stream  # peek без drain (drain в phase 10)
        if not _claims:
            return

        for _intent in intents:
            if not hasattr(_intent, 'npc_id'):
                continue
            _npc_id = _intent.npc_id
            _npc_claims = [c for c in _claims
                           if c.get("target_npc") == _npc_id or c.get("npc_id") == _npc_id]
            if not _npc_claims:
                continue

            _reason = getattr(_intent, 'reason', '')

            # Аддитивный скоринг: base + Σ(energy × weight × alignment)
            _drf_bonus = 0.0
            for c in _npc_claims:
                _ptype = c.get("pressure_type", "ROUTINE")
                _weight = _DRF_PRESSURE_WEIGHTS.get(_ptype, 0.02)
                _energy = c.get("energy", 0.5)
                _vector = str(c.get("vector", ""))
                _aligned = _vector in _reason
                _alignment_mult = _DRF_ALIGNED if _aligned else _DRF_MISALIGNED
                _drf_bonus += _energy * _weight * _alignment_mult

            _old_priority = _intent.priority
            _intent.priority = min(1.0, _intent.priority + _drf_bonus)
            if _drf_bonus > 0.01:
                print(f"[DRF_VOTE] npc={_npc_id} base={_old_priority:.2f} bonus={_drf_bonus:.3f} final={_intent.priority:.2f}")

    # ── Хелперы ───────────────────────────────────────────────────────

    @staticmethod
    def _get_npc_runtime_path(campaign_id: str) -> Path:
        """Путь к runtime-данным NPC для кампании (saves_dir/campaign_id/npc_runtime.json)."""
        from app.core.config import settings
        return Path(settings.saves_dir) / campaign_id / "npc_runtime.json"
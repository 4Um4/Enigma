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
from app.models.delta_payloads import EmotionPayload
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
        _has_svc = ctx.npc_services and hasattr(ctx.npc_services, 'spatial_service') and ctx.npc_services.spatial_service
        print(f"[DIAG][SPATIAL_RESOLVE] npc_services={ctx.npc_services is not None}, has_svc={_has_svc}")
        if _has_svc:
            self._spatial_service = ctx.npc_services.spatial_service
            return self._spatial_service
            
        # 2. Аварийная сборка из scene_state (если GameLoop не пробросил сервис)
        _loc_id = ctx.scene_state.get("location_id", "")
        print(f"[DIAG][SPATIAL_RESOLVE] loc_id='{_loc_id}', campaign_id='{ctx.campaign_id}'")
        if _loc_id:
            try:
                logger.warning(f"[SPATIAL_AUTHORITY] ADR-048 VIOLATION: SpatialService собран вручную для {_loc_id}. GameLoop не пробросил сервис!")
                self._spatial_service = SpatialService.build_for_location(
                    campaign_id=ctx.campaign_id,
                    location_id=_loc_id,
                    scene_state=ctx.scene_state,
                )
                print(f"[DIAG][SPATIAL_RESOLVE] Emergency build result: {self._spatial_service is not None}")
                return self._spatial_service
            except Exception as e:
                print(f"[DIAG][SPATIAL_RESOLVE] CRASH during emergency build: {type(e).__name__}: {e}")
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

        ctx = _TickContext(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=tick_number,
            dm_ctx=dm_ctx,
            npc_services=npc_services,
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
                if event.type in ("PLAYER_ATTACKS", "NPC_ATTACKED"):
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
        npc_buffer = run_npc_pipeline(npc_input, npc_buffer, ctx.npc_services)

        # CommunicationIntents из pipeline → Фаза 6 (Устав §5.1)
        if npc_buffer.communication_intents:
            ctx.communication_intents = npc_buffer.communication_intents

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
        ctx = _TickContext(
            campaign_id=shared_context.scene_state.get("location_id", ""),
            scene_state=shared_context.scene_state or {},
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
            if ctx.npc_states:
                ctx.all_npcs_raw = ctx.npc_states
            
            # ADR-064 Fix: Fallback на DMContextDTO, так как LifeEngine возвращает []
            # при холодном кэше (ход игрока до idle-тика). Каузальная труба Воли не должна обрываться.
            if not ctx.all_npcs_raw and ctx.dm_ctx and ctx.dm_ctx.all_npcs_raw:
                ctx.all_npcs_raw = ctx.dm_ctx.all_npcs_raw
                logger.info("[CAUSALITY] all_npcs_raw загружен из dm_ctx (LifeEngine кэш пуст).")

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
        print(f"[DIAG] player_result={ctx.player_result is not None} movement_intents={len(ctx.player_result.movement_intents) if ctx.player_result and ctx.player_result.movement_intents else 0}")
        if ctx.player_result and ctx.player_result.movement_intents:
            from app.services.spatial.movement_engine import MovementEngine
            _spatial_svc = self._resolve_spatial_service(ctx)
            print(f"[DIAG] spatial_svc={_spatial_svc is not None} scene_manager={self._scene_manager is not None}")
            if _spatial_svc:
                me = MovementEngine()
                me.set_spatial_service(_spatial_svc)
                _tick = self.get_current_tick(ctx.campaign_id)
                changes = me.process_intents(
                    ctx.player_result.movement_intents, _tick,
                    ctx.scene_state.get("npc_positions", {}),
                    campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
                )
                print(f"[DIAG] changes={len(changes)} scene_manager={self._scene_manager is not None}")
                if changes and self._scene_manager:
                    self._scene_manager.apply_changes(ctx.campaign_id, changes, ctx.scene_state)
                    logger.warning(f"[PLAYER_TURN] Applied {len(changes)} reactive movement changes")
                elif changes and not self._scene_manager:
                    print(f"[DIAG] CRITICAL: scene_manager is None! Changes lost!")
            else:
                logger.error("[SPATIAL_AUTHORITY] SpatialService отсутствует, реактивное движение заблокировано.")

        # Фаза 0.5: время не останавливается (decay = всегда)
        self._phase_0_5_idle_services(ctx)
        # Фазы 8→9→10 — единая последовательность (Устав §3)
        self._phase_8_player_handlers(ctx)
        self._phase_9_player_integration(ctx)
        self._phase_10_player_persistence(ctx)

        # Возвращаем обновлённый результат (с finalize_result)
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
        """Фаза 0.75: Authoritative Traversal Lifecycle.
        Проверяем ожидаемое время прибытия. Если время пришло — NPC каузально прибыл.
        Визуальной интерполяцией владеет фронтенд (Kinematic Illusion).
        """
        traversals = ctx.scene_state.get("active_traversals", {})
        if not traversals:
            return
            
        current_time = ctx.scene_state.get("game_time_seconds", 0)
        completed_ids = []
        
        for npc_id, trav in list(traversals.items()):
            if trav.get("status") != "MOVING":
                continue
            
            expected_arrival = trav.get("expected_arrival_time", float('inf'))
            
            # Если текущее время превысило ожидаемое время прибытия — Транзит завершен
            if current_time >= expected_arrival:
                completed_ids.append(npc_id)
                # Каузальный узел уже обновлен в SceneStateManager (Вариант А).
                # В будущем здесь: rebuild ClusterOccupancy, генерация ArrivalDisturbance, смена владельца кластера.
                
        for npc_id in completed_ids:
            if npc_id in traversals:
                del traversals[npc_id]
                logger.debug(f"[TRAVERSAL] Lifecycle complete: npc={npc_id} arrived causally at tick time {current_time}.")

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
        _sem_target = getattr(intent, 'parameters', None) and intent.parameters.target_id or getattr(intent, 'target', 'UNKNOWN')
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
        """
        if ctx.shared_context is None:
            return

        _finalize = self._phase_finalize(
            ctx, ctx.actions, ctx.shared_context, ctx.campaign_id,
            ctx.rules_result, ctx.r3_direct_mode,
        )

        # Сохраняем для возврата из execute()
        if ctx.player_result is not None:
            ctx.player_result.finalize_result = _finalize

    def _phase_10_player_persistence(self, ctx: _TickContext) -> None:
        """Player turn: atomic commit (Устав §10 — Persistence).

        Единственная точка коммита за тик (Устав §4.2.1).
        """
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
                logger.debug(f"[AFFECT_DECAY] Failed for {npc_dict.get('npc_id')}: {e}")

        if not self._idle_handlers:
            return

        current_tick = self._get_life_engine().get_current_tick(ctx.campaign_id)
        snapshots = self._build_npc_snapshots(ctx.all_npcs_raw)

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
                injuries_by_zone=injuries_by_zone,
                base_abilities=_base_abilities,
                modifiers=_modifiers,
                statuses=_statuses,
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
        return list(groups.values()) + physics_deltas

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
        events = handler.drain_events()
        if not events:
            return None

        _npc_contexts = (
            ctx.player_result.npc_contexts
            if ctx.player_result is not None
            else []
        )
        phase8_ctx = Phase8Context(
            all_npcs_raw=ctx.all_npcs_raw,
            all_npc_contexts=_npc_contexts,
            shared_context=ctx.shared_context,
            campaign_id=ctx.campaign_id,
            tick_ctx=ctx,
            physical_deltas_materialized=physical_deltas_materialized,
        )

        try:
            result = handler.handle(events, phase8_ctx)
        except Exception as e:
            # Safeguard: потеря событий в одном тике допустима, крах — нет
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
        
        # --- CFRM P2: 3-фазный редюсер и интерпретация давления ---
        if ctx.event_buffer and ctx.cluster_occupancy and ctx.all_npcs_raw:
            cluster_graph = self._spatial_service.build_cluster_graph() if self._spatial_service else None
            if cluster_graph:
                # Вычисление феноменологической реальности для каждого NPC
                phenomena_states = self._causal_solver.solve(
                    event_buffer=ctx.event_buffer,
                    cluster_graph=cluster_graph,
                    occupancy=ctx.cluster_occupancy,
                    all_npcs_raw=ctx.all_npcs_raw
                )
                
                # Интерпретация: Превращение локальной истины в обновление восприятия (ADR-O)
                for entity_id, p_state in phenomena_states.items():
                    if p_state.threat_level < 0.1 and not p_state.visible_blood:
                        continue # Слишком слабое возмущение для мутации
                    
                    # Генерация давления
                    pressure = PsychologicalPressure(
                        fear=p_state.threat_level * 40.0,
                        uncertainty=p_state.anomaly_score * 20.0,
                        aggression_trigger=0.0 if p_state.threat_level < 0.5 else p_state.threat_level * 10.0
                    )
                    
                    # ADR-O: Реальность обновляет восприятие, а не эмоции напрямую.
                    # PerceptualKernel накапливает градиент угрозы.
                    perception_payload = PerceptionPayload(
                        threat_gradient_delta=pressure.fear / 100.0,  # Нормализация к 0.0-1.0
                        uncertainty_delta=pressure.uncertainty / 100.0,
                        anomaly_score_delta=p_state.anomaly_score * 0.5,
                        dominant_emotion_hint="panic" if pressure.fear > 30 else "fear"
                    )
                        
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
                        from app.services.affective.emotion_transition import resolve_emotion_transition
                        from app.models.npc_state import PerceptualKernel
                        
                        psyche = npc_raw.get("psyche", {}).get("drives_base", {})
                        pk_dict = npc_raw.get("perceptual_kernel", {})
                        
                        # Легковесная проекция: старое ядро + текущая дельта (clamping 0.0-1.0)
                        projected_kernel = PerceptualKernel(
                            threat_gradient=min(1.0, max(0.0, pk_dict.get("threat_gradient", 0.0) + perception_payload.threat_gradient_delta)),
                            uncertainty=min(1.0, max(0.0, pk_dict.get("uncertainty", 0.0) + perception_payload.uncertainty_delta)),
                            anomaly_score=min(1.0, max(0.0, pk_dict.get("anomaly_score", 0.0) + perception_payload.anomaly_score_delta)),
                            compliance_bias=pk_dict.get("compliance_bias", 0.0),
                            aggression_inhibition=pk_dict.get("aggression_inhibition", 0.0),
                            initiative_suppression=pk_dict.get("initiative_suppression", 0.0)
                        )
                        
                        # ADR-049: Интеграция аффективного давления (Страх = интеграл угрозы по времени)
                        current_load = npc_raw.get("affective_load", 0.0)
                        new_load = integrate_affective_pressure(projected_kernel, current_load, psyche)
                        
                        # ADR-049: Фазовый переход эмоции при пересечении порога
                        if emotion_payload := resolve_emotion_transition(new_load, current_load, psyche):
                            # Передаем новое значение интеграла в Applicator для сохранения в NPCState
                            from dataclasses import replace
                            emotion_payload = replace(emotion_payload, affective_load=new_load)
                            
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

        # ТЗ EMBODIED UI PERCEPTION: Симметричная онтология восприятия (Слои 1-5)
        from app.services.perception.phenomenology_projection_service import PhenomenologyProjectionService
        from app.services.perception.perceptual_attention_service import PerceptualAttentionService
        from app.domain.snapshot import AvatarStateDTO
        
        _projector = PhenomenologyProjectionService()
        _attention = PerceptualAttentionService()
        _location_id = ctx.scene_state.get("location_id", "")
        
        # Шаг 1: Генерация смыслов (Сырые стейты -> PerceptionEvent)
        _perception_events = _projector.project(ctx.all_npcs_raw, ctx.tick_number, _location_id)
        # Шаг 2: Диафрагма внимания (PerceptionEvent + AvatarState -> PlayerPerceptionDTO)
        # Защита от None: если аватар не найден, используем дефолтный стейт (без искажений)
        _avatar_for_perception = _avatar_projection if _avatar_projection else AvatarStateDTO()
        _player_perception = _attention.build_perception(_perception_events, _avatar_for_perception, ctx.tick_number)
        
        # PIPELINE TRACE: Верификация генерации смыслов
        logger.info(f"[PERCEPTION_TRACE] Events={len(_perception_events)} | Active={len(_player_perception.active_perceptions)} | Cues={len(_player_perception.peripheral_cues)}")
        
        builder = self._get_snapshot_builder()
        ctx.world_snapshot = builder.build(
            scene_state=ctx.scene_state,
            tick=ctx.tick_number,
            avatar_state=_avatar_projection,
            all_npcs_raw=ctx.all_npcs_raw, # ADR-037: Передаем сырые данные для Ambient Phenomenology
            player_perception=_player_perception, # ТЗ EMBODIED UI: Передаем наблюдения игрока
        )

    def _phase_10_persistence(self, ctx: _TickContext) -> None:
        """Atomic commit: SQLite (runtime truth) + YAML (для человека).

        Единственная точка сохранения за тик (Устав §4.2.1).
        Делегирует в SceneStateManager.commit(), который вызывает PersistencePort.atomic_commit().
        """
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

    # ── Хелперы ───────────────────────────────────────────────────────

    @staticmethod
    def _get_npc_runtime_path(campaign_id: str) -> Path:
        """Путь к runtime-данным NPC для кампании (saves_dir/campaign_id/npc_runtime.json)."""
        from app.core.config import settings
        return Path(settings.saves_dir) / campaign_id / "npc_runtime.json"
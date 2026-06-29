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
import sys
logger = logging.getLogger(__name__)
import time
from dataclasses import dataclass, field, replace
from app.contracts.interventions import InterventionEvent
from typing import Any, Callable, Dict, List, Optional, Union

from app.services.npc.kernel_rng import KernelRNG

from pathlib import Path
from enum import Enum

from app.domain.tick import TickResultDTO
from app.domain.intent import IntentDTO
from app.models.state_delta import DeltaDomain, StateDeltas
from app.models.cfrm import EventBuffer, ClusterOccupancy

from app.services.scene_change import SceneChange, ChangeType
from app.services.drf_bus import DRFBus, DRFExecutionContext, _DRF_PRESSURE_WEIGHTS, _DRF_ALIGNED, _DRF_MISALIGNED
from app.services.dto import ReductionPolicy, DELTA_POLICY_REGISTRY, SemanticFrame, _TickContext, DMContextDTO, TickPlayerResultDTO

# ReductionPolicy, DELTA_POLICY_REGISTRY, _TickContext, DMContextDTO, TickPlayerResultDTO, SemanticFrame вынесены в app.services.dto (Декомпозиция Шаг 2)

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
from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder
# ADR-O-201 ФАЗА 1: Dual Rail Execution
from app.models.world_snapshot import WorldSnapshot, build_snapshot
from app.services.event_compiler import EventCompiler
from app.services.equivalence_validator import EquivalenceValidator

logger = logging.getLogger(__name__)


class TickOrchestrator:
    """
    Оркестратор тика мира.
    
    НЕ содержит бизнес-логику — только порядок вызовов фаз.
    Каждая фаза — отдельный сервис из services/.
    """

    def __init__(self, scene_manager=None, memory_manager=None, event_bus=None, store=None) -> None:
        self._scene_manager = scene_manager
        # DI: внешние сервисы (GameLoop передаёт свои инстансы)
        self._memory_manager = memory_manager
        self._event_bus = event_bus
        # Ленивая инициализация для оставшихся
        self._life_engine = None
        self._snapshot_builder = None
        self._spatial_service = None  # ADR-029: Инъекция для CFRM ClusterGraph
        # ADR-O-310: Action Windup Registry. Живёт на уровне Orchestrator, переживает тики.
        # Ключ: (campaign_id, actor_id). Значение: List[ActionWindup].
        # Изоляция по campaign_id предотвращает коллизии в мульти-кампаниях.
        self._windup_registry: Dict[Tuple[str, str], List[Any]] = {}
        
        # DEBT-310.1: Hold & Release Gate storage. Хранит отложенные CommunicationIntent.
        # Ключ: intent_id. Значение: CommunicationIntent.
        self._pending_intents: Dict[str, Any] = {}
        # S91: Персистентные стигмергические слои (DynamicAffordanceField + Provider)
        from app.services.spatial.world_topology_provider import WorldTopologyProvider, DynamicAffordanceField
        self._dynamic_field = DynamicAffordanceField()
        self._topology_provider = WorldTopologyProvider(dynamic_field=self._dynamic_field)
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
        
        # ADR-O-208: Органы времени и проекции идентичности.
        # L1Chronicle (хроника деформаций) и DriveResolver (эфемерная проекция)
        # являются внутренней физикой Оркестратора, не требуют внешнего DI.
        # ADR-O-208: Органы времени и проекции идентичности.
        # L1Chronicle (хроника деформаций) и DriveResolver (эфемерная проекция)
        # ADR-L1-PERSIST: L1Chronicle принимает store для персистентности в SQLite.
        from app.services.npc.l1_chronicle import L1Chronicle
        from app.services.npc.drive_resolver import DriveResolver
        from app.services.npc.pattern_detector import PatternDetector
        from app.services.npc.belief_crystallization_engine import BeliefCrystallizationEngine
        from app.services.npc.crystallized_belief_store import CrystallizedBeliefStore
        self.l1_chronicle = L1Chronicle(store=store)
        # S-93: PatternDetector получает ссылку на L1Chronicle для запроса сырых событий
        self.pattern_detector = PatternDetector(chronicle=self.l1_chronicle)
        self.drive_resolver = DriveResolver()
        # L1.5 / L2.5: Статистика и Кристаллизация убеждений (ADR-O-305)
        self.belief_engine = BeliefCrystallizationEngine()
        self.crystallized_belief_store = CrystallizedBeliefStore()
        # ReputationEngine для reputation decay
        self._reputation_engine: Any = None
        # DRF: Instance-level causal bus — переживает execute() / execute_player_finalize()
        self._drf_bus: DRFBus = DRFBus()
        # ADR-O-201 ФАЗА 1: Dual Rail Execution (Shadow Observer)
        self._event_compiler: EventCompiler = EventCompiler()
        self._equivalence_validator: EquivalenceValidator = EquivalenceValidator()
        self._drift_stats: Dict[str, int] = {"total_comparisons": 0}

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
            self._topology_provider.set_spatial_service(self._spatial_service)
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
                from app.services.spatial.spatial_factory import SpatialFactory
                self._spatial_service = SpatialFactory.build_for_campaign(
                    campaign_id=ctx.campaign_id,
                    location_id=_loc_id,
                    scene_state=ctx.scene_state,
                )
                self._topology_provider.set_spatial_service(self._spatial_service)
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
        start_time = time.perf_counter()  # §15.2: Telemetry (profiling)
            
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
                
        elapsed_ms = (time.perf_counter() - start_time) * 1000  # §15.2: Telemetry (profiling)
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
        interventions: Optional[List["InterventionEvent"]] = None,
        npc_services: Optional[Any] = None,
        spatial_service: Optional[Any] = None, # ADR-048: Инъекция от GameLoop
        dm_ctx: Optional["DMContextDTO"] = None, # Backward compat (мостируется в interventions)
    ) -> Union[TickResultDTO, TickPlayerResultDTO]:
        """Единая точка входа для тика мира (TZ-08 v0.2).

        Ядро не знает 'player'. Если interventions пуст — idle tick.
        Если передан legacy dm_ctx — он мостируется в InterventionEvent.
        """
        if interventions is None:
            interventions = []
        
        # Мостируем legacy dm_ctx в новый event-driven формат
        if dm_ctx is not None and not interventions:
            interventions = [InterventionEvent(
                source="player",
                payload={"dm_ctx": dm_ctx},
                tick=tick_number,
            )]
        # ADR-L1-PERSIST: Привязка L1Chronicle к текущей кампании для ленивой загрузки
        self.l1_chronicle.bind_campaign(campaign_id)
        if scene_state is None:
            return TickResultDTO(status="no_scene")

        # S83.1: Tick = Pure Function Evaluation. Freeze input snapshot.
        # Все фазы работают от frozen copy. Оригинал не мутируется внутри тика.
        import copy
        input_snapshot = copy.deepcopy(scene_state)

        # ADR-048: Приоритет инъекции от GameLoop. Если нет — аварийная сборка.
        if spatial_service:
            self._spatial_service = spatial_service

        # DRF: Сброс шины на начало тика (один bus на весь lifecycle: execute + finalize)
        self._drf_bus.stream.clear()
        logger.info(f"[DRF_BUS_RESET] bus_id={id(self._drf_bus)} tick={tick_number}")
        # KERNEL-ISOLATION: factory для per-NPC deterministic RNG.
        # Каждый NPC получает свой RNG, seeded by (tick, npc_id).
        _tick_for_rng = tick_number
        _rng_factory = lambda npc_id: KernelRNG(tick=_tick_for_rng, npc_id=npc_id)

        ctx = _TickContext(
            campaign_id=campaign_id,
            scene_state=input_snapshot,
            tick_number=tick_number,
            interventions=interventions,
            npc_services=npc_services,
            drf_bus=self._drf_bus,  # Instance-level bus — не создаём новый!
            rng_factory=_rng_factory,
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
            self._run_core_phases(ctx)
        except Exception as e:
            logger.error(f"[TICK_CRASH] campaign={campaign_id} tick={tick_number} error={e}")
            logger.error(f"[TICK_ORCH] Ошибка в тике {campaign_id}: {e}", exc_info=True)
            return TickResultDTO(status="error", error=str(e))
        finally:
            # CFRM P2: Гарантированно отключаем мост деобъективации в конце тика
            event_bus.detach_cfrm_bridge()

        # S83.1: TickOrchestrator = единственный владелец результата тика.
        # input_snapshot (frozen input) прошёл через фазы → final_snapshot (output тика).
        # commit_tick_result обновляет persistence target через deepcopy (без алиасинга).
        # unlock_tick() сохранит обновлённый _tick_scene на диск.
        final_snapshot = input_snapshot  # после мутаций фазами — это уже output, не input
        logger.debug(f"[TICK_OK] campaign={campaign_id} tick={tick_number} preparing commit_tick_result")
        if self._scene_manager is not None:
            self._scene_manager.commit_tick_result(campaign_id, final_snapshot)

        # TZ-08 v0.2: Ядро всегда возвращает единый TickResultDTO. Никаких ветвлений по источнику.
        return TickResultDTO(
            status="ok",
            changes_count=len(ctx.scene_changes),
            significant_events=ctx.decision_events,
            world_snapshot=ctx.world_snapshot,
            npc_contexts=ctx.npc_contexts,
        )

    # ── Player Turn (тонкая обёртка) ────────────────────────────────

    def tick_player_turn(
        self,
        campaign_id: str,
        location: str,
        scene_state: dict,
        dm_ctx: DMContextDTO,
        npc_services: Any,
    ) -> TickResultDTO:
        """Player turn делегирует в execute() — единственная точка входа."""
        # Мостируем legacy dm_ctx в InterventionEvent (TZ-08 v0.2)
        _intervention = InterventionEvent(
            source="player",
            payload={"dm_ctx": dm_ctx},
            tick=dm_ctx.current_tick,
        )
        return self.execute(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=dm_ctx.current_tick,
            interventions=[_intervention],
            npc_services=npc_services,
        )

    # ── Core Pipeline (Immutable Sequence) ──────────────────────────

    def _run_core_phases(self, ctx: _TickContext) -> None:
        """A2-FIX v0.2: Immutable core pipeline. NO mode, NO player branching."""
        self._snapshot_positions_before(ctx)
        self._phase_0_simulation(ctx)
        self._phase_0_5_idle_services(ctx)
        self._phase_1_npic_normalize(ctx)
        self._phase_1_input_merge(ctx)
        self._apply_willpower_gate(ctx)
        self._phase_2_event_bus_primary(ctx)
        self._phase_3_memory(ctx)
        self._phase_4_pre_decision(ctx)
        self._phase_5_decision(ctx)
        self._phase_6_post_decision(ctx)
        self._phase_7_windup_resolution(ctx) # ADR-O-310: Execution Gate
        self._phase_8_drain_secondary(ctx)
        self._phase_9_integration(ctx)
        self._run_affective_pipeline(ctx)
        self._phase_10_persistence(ctx)

    def _phase_1_npic_normalize(self, ctx: _TickContext) -> None:
        """Подслой 1.1: NPIC NORMALIZATION."""
        if ctx.all_npcs_raw:
            from app.models.npc_state import BODY_STATE_DISABLED
            for _npc in ctx.all_npcs_raw:
                _bs = _npc.get("body_state")
                if not _bs:
                    _npc["body_state"] = dict(BODY_STATE_DISABLED)
                    logger.warning(f"[NPIC_NORMALIZE] NPC '{_npc.get('npc_id', '?')}' missing body_state. Injected DISABLED sentinel.")

    def _phase_1_input_merge(self, ctx: _TickContext) -> None:
        """Подслой 1.2: Merge interventions into delta_buffer."""
        if not ctx.interventions:
            return

        _life_engine = self._get_life_engine()
        if _life_engine:
            ctx.npc_states = _life_engine.get_npc_states(ctx.campaign_id)
            if ctx.npc_states:
                _player_entry = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
                ctx.all_npcs_raw = ctx.npc_states
                if _player_entry:
                    ctx.all_npcs_raw = [n for n in ctx.all_npcs_raw if n.get("npc_id") != "player"]
                    ctx.all_npcs_raw.append(_player_entry)

        for interv in ctx.interventions:
            if interv.source == "player" and "dm_ctx" in interv.payload:
                _dm_ctx = interv.payload.get("dm_ctx")
                if _dm_ctx:
                    self._process_player_dm_action(ctx, _dm_ctx)
            elif interv.source == "player":
                self._process_player_action(ctx, interv)
            else:
                logger.debug(f"[INPUT_MERGE] unhandled intervention source: {interv.source}")

    def _apply_willpower_gate(self, ctx: _TickContext) -> None:
        """Подслой 1.3: WillpowerGate. Явный вызов без условного ветвления."""
        self._phase_1_input(ctx)

    def _process_player_dm_action(self, ctx: _TickContext, dm_ctx: Any) -> None:
        """Обработка player DM action (directive handling, cognitive overlay)."""
        logger.warning(f"[PDM_DEBUG] ENTER. dm_ctx={dm_ctx is not None}")
        if hasattr(dm_ctx, 'intent_resolution') and dm_ctx.intent_resolution:
            _intent_res = dm_ctx.intent_resolution
            _params = _intent_res.original_intent.parameters if _intent_res.original_intent else None
            _sem_action = getattr(_params, 'semantic_action', None) if _params else None
            _sem_target = getattr(_params, 'target_reference', None) if _params else None
            logger.warning(f"[PDM_DEBUG] sem_action={_sem_action} sem_target={_sem_target}")
            _intent_res = dm_ctx.intent_resolution
            _params = _intent_res.original_intent.parameters if _intent_res.original_intent else None
            _sem_action = getattr(_params, 'semantic_action', None) if _params else None
            _sem_target = getattr(_params, 'target_reference', None) if _params else None

            # ADR-082: Регистронезависимое сравнение (IC может вернуть "move" или "MOVE")
            if _sem_action and _sem_action.upper() == "MOVE" and _sem_target:
                _target_ref = _sem_target.lower()
                _is_npc_target = any(
                    _target_ref in n.get("name", "").lower() or _target_ref in n.get("npc_id", "").lower()
                    for n in ctx.all_npcs_raw
                ) if ctx.all_npcs_raw else False

                if _is_npc_target:
                    try:
                        from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber
                        import types
                        _target_id = getattr(_params, 'target_id', None)
                        _directive_payload = {
                            "semantic_action": _sem_action,
                            "target_reference": _sem_target,
                            "target_id": _target_id,
                            "social_pressure": 0.8,
                        }
                        _mock_event = types.SimpleNamespace(payload=_directive_payload)
                        _directive_deltas = DirectiveInterpretationSubscriber().handle(_mock_event, ctx.all_npcs_raw)
                        if _directive_deltas:
                            ctx.delta_buffer.extend(_directive_deltas)
                            for delta in _directive_deltas:
                                _npc_id = delta.npc_id
                                _npc_state = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _npc_id), None)
                                if not _npc_state:
                                    continue
                                if hasattr(delta.payload, 'recent_directive_data') and delta.payload.recent_directive_data:
                                    _npc_state.setdefault("perceptual_kernel", {})["recent_directive"] = delta.payload.recent_directive_data
                                if hasattr(delta.payload, 'stress_delta') and delta.payload.stress_delta != 0:
                                    _npc_state.setdefault("emotion", {})["stress"] = _npc_state.get("emotion", {}).get("stress", 0.0) + delta.payload.stress_delta
                                if hasattr(delta.payload, 'fear_delta') and delta.payload.fear_delta != 0:
                                    _npc_state.setdefault("social_stats", {})["fear_of_player"] = _npc_state.get("social_stats", {}).get("fear_of_player", 0.1) + delta.payload.fear_delta
                                if hasattr(delta.payload, 'shock_impulse') and getattr(delta.payload, 'shock_impulse', 0.0) > 0.5:
                                    _npc_state.setdefault("body_state", {})["shock_impulse"] = getattr(_npc_state.get("body_state", {}), "shock_impulse", 0.0) + delta.payload.shock_impulse
                                    _npc_state.setdefault("body_state", {})["consciousness"] = max(0.0, 1.0 - delta.payload.shock_impulse)
                    except Exception as e:
                        logger.error(f"[CAUSALITY_CRASH] DirectiveInterpretationSubscriber failed: {e}", exc_info=True)

            # ADR-TZ09-2: Fast Path для реактивного движения.
            # Вызывается немедленно после инъекции директивы, чтобы NPC сдвинулся в том же тике.
            logger.warning(f"[FAST_PATH_DEBUG] sem_action={_sem_action} is_npc={_is_npc_target} target_id={getattr(_params, 'target_id', None)}")
            if _is_npc_target and _target_id:
                from app.domain.movement import LocalSteeringGoal
                from app.services.spatial.movement_engine import MovementEngine
                _spatial_svc = self._resolve_spatial_service(ctx)
                logger.warning(f"[FAST_PATH_DEBUG] spatial_svc={_spatial_svc is not None}")
                if _spatial_svc:
                    _player_pos = ctx.scene_state.get("player_spatial", {}).get("local_position", {"x": 0.0, "y": 0.0})
                    logger.warning(f"[FAST_PATH_DEBUG] player_pos={_player_pos}")
                    _fast_intents = [LocalSteeringGoal(
                        npc_id=_target_id,
                        local_target_xy=(_player_pos.get("x", 0.0), _player_pos.get("y", 0.0)),
                        reason="micro_snap:approach",
                        priority=0.9
                    )]
                    me = MovementEngine()
                    me.set_spatial_service(_spatial_svc)
                    _changes = me.process_intents(
                        _fast_intents, ctx.tick_number,
                        ctx.scene_state.get("npc_positions", {}),
                        campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
                    )
                    logger.warning(f"[FAST_PATH_DEBUG] changes={len(_changes) if _changes else 0}")
                    if _changes and self._scene_manager:
                        self._apply_with_shadow_observation(ctx, _changes, phase_label="FAST_PATH_MOVE")
                        logger.warning(f"[FAST_PATH] Applied {len(_changes)} reactive movement changes for {_target_id}")

    def _process_player_action(self, ctx: _TickContext, interv: Any) -> None:
        """Generic player action intervention (не dm_ctx)."""
        pass # TODO: implement for CK successor directives

    # ── Player Turn: decision через legacy pipeline ───────────────────
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
        """DEPRECATED (TZ-08 v0.2). Фазы 8-10 уже выполнены внутри execute().
        
        Метод оставлен как no-op (заглушка) для обратной совместимости с game_loop,
        чтобы не ломать вызывающий код до полного перехода на event-driven модель.
        """
        # Возвращаем player_result, который уже был сформирован в execute() -> _phase_5_player_decision
        return player_result

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
                        _npc["body_state"] = dict(BODY_STATE_DISABLED)
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
            # ADR-082: Регистронезависимое сравнение (IC может вернуть "move" или "MOVE")
            if _sem_action and _sem_action.upper() == "MOVE" and _sem_target:
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
                            # SHI-FIX: L1Chronicle emission for directives
                            if hasattr(self, "l1_chronicle") and self.l1_chronicle is not None:
                                from app.models.delta_payloads import IdentityPayload
                                _dir_events = []
                                for _d in _directive_deltas:
                                    if hasattr(_d, 'payload') and isinstance(_d.payload, IdentityPayload) and _d.payload.recent_directive_data:
                                        _dir_events.append(TraitDriftEvent(
                                            tick_id=ctx.tick_number, target_id=_d.npc_id or _d.intent_target,
                                            source_id="player", effect_value=0.1, observation_weight=1.0, event_type="directive"
                                        ))
                                if _dir_events:
                                    self.l1_chronicle.commit_tick_buffer(_dir_events, ctx.tick_number)
                    except Exception as e:
                        logger.error(f"[CAUSALITY_CRASH] DirectiveInterpretationSubscriber failed: {e}", exc_info=True)
                else:
                    logger.info(f"[CAUSALITY] MOVE target '{_target_ref}' is not an NPC. Treating as player spatial action.")


        # Фаза 0.5: время не останавливается (decay = всегда)
        self._phase_0_5_idle_services(ctx)

        # ── ФИКС P0: Передать npc_contexts в shared_context ──
        # Без этого DM-агент видит пустой npc_contexts → "NPC не предпринимают значимых действий"
        if ctx.npc_contexts:
            ctx.shared_context.npc_contexts = ctx.npc_contexts
            logger.warning(f"[P0_FIX] npc_contexts transferred: {len(ctx.npc_contexts)} contexts")
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

        # SEL CRITICAL FIX: Врезка аффективного контура (Котла) напрямую в action pipeline.
        # Ранее _run_affective_pipeline жил внутри _phase_9_player_integration и убивался 
        # guard-условием (shared_context is None). Теперь Котёл работает безусловно.
        import sys
        logger.debug("[SEL_BYPASS] Injecting _run_affective_pipeline directly into action tick", file=sys.stderr, flush=True)
        self._run_affective_pipeline(ctx)

        self._phase_9_player_integration(ctx)
        self._phase_10_player_persistence(ctx)

        # Perception pipeline для action tick (тот же что idle tick)
        # Без этого action response не содержит player_perception → cues_received=0
        # ADR-092: Perception pipeline для action tick
        # TZ-08 v0.2 (C2): Perception pipeline вынесен из ядра в PerceptionProjector (game_loop).
        # Ядро больше не формирует player_perception.

        # Возвращаем обновлённый результат (с finalize_result)
        # SCENE_IDENTITY: проверяем, что scene_state не потерян между фазами
        _final_traversals = list(ctx.scene_state.get("active_traversals", {}).keys()) if ctx.scene_state else []
        if _final_traversals:
            logger.warning(f"[SCENE_IDENTITY] finalize exits with traversals: {_final_traversals} id={id(ctx.scene_state)}")
        return ctx.player_result

    # ── Player Turn: finalize + commit ─────────────────────────────────

    # ── Слой 4: подготовка ────────────────────────────────────────────

    def _snapshot_positions_before(self, ctx: _TickContext) -> None:
        """Снимок позиций NPC ДО тика — для SpatialEventDetector (Слой 4).
        Также продвигает TransitTracker (NPC в пути двигаются на 1 шаг).
        """
        ctx.old_npc_positions = _npc_positions_snapshot(ctx.scene_state)

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
        _trav_keys = sorted(ctx.scene_state.get("active_traversals", {}).keys())
        _pos_keys = sorted(ctx.scene_state.get("npc_positions", {}).keys())
        logger.debug(f"[NPC_SET] tick={ctx.tick_number} traversals={_trav_keys} positions={_pos_keys}")
        
        # ADR-048: Авторитетный SpatialService берется из единого резолвера
        _spatial_svc = self._resolve_spatial_service(ctx)
        if _spatial_svc:
            engine.set_spatial_service(_spatial_svc)
        
        # DRF: Инъекция единой причинной шины в LifeEngine
        engine.set_claim_bus(ctx.drf_bus)
        logger.debug(f"[DRF_BIND_LIFE] bus_id={id(ctx.drf_bus)}")
        changes, life_intents = engine.tick(ctx.campaign_id, ctx.scene_state, runtime_path=runtime_path)
        logger.debug(f"[GATE_A] tick={ctx.tick_number} life_intents={len(life_intents)} cognitive_changes={len(changes or [])}")
        ctx.scene_changes = changes or []
        # Заполняем полные стейты для фаз 3-6, 10 (Устав §3.1)
        ctx.npc_states = engine.get_npc_states(ctx.campaign_id)
        # ADR-002: Единый мутатор работает с all_npcs_raw. В idle-пути это те же данные, что и npc_states
        ctx.all_npcs_raw = ctx.npc_states
        if changes and self._scene_manager:
            self._apply_with_shadow_observation(ctx, changes, phase_label="IDLE_COGNITIVE")
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
                logger.debug(f"[GATE_B2] tick={ctx.tick_number} spatial_changes={len(spatial_changes or [])} from_intents={len(life_intents)}")
                if spatial_changes and self._scene_manager:
                    self._apply_with_shadow_observation(ctx, spatial_changes, phase_label="IDLE_SPATIAL")
                    logger.info(f"[TICK_ORCH] Фаза 0: {len(spatial_changes)} spatial changes from {len(life_intents)} LifeEngine intents")

        # ADR-019: Фаза 0.75 — Authoritative Traversal Lifecycle.
        # Бэкенд не интерполирует пиксели, но владеет жизненным циклом перемещения.
        self._process_traversals(ctx)
        
        # ETKE-IK v1: Непрерывное движение (параллельная ветка).
        # Обрабатывает DriveVector для NPC без активных макро-транзитов.
        self._process_continuous_motion(ctx, _spatial_svc)

    def _process_continuous_motion(self, ctx: _TickContext, _spatial_svc: Optional["SpatialService"] = None) -> None:
        """ETKE-IK v1: Непрерывная кинематика (SteeringResolver + MotionIntegrator).
        
        Если у NPC есть DriveVector и нет активного MovementIntent,
        его позиция вычисляется через непрерывное поле возможностей.
        """
        from app.services.motion.motion_pipeline import SteeringResolver, MotionIntegrator, CollisionAvoidance
        from app.domain.motion_core import BodySchema, DriveVector, MotionPrimitive
        from app.core.constants import ETKE_IK_SUBSTEP_DT
        
        npc_positions = ctx.scene_state.get("npc_positions", {})
        active_traversals = ctx.scene_state.get("active_traversals", {})
        continuous_changes = []
        
        # S91: Используем персистентный провайдер уровня экземпляра (стигмергия)
        wtp = self._topology_provider
        wtp.set_spatial_service(_spatial_svc)
        
        # TODO: В будущем LifeEngine будет класть DriveVector в npc_state.
        # Пока читаем заглушку (если её нет — пропускаем).
        for npc_data in ctx.all_npcs_raw:
            npc_id = npc_data.get("id", npc_data.get("npc_id", ""))
            if not npc_id or npc_id in active_traversals:
                continue
                
            dv_raw = npc_data.get("drive_vector")
            if not dv_raw:
                continue
            
            # ETKE-IK v2: Чтение MotionPrimitive (4-й элемент, fallback на approach)
            _prim_name = dv_raw[3] if len(dv_raw) > 3 else "approach"
            drive = DriveVector(
                direction=(dv_raw[0], dv_raw[1]),
                intensity=dv_raw[2],
                primitive=MotionPrimitive(_prim_name)
            )
            
            pos_data = npc_positions.get(npc_id, {})
            current_pos = pos_data.get("local_position", {"x": 0.0, "y": 0.0})
            current_vel = pos_data.get("velocity", (0.0, 0.0))
            current_exertion = pos_data.get("exertion_level", 0.0)
            
            body = BodySchema()
            
            affordance = wtp.query_affordance_field(
                ctx.scene_state.get("location_id", ""),
                (current_pos.get("x", 0.0), current_pos.get("y", 0.0))
            )
            
            # ETKE-IK v2: Реактивная коррекция направления перед вычислением скорости
            _pos_tuple = (current_pos.get("x", 0.0), current_pos.get("y", 0.0))
            _loc_id = ctx.scene_state.get("location_id", "")
            # S91: Передаём позиции всех NPC для избегания столкновений
            drive = CollisionAvoidance.apply(
                drive=drive, pos=_pos_tuple, topology=wtp, region=_loc_id,
                npc_positions=npc_positions, current_npc_id=npc_id
            )
            
            new_vel = SteeringResolver.resolve(
                drive=drive, body=body, affordance=affordance,
                current_velocity=current_vel, dt=ETKE_IK_SUBSTEP_DT
            )
            
            new_pos = MotionIntegrator.integrate(
                position=(current_pos.get("x", 0.0), current_pos.get("y", 0.0)),
                velocity=new_vel, body=body, affordance=affordance, dt=ETKE_IK_SUBSTEP_DT
            )
            
            new_exertion = MotionIntegrator.compute_exertion(
                velocity=new_vel, body=body,
                current_exertion=current_exertion, dt=0.1
            )

            # S91: Эмит стигмергического следа (movement_density)
            _zone_id = _spatial_svc.get_zone_id(new_pos[0], new_pos[1]) if _spatial_svc else None
            if _zone_id:
                from app.domain.motion_core import TracePayload
                _trace = TracePayload(
                    region=_loc_id,
                    zone_id=_zone_id,
                    trace_type="movement_density", # Толпа создает сопротивление
                    magnitude=0.1, # Небольшая величина, накапливается со временем
                    created_tick=ctx.tick_number,
                    ttl=50, # След остывает за 50 тиков
                    source_id=npc_id
                )
                self._dynamic_field.apply_trace(_trace)
            
            continuous_changes.append(SceneChange(
                type=ChangeType.NPC_POSITION, target=npc_id, field="local_position",
                value={"x": new_pos[0], "y": new_pos[1]},
                cause="etke_continuous_motion", tick=ctx.tick_number
            ))
            continuous_changes.append(SceneChange(
                type=ChangeType.NPC_STATE, target=npc_id, field="velocity",
                value=new_vel, cause="etke_continuous_motion", tick=ctx.tick_number
            ))
            continuous_changes.append(SceneChange(
                type=ChangeType.NPC_STATE, target=npc_id, field="exertion_level",
                value=new_exertion, cause="etke_continuous_motion", tick=ctx.tick_number
            ))

        if continuous_changes and self._scene_manager:
            self._apply_with_shadow_observation(ctx, continuous_changes, phase_label="ETKE_CONTINUOUS")
            logger.debug(f"[ETKE] Processed continuous motion for {len(continuous_changes)//3} NPCs")

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
            _status = trav.get("status", "UNKNOWN")
            if _status != "MOVING":
                if ctx.tick_number % 50 == 0:
                    logger.debug(f"[GATE_F_SKIP] npc={npc_id} status={_status}")
                continue
            
            started_tick = trav.get("started_tick", 0)
            duration_ticks = trav.get("duration_ticks", 1)
            expected_arrival_tick = started_tick + duration_ticks
            
            logger.debug(f"[GATE_F] npc={npc_id} current_tick={current_tick} started={started_tick} duration={duration_ticks} expected={expected_arrival_tick} remaining={expected_arrival_tick - current_tick}")
            
            if current_tick >= expected_arrival_tick:
                # STL: Транзит завершён. Генерируем финальный факт перемещения.
                target_node = trav.get("target_node")
                wp = trav.get("path_waypoints", [])
                
                # ДОЛГ 6.2: Boundary resolution at completion time (не creation time).
                # Boundary — свойство ФАКТА пересечения, не свойства маршрута.
                # Runtime query к SpatialService в точке факта.
                _is_boundary = False
                _entry_node = target_node
                _target_location_id = ""
                
                _svc = self._spatial_service
                if _svc and target_node and _svc.is_boundary_node(target_node):
                    _boundary_info = _svc.get_boundary_info(target_node)
                    if _boundary_info:
                        _neighbor = _boundary_info.get("neighbor_chunk", "")
                        _entry_hint = _boundary_info.get("entry_node_hint", "")
                        _entry_dir = _boundary_info.get("entry_direction", "")
                        if _neighbor:
                            _is_boundary = True
                            _target_location_id = _neighbor
                            # Резолвим entry node: hint → direction → fallback
                            if _entry_hint:
                                _entry_node = _entry_hint
                            elif _entry_dir:
                                _entry_node = f"{_neighbor}:entry_{_entry_dir}"
                            else:
                                _entry_node = f"{_neighbor}:entrance"
                            logger.info(
                                f"[BOUNDARY_TRANSITION] npc={npc_id} "
                                f"node={target_node} → chunk={_neighbor} "
                                f"entry={_entry_node}"
                            )
                
                # Факт 1: Каузальная позиция (semantic truth, NO geometry)
                completion_changes.append(SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="position",
                    value=_entry_node,
                    cause="traversal_complete",
                    tick=current_tick,
                    target_location_id=_target_location_id,  # ДОЛГ 6.2
                ))
                
                # Факт 2: Визуальная позиция — только intra-location.
                # ДОЛГ 6.2: Boundary transition НЕ эмитит local_position.
                # SceneChange = semantic event, apply_changes = geometric resolver.
                if not _is_boundary and len(wp) >= 2:
                    completion_changes.append(SceneChange(
                        type=ChangeType.NPC_POSITION,
                        target=npc_id,
                        field="local_position",
                        value={"x": wp[-1][0], "y": wp[-1][1]},
                        cause="traversal_complete",
                        tick=current_tick
                    ))
                
                # ADR-XXX: Traversal Lifecycle — SSM owns status transitions.
                # TickOrchestrator только эмитит факты (SceneChange), не мутирует active_traversals.
                # SSM.apply_change выполнит: position snap → status COMPLETED → zombie cleanup.
                logger.debug(f"[TRAVERSAL] Lifecycle emit: npc={npc_id} arrived at {target_node} boundary={_is_boundary}. SceneChanges emitted.")

        # ADR-XXX: Zombie cleanup перенесён в SSM.apply_changes (SSOT owner).
        # TickOrchestrator больше не мутирует active_traversals напрямую.

        # STL: Схлопываем реальность через единый commit-point
        if completion_changes and self._scene_manager:
            self._apply_with_shadow_observation(ctx, completion_changes, phase_label="TRAVERSAL_COMPLETE")
            logger.info(f"[STL_COMMIT] Traversal completion: {len(completion_changes)} changes applied")

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-O-201 ФАЗА 1: Dual Rail Execution (Shadow Observer)
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_with_shadow_observation(
        self, ctx: "_TickContext", changes: list, phase_label: str = ""
    ) -> int:
        """ФАЗА 1 (ADR-O-201): Legacy + Shadow parallel execution.

        Legacy = AUTHORITATIVE. Shadow = OBSERVER only.
        Нулевое изменение поведения системы.

        Порядок:
        1. Строим snapshot ДО мутации
        2. Shadow компилирует NPC_POSITION changes
        3. Legacy применяет (авторитетный)
        4. Сравниваем результаты через EquivalenceValidator
        """
        if not changes or not self._scene_manager:
            return 0

        # ── Shadow compilation (ДО мутации) ─────────────────────────
        _spatial_changes = [
            ch for ch in changes
            if isinstance(ch, SceneChange)
            and ch.type == ChangeType.NPC_POSITION
            and ch.field in ("position", "local_position")
        ]

        logger.debug(f"[GATE_C] phase={phase_label} total_changes={len(changes)} spatial_candidates={len(_spatial_changes)} has_svc={self._spatial_service is not None}")
        _snapshot: Optional[WorldSnapshot] = None
        _shadow_results: Dict[str, Any] = {}

        if _spatial_changes and self._spatial_service:
            try:
                _snapshot = build_snapshot(
                    tick=ctx.tick_number,
                    campaign_id=ctx.campaign_id,
                    location_id=ctx.scene_state.get("location_id", ""),
                    spatial_service=self._spatial_service,
                    scene_state=ctx.scene_state,
                    rng_seed=ctx.tick_number,
                )
                logger.debug(f"[GATE_D1] phase={phase_label} snapshot_created={_snapshot is not None}")
                _compiled_count = 0
                for _ch in _spatial_changes:
                    _thick = self._event_compiler.compile(_snapshot, _ch)
                    logger.debug(f"[GATE_D2] phase={phase_label} compiled_thick={_thick is not None}")
                    if _thick is not None:
                        _shadow_results[_ch.target] = _thick
                        # CSSE Stage 2: collect ThickSceneChange for projection parity
                        if not hasattr(self, '_tick_thick_changes'):
                            self._tick_thick_changes = []
                        self._tick_thick_changes.append(_thick)
                        _compiled_count += 1
                logger.info(
                    f"[DUAL_RAIL][{phase_label}] spatial_changes={len(_spatial_changes)} "
                    f"shadow_compiled={_compiled_count} snapshot_id={_snapshot.snapshot_id.hex[:8]}"
                )
            except Exception as _e:
                logger.warning(f"[DUAL_RAIL] Shadow compilation failed: {_e}")

        # ── Legacy apply (AUTHORITATIVE) ────────────────────────────
        _applied = self._scene_manager.apply_changes(
            ctx.campaign_id, changes, ctx.scene_state
        )

        # ── Validation (ПОСЛЕ мутации) ──────────────────────────────
        if _shadow_results and _snapshot is not None:
            for _npc_id, _thick in _shadow_results.items():
                self._validate_shadow_vs_legacy(
                    snapshot=_snapshot,
                    tick=ctx.tick_number,
                    npc_id=_npc_id,
                    thick=_thick,
                    scene_state=ctx.scene_state,
                    phase_label=phase_label,
                )

        logger.debug(f"[GATE_E] phase={phase_label} validated={len(_shadow_results) if _shadow_results else 0} applied={_applied}")
        return _applied

    def _validate_shadow_vs_legacy(
        self,
        snapshot: WorldSnapshot,
        tick: int,
        npc_id: str,
        thick: Any,
        scene_state: dict,
        phase_label: str = "",
    ) -> None:
        """Сравнение shadow ThickSceneChange с legacy состоянием.

        ФАЗА 2: Position (L0/L3) + Topology (L1) + Boundary (L2) + Traversal (L2).
        Class A/B → info (ожидаемый), Class C → warning+DEPRECATION,
        Class D/E → error+DEPRECATION.
        """
        _npc_entry = scene_state.get("npc_positions", {}).get(npc_id, {})
        _legacy_pos = _npc_entry.get("local_position")
        _legacy_node = _npc_entry.get("position", "")
        # FIX: _legacy_location должен браться из фактической позиции NPC в сцене,
        # а не из кэша LifeEngine (где хранится "должность" по расписанию).
        # Без этого возникает ложный boundary-дрейф, если NPC работает в другой локации.
        _legacy_location = _npc_entry.get("location_id", _npc_entry.get("location", ""))

        # Shadow state из ThickSceneChange
        _shadow_pos = thick.spatial.target_xy if thick.spatial else None
        _shadow_node = thick.spatial.target_node if thick.spatial else ""

        # Shadow boundary/target location
        _shadow_target_location = ""
        if thick.boundary and thick.boundary.neighbor_chunk:
            _shadow_target_location = thick.boundary.neighbor_chunk
        elif thick.spatial and thick.spatial.target_location:
            _shadow_target_location = thick.spatial.target_location

        _drifts: list = []

        # Position drift (L0 — ontological + L3 — presentation)
        _drifts += self._equivalence_validator.validate_position(
            snapshot_id=snapshot.snapshot_id,
            tick=tick,
            npc_id=npc_id,
            legacy_position=_legacy_pos,
            shadow_position=_shadow_pos,
        )

        # Topology drift (L1)
        # FIX: Пропускаем топологический дрейф при boundary transition.
        # При смене локации узлы гарантированно разные (exit_east vs exit_west),
        # и это не является ошибкой. Смену локации проверяет validate_boundary.
        if _shadow_node and _legacy_node and not _shadow_target_location:
            _drifts += self._equivalence_validator.validate_topology(
                snapshot_id=snapshot.snapshot_id,
                tick=tick,
                npc_id=npc_id,
                legacy_node=_legacy_node,
                shadow_node=_shadow_node,
            )

        # ── ФАЗА 2: Boundary drift (L2) ────────────────────────────
        # Legacy boundary: NPC оказался в другой локации после apply
        _legacy_is_boundary = bool(
            _legacy_location and _legacy_location != snapshot.location_id
        )
        _shadow_is_boundary = bool(thick.boundary and thick.boundary.is_boundary)
        _drifts += self._equivalence_validator.validate_boundary(
            snapshot_id=snapshot.snapshot_id,
            tick=tick,
            npc_id=npc_id,
            legacy_is_boundary=_legacy_is_boundary,
            shadow_is_boundary=_shadow_is_boundary,
            legacy_target_location=_legacy_location,
            shadow_target_location=_shadow_target_location,
        )

        # ── ФАЗА 2: Traversal drift (L2) ───────────────────────────
        _legacy_traversal = scene_state.get("active_traversals", {}).get(npc_id)
        _shadow_traversal = thick.traversal if thick.traversal else None
        _drifts += self._equivalence_validator.validate_traversal(
            snapshot_id=snapshot.snapshot_id,
            tick=tick,
            npc_id=npc_id,
            legacy_traversal=_legacy_traversal,
            shadow_traversal=_shadow_traversal,
        )

        # Логируем и собираем статистику
        self._drift_stats["total_comparisons"] += 1
        if _drifts:
            self._equivalence_validator.log_drifts(_drifts)
            for _d in _drifts:
                self._drift_stats.setdefault(f"drift_{_d.drift_class.value}", 0)
                self._drift_stats[f"drift_{_d.drift_class.value}"] += 1
                logger.info(
                    f"[DUAL_RAIL][{phase_label}] npc={npc_id} "
                    f"class={_d.drift_class.value} field={_d.field}"
                )

        # Периодический отчёт (каждые 100 наблюдений)
        self._log_drift_summary()

    def collect_thick_changes(self) -> list:
        """CSSE Stage 2: возвращает и очищает буфер ThickSceneChange.

        Swap pattern: возвращает список и создаёт новый пустой.
        Безопасен для вызова между тиками.
        """
        if not hasattr(self, '_tick_thick_changes'):
            self._tick_thick_changes = []
        result = self._tick_thick_changes
        self._tick_thick_changes = []
        return result

    def _log_drift_summary(self) -> None:
        """Периодический отчёт о дрейфе (ФАЗА 2 — с DEPRECATION индикатором).

        Критерий переключения ФАЗА 2→3:
        0 Ontological + 0 Causal + 0 Topological drift за N ≥ 100000 тиков.
        """
        _total = self._drift_stats.get("total_comparisons", 0)
        if _total > 0 and _total % 100 == 0:
            _a = self._drift_stats.get("drift_A", 0)
            _b = self._drift_stats.get("drift_B", 0)
            _c = self._drift_stats.get("drift_C", 0)
            _d = self._drift_stats.get("drift_D", 0)
            _e = self._drift_stats.get("drift_E", 0)
            # ФАЗА 2: Индикатор готовности к Phase 3 takeover
            _structural_drift = _c + _d + _e
            _ready = "READY" if _structural_drift == 0 and _total >= 100000 else "NOT_READY"
            logger.info(
                f"[DUAL_RAIL] Drift summary after {_total} observations: "
                f"A(cosmetic)={_a} B(projection)={_b} C(topological)={_c} "
                f"D(causal)={_d} E(ontological)={_e} "
                f"phase3={_ready}"
            )

    def _phase_1_input(self, ctx: _TickContext) -> None:
        """Фильтрация воли игрока через WillpowerGate (ADR-031).
        
        Если интент угрожает идентичности аватара — возникает конфликт воли.
        """
        # БЕЗУСЛОВНАЯ ДИАГНОСТИКА: Вызывается ли метод вообще?
        import sys
        logger.debug(f"[WILL_TRACE] _phase_1_input CALLED. Has intent: {ctx.player_intent is not None}")
        
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
        mm = self._get_memory_manager()
        from app.models.npc_state import NPCState
        from app.services.npc.npc_loader import load_l2_state_from_runtime_dict

        # Шаг 11 (ТЗ-02): Memory promotion.
        # YELLOW (Allowed in idle): compress_narrative_cache (структурная оптимизация)
        if ctx.tick_number % 10 == 0:
            for npc_dict in ctx.npc_states:
                npc_id = npc_dict.get("id")
                if not npc_id:
                    continue
                try:
                    npc_state = load_l2_state_from_runtime_dict(npc_dict)
                    _compressed = mm.compress_narrative_cache(npc_state.narrative_cache)
                    if _compressed != npc_state.narrative_cache:
                        npc_state.narrative_cache = _compressed
                        # Синхронизация обратно в dict
                        # ADR-117: write_to_legacy — staticmethod. Вызов через класс.
                        from app.models.npc_state import NPCState
                        NPCState.write_to_legacy(npc_state, npc_dict)
                except Exception as e:
                    logger.warning(f"[PHASE_3_MEMORY] compress_narrative_cache failed for {npc_id}: {e}")

        # GREEN GATE: Memory cannot generate new identity without causal input.
        # Запрет кристаллизации L2.5 в idle-тиках (предотвращение фантомного дрейфа).
        if not ctx.phase_2_events:
            return

        # GREEN (Requires events): check_identity_promotion (L2.5 Crystallization)
        if ctx.tick_number % 50 == 0:
            for npc_dict in ctx.npc_states:
                npc_id = npc_dict.get("id")
                if not npc_id:
                    continue
                try:
                    _new_traits = mm.check_identity_promotion(
                        campaign_id=ctx.campaign_id, npc_id=npc_id
                    )
                    if _new_traits:
                        logger.info(f"[PHASE_3_MEMORY] new identity traits for {npc_id}: {_new_traits}")
                except Exception as e:
                    logger.warning(f"[PHASE_3_MEMORY] check_identity_promotion failed for {npc_id}: {e}")

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

    def _compute_effective_drives(self, npc_list: list[dict], tick_number: int) -> Tuple[Dict[str, "EffectiveDrives"], Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
        """STEP B + TSHL: Вычисление L3_raw и фильтрация в L3_stable через CalibrationEngine.
        Возвращает L3_stable (для DecisionHub), drives_updates и strain_updates (для StateApplicator).
        """
        from app.domain.identity_events import EffectiveDrives
        from app.services.npc.calibration_engine import CalibrationEngine
        
        effective_drives_map: Dict[str, EffectiveDrives] = {}
        drives_updates: Dict[str, Dict[str, float]] = {}
        strain_updates: Dict[str, Dict[str, float]] = {}
        
        if hasattr(self, 'drive_resolver') and hasattr(self, 'l1_chronicle'):
            from app.models.npc_state import personality_from_legacy
            _calibration = CalibrationEngine()
            
            for npc_dict in npc_list:
                _nid = npc_dict.get("id") or npc_dict.get("npc_id")
                if _nid:
                    _profile_l0 = personality_from_legacy(npc_dict)
                    _beliefs = self.crystallized_belief_store.get_beliefs(_nid)
                    _projection = self.drive_resolver.resolve_drives(_profile_l0, _beliefs)
                    
                    if isinstance(_projection, EffectiveDrives):
                        l3_raw = _projection
                    else:
                        l3_raw = EffectiveDrives.from_dict(_projection)
                    
                    # TSHL: Фильтруем L3_raw через фазовый переход
                    _prev_runtime = npc_dict.get("drives", {})
                    _prev_strain = npc_dict.get("strain_memory", {})
                    _baseline_l0 = dict(_profile_l0.drives_base)
                    
                    l3_stable, drives_update, strain_update = _calibration.stabilize(
                        l3_raw, _prev_runtime, _baseline_l0, _prev_strain
                    )
                    
                    effective_drives_map[_nid] = l3_stable
                    drives_updates[_nid] = drives_update
                    strain_updates[_nid] = strain_update
                    
        return effective_drives_map, drives_updates, strain_updates

    def _phase_5_decision(self, ctx: _TickContext) -> None:
        """TZ-09: Unified Execution Kernel.
        
        Собирает TickState (causal snapshot), вызывает NpcTickPipeline.run() (pure reducer),
        применяет TickMutation к контексту. Никаких ветвлений на player/idle.
        """
        from app.domain.tick import create_tick_state, TickMutation
        from app.services.npc.npc_tick_pipeline import NpcTickPipeline
        from app.services.npc.break_progress_engine import BreakProgressEngine
        from app.models.npc_state import NPCStateAdapter
        from app.models.behavior_mask import BehaviorMask, BehaviorMaskState
        from app.models.will import WillState
        from app.domain.identity_events import TraitDriftEvent

        logger.info(f"[PHASE_5_UNIFIED] ENTER: tick={ctx.tick_number}, interventions={len(ctx.interventions)}")

        # 1. Assembler: Подготовка данных (BreakProgress, BehaviorMask, L3 Drives)
        mm = self._get_memory_manager()
        identities: dict[str, dict[str, float]] = {}
        for npc_dict in ctx.npc_states:
            if npc_id := npc_dict.get("id"):
                if traits := mm.get_identity_traits(ctx.campaign_id, npc_id):
                    identities[npc_id] = traits

        for npc_dict in ctx.npc_states:
            npc_id = npc_dict.get("id")
            if not npc_id: continue
            try:
                _npc_state = NPCStateAdapter.from_legacy(npc_dict)
                _willpower = getattr(_npc_state.psyche, "willpower", 50.0) if hasattr(_npc_state, "psyche") else 50.0
                _break_deltas = BreakProgressEngine.calculate(
                    state=_npc_state, willpower=_willpower,
                    recent_failures=getattr(_npc_state, "recent_failures", 0),
                    support_present=getattr(_npc_state, "support_present", False)
                )
                _npc_state.identity_integrity = max(0.0, min(1.0, _npc_state.identity_integrity + _break_deltas.identity_integrity_delta))
                _npc_state.pressure_resistance = max(0.0, min(1.0, _npc_state.pressure_resistance + _break_deltas.pressure_resistance_delta))
                if _break_deltas.will_state_override is not None:
                    _npc_state.will_state = _break_deltas.will_state_override

                # ADR-O-208: Сохраняем вычисленные дельты обратно в npc_dict.
                from app.models.npc_state import NPCState
                NPCState.write_to_legacy(_npc_state, npc_dict)

                # L1Chronicle: Фиксация давления и идентичности.
                if hasattr(self, "l1_chronicle") and self.l1_chronicle is not None:
                    _affect = _npc_state.affective_load * 100
                    _events_to_log = []
                    if _affect > 10.0:
                        _events_to_log.append(
                            TraitDriftEvent(tick_id=ctx.tick_number, target_id=npc_id,
                                           source_id=f"break_progress:{_break_deltas.stage}",
                                           effect_value=-0.01, observation_weight=1.0, event_type="pressure")
                        )
                    # Логируем identity и will всегда, когда есть давление
                    if _affect > 10.0 or _break_deltas.identity_integrity_delta < 0:
                        _events_to_log.append(
                            TraitDriftEvent(tick_id=ctx.tick_number, target_id=npc_id,
                                           source_id=f"break_progress:{_break_deltas.stage}",
                                           effect_value=_break_deltas.identity_integrity_delta, observation_weight=1.0, event_type="identity")
                        )
                        _events_to_log.append(
                            TraitDriftEvent(tick_id=ctx.tick_number, target_id=npc_id,
                                           source_id=f"break_progress:{_break_deltas.stage}",
                                           effect_value=-0.01, observation_weight=1.0, event_type="will")
                        )

                    if _events_to_log:
                        self.l1_chronicle.commit_tick_buffer(_events_to_log, ctx.tick_number)

                    if _break_deltas.will_state_override is not None:
                        self.l1_chronicle.commit_tick_buffer([
                            TraitDriftEvent(tick_id=ctx.tick_number, target_id=npc_id,
                                           source_id=f"break_progress:{_break_deltas.stage}",
                                           effect_value=-0.1, observation_weight=1.0, event_type="will_state")
                        ], ctx.tick_number)

                _rel_cache = getattr(_npc_state, "relationship_cache", {})
                _player_rel = _rel_cache.get("player", {}) if isinstance(_rel_cache, dict) else {}
                _trust = _player_rel.get("trust", 0.0)
                _fear = _player_rel.get("fear", 0.0) * 100
                _has_hidden = bool(getattr(_npc_state, "hidden_truth", None))

                _new_mask, _mask_intensity = BehaviorMask.NONE, 0.0
                if _npc_state.will_state == WillState.BROKEN:
                    _new_mask, _mask_intensity = BehaviorMask.COLLAPSE, 0.8
                elif _fear > 60 and _trust < 0 and _willpower > 40:
                    _new_mask, _mask_intensity = BehaviorMask.FAKE_SUBMISSION, min(0.7, _fear / 100)
                elif _trust < -50 and _fear < 30 and _has_hidden:
                    _new_mask, _mask_intensity = BehaviorMask.BETRAYAL, min(0.6, abs(_trust) / 100)

                if _new_mask != _npc_state.behavior_mask.mask:
                    _npc_state.behavior_mask = BehaviorMaskState(mask=_new_mask, intensity=_mask_intensity, applied_at_day=getattr(ctx, "game_day", 0))

                npc_dict["identity_integrity"] = _npc_state.identity_integrity
                npc_dict["pressure_resistance"] = _npc_state.pressure_resistance
                npc_dict["will_state"] = _npc_state.will_state.value if hasattr(_npc_state.will_state, "value") else _npc_state.will_state
                npc_dict["behavior_mask"] = _npc_state.behavior_mask.mask.value
                npc_dict["behavior_mask_intensity"] = _npc_state.behavior_mask.intensity
            except Exception as e:
                logger.error(f"[BREAK_PROGRESS] failed for {npc_id}: {e}")
                raise

        ctx.effective_drives_map, ctx.drives_updates, ctx.strain_updates = self._compute_effective_drives(ctx.npc_states, ctx.tick_number)

        # 2. Извлечение данных игрока (если есть)
        _dm_ctx = None
        for interv in ctx.interventions:
            if interv.source == "player" and "dm_ctx" in interv.payload:
                _dm_ctx = interv.payload["dm_ctx"]
                break

        # 3. Execute: Сборка TickState и вызов Pure Reducer
        # ADR-123: Death Lock. Мёртвые полностью исключаются из reasoning pipeline.
        _alive_npcs = [n for n in (ctx.all_npcs_raw or ctx.npc_states) if n.get("body_state", {}).get("life_status") != "DEAD"]

        # S-93: Active Inference. Сборка PE-модификаторов из ExpectationStore.
        _pe_mods_map: dict[str, dict[str, float]] = {}
        if hasattr(self, '_expectation_store') and self._expectation_store is not None:
            from app.services.npc.pe_modifier_resolver import PEModifierResolver
            _pe_resolver = PEModifierResolver()
            for npc_dict in _alive_npcs:
                if npc_id := npc_dict.get("id"):
                    _exp = self._expectation_store.get_expectation(npc_id, "player")
                    _pe_mods = _pe_resolver.resolve(_exp)
                    if _pe_mods:
                        _pe_mods_map[npc_id] = _pe_mods

        # TZ-10: Preload Data для Pure Reducer (вынос I/O из run)
        _svc = ctx.npc_services
        _memory_weights_map = {}
        _narrative_cache_map = {}
        _social_modifiers_map = {}
        _reputation_modifiers_map = {}
        _economic_profiles_map = {}
        _crystallized_beliefs_map = {}
        _identity_traits_map = {}

        if _svc:
            for n in _alive_npcs:
                _nid = n.get("id") or n.get("npc_id")
                if not _nid: continue
                
                if _svc.memory_manager:
                    _memory_weights_map[_nid] = _svc.memory_manager.get_weights_for_decision(campaign_id=ctx.campaign_id, npc_id=_nid, target_id="player")
                    _narrative_cache_map[_nid] = _svc.memory_manager.load_narrative_from_sqlite(ctx.campaign_id, _nid)
                    _identity_traits_map[_nid] = _svc.memory_manager.get_identity_traits(campaign_id=ctx.campaign_id, npc_id=_nid)
                
                if _svc.social_engine:
                    _social_modifiers_map[_nid] = _svc.social_engine.compute_social_modifiers(npc_id=_nid)
                
                if _svc.reputation_engine:
                    _reputation_modifiers_map[_nid] = _svc.reputation_engine.compute_reputation_modifier(npc_id=_nid)
                
                if hasattr(_svc, 'economic_profiles'):
                    _economic_profiles_map[_nid] = _svc.economic_profiles.get(_nid)
                
                _cstore = getattr(_svc, 'crystallized_belief_store', None)
                if _cstore:
                    _crystallized_beliefs_map[_nid] = _cstore.get_beliefs(npc_id=_nid)

        _tick_state = create_tick_state(
            tick_id=ctx.tick_number,
            campaign_id=ctx.campaign_id,
            scene_state=ctx.scene_state,
            all_npcs_raw=_alive_npcs,
            effective_drives_map=ctx.effective_drives_map,
            pe_modifiers_map=_pe_mods_map,
            interventions=ctx.interventions,
            hub_event=_dm_ctx.hub_event if _dm_ctx else None,
            player_target_id=_dm_ctx.player_target_id if _dm_ctx else None,
            action_type=_dm_ctx.action_type if _dm_ctx else "idle",
            raw_input=_dm_ctx.raw_input if _dm_ctx else "",
            is_session_start=_dm_ctx.is_session_start if _dm_ctx else False,
            nearby_npcs=_dm_ctx.nearby_npcs if _dm_ctx else ctx.all_npcs_raw,
            line_of_sight=_dm_ctx.line_of_sight if _dm_ctx else {n.get("id", n.get("npc_id")): True for n in ctx.all_npcs_raw},
            scene_continuity=_dm_ctx.scene_continuity if _dm_ctx else None,
            spatial_events=_dm_ctx.spatial_events if _dm_ctx else [],
            drf_tick_id=ctx.tick_number,
            memory_weights_map=_memory_weights_map,
            narrative_cache_map=_narrative_cache_map,
            social_modifiers_map=_social_modifiers_map,
            reputation_modifiers_map=_reputation_modifiers_map,
            economic_profiles_map=_economic_profiles_map,
            crystallized_beliefs_map=_crystallized_beliefs_map,
            identity_traits_map=_identity_traits_map,
            relationship_store=_svc.relationship_store if _svc else None,
            spatial_service=_svc.spatial_service if _svc else None,
            spatial_query=_svc.spatial_query if _svc else None,
        )

        _drf_ctx = DRFExecutionContext(tick_id=ctx.tick_number, bus=ctx.drf_bus)
        _mutation: TickMutation = NpcTickPipeline.run(
            state=_tick_state,
            drf_ctx=_drf_ctx,
            rng_factory=ctx.rng_factory
        )

        # TZ-10: Committer — применение отложенных мутаций из TickMutation
        ctx.communication_intents = _mutation.communication_intents or []
        ctx.movement_intents = _mutation.movement_intents or []
        ctx.significant_events = _mutation.npc_deltas or []
        
        # Применение L1 Drift Events (Append-only Chronicle)
        if _mutation.l1_drift_events and _svc and _svc.memory_manager:
            for _event in _mutation.l1_drift_events:
                _svc.memory_manager.l1_chronicle.append(_event)
        
        # Применение Memory Events (STM/L2 update)
        if _mutation.memory_events and _svc and _svc.memory_manager:
            for _mem_evt in _mutation.memory_events:
                # События памяти применяются к контексту, но состояние будет обновлено в Фазе 9
                ctx.event_bus.publish(_mem_evt) if hasattr(ctx, 'event_bus') else None

        # 4. Committer: Применение мутаций к контексту
        ctx.communication_intents = _mutation.communication_intents or []
        ctx.movement_intents = _mutation.movement_intents or []
        ctx.significant_events = _mutation.npc_deltas or []
        # TODO: Полная обработка npc_deltas через StateApplicator将在 Phase 4

        # SHI-FIX: Построение ctx.npc_contexts из communication_intents.
        # Без этого R3_DIRECT получает 0 decisions → DM видит пустой мир → "Ничего не произошло".
        # TickMutation не содержит npc_contexts (только comm_intents), поэтому маппим здесь.
        # CommunicationIntent имеет .speaker/.topic, а R3_DIRECT ждёт .npc_id/.intent/.deltas —
        # создаём _DecisionResultAdapter.
        if ctx.communication_intents:
            from app.models.npc_state import personality_from_legacy
            from app.models.npc_state import Intent as NpcIntent
            from app.models.state_delta import StateDeltas, DeltaDomain
            from app.models.delta_payloads import IdentityPayload
            from dataclasses import dataclass

            @dataclass
            class _DecisionResultAdapter:
                """Адаптер CommunicationIntent → интерфейс DecisionResult для R3_DIRECT."""
                npc_id: str
                intent: Any
                intent_target: str = "player"
                score: float = 0.5
                deltas: Any = None
                communication: Any = None
                decision: Any = None
                narrative_fact: Optional[str] = None
                micro_event: Optional[str] = None

            for _intent in ctx.communication_intents:
                _speaker = getattr(_intent, 'speaker', '') or getattr(_intent, 'npc_id', '')
                if not _speaker:
                    continue
                _npc_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _speaker or n.get("id") == _speaker), None)
                if not _npc_dict:
                    continue
                _profile_l0 = personality_from_legacy(_npc_dict)
                _topic = getattr(_intent, 'topic', '') or getattr(_intent, 'intent_type', '')
                _intent_type_str = getattr(_intent, 'intent_type', 'диалог').lower()
                _npc_intent = NpcIntent.TALK
                try:
                    if "угроз" in _intent_type_str or "threat" in _intent_type_str:
                        _npc_intent = NpcIntent.THREATEN
                    elif "atan" in _intent_type_str or "attack" in _intent_type_str:
                        _npc_intent = NpcIntent.ATTACK
                    elif "бег" in _intent_type_str or "flee" in _intent_type_str:
                        _npc_intent = NpcIntent.FLEE
                except Exception as e:
                    logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
                _empty_deltas = StateDeltas(
                    npc_id=_speaker, domain=DeltaDomain.IDENTITY,
                    payload=IdentityPayload(), source="communication_intent_adapter",
                )
                _adapter = _DecisionResultAdapter(
                    npc_id=_speaker, intent=_npc_intent,
                    intent_target=getattr(_intent, 'target_id', 'player') or 'player',
                    score=0.5, deltas=_empty_deltas, communication=_intent, decision=None,
                )
                ctx.npc_contexts.append({
                    "npc_id": _speaker,
                    "tier": _profile_l0.tier if _profile_l0 else "minor",
                    "profile_l0": _profile_l0,
                    "topic": _topic,
                    "decision_result": _adapter,
                    "observed_state": {
                        "name": _npc_dict.get("name", _speaker),
                        "description": _npc_dict.get("description", ""),
                        "narrative_cache": _npc_dict.get("narrative_cache", []),
                    },
                    "micro_events": [],
                    "perceived_events": [],
                    "communication_intent": _intent,
                })
        
        # Каузальный мост: когнитивные решения → пространственное движение
        if ctx.movement_intents:
            from app.services.spatial.movement_engine import MovementEngine
            from app.domain.movement import MacroMovementGoal, LocalSteeringGoal
            
            _merged_intents = []
            _per_npc = {}
            for i in ctx.movement_intents:
                _nid = getattr(i, 'npc_id', None)
                if _nid: _per_npc.setdefault(_nid, []).append(i)
                else: _merged_intents.append(i)
                
            for _nid, _intents in _per_npc.items():
                if len(_intents) > 1:
                    _intents.sort(key=lambda x: isinstance(x, LocalSteeringGoal))
                _merged_intents.extend(_intents)
            
            _spatial_svc = self._resolve_spatial_service(ctx)
            if _spatial_svc:
                self._apply_drf_scoring_overlay(_merged_intents, ctx)
                me = MovementEngine()
                me.set_spatial_service(_spatial_svc)
                spatial_changes = me.process_intents(
                    _merged_intents, tick=ctx.tick_number,
                    npc_positions=ctx.scene_state.get("npc_positions", {}),
                    campaign_id=ctx.campaign_id, scene_state=ctx.scene_state
                )
                if spatial_changes and self._scene_manager:
                    self._apply_with_shadow_observation(ctx, spatial_changes, phase_label="CAUSAL_BRIDGE")
            else:
                logger.error("[SPATIAL_AUTHORITY] SpatialService missing in Phase 5")

    def _phase_6_post_decision(self, ctx: _TickContext) -> None:
        """IntentEventAdapter: CommunicationIntent → EventDTO (Устав §3.3).
        
        Единственная легальная точка CommunicationIntent → EventDTO.
        Когда Phase 5 начнёт производить CommunicationIntent — провода уже готовы.
        ADR-O-310: WindupWriteGate — перехват ATTACK для создания ActionWindup.
        """
        if not ctx.communication_intents:
            return

        bus = get_event_bus()
        adapter = IntentEventAdapter()
        converted = 0
        windups_created = 0

        for intent in ctx.communication_intents:
            event = adapter.to_event(intent)
            
            # ADR-O-310: Windup Write Gate
            if getattr(intent, 'intent_type', '') == "attack":
                from app.domain.action_windup import ActionWindup, WindupStatus, ActionCommitment
                _actor_id = getattr(intent, 'speaker', '')
                _target_id = getattr(intent, 'target_id', '')
                
                if _actor_id and _target_id:
                    # B1.5-FIX: Изоляция по campaign_id (ключ - кортеж).
                    _reg_key = (ctx.campaign_id, _actor_id)
                    if _reg_key not in self._windup_registry:
                        self._windup_registry[_reg_key] = []
                    
                    # B1.5-FIX: Защита от накопления (Deduplication).
                    _has_active = any(
                        w.target_id == _target_id and w.action_type == "attack" and w.status == WindupStatus.PENDING
                        for w in self._windup_registry[_reg_key]
                    )
                    
                    if not _has_active:
                        import uuid
                        # DEBT-310.1: Сохраняем сам интент, генерируем ID для него.
                        _intent_id = uuid.uuid4().hex
                        self._pending_intents[_intent_id] = intent
                        
                        # Создаём окно подготовки (пока статичная длительность = 2 тика для тестов)
                        windup = ActionWindup(
                            actor_id=_actor_id,
                            target_id=_target_id,
                            action_type="attack",
                            started_tick=ctx.tick_number,
                            duration_ticks=2,
                            status=WindupStatus.PENDING,
                            held_intent_id=_intent_id # DEBT-310.1: Pure temporal gate
                        )
                        # Добавляем в стек подготовок актёра (на уровне Orchestrator)
                        self._windup_registry[_reg_key].append(windup)
                        windups_created += 1
                        
                        # ADR-O-310: НЕ публикуем EventDTO сейчас. Он будет опубликован в Фазе 7.
                        continue # Пропускаем bus.publish(event) ниже
            
            bus.publish(event)
            converted += 1

        logger.info(f"[TICK_ORCH] Фаза 6: {converted} intents → EventDTO, {windups_created} windups created")

    def _phase_7_windup_resolution(self, ctx: _TickContext) -> None:
        """ADR-O-310: Windup Execution Gate.
        
        Проверяет self._windup_registry на завершённые подготовки.
        Если windup завершён (started_tick + duration_ticks <= ctx.tick_number),
        реконструирует CommunicationIntent из ActionCommitment и передаёт в IntentEventAdapter.
        """
        import dataclasses
        from app.domain.action_windup import WindupStatus
        from app.services.events.intent_event_adapter import IntentEventAdapter
        
        bus = get_event_bus()
        adapter = IntentEventAdapter()
        executed_windups = 0
        
        for _reg_key, windups in list(self._windup_registry.items()):
            _campaign_id, _actor_id = _reg_key
            if _campaign_id != ctx.campaign_id:
                continue
                
            updated_windups = []
            for windup in windups:
                if windup.status == WindupStatus.PENDING:
                    if windup.started_tick + windup.duration_ticks <= ctx.tick_number:
                        # DEBT-310.1: Windup completed! Pure release of held intent.
                        if windup.held_intent_id:
                            _held_intent = self._pending_intents.pop(windup.held_intent_id, None)
                            if _held_intent:
                                _actor_id = getattr(_held_intent, 'speaker', '')
                                _target_id = getattr(_held_intent, 'target_id', '')
                                
                                # DEBT-310.2: Minimal Guard - Stale Intent Validation
                                _is_stale = False
                                _reason = ""
                                
                                # 1. Actor validation
                                _actor_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _actor_id or n.get("id") == _actor_id), None)
                                if not _actor_dict:
                                    _is_stale, _reason = True, "actor_missing"
                                elif _actor_dict.get("body_state", {}).get("life_status") == "DEAD":
                                    _is_stale, _reason = True, "actor_dead"
                                    
                                # 2. Target validation (if actor is valid)
                                if not _is_stale and _target_id:
                                    if _target_id == "player":
                                        if "player" not in ctx.scene_state.get("npc_positions", {}):
                                            _is_stale, _reason = True, "target_player_missing"
                                    else:
                                        _target_dict = next((n for n in ctx.all_npcs_raw if n.get("npc_id") == _target_id or n.get("id") == _target_id), None)
                                        if _target_dict and _target_dict.get("body_state", {}).get("life_status") == "DEAD":
                                            _is_stale, _reason = True, "target_dead"
                                        elif not _target_dict and _target_id not in ctx.scene_state.get("npc_positions", {}):
                                            _is_stale, _reason = True, "target_missing"
                                
                                if _is_stale:
                                    logger.info(f"[PHASE_7][STALE_INTERRUPT] npc={_actor_id} target={_target_id} reason={_reason}")
                                    windup = dataclasses.replace(windup, status=WindupStatus.INTERRUPTED)
                                else:
                                    event = adapter.to_event(_held_intent)
                                    bus.publish(event)
                                    executed_windups += 1
                                    windup = dataclasses.replace(windup, status=WindupStatus.COMPLETED)
                            else:
                                windup = dataclasses.replace(windup, status=WindupStatus.COMPLETED)
                        else:
                            windup = dataclasses.replace(windup, status=WindupStatus.COMPLETED)
                if windup.status == WindupStatus.PENDING:
                    updated_windups.append(windup)
            
            self._windup_registry[_reg_key] = [w for w in updated_windups if w.status == WindupStatus.PENDING]

        if executed_windups > 0:
            logger.info(f"[TICK_ORCH] Фаза 7: {executed_windups} windups executed (EventDTO published)")

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
        import sys
        logger.debug(f"[P9_DIAG] _phase_9 ENTERED. shared_context is None: {ctx.shared_context is None}")
        if ctx.shared_context is None:
            logger.debug("[P9_DIAG] ABORT: shared_context is None!")
            return

        # TZ-08 v0.2: dm_frame вынесен в game_loop. Здесь только работа с памятью NPC.
        from app.services.memory.working_memory_tick import write_npc_reactions_to_memory, run_decay_and_resonance
        if ctx.shared_context and ctx.shared_context.npc_contexts:
            write_npc_reactions_to_memory(
                self._get_memory_manager(),
                ctx.shared_context.npc_contexts,
                ctx.all_npcs_raw,
                ctx.campaign_id,
            )

        # Decay через TemporalContext — единое расписание (Устав §8)
        _temporal = self._get_life_engine().get_temporal_context(ctx.campaign_id)
        run_decay_and_resonance(
            self._get_memory_manager(), ctx.campaign_id, _temporal,
            ctx.shared_context.active_npc_ids if ctx.shared_context else [],
        )
        # Фиксируем выполнение decay, чтобы счётчик сбросился
        if _temporal.should_run_memory_decay:
            self._get_life_engine().mark_decay_executed(ctx.campaign_id)

        # ADR-049: Аффективный pipeline перенесён в tick_player_turn (SEL CRITICAL FIX).
        # Больше не зависит от guard-условия shared_context в этом методе.

    def _phase_10_player_persistence(self, ctx: _TickContext) -> None:
        """Player turn: atomic commit (Устав §10 — Persistence).

        Единственная точка коммита за тик (Устав §4.2.1).
        """
        # DRF Observer: Схлопываем и логируем поле причинных напряжений ПЕРЕД коммитом
        logger.debug(f"[DRF_DRAIN_BUS] bus_id={id(ctx.drf_bus)} stream_size={len(ctx.drf_bus.stream)}")
        _claims = ctx.drf_bus.drain()
        if _claims:
            from collections import defaultdict
            _npc_claims = defaultdict(list)
            for c in _claims:
                _npc_claims[c.get("target_npc", "unknown")].append(f"{c.get('pressure_type', '?')}:{c.get('vector', '?')}({c.get('energy', 0.0):.1f})")
            for npc, claims_str in _npc_claims.items():
                logger.debug(f"[DRF_FIELD] npc={npc} pressures={claims_str}")
        else:
            # [DRF_FIELD] claim_field is EMPTY this tick
            pass
        if ctx.shared_context is None:
            return

        # DSTC: Мутируем M₀ IN-PLACE, сохраняя идентичность списка для всех держателей ссылок.
        # Присваивание среза гарантирует, что никто не останется со ссылкой на мёртвый M₀.
        if ctx.interpretation_snapshot is not None:
            ctx.all_npcs_raw[:] = ctx.interpretation_snapshot
            ctx.interpretation_snapshot = None

        # Flush: применяем остатки дельт (если Pipeline не забрал их в interpretation_snapshot)
        if ctx.delta_buffer:
            _aggregated = self._aggregate_deltas(ctx.delta_buffer)
            if _aggregated and self._state_applicator:
                self._state_applicator.apply_batch(
                    _aggregated, ctx.all_npcs_raw, ctx.campaign_id
                )
                ctx.delta_buffer.clear()

        # SIL: Reconciliation S → M. Сбрасываем semantic_buffer в all_npcs_raw.
        # SIL: Reconciliation S → M. Сбрасываем semantic_buffer в all_npcs_raw.
        if ctx.semantic_buffer and ctx.all_npcs_raw:
            for npc_dict in ctx.all_npcs_raw:
                nid = npc_dict.get("npc_id") or npc_dict.get("id")
                if nid in ctx.semantic_buffer:
                    frame = ctx.semantic_buffer[nid]
                    if frame.emotion_tag is not None:
                        npc_dict["emotion"] = frame.emotion_tag
                    if frame.affective_load is not None:
                        npc_dict["affective_load"] = frame.affective_load
            ctx.semantic_buffer.clear()

        # RCG: Flush scene_changes buffer through apply_changes before commit
        if ctx.scene_changes and self._scene_manager:
            self._scene_manager.apply_changes(ctx.campaign_id, ctx.scene_changes, ctx.shared_context.scene_state)
            ctx.scene_changes.clear()

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
        # S91: Очистка истекших деформаций среды (Temporalization Layer)
        self._dynamic_field.purge_hard_overrides(current_tick=ctx.tick_number)
        self._dynamic_field.step_decay()   
        
        # S-93: PE Decay (Per-Tick, Elastic Time).
        # Инвариант: PE остаётся строго индивидуальным bias-layer.
        # Ожидания затухают со временем, привязанным к game_time_seconds.
        if hasattr(self, '_expectation_store') and self._expectation_store is not None:
            from app.core.constants import GAME_TICK_INTERVAL_SECONDS
            # Берем dt из разницы времени, или фоллбэк на константу тика (5 сек)
            _dt_game = ctx.scene_state.get("game_time_seconds", 0)
            _prev_time = ctx.scene_state.get("prev_game_time_seconds", _dt_game - GAME_TICK_INTERVAL_SECONDS)
            _delta_dt = max(0.1, _dt_game - _prev_time)
            self._expectation_store.decay(_delta_dt)

        # ADR-036 / ADR-O-302: Affective Decay (Leaky Integrator для памяти)
        # Травмы затухают со временем, если не подкрепляются.
        from app.services.affect import decay_affective_imprints
        from app.models.affect import AffectiveImprint
        from app.core.constants import GAME_TICK_INTERVAL_SECONDS
        from dataclasses import asdict
        _current_time = ctx.scene_state.get("game_time_seconds", 0)
        for npc_dict in ctx.all_npcs_raw:
            imp_dicts = npc_dict.get("affective_imprints", [])
            if not imp_dicts: continue
            try:
                imprints = tuple(AffectiveImprint(**imp) for imp in imp_dicts)
                # ADR-O-302: delta_time = GAME_TICK_INTERVAL_SECONDS (60 сек). Магическое число 5.0 убито.
                decayed = decay_affective_imprints(imprints, float(GAME_TICK_INTERVAL_SECONDS), _current_time)
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
            logger.debug(f"[AFF_DEBUG] handlers={[type(h).__name__ for h in self._idle_handlers]} aff_load={_sample.get('affective_load', '<MISSING>')} emo={_sample.get('emotion', '<MISSING>')}")

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
                # SHI-FIX: L1Chronicle emission for decay
                if hasattr(handler, 'name') and handler.name == "physiology_decay":
                    if hasattr(self, "l1_chronicle") and self.l1_chronicle is not None:
                        _decay_events = []
                        for _d in deltas:
                            if _d.npc_id and (abs(getattr(_d.payload, 'pain_delta', 0.0)) > 0 or abs(getattr(_d.payload, 'blood_loss_delta', 0.0)) > 0):
                                 _decay_events.append(TraitDriftEvent(tick_id=ctx.tick_number, target_id=_d.npc_id,
                                                               source_id="physiology_decay", effect_value=-0.01, observation_weight=1.0, event_type="decay"))
                        if _decay_events:
                            self.l1_chronicle.commit_tick_buffer(_decay_events, ctx.tick_number)

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
            _combat_l1_events = [] # SHI-FIX: L1Chronicle emission for attack/damage
            for d in (combat_result.deltas or []):
                if d.domain == DeltaDomain.PHYSIOLOGY and d.payload and isinstance(d.payload, PhysiologyPayload):
                    _target = d.npc_id or d.target or "unknown"
                    _combat_data[_target] = {
                        "pain_delta": d.payload.pain_delta,
                        "blood_loss_delta": d.payload.blood_loss_delta,
                        "shock_impulse": d.payload.shock_impulse,
                        "injuries": [{"zone": i.target_zone, "severity": i.structural_damage, "damage_type": i.damage_type} for i in d.payload.add_injuries] if d.payload.add_injuries else []
                    }
                    # SHI-FIX: L1Chronicle emission for attack/damage
                    if d.payload.hp_delta < 0 or d.payload.add_injuries:
                        _combat_l1_events.append(TraitDriftEvent(tick_id=ctx.tick_number, target_id=_target, source_id="player", effect_value=-0.2, observation_weight=1.0, event_type="attack"))
                        _combat_l1_events.append(TraitDriftEvent(tick_id=ctx.tick_number, target_id=_target, source_id="combat", effect_value=d.payload.hp_delta, observation_weight=1.0, event_type="damage"))
            
            # SHI-FIX: Commit L1 events
            if _combat_l1_events and hasattr(self, "l1_chronicle") and self.l1_chronicle is not None:
                self.l1_chronicle.commit_tick_buffer(_combat_l1_events, ctx.tick_number)

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

        # DSTC: Удалён досрочный apply_batch (S75-FIX).
        # Дельты останутся в delta_buffer и будут применены к interpretation_snapshot в Phase 9.

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
            ctx.npc_contexts
            if ctx.npc_contexts
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
                ctx.npc_contexts
                if ctx.npc_contexts
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

            # S91: Эмит стигмергического следа (safety_confidence) при акте насилия
            if handler_name == "combat":
                from app.domain.motion_core import TracePayload
                _loc_id = ctx.scene_state.get("location_id", "")
                _svc = self._resolve_spatial_service(ctx)
                for delta in result.deltas:
                    if delta.domain == DeltaDomain.PHYSIOLOGY:
                        _target_id = getattr(delta, 'npc_id', None)
                        if _target_id and _svc:
                            _pos_data = ctx.scene_state.get("npc_positions", {}).get(_target_id, {})
                            _pos = _pos_data.get("local_position", {})
                            _zone_id = _svc.get_zone_id(_pos.get("x", 0.0), _pos.get("y", 0.0))
                            if _zone_id:
                                _trace = TracePayload(
                                    region=_loc_id,
                                    zone_id=_zone_id,
                                    trace_type="safety_confidence", # Насилие снижает безопасность
                                    magnitude=-0.2, # Отрицательное значение (снижает уверенность)
                                    created_tick=ctx.tick_number,
                                    ttl=100, # След насилия остывает дольше
                                    source_id="combat"
                                )
                                self._dynamic_field.apply_trace(_trace)

        # Legacy: prop_dirty от старых обработчиков (совместимость)
        if result.prop_dirty:
            ctx.prop_dirty = True

    def _phase_9_integration(self, ctx: _TickContext) -> None:
        """CFRM P2: Вычисление локальной реальности + WorldSnapshotBuilder."""
        
        # DSTC: Создание канонического среза реальности (Snapshot Barrier).
        # M₀ (all_npcs_raw) остаётся нетронутым. Дельты применяются к interpretation_snapshot.
        # Это даёт Phase 9 актуальную физику без разрушения исходного состояния тика.
        import copy
        if ctx.interpretation_snapshot is None:
            ctx.interpretation_snapshot = copy.deepcopy(ctx.all_npcs_raw)
            if ctx.delta_buffer and self._state_applicator:
                _aggregated = self._aggregate_deltas(ctx.delta_buffer)
                if _aggregated:
                    self._state_applicator.apply_batch(
                        _aggregated, ctx.interpretation_snapshot, ctx.campaign_id
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
                        
                        # ADR-O-208: Смерть npc_raw["drives"]. 
                        # Котёл читает ТОЛЬКО эфемерную проекцию из DriveResolver (L0 + L1).
                        # ВНИМАНИЕ: блок перенесён ВЫШЕ compute_continuous_drift —
                        # TIFL требует _drives_projection и _psyche_raw на вход.
                        from app.models.npc_state import personality_from_legacy
                        _profile_l0 = personality_from_legacy(npc_raw)
                        _beliefs = self.crystallized_belief_store.get_beliefs(entity_id)
                        _drives_projection = self.drive_resolver.resolve_drives(_profile_l0, _beliefs)

                        _psyche_raw = npc_raw.get("psyche", {})
                        psyche = {
                            "fear": _drives_projection.get("fear", 0.25),
                            "control": _drives_projection.get("control", 0.25),
                            "significance": _drives_projection.get("significance", 0.25),
                            "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
                        }

                        # Active Inference: prediction error для TIFL
                        _drive_fear = _drives_projection.get("fear", 0.25)
                        _drive_control = _drives_projection.get("control", 0.25)
                        _drive_significance = _drives_projection.get("significance", 0.25)
                        
                        # ADR-O-208 / L3-P2: TIFL получает эфемерную проекцию, а не сырой стейт
                        from app.services.npc.break_progress_engine import compute_continuous_drift
                        _rigidity = _psyche_raw.get("identity_rigidity", 0.5) if _psyche_raw else 0.5
                        
                        # Легковесная проекция ядра для TIFL (на основе дельт)
                        _pk_load_for_tifl = min(1.0,
                            perception_payload.threat_gradient_delta * _drive_fear +
                            perception_payload.uncertainty_delta * _drive_control +
                            perception_payload.anomaly_score_delta * _drive_significance
                        )
                        _prev_memory = float(npc_raw.get("affective_memory", 0.0))
                        _delta = _pk_load_for_tifl - _prev_memory
                        _abs_error = abs(_delta)
                        _error_vector = {"fear": 0.33, "control": 0.33, "significance": 0.33}
                        if _abs_error > 0.05:
                            _w_fear = perception_payload.threat_gradient_delta * _drive_fear
                            _w_control = perception_payload.uncertainty_delta * _drive_control
                            _w_signif = perception_payload.anomaly_score_delta * _drive_significance
                            _total_w = _w_fear + _w_control + _w_signif + 1e-6
                            _error_vector = {
                                "fear": _w_fear / _total_w,
                                "control": _w_control / _total_w,
                                "significance": _w_signif / _total_w,
                            }

                        _drift_events = compute_continuous_drift(
                            effective_drives=_drives_projection,
                            npc_id=entity_id,
                            rigidity=_rigidity,
                            prediction_error=_abs_error,
                            error_vector=_error_vector,
                            current_tick=ctx.tick_number
                        )
                        if _drift_events:
                            self.l1_chronicle.commit_tick_buffer(_drift_events, ctx.tick_number)

                        pk_dict = npc_raw.get("perceptual_kernel", {})
                        _body_idle = npc_raw.get("body_state") or {}
                        _pain_norm_idle = float(_body_idle.get("pain", 0.0)) / 100.0
                        _shock_norm_idle = float(_body_idle.get("shock_impulse", 0.0))
                        _somatic_urg_idle = (_pain_norm_idle + _shock_norm_idle) / 2.0

                        projected_kernel = PerceptualKernel(
                            threat_gradient=min(1.0, max(0.0, pk_dict.get("threat_gradient", 0.0) + perception_payload.threat_gradient_delta)),
                            uncertainty=min(1.0, max(0.0, pk_dict.get("uncertainty", 0.0) + perception_payload.uncertainty_delta)),
                            anomaly_score=min(1.0, max(0.0, pk_dict.get("anomaly_score", 0.0) + perception_payload.anomaly_score_delta)),
                            compliance_bias=pk_dict.get("compliance_bias", 0.0),
                            aggression_inhibition=pk_dict.get("aggression_inhibition", 0.0),
                            initiative_suppression=pk_dict.get("initiative_suppression", 0.0),
                            somatic_urgency=_somatic_urg_idle,
                        )
                        
                        from app.domain.perception import ProjectionFrame
                        if "_projection_frames" not in locals():
                            _projection_frames = []
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

                        # ADR-049: Единый интегратор аффективного давления
                        current_load = float(npc_raw.get("affective_load", 0.0))
                        current_memory = float(npc_raw.get("affective_memory", 0.0))
                        new_load, new_memory = integrate_affective_pressure(
                            kernel=projected_kernel,
                            psyche=psyche,
                            current_load=current_load,
                            current_memory=current_memory
                        )
                        
                        emotion_payload = resolve_emotion_transition(new_load, current_load, psyche)
                        
                        # §ENIGMA-DUAL-CIRCUIT: Sustaining Loop УБИТ (S73).
                        # Эмоция не удерживается искусственно при высоком load.
                        # Если EmotionTransition не дал фазового перехода — эмоция = neutral.
                        # Это обнажает честную динамику для диагностики S73-R1.
                        
                        if emotion_payload:
                            # SHI-FIX: L1Chronicle emission for fear
                            if hasattr(self, "l1_chronicle") and self.l1_chronicle is not None:
                                _emo_tag = getattr(emotion_payload, 'emotion_tag', None)
                                if _emo_tag and hasattr(_emo_tag, 'value') and 'fear' in _emo_tag.value:
                                    self.l1_chronicle.commit_tick_buffer([
                                        TraitDriftEvent(tick_id=ctx.tick_number, target_id=entity_id,
                                                       source_id="combat", effect_value=0.2, observation_weight=1.0, event_type="fear")
                                    ], ctx.tick_number)
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

        # L1.5 / L2.5: Pattern Detection & Belief Crystallization (ADR-O-305)
        # Запускается ПОСЛЕ аффективного цикла, до сборки снапшота.
        _npc_truth_source = ctx.interpretation_snapshot if ctx.interpretation_snapshot is not None else ctx.all_npcs_raw
        for npc_dict in _npc_truth_source:
            _npc_id = npc_dict.get("npc_id")
            if not _npc_id: continue
            
            # L1: Чтение сырой хроники
            _l1_events = self.l1_chronicle.query_raw(_npc_id)
            if not _l1_events: continue
            
            # L1.5: Детектирование паттернов (чистая статистика)
            _evidence_list = self.pattern_detector.detect(_l1_events)
            if not _evidence_list: continue
            
            # L0: Извлечение базовых драйвов для модуляции
            _drives_base = npc_dict.get("drives", npc_dict.get("psyche", {}).get("drives_base", {}))
            if not _drives_base: 
                _drives_base = {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
            
            # L2.5: Кристаллизация убеждений (проекция через личность)
            _existing_beliefs = self.crystallized_belief_store.get_beliefs(_npc_id)
            _updated_beliefs = self.belief_engine.crystallize(
                evidence_list=_evidence_list,
                drives_base=_drives_base,
                existing_beliefs=_existing_beliefs,
                current_tick=ctx.tick_number
            )
            self.crystallized_belief_store.update_beliefs(_npc_id, _updated_beliefs)

        # WorldSnapshotBuilder: собирает WorldSnapshotDTO из финального state
        # ADR-035: Трансляция стейта аватара в феноменологическую проекцию
        from app.services.presentation.avatar_presentation_assembler import assemble_avatar_presentation
        # DSTC: Читаем NPC из interpretation_snapshot (M₀ + deltas), а не из M₀.
        _npc_truth_source = ctx.interpretation_snapshot if ctx.interpretation_snapshot is not None else ctx.all_npcs_raw
        player_dict = next((n for n in _npc_truth_source if n.get("npc_id") == "player"), None)
        _avatar_projection = assemble_avatar_presentation(player_dict) if player_dict else None

        # TZ-08 v0.2: Perception pipeline — internal causal observability layer (post-mutation).
        # Формирует модель наблюдаемости мира на основе state_t+1.
        if not hasattr(self, '_manifest_svc'):
            from app.services.perception.behavior_manifestation_service import BehaviorManifestationService
            from app.services.perception.phenomenology_projection_service import PhenomenologyProjectionService
            self._manifest_svc = BehaviorManifestationService()
            self._project_svc = PhenomenologyProjectionService()
            
        _traces = self._manifest_svc.produce_traces(ctx.scene_state, all_npcs_raw=_npc_truth_source)
        _player_perception = self._project_svc.project(_traces, ctx.scene_state, tick=ctx.tick_number)

        builder = self._get_snapshot_builder()
        ctx.world_snapshot = builder.build(
            scene_state=ctx.scene_state,
            tick=ctx.tick_number,
            avatar_state=_avatar_projection,
            all_npcs_raw=ctx.all_npcs_raw,
            player_perception=_player_perception,
        )

    def _run_affective_pipeline(self, ctx: _TickContext) -> None:
        """ADR-049: Аффективный аккумулятор — накопление давления и фазовый переход эмоций.
        
        Вызывается из ОБЕИХ путей (idle + player turn).
        Без этого affective_load не растёт при player turn → emotion=NEUTRAL → _emotion_modifier()=0.0.
        """
        import sys
        logger.debug(f"[SEL_DIAG] _run_affective_pipeline ENTERED. Snapshot is None: {ctx.interpretation_snapshot is None}")
        # DSTC: Ленивое создание interpretation_snapshot, если Pipeline вызван до Phase 9 (например, в player turn)
        import copy
        if ctx.interpretation_snapshot is None:
            ctx.interpretation_snapshot = copy.deepcopy(ctx.all_npcs_raw)
            if ctx.delta_buffer and self._state_applicator:
                _aggregated = self._aggregate_deltas(ctx.delta_buffer)
                if _aggregated:
                    self._state_applicator.apply_batch(
                        _aggregated, ctx.interpretation_snapshot, ctx.campaign_id
                    )
                ctx.delta_buffer.clear()

        if not ctx.interpretation_snapshot:
            logger.debug("[AFFECTIVE_PLAYER] SKIP: interpretation_snapshot is empty")
            return

        from app.services.affective.affective_integrator import integrate_affective_pressure
        from app.services.affective.emotion_transition import resolve_emotion_transition, THRESHOLD_ANXIOUS, THRESHOLD_FEARFUL, THRESHOLD_PANIC
        from app.models.npc_state import PerceptualKernel
        from app.models.delta_payloads import EmotionPayload, PerceptionPayload
        from app.models.state_delta import StateDeltas, DeltaDomain
        from dataclasses import replace as dataclass_replace

        _snap_len = len(ctx.interpretation_snapshot) if ctx.interpretation_snapshot else 0
        logger.debug(f"[SEL_DIAG] Entering NPC loop. Snapshot count: {_snap_len}")
        # DSTC: Читаем ONLY из interpretation_snapshot (M₀ + deltas)
        # DSTC: Читаем ONLY из interpretation_snapshot (Pure Read)
        for npc_raw in ctx.interpretation_snapshot:
            entity_id = npc_raw.get("npc_id") or npc_raw.get("id")
            if not entity_id or entity_id == "player":
                continue  # Игрок не проходит аффективный pipeline

            pk_dict = npc_raw.get("perceptual_kernel", {})
            _psyche_raw = npc_raw.get("psyche", {})

            # ADR-O-208: Смерть npc_raw["drives"]. 
            # Котёл читает ТОЛЬКО эфемерную проекцию из DriveResolver (L0 + L1).
            from app.models.npc_state import personality_from_legacy
            _profile_l0 = personality_from_legacy(npc_raw)
            _beliefs = self.crystallized_belief_store.get_beliefs(entity_id)
            _drives_projection = self.drive_resolver.resolve_drives(_profile_l0, _beliefs)

            # S72: Drives Projection как Линза Реальности.
            _drive_fear = _drives_projection.get("fear", 0.25)
            _drive_control = _drives_projection.get("control", 0.25)
            _drive_significance = _drives_projection.get("significance", 0.25)

            psyche = {
                "fear": _drive_fear,
                "control": _drive_control,
                "significance": _drive_significance,
                "willpower": min(1.0, _psyche_raw.get("willpower", 50) / 100.0),
            }

            # ADR-O-143: Somatic urgency из body_state для PerceptualKernel.
            # Боль/шок проходят через PK.somatic_urgency и модулируются личностью в integrator.
            _body = npc_raw.get("body_state") or {}
            _pain_norm = float(_body.get("pain", 0.0)) / 100.0  # ADR-094: 0-100 → 0-1
            _shock_norm = float(_body.get("shock_impulse", 0.0))  # уже 0-1
            _somatic_urg = (_pain_norm + _shock_norm) / 2.0

            # Проекция ядра: текущее состояние (без delta — delta уже применена в idle tick)
            projected_kernel = PerceptualKernel(
                threat_gradient=pk_dict.get("threat_gradient", 0.0),
                uncertainty=pk_dict.get("uncertainty", 0.0),
                anomaly_score=pk_dict.get("anomaly_score", 0.0),
                compliance_bias=pk_dict.get("compliance_bias", 0.0),
                aggression_inhibition=pk_dict.get("aggression_inhibition", 0.0),
                initiative_suppression=pk_dict.get("initiative_suppression", 0.0),
                somatic_urgency=_somatic_urg,  # ADR-O-143: воспринимаемый телесный дистресс
            )

            # S73-DIAG: Проверка очага аффекта. Видит ли пайплайн боль от удара?
            if entity_id in ("thief_shadow", "guard_borko"):
                logger.debug(f"[AFF_SOURCE] npc={entity_id} pain_raw={_body.get('pain', 0.0)} shock_raw={_body.get('shock_impulse', 0.0)} somatic_urg={_somatic_urg:.3f} prev_aff={npc_raw.get('affective_load', 0.0)} emo={npc_raw.get('emotion', '?')}")

            # ADR-049: Единый интегратор аффективного давления
            current_load = float(npc_raw.get("affective_load", 0.0))
            current_memory = float(npc_raw.get("affective_memory", 0.0))
            new_load, new_memory = integrate_affective_pressure(
                kernel=projected_kernel,
                psyche=psyche,
                current_load=current_load,
                current_memory=current_memory
            )
            
            if entity_id in ("thief_shadow", "guard_borko", "merchant_goran"):
                logger.debug(f"[TIFL_PROBE] npc={entity_id} new_load={new_load:.3f} new_mem={new_memory:.3f}", file=sys.stderr, flush=True)

            emotion_payload = resolve_emotion_transition(new_load, current_load, psyche)

            # S73-DIAG: Вычислен ли new_load и почему он теряется?
            if entity_id in ("thief_shadow", "guard_borko"):
                logger.debug(f"[AFF_RESULT] npc={entity_id} current={current_load:.3f} new={new_load:.3f} has_transition={emotion_payload is not None}")

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
                # SIL: Изоляция S-слоя. Эмоция не идёт в delta_buffer (M-слой).
                # Она сохраняется в semantic_buffer для T+0 визуализации и Phase 10 persistence.
                ctx.semantic_buffer[entity_id] = SemanticFrame(
                    emotion_tag=emotion_payload.emotion_tag,
                    affective_load=new_load,
                    stress_delta=emotion_payload.stress_delta,
                    tick_id=ctx.tick_number
                )
                logger.debug(f"[SIL_REDIRECT] npc={entity_id} EmotionPayload redirected to semantic_buffer")

            # SEL: Коммит Trace State в M-слой. 
            # Передаём new_load (после интеграции с волей), а не сырой current_load.
            # Это гарантирует, что DecisionHub получит эмоцию, модулированную личностью.
            ctx.delta_buffer.append(StateDeltas(
                npc_id=entity_id,
                domain=DeltaDomain.EMOTION,
                target="system",
                payload=EmotionPayload(
                    affective_load=new_load,
                    affective_memory=new_memory
                ),
                source="sel_trace_commit"
            ))

            # S73-L0: Epistemic Trace (Log-only instrumentation).
            # Фиксируем субъективную проекцию реальности NPC для анализа RSI (Reality Split Index).
            # Не влияет на симуляцию. Позволяет CDS измерять расхождение интерпретаций.
            # S73-DIAG: Отслеживание источника эмоции для диагностики конкуренции контуров
            _e_tag = emotion_payload.emotion_tag if emotion_payload else (npc_raw.get("emotion", "neutral") or "neutral")
            _e_src = "TRANSITION" if emotion_payload else "NONE"
            _prev_src = "memory" if current_memory > 0.01 else "pk"
            _incoming_val = (
                projected_kernel.threat_gradient * _drive_fear +
                projected_kernel.uncertainty * _drive_control +
                projected_kernel.anomaly_score * _drive_significance +
                projected_kernel.somatic_urgency  # ADR-O-143: somatic через PK
            )
            logger.info(
                f"[EPISTEMIC_TRACE] npc={entity_id} "
                f"threat={projected_kernel.threat_gradient:.3f} "
                f"unc={projected_kernel.uncertainty:.3f} "
                f"anom={projected_kernel.anomaly_score:.3f} "
                f"somatic={projected_kernel.somatic_urgency:.3f} "
                f"drives=[f={_drive_fear:.2f},c={_drive_control:.2f},s={_drive_significance:.2f}] "
                f"prev={current_load:.3f}<{_prev_src}> inc={_incoming_val:.3f} "
                f"load={new_load:.3f} emotion={_e_tag} src={_e_src}"
            )

    def _phase_10_persistence(self, ctx: _TickContext) -> None:
        """Atomic commit: SQLite (runtime truth) + YAML (для человека).

        Единственная точка сохранения за тик (Устав §4.2.1).
        Делегирует в SceneStateManager.commit(), который вызывает PersistencePort.atomic_commit().
        В конце вызывает WorldProjectionBuffer для генерации вторичных эффектов (ADR-O-309).
        """
        # DRF Observer: Схлопываем поле причинных напряжений ПЕРЕД коммитом
        logger.debug(f"[DRF_DRAIN_BUS] bus_id={id(ctx.drf_bus)} stream_size={len(ctx.drf_bus.stream)}")
        _claims = ctx.drf_bus.drain()
        if _claims:
            from collections import defaultdict
            _npc_claims = defaultdict(list)
            for c in _claims:
                _npc_claims[c.get("target_npc", c.get("npc_id", "unknown"))].append(f"{c.get('pressure_type', '?')}:{c.get('vector', '?')}({c.get('energy', 0.0):.1f})")
            for npc, claims_str in _npc_claims.items():
                logger.debug(f"[DRF_FIELD] npc={npc} pressures={claims_str}")
        else:
            # [DRF_FIELD] claim_field is EMPTY this tick
            pass

        if self._scene_manager is None:
            logger.warning("[TICK_ORCH] Фаза 10: нет scene_manager — коммит пропущен")
            return

        # DSTC: Мутируем M₀ IN-PLACE, сохраняя идентичность списка для всех держателей ссылок.
        if ctx.interpretation_snapshot is not None:
            ctx.all_npcs_raw[:] = ctx.interpretation_snapshot
            ctx.interpretation_snapshot = None

        # Flush: применяем остатки дельт
        if ctx.delta_buffer:
            _aggregated = self._aggregate_deltas(ctx.delta_buffer)
            if _aggregated and self._state_applicator:
                self._state_applicator.apply_batch(
                    _aggregated, ctx.all_npcs_raw, ctx.campaign_id
                )
                ctx.delta_buffer.clear()

        # SIL: Reconciliation S → M. Сбрасываем semantic_buffer в all_npcs_raw.
        # SIL: Reconciliation S → M. Сбрасываем semantic_buffer в all_npcs_raw.
        if ctx.semantic_buffer and ctx.all_npcs_raw:
            for npc_dict in ctx.all_npcs_raw:
                nid = npc_dict.get("npc_id") or npc_dict.get("id")
                if nid in ctx.semantic_buffer:
                    frame = ctx.semantic_buffer[nid]
                    if frame.emotion_tag is not None:
                        npc_dict["emotion"] = frame.emotion_tag
                    if frame.affective_load is not None:
                        npc_dict["affective_load"] = frame.affective_load
            ctx.semantic_buffer.clear()

        # ADR-117: Синхронизация LifeEngine кэша с мутированными данными
        if ctx.all_npcs_raw:
            engine = self._get_life_engine()
            engine.update_cache(ctx.campaign_id, ctx.all_npcs_raw)

        # Собираем события тика для аудита
        ctx.tick_events = ctx.decision_events  # TODO: расширить spatial + handler events

        # RCG: Flush scene_changes buffer through apply_changes before commit
        if ctx.scene_changes and self._scene_manager:
            self._scene_manager.apply_changes(ctx.campaign_id, ctx.scene_changes, ctx.scene_state)
            ctx.scene_changes.clear()

        saved = self._scene_manager.commit(
            campaign_id=ctx.campaign_id,
            scene_state=ctx.scene_state,
            npc_dicts=ctx.npc_states,
            significant_events=ctx.significant_events or [],
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
                logger.debug(f"[DRF_VOTE] npc={_npc_id} base={_old_priority:.2f} bonus={_drf_bonus:.3f} final={_intent.priority:.2f}")

    # ── Хелперы ───────────────────────────────────────────────────────

    @staticmethod
    def _get_npc_runtime_path(campaign_id: str) -> Path:
        """Путь к runtime-данным NPC для кампании (saves_dir/campaign_id/npc_runtime.json)."""
        from app.core.config import settings
        return Path(settings.saves_dir) / campaign_id / "npc_runtime.json"
# -*- coding: utf-8 -*-
"""
TickOrchestrator — единая точка входа для тика мира.

Строгая последовательность фаз из Архитектурного Устава §3.
Ни один сервис не вызывает другой напрямую — всё через фазы.

path: backend/app/services/tick_orchestrator.py
Назначение: Единая точка входа для тика мира. Оркестрация фаз (§3).
Зависимости: domain.tick, services.events.event_bus, services.npc.life_engine, services.memory.memory_manager, services.integration.world_snapshot_builder
Основные сущности: TickOrchestrator, _TickContext

ФАЗА 0: Simulation (LifeEngine — чистый Python, без LLM)
ФАЗА 0.5: Time-Driven Decay (Idle Services, DynamicAffordanceField, PE Decay)
ФАЗА 1: Input Merge (NPIC Normalize, Interventions, WillpowerGate)
ФАЗА 2: EventBus (первичная волна — spatial events)
ФАЗА 3: Memory Phase (MemoryManager.apply для затронутых NPC)
ФАЗА 4: Pre-Decision (TopicExtractor → тема для каждого NPC)
ФАЗА 5: Decision (TickState assembly -> NpcTickPipeline.run -> TickMutation commit)
ФАЗА 6: Post-Decision (IntentEventAdapter → EventDTO, Windup Write Gate)
ФАЗА 7: Windup Resolution (Execution Gate, Stale Intent Validation)
ФАЗА 8: Handlers (детерминированный drain: drain_events + handle → Phase8Result)
ФАЗА 9: Integration (CFRM P2, L2.5 Belief Crystallization, WorldSnapshotBuilder → WorldSnapshotDTO)
ФАЗА 9.1: Affective Pipeline (Интеграл аффекта, EmotionTransition)
ФАЗА 10: Persistence (atomic commit через PersistencePort)
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional, Union

from app.contracts.interventions import InterventionEvent
from app.domain.tick import TickResultDTO
from app.models.state_delta import DeltaDomain, StateDeltas
from app.models.cfrm import EventBuffer, ClusterOccupancy

from app.services.scene_change import SceneChange, ChangeType
from app.services.drf_bus import DRFBus, DRFExecutionContext
from app.services.dto import _TickContext, DMContextDTO, TickPlayerResultDTO
from app.services.events.event_types import EventType
from app.services.npc.life_engine import get_life_engine
from app.services.events.event_bus import get_event_bus
from app.services.cfrm.local_causal_solver import LocalCausalSolver
from app.models.cfrm import PhenomenologicalState, PsychologicalPressure
from app.models.delta_payloads import EmotionPayload, PerceptionPayload
from app.models.will import IntentPressureProfile, WillResponseDTO, WillState
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
from app.services.events.social_input_projector import SocialInputProjector


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
        from app.services.npc.homeostasis_projector import HomeostasisProjector
        self._homeostasis_sub: HomeostasisProjector = HomeostasisProjector()
        self._social_input_proj: SocialInputProjector = SocialInputProjector(self._get_event_bus())
        
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
        import time
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

        # ADR-048: Приоритет инъекции от GameLoop. Если нет — аварийная сборка.
        if spatial_service:
            self._spatial_service = spatial_service

        # DRF: Сброс шины на начало тика (один bus на весь lifecycle: execute + finalize)
        self._drf_bus.stream.clear()
        logger.info(f"[DRF_BUS_RESET] bus_id={id(self._drf_bus)} tick={tick_number}")

        # [S98] Сборка контекста вынесена в tick_utils.create_tick_context
        from app.services.tick_utils import create_tick_context
        ctx = create_tick_context(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=tick_number,
            interventions=interventions,
            npc_services=npc_services,
            drf_bus=self._drf_bus,
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
        # ctx.scene_state (frozen input) прошёл через фазы → final_snapshot (output тика).
        # Важно: мы не клонируем повторно, а передаём ссылку.
        # Мутации происходили in-place внутри ctx.scene_state.
        final_snapshot = ctx.scene_state  # после мутаций фазами — это уже output, не input
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
        """LifeEngine: need-driven, schedule, random events. Чистый Python."""
        from app.services.phases.simulation import run_phase_0_simulation
        run_phase_0_simulation(ctx, self)

        # Тело метода удалено. Логика перенесена в phases/simulation.py

    def _process_continuous_motion(self, ctx: _TickContext, _spatial_svc: Optional["SpatialService"] = None) -> None:
        """ETKE-IK v1: Непрерывная кинематика (SteeringResolver + MotionIntegrator)."""
        from app.services.phases.motion import process_continuous_motion
        process_continuous_motion(ctx, self, _spatial_svc)

        # Тело метода удалено. Логика перенесена в phases/motion.py

    def _process_traversals(self, ctx: _TickContext) -> None:
        """Фаза 0.75: Authoritative Traversal Lifecycle (STL Phase 1)."""
        from app.services.phases.traversal import process_traversals
        process_traversals(ctx, self)

        # Тело метода удалено. Логика перенесена в phases/traversal.py

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-O-201 ФАЗА 1: Dual Rail Execution (Shadow Observer)
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_with_shadow_observation(
        self, ctx: "_TickContext", changes: list, phase_label: str = ""
    ) -> int:
        """ФАЗА 1 (ADR-O-201): Legacy + Shadow parallel execution."""
        from app.services.phases.traversal import apply_with_shadow_observation
        return apply_with_shadow_observation(ctx, self, changes, phase_label)

        # Тело метода удалено. Логика перенесена в phases/traversal.py

    def _validate_shadow_vs_legacy(
        self,
        snapshot: WorldSnapshot,
        tick: int,
        npc_id: str,
        thick: Any,
        scene_state: dict,
        phase_label: str = "",
    ) -> None:
        """Сравнение shadow ThickSceneChange с legacy состоянием."""
        from app.services.phases.validation import validate_shadow_vs_legacy
        validate_shadow_vs_legacy(
            orchestrator=self,
            snapshot=snapshot,
            tick=tick,
            npc_id=npc_id,
            thick=thick,
            scene_state=scene_state,
            phase_label=phase_label,
        )

        # Тело метода удалено. Логика перенесена в phases/validation.py

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
        """Фильтрация воли игрока через WillpowerGate (ADR-031)."""
        from app.services.phases.input import run_phase_1_input, Phase1InputDeps
        
        deps = Phase1InputDeps()
        run_phase_1_input(ctx, deps)

        # Тело метода удалено. Логика перенесена в phases/input.py

    def _publish_player_intent(self, ctx: _TickContext, intent: IntentDTO) -> None:
        """Публикация разрешенного намерения игрока в шину."""
        from app.services.phases.input import publish_player_intent
        publish_player_intent(ctx, intent)

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
        """Memory Phase: делегировано в phases/memory.py (S100)."""
        from app.services.phases.memory import execute_memory_phase
        execute_memory_phase(ctx, self._get_memory_manager())


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

            topic = None
            # 1. Проверяем spatial events затронувшие этого NPC
            for event in ctx.phase_2_events:
                from app.services.tick_utils import resolve_affected_npcs
                affected = resolve_affected_npcs(event)
                if npc_id in affected:
                    from app.services.npc.topic_extractor import extract_topic
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
                    
                    # ADR-O-208: L3-P1. CalibrationEngine — pass-through (ADR-O-211).
                    # L3 строго эфемерна. Чтение кэша drives_runtime запрещено.
                    l3_stable = l3_raw
                    
                    effective_drives_map[_nid] = l3_stable
                    
        return effective_drives_map, {}, {}

    def _phase_5_decision(self, ctx: _TickContext) -> None:
        """TZ-09: Unified Execution Kernel.
        
        Собирает TickState (causal snapshot), вызывает NpcTickPipeline.run() (pure reducer),
        применяет TickMutation к контексту. Никаких ветвлений на player/idle.
        """
        from app.domain.tick import create_tick_state, TickMutation
        from app.services.npc.npc_tick_pipeline import NpcTickPipeline
        from app.services.phases.decision import evaluate_behavior_and_identity

        logger.info(f"[PHASE_5_UNIFIED] ENTER: tick={ctx.tick_number}, interventions={len(ctx.interventions)}")

        # [S99] Block 4 (Behavior Evaluation) вынесен в phases/decision.py
        evaluate_behavior_and_identity(
            npc_states=ctx.npc_states,
            campaign_id=ctx.campaign_id,
            tick_number=ctx.tick_number,
            game_day=getattr(ctx, "game_day", 0),
            memory_manager=self._get_memory_manager(),
            l1_chronicle=getattr(self, "l1_chronicle", None)
        )

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

        # [S98] Сборка TickState и запуск Pipeline вынесены в pipeline_runner.py
        from app.services.pipeline_runner import build_tick_state, run_pipeline, build_npc_contexts_from_intents
        from app.services.phases.decision import assemble_preloaded_data
        
        (_memory_weights_map, _narrative_cache_map, _social_modifiers_map, 
         _reputation_modifiers_map, _economic_profiles_map, _crystallized_beliefs_map, 
         _identity_traits_map) = assemble_preloaded_data(ctx, _alive_npcs)
        
        _tick_state = build_tick_state(
            ctx=ctx,
            alive_npcs=_alive_npcs,
            effective_drives_map=ctx.effective_drives_map,
            pe_mods_map=_pe_mods_map,
            memory_weights_map=_memory_weights_map,
            narrative_cache_map=_narrative_cache_map,
            social_modifiers_map=_social_modifiers_map,
            reputation_modifiers_map=_reputation_modifiers_map,
            economic_profiles_map=_economic_profiles_map,
            crystallized_beliefs_map=_crystallized_beliefs_map,
            identity_traits_map=_identity_traits_map,
        )

        _drf_ctx = DRFExecutionContext(tick_id=ctx.tick_number, bus=ctx.drf_bus)
        _mutation = run_pipeline(_tick_state, _drf_ctx, ctx.rng_factory)

        # 4. Committer: Применение мутаций к контексту
        build_npc_contexts_from_intents(ctx, _mutation)
        
        # [S99] Block 5 (Movement Bridge) вынесен в phases/movement_bridge.py
        from app.services.phases.movement_bridge import process_movement_intents
        process_movement_intents(
            movement_intents=ctx.movement_intents,
            ctx=ctx,
            orchestrator=self
        )

    def _phase_6_post_decision(self, ctx: _TickContext) -> None:
        """IntentEventAdapter: CommunicationIntent → EventDTO (Устав §3.3)."""
        from app.services.phases.post_decision import run_phase_6_post_decision
        run_phase_6_post_decision(ctx, self)

        # Тело метода удалено. Логика перенесена в phases/post_decision.py

    def _phase_7_windup_resolution(self, ctx: _TickContext) -> None:
        """ADR-O-310: Windup Execution Gate."""
        from app.services.phases.post_decision import run_phase_7_windup_resolution
        run_phase_7_windup_resolution(ctx, self)

        # Тело метода удалено. Логика перенесена в phases/post_decision.py

    # _phase_8_player_handlers удалён (S100) — был мёртвым прокси на _phase_8_drain_secondary.
    # Вызов на строке 764 заменён на прямой вызов _phase_8_drain_secondary.

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
        """Player turn: atomic commit (Устав §10 — Persistence)."""
        from app.services.phases.commit_phase import execute_persistence
        execute_persistence(ctx, self, is_player_turn=True)

    # ── Фаза 0.5: Time-driven idle-сервисы (ВСЕГДА, время не останавливается) ──

    def _phase_0_5_idle_services(self, ctx: _TickContext) -> None:
        """Time-driven decay: social drift, reputation drift, affective decay.
        Выполняется КАЖДЫЙ тик (idle + player path).
        Время идёт непрерывно — эксплойты через движение исключены.
        Дельты собираются в ctx.delta_buffer → apply_batch() в Фазе 10.
        """
        from app.services.phases.idle_services import run_phase_0_5, Phase0_5Deps
        
        # ADR-002: Время не останавливается. Каждый тик продвигает часы на GAME_TICK_INTERVAL_SECONDS
        self._advance_idle_time(ctx)
        
        deps = Phase0_5Deps(
            l1_chronicle=getattr(self, 'l1_chronicle', None),
            dynamic_field=self._dynamic_field,
            homeostasis_sub=self._homeostasis_sub,
            social_input_proj=self._social_input_proj,
            expectation_store=getattr(self, '_expectation_store', None),
            idle_handlers=self._idle_handlers,
            life_engine=self._get_life_engine()
        )
        run_phase_0_5(ctx, deps)
                
        # Тело метода удалено. Логика перенесена в phases/idle_services.py

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


    def _phase_8_drain_secondary(self, ctx: _TickContext) -> None:
        """ФАЗА 8: Layered Reduction — делегировано в phases/reduction.py (S100)."""
        from app.services.phases.reduction import execute_reduction_phase
        _l1 = getattr(self, 'l1_chronicle', None)
        execute_reduction_phase(
            ctx,
            combat_sub=self._combat_sub,
            reaction_sub=self._reaction_sub,
            social_sub=self._social_sub,
            homeostasis_sub=self._homeostasis_sub,
            social_input_proj=self._social_input_proj,
            dynamic_field=self._dynamic_field,
            l1_chronicle=_l1,
            resolve_spatial_fn=lambda: self._resolve_spatial_service(ctx),
        )

    def _phase_9_integration(self, ctx: _TickContext) -> None:
        """CFRM P2: Вычисление локальной реальности + WorldSnapshotBuilder."""
        if not hasattr(self, '_manifest_svc'):
            from app.services.perception.behavior_manifestation_service import BehaviorManifestationService
            from app.services.perception.phenomenology_projection_service import PhenomenologyProjectionService
            self._manifest_svc = BehaviorManifestationService()
            self._project_svc = PhenomenologyProjectionService()

        from app.services.phases.integration import run_phase_9_integration, Phase9IntegrationDeps
        
        deps = Phase9IntegrationDeps(
            state_applicator=self._state_applicator,
            spatial_service=self._spatial_service,
            causal_solver=self._causal_solver,
            crystallized_belief_store=self.crystallized_belief_store,
            drive_resolver=self.drive_resolver,
            l1_chronicle=self.l1_chronicle,
            pattern_detector=self.pattern_detector,
            belief_engine=self.belief_engine,
            snapshot_builder=self._get_snapshot_builder(),
            manifest_svc=self._manifest_svc,
            project_svc=self._project_svc
        )
        run_phase_9_integration(ctx, deps)

        # Тело метода удалено. Логика перенесена в phases/integration.py

    def _run_affective_pipeline(self, ctx: _TickContext) -> None:
        """ADR-049: Аффективный аккумулятор — накопление давления и фазовый переход эмоций.
        
        Вызывается из ОБЕИХ путей (idle + player turn).
        Без этого affective_load не растёт при player turn → emotion=NEUTRAL → _emotion_modifier()=0.0.
        """
        from app.services.phases.affective import run_affective_pipeline, Phase9Deps
        
        deps = Phase9Deps(
            crystallized_belief_store=self.crystallized_belief_store,
            drive_resolver=self.drive_resolver,
            l1_chronicle=self.l1_chronicle,
            pattern_detector=self.pattern_detector,
            belief_engine=self.belief_engine,
            state_applicator=self._state_applicator,
            snapshot_builder=self._get_snapshot_builder(),
            manifest_svc=getattr(self, '_manifest_svc', None),
            project_svc=getattr(self, '_project_svc', None)
        )
        run_affective_pipeline(ctx, deps)

        # Тело метода удалено. Логика перенесена в phases/affective.py

    def _phase_10_persistence(self, ctx: _TickContext) -> None:
        """Atomic commit: SQLite (runtime truth) + YAML (для человека)."""
        from app.services.phases.commit_phase import execute_persistence
        execute_persistence(ctx, self, is_player_turn=False)

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
                from app.services.drf_bus import _DRF_PRESSURE_WEIGHTS
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
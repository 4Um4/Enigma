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
from app.models.cfrm import ClusterOccupancy

# ADR-O-201 ФАЗА 1: Dual Rail Execution
from app.models.world_snapshot import WorldSnapshot
from app.services.cfrm.local_causal_solver import LocalCausalSolver
from app.services.combat.combat_subscriber import CombatSubscriber
from app.services.drf_bus import DRFBus, DRFExecutionContext
from app.services.dto import DMContextDTO, TickPlayerResultDTO, _TickContext
from app.services.equivalence_validator import EquivalenceValidator
from app.services.event_compiler import EventCompiler
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.events.reaction_subscriber import ReactionSubscriber
from app.services.events.social_input_projector import SocialInputProjector
from app.services.events.social_subscriber import SocialSubscriber
from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder
from app.services.npc.life_engine import get_life_engine
from app.services.spatial.spatial_event_detector import (
    SpatialEventDetector,
    _npc_positions_snapshot,
)
from app.services.spatial.spatial_service import SpatialService


class TickOrchestrator:
    """
    Оркестратор тика мира.

    НЕ содержит бизнес-логику — только порядок вызовов фаз.
    Каждая фаза — отдельный сервис из services/.
    """

    def __init__(
        self, scene_manager=None, memory_manager=None, event_bus=None, store=None
    ) -> None:
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
        from app.services.spatial.world_topology_provider import (
            DynamicAffordanceField,
            WorldTopologyProvider,
        )

        self._dynamic_field = DynamicAffordanceField()
        self._topology_provider = WorldTopologyProvider(
            dynamic_field=self._dynamic_field
        )
        # P1.1f: Social propagation — состояние тика переносим с GameLoop
        self._social_engine_factory: Any = None  # callable(campaign_id) → SocialEngine
        # §5.1 подписчики EventBus
        # P2: PerceptionSubscriber удален. Восприятие перенесено в LocalCausalSolver (Фаза 9)
        self._reaction_sub: ReactionSubscriber = ReactionSubscriber(
            self._get_event_bus()
        )
        self._social_sub: SocialSubscriber = SocialSubscriber(self._get_event_bus())
        self._combat_sub: CombatSubscriber = CombatSubscriber(self._get_event_bus())
        from app.services.npc.homeostasis_projector import HomeostasisProjector

        self._homeostasis_sub: HomeostasisProjector = HomeostasisProjector()
        self._social_input_proj: SocialInputProjector = SocialInputProjector(
            self._get_event_bus()
        )

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
        from app.services.npc.belief_crystallization_engine import (
            BeliefCrystallizationEngine,
        )
        from app.services.npc.crystallized_belief_store import CrystallizedBeliefStore
        from app.services.npc.drive_resolver import DriveResolver
        from app.models.npc_state import NPCIdentityL1
        from app.services.npc.l1_chronicle import L1Chronicle
        from app.services.npc.pattern_detector import PatternDetector

        self.l1_chronicle = L1Chronicle(store=store)
        # S-93: PatternDetector получает ссылку на L1Chronicle для запроса сырых событий
        self.pattern_detector = PatternDetector(chronicle=self.l1_chronicle)
        self.drive_resolver = DriveResolver()
        # L1.5 / L2.5: Статистика и Кристаллизация убеждений (ADR-O-305)
        self.belief_engine = BeliefCrystallizationEngine()
        # DEEP-013: Передаём store для SQLite-персистентности убеждений
        self.crystallized_belief_store = CrystallizedBeliefStore(store=store)
        # ReputationEngine для reputation decay
        self._reputation_engine: Any = None
        # DRF: Instance-level causal bus — переживает execute()
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

    def _resolve_spatial_service(
        self, ctx: "_TickContext"
    ) -> Optional["SpatialService"]:
        """ADR-048: Единственный легитимный способ получить SpatialService.
        Приоритет: Инъекция GameLoop -> Аварийная сборка (с предупреждением).
        Кэш не используется для подмены отсутствующего сервиса в новом контексте.
        """
        # 1. Авторитетный источник: передан через NpcTickServices из npc_orchestration
        if (
            ctx.npc_services
            and hasattr(ctx.npc_services, "spatial_service")
            and ctx.npc_services.spatial_service
        ):
            self._spatial_service = ctx.npc_services.spatial_service
            self._topology_provider.set_spatial_service(self._spatial_service)
            return self._spatial_service

        # 1.5. Кэш текущего тика: execute() создаёт _TickContext с npc_services (ADR-065).
        # Переиспользуем уже установленный сервис вместо аварийной сборки.
        if self._spatial_service:
            return self._spatial_service

        # 2. Аварийная сборка из scene_state (если GameLoop не пробросил сервис)
        _loc_id = ctx.scene_state.get("location_id", "")
        if _loc_id:
            try:
                logger.warning(
                    f"[SPATIAL_AUTHORITY] ADR-048 VIOLATION: SpatialService собран вручную для {_loc_id}. GameLoop не пробросил сервис!"
                )
                from app.services.spatial.spatial_factory import SpatialFactory

                self._spatial_service = SpatialFactory.build_for_campaign(
                    campaign_id=ctx.campaign_id,
                    location_id=_loc_id,
                    scene_state=ctx.scene_state,
                )
                self._topology_provider.set_spatial_service(self._spatial_service)
                return self._spatial_service
            except Exception as e:
                logger.error(
                    f"[SPATIAL_AUTHORITY] Crash during emergency build: {type(e).__name__}: {e}"
                )
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

        # Синхронизация: если NPC из all_npcs_raw принадлежит текущей локации,
        # но отсутствует в npc_positions (рассинхрон SSOT), восстанавливаем его запись.
        if hasattr(ctx, "all_npcs_raw") and ctx.all_npcs_raw:
            from app.models.spatial_contracts import NodeRole

            _spatial_svc = self._resolve_spatial_service(ctx)
            _current_loc = ctx.scene_state.get("location_id", "")

            for _npc in ctx.all_npcs_raw:
                _npc_id = _npc.get("npc_id") or _npc.get("id")
                if not _npc_id:
                    continue

                # Фильтр: симулируем только NPC текущей локации (остальные оффскрин)
                _npc_loc = _npc.get("location_id") or _npc.get("location", "")
                if _npc_loc != _current_loc:
                    continue

                if _npc_id not in npc_positions:
                    _pos = _npc.get("position")
                    _local_pos = _npc.get("local_position")

                    # Если позиция утеряна, пытаемся найти узел DEFAULT через SpatialService
                    if not _pos and _spatial_svc:
                        _ref = _spatial_svc.resolve_node(
                            role=NodeRole.DEFAULT, origin_zone=_current_loc
                        )
                        if _ref:
                            _pos = _ref.node_id
                            _local_pos = {"x": _ref.x, "y": _ref.y}

                    if _pos:
                        npc_positions[_npc_id] = {
                            "position": _pos,
                            "local_position": _local_pos or {"x": 0.0, "y": 0.0},
                            "name": _npc.get("name", _npc_id),
                        }
                        logger.warning(
                            f"[CFRM] ClusterOccupancy: Восстановлен NPC '{_npc_id}' в npc_positions (loc={_current_loc}, pos={_pos})."
                        )

                        # Обновляем кластер для восстановленного NPC
                        if ":" in str(_pos) or not _current_loc:
                            cluster_id = str(_pos)
                        else:
                            cluster_id = f"{_current_loc}:{_pos}"
                        ctx.cluster_occupancy.update_entity(_npc_id, cluster_id)
                    else:
                        logger.error(
                            f"[CFRM] ClusterOccupancy: NPC '{_npc_id}' в локации {_current_loc}, но нет позиции и SpatialService не смог найти узел."
                        )

        elapsed_ms = (
            time.perf_counter() - start_time
        ) * 1000  # §15.2: Telemetry (profiling)
        logger.info(
            f"[CFRM] ClusterOccupancy rebuild: {len(npc_positions)} entities in {elapsed_ms:.2f}ms"
        )

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
        spatial_service: Optional[Any] = None,  # ADR-048: Инъекция от GameLoop
        dm_ctx: Optional[
            "DMContextDTO"
        ] = None,  # Backward compat (мостируется в interventions)
        all_npcs_raw: Optional[
            list
        ] = None,  # S113: Явная передача NPC (включая аватара)
        shared_context: Optional[
            Any
        ] = None,  # S116 FIX: Проброс shared_context для CombatSubscriber
        hub_event: Optional[Any] = None,  # BUG-CORE-003 FIX: Проброс контекста игрока
        task_scheduler: Optional[Any] = None,  # S128 FIX: Проброс для Фазы 4
        active_location_id: Optional[str] = None, # Дополнение Б: локация игрока
        location_ids: Optional[List[str]] = None, # Дополнение Б: список всех локаций
    ) -> Union[TickResultDTO, TickPlayerResultDTO]:
        """Единая точка входа для тика мира (TZ-08 v0.2 + Дополнение Б).

        Ядро не знает 'player'. Если interventions пуст — idle tick.
        Если передан legacy dm_ctx — он мостируется в InterventionEvent.
        Дополнение Б: Если передан location_ids, тикает все локации из списка.
        """
        if interventions is None:
            interventions = []

        # Мостируем legacy dm_ctx в новый event-driven формат
        if dm_ctx is not None and not interventions:
            interventions = [
                InterventionEvent(
                    source="player",
                    payload={"dm_ctx": dm_ctx},
                    tick=tick_number,
                )
            ]
        # ADR-L1-PERSIST: Привязка L1Chronicle к текущей кампании для ленивой загрузки
        self.l1_chronicle.bind_campaign(campaign_id)
        # DEEP-013: Привязка CrystallizedBeliefStore к текущей кампании для ленивой загрузки
        self.crystallized_belief_store._campaign_id = campaign_id
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

        # Дополнение Б: Определяем список локаций для тика
        _all_scenes = {scene_state.get("location_id", "default"): scene_state}
        if location_ids:
            for _loc_id in location_ids:
                if _loc_id not in _all_scenes:
                    _extra_scene = self._scene_manager.get_scene_state(campaign_id, _loc_id)
                    if _extra_scene:
                        _all_scenes[_loc_id] = _extra_scene

        _tick_results = []
        _final_result = None
        for _loc_id, _scene in _all_scenes.items():
            _is_active = (_loc_id == active_location_id) if active_location_id else True
            
            ctx = create_tick_context(
                campaign_id=campaign_id,
                scene_state=_scene,
                tick_number=tick_number,
                interventions=interventions if _is_active else [],
                npc_services=npc_services,
                drf_bus=self._drf_bus,
                all_npcs_raw=all_npcs_raw,
                shared_context=shared_context,
                task_scheduler=task_scheduler,
                hub_event=hub_event,  # BUG-CORE-003 FIX: Передача контекста в фабрику
            )
            self._rebuild_cluster_occupancy(ctx)

            # BUG-CORE-001 FIX: Мёртвый код (135 строк после return) удалён.
            # Логика CFRM-моста и AdaptiveTickLoader восстановлена внутри активного цикла.

            # CFRM P2: Мост деобъективации — превращение объективных событий в возмущения поля
            event_bus = self._get_event_bus()

            def _deobjectify_event(event: "EventDTO") -> None:
                """Трансформирует EventDTO в FieldDisturbance на основе контекста тика."""
                import logging

                from app.models.cfrm import (
                    CausalAxis,
                    DisturbanceVector,
                    FieldDisturbance,
                    classify_event,
                )

                result = classify_event(event.type)
                axis = result.axis

                if result.confidence < 0.5:
                    logging.warning(
                        f"[CFRM] classify_event: {event.type} -> {axis.value} (confidence={result.confidence}, source={result.source.value})"
                    )

                origin_cluster = (
                    ctx.cluster_occupancy.get_cluster(event.source) or "world:unknown"
                )

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

                magnitude = event.payload.get("intensity", 0.5)

                disturbance = FieldDisturbance(
                    origin_cluster=origin_cluster,
                    disturbance_type=axis,
                    magnitude=magnitude,
                    vectors=tuple(vectors),
                    source_entity=event.source,
                )
                ctx.event_buffer.add(disturbance, axis)

            event_bus.attach_cfrm_bridge(_deobjectify_event)

            # Дополнение Б: Адаптивный LOD
            if not hasattr(self, '_adaptive_loader'):
                from app.services.adaptive_tick_loader import AdaptiveTickLoader
                self._adaptive_loader = AdaptiveTickLoader()
                
            # Определяем, должна ли эта локация тикать полностью
            _tick_fully = True
            if self._adaptive_loader.is_lod_active() and active_location_id:
                _connected = []
                try:
                    from app.services.spatial.spatial_registry import SpatialRegistry
                    _reg = SpatialRegistry.get_or_load(campaign_id)
                    if _reg:
                        _connected = [e.location_b for e in _reg.get_neighbors(active_location_id)]
                except Exception as e:
                    # BUG-V68-001 FIX: Заменён silent pass на логирование.
                    # Если SpatialRegistry упадёт, LOD throttling не применится, но ошибка будет видна.
                    logger.warning(f"[ADAPTIVE_LOADER] SpatialRegistry load failed: {e}")
                _current_loc = _scene.get("location_id", "default")
                _tick_fully = self._adaptive_loader.should_tick_fully(_current_loc, active_location_id, _connected)

            import time as _time
            _start_time = _time.time()
            
            try:
                self._run_core_phases(ctx, tick_fully=_tick_fully)
            except Exception as e:
                logger.error(
                    f"[TICK_CRASH] campaign={campaign_id} tick={tick_number} loc={_loc_id} error={e}"
                )
                logger.error(f"[TICK_ORCH] Ошибка в тике {campaign_id} (loc={_loc_id}): {e}", exc_info=True)
                return TickResultDTO(status="error", error=str(e))
            finally:
                # V8.6 FIX: Безопасный доступ к event_bus, даже если тик упал до Фазы 9
                event_bus.detach_cfrm_bridge()
                
                # Дополнение Б: Запись времени тика для AdaptiveTickLoader
                _duration_ms = (_time.time() - _start_time) * 1000
                _npc_count = len(all_npcs_raw) if all_npcs_raw else 0
                self._adaptive_loader.record_tick(_duration_ms, _npc_count)

            # S83.1: TickOrchestrator = единственный владелец результата тика.
            final_snapshot = ctx.scene_state

            # TZ-08 v0.2: Ядро всегда возвращает единый TickResultDTO. Никаких ветвлений по источнику.
            _final_facts = getattr(ctx, "observed_facts_for_dm", [])
            # INV-DEF: Эмиттер сводки тика для CausalObserver (InvariantHealthChecker)
            _moved_count = sum(
                1
                for v in ctx.scene_state.get("active_traversals", {}).values()
                if getattr(v, "status", None) == "MOVING"
            )
            _decisions_count = len(ctx.communication_intents) + sum(
                1 for i in getattr(ctx, "movement_intents", []) if i
            )
            _verbal_count = len(ctx.communication_intents)
            _game_time = ctx.scene_state.get("game_time_seconds", 0.0)
            logger.debug(
                f"[TICK_ORCH] tick={ctx.tick_number} loc={_loc_id} game_time={_game_time} decisions={_decisions_count} verbal={_verbal_count} moved={_moved_count}"
            )

            logger.debug(
                f"[DEBUG_TICK_ORCH] returning TickResultDTO with observed_facts count={len(_final_facts)}"
            )
            _res = TickResultDTO(
                status="ok",
                changes_count=ctx.changes_count,
                significant_events=ctx.significant_events,
                world_snapshot=ctx.world_snapshot,
                npc_contexts=ctx.npc_contexts,
                observed_facts=_final_facts,
                final_scene_state=final_snapshot,
                all_npcs_raw=ctx.all_npcs_raw,
            )
            _tick_results.append(_res)
            if _is_active:
                _final_result = _res

        if _final_result is None and _tick_results:
            _final_result = _tick_results[0]
        if _final_result is None:
            _final_result = TickResultDTO(status="error", error="No scenes ticked")
        return _final_result

    # ── Player Turn (тонкая обёртка) ────────────────────────────────

    # ── Core Pipeline (Immutable Sequence) ──────────────────────────

    def _run_core_phases(self, ctx: _TickContext, tick_fully: bool = True) -> None:
        """A2-FIX v0.2: Immutable core pipeline. NO mode, NO player branching."""
        # BUG-CORE-014 FIX: CAUSAL_CONTRACT §4.6.45 — исключаем мёртвых NPC ДО любых фаз.
        # Ранее фильтр был только в _phase_5_decision, что позволяло мёртвым мутировать state в Фазах 0-4.
        ctx.all_npcs_raw = [
            n for n in (ctx.all_npcs_raw or [])
            if n.get("body_state", {}).get("life_status") != "DEAD"
        ]
        if hasattr(ctx, "npc_states") and ctx.npc_states:
            ctx.npc_states = [
                n for n in ctx.npc_states
                if n.get("body_state", {}).get("life_status") != "DEAD"
            ]

        self._snapshot_positions_before(ctx) #1
        self._phase_0_simulation(ctx) #2
        self._phase_0_5_idle_services(ctx) #3
        
        # Дополнение Б (п. Б.11): Adaptive Tick Loader
        # Если LOD активен и это дальняя локация — пропускаем тяжелые фазы (память, решения, движение)
        if not tick_fully:
            self._phase_10_persistence(ctx) #16
            return
            
        self._phase_1_npic_normalize(ctx) #4
        self._phase_1_input_merge(ctx) #5
        self._apply_willpower_gate(ctx) #6
        self._phase_2_event_bus_primary(ctx) #7
        self._phase_3_memory(ctx) #8
        self._phase_4_pre_decision(ctx) #9
        self._phase_5_decision(ctx) #10
        self._phase_6_post_decision(ctx) #11
        self._phase_7_windup_resolution(ctx)  #12 ADR-O-310: Execution Gate
        self._phase_8_drain_secondary(ctx) #13
        self._phase_9_integration(ctx) #14
        self._run_affective_pipeline(ctx) #15
        self._phase_10_persistence(ctx) #16

        # Подсистема 3: Causal Probes (real-time invariant monitor)
        from app.services.probes.probe_runner import ProbeRunner
        from app.services.probes.probe_registry import ProbeContext
        from app.services.probes.probes.spatial_coherence_probe import SpatialCoherenceProbe
        from app.services.probes.probes.traversal_fsm_probe import TraversalFSMProbe
        from app.services.probes.probes.death_lock_probe import DeathLockProbe
        
        _probe_ctx = ProbeContext(
            tick_id=ctx.tick_number,
            game_time_seconds=ctx.scene_state.get("game_time_seconds", 0.0),
            scene_state=ctx.scene_state,
            all_npcs_raw=ctx.all_npcs_raw
        )
        _runner = ProbeRunner(probes=[SpatialCoherenceProbe(), TraversalFSMProbe(), DeathLockProbe()])
        _runner.run_all(_probe_ctx)

        # N2 FIX: Эмитим событие TICK_COMPLETED для подписчиков (например, MvpTavernController)
        from app.domain.events import EventDTO
        _tick_completed_event = EventDTO.create(
            event_type=EventType.TICK_COMPLETED.value,
            source="tick_orchestrator",
            payload={
                "tick_number": ctx.tick_number,
                "snapshot": ctx,
            }
        )
        self._get_event_bus().publish(_tick_completed_event)

    def _phase_1_npic_normalize(self, ctx: _TickContext) -> None:
        """Подслой 1.1: NPIC NORMALIZATION."""
        if ctx.all_npcs_raw:
            from app.models.npc_state import BODY_STATE_DISABLED_DATA

            for _npc in ctx.all_npcs_raw:
                _bs = _npc.get("body_state")
                if not _bs:
                    _npc["body_state"] = dict(BODY_STATE_DISABLED_DATA)
                    logger.warning(
                        f"[NPIC_NORMALIZE] NPC '{_npc.get('npc_id', '?')}' missing body_state. Injected DISABLED sentinel."
                    )

    def _phase_1_input_merge(self, ctx: _TickContext) -> None:
        """Подслой 1.2: Merge interventions into delta_buffer."""
        if not ctx.interventions:
            return

        _life_engine = self._get_life_engine()
        if _life_engine:
            ctx.npc_states = _life_engine.get_npc_states(ctx.campaign_id)
            if ctx.npc_states:
                # Сохраняем аватара игрока из переданного контекста (от GameLoop)
                _player_entry = next(
                    (n for n in ctx.all_npcs_raw if n.get("npc_id") == "player"), None
                )
                # Если список из LifeEngine не пуст, используем его как базу
                ctx.all_npcs_raw = ctx.npc_states
                # Возвращаем аватара игрока в конец списка
                if _player_entry:
                    ctx.all_npcs_raw = [
                        n for n in ctx.all_npcs_raw if n.get("npc_id") != "player"
                    ]
                    ctx.all_npcs_raw.append(_player_entry)

        for interv in ctx.interventions:
            if interv.source == "player" and "dm_ctx" in interv.payload:
                _dm_ctx = interv.payload.get("dm_ctx")
                if _dm_ctx:
                    self._process_player_dm_action(ctx, _dm_ctx)
            elif interv.source == "player":
                self._process_player_action(ctx, interv)
            else:
                logger.debug(
                    f"[INPUT_MERGE] unhandled intervention source: {interv.source}"
                )

    def _apply_willpower_gate(self, ctx: _TickContext) -> None:
        """Подслой 1.3: WillpowerGate. Явный вызов без условного ветвления."""
        self._phase_1_input(ctx)

    def _process_player_dm_action(self, ctx: _TickContext, dm_ctx: Any) -> None:
        """Обработка player DM action (directive handling, cognitive overlay)."""
        logger.warning(f"[PDM_DEBUG] ENTER. dm_ctx={dm_ctx is not None}")
        if hasattr(dm_ctx, "intent_resolution") and dm_ctx.intent_resolution:
            _intent_res = dm_ctx.intent_resolution
            _params = (
                _intent_res.original_intent.parameters
                if _intent_res.original_intent
                else None
            )
            _fast_actor = None
            _fast_target_xy = None
            _target_id = getattr(_params, "target_id", None) if _params else None
            _movement_req = getattr(_intent_res, "movement_request", None) # V8-TICK-1 FIX
            
            # V8-TICK-1 FIX: определяем семантические переменные для directive_payload
            _sem_action = getattr(_params, "semantic_action", "") if _params else ""
            _sem_target = getattr(_params, "target_reference", "") if _params else ""

            if _movement_req:
                _fast_actor = _movement_req.actor_id
                _target_id = _movement_req.target_actor_id
                _target_pos_dict = (
                    ctx.scene_state.get("npc_positions", {})
                    .get(_target_id, {})
                    .get("local_position", {"x": 0.0, "y": 0.0})
                )
                _fast_target_xy = (
                    _target_pos_dict.get("x", 0.0),
                    _target_pos_dict.get("y", 0.0),
                )

                # Применяем социальное давление только если Игрок приказывает NPC подойти
                if _fast_actor != "player" and _target_id == "player":
                    try:
                        import types

                        from app.services.social.directive_interpretation_subscriber import (
                            DirectiveInterpretationSubscriber,
                        )

                        _directive_payload = {
                            "semantic_action": _sem_action,
                            "target_reference": _sem_target,
                            "target_id": _fast_actor,
                            "social_pressure": 0.8,
                        }
                        _mock_event = types.SimpleNamespace(payload=_directive_payload)
                        _directive_deltas = DirectiveInterpretationSubscriber().handle(
                            _mock_event, ctx.all_npcs_raw
                        )
                        if _directive_deltas:
                            ctx.delta_buffer.extend(_directive_deltas)
                            for delta in _directive_deltas:
                                _npc_id = delta.npc_id
                                _npc_state = next(
                                    (
                                        n
                                        for n in ctx.all_npcs_raw
                                        if n.get("npc_id") == _npc_id
                                    ),
                                    None,
                                )
                                if not _npc_state:
                                    continue
                                if (
                                    hasattr(delta.payload, "recent_directive_data")
                                    and delta.payload.recent_directive_data
                                ):
                                    _npc_state.setdefault("perceptual_kernel", {})[
                                        "recent_directive"
                                    ] = delta.payload.recent_directive_data
                                if (
                                    hasattr(delta.payload, "stress_delta")
                                    and delta.payload.stress_delta != 0
                                ):
                                    # V8-TICK-5 / V8-PSY-21 FIX: stress пишется в psyche sub-dict, а не в emotion (строка)
                                    _psyche = _npc_state.setdefault("psyche", {})
                                    _psyche["stress"] = max(0, min(100, _psyche.get("stress", 0.0) + delta.payload.stress_delta))
                                if (
                                    hasattr(delta.payload, "fear_delta")
                                    and delta.payload.fear_delta != 0
                                ):
                                    _npc_state.setdefault("social_stats", {})[
                                        "fear_of_player"
                                    ] = (
                                        _npc_state.get("social_stats", {}).get(
                                            "fear_of_player", 0.1
                                        )
                                        + delta.payload.fear_delta
                                    )
                                if (
                                    hasattr(delta.payload, "shock_impulse")
                                    and getattr(delta.payload, "shock_impulse", 0.0)
                                    > 0.5
                                ):
                                    _npc_state.setdefault("body_state", {})[
                                        "shock_impulse"
                                    ] = (
                                        getattr(
                                            _npc_state.get("body_state", {}),
                                            "shock_impulse",
                                            0.0,
                                        )
                                        + delta.payload.shock_impulse
                                    )
                                    _npc_state.setdefault("body_state", {})[
                                        "consciousness"
                                    ] = max(0.0, 1.0 - delta.payload.shock_impulse)
                    except Exception as e:
                        logger.error(
                            f"[CAUSALITY_CRASH] DirectiveInterpretationSubscriber failed: {e}",
                            exc_info=True,
                        )

                logger.warning(
                    f"[FAST_PATH_DEBUG] actor={_fast_actor} target={_target_id}"
                )

            # BUG-N5 FIX: Исключаем игрока из fast-path макро-движения, так как он не зарегистрирован в npc_positions как spatial-сущность.
            if _fast_actor and _fast_target_xy and _fast_actor != "player":
                from app.domain.movement import LocalSteeringGoal
                from app.services.spatial.movement_engine import MovementEngine

                _spatial_svc = self._resolve_spatial_service(ctx)
                if _spatial_svc:
                    _fast_intents = [
                        LocalSteeringGoal(
                            actor_id=_fast_actor,
                            local_target_xy=_fast_target_xy,
                            reason="micro_snap:approach",
                            priority=0.9,
                        )
                    ]
                    me = MovementEngine()
                    me.set_spatial_service(_spatial_svc)
                    _changes = me.process_intents(
                        _fast_intents,
                        ctx.tick_number,
                        ctx.scene_state.get("npc_positions", {}),
                        campaign_id=ctx.campaign_id,
                        scene_state=ctx.scene_state,
                    )
                    if _changes and self._scene_manager:
                        self._apply_with_shadow_observation(
                            ctx, _changes, phase_label="FAST_PATH_MOVE"
                        )
                        logger.warning(
                            f"[FAST_PATH] Applied {len(_changes)} movement changes for actor={_fast_actor}"
                        )

    def _process_player_action(self, ctx: _TickContext, interv: Any) -> None:
        """Generic player action intervention (не dm_ctx).

        S115 FIX: Перенос логики директив из _process_player_dm_action.
        Обрабатывает InterventionEvent от игрока (MOVE, THREATEN, etc.).
        """
        _payload = getattr(interv, "payload", {})
        _sem_action = _payload.get("semantic_action")
        _sem_target = _payload.get("target_reference", "")
        _target_id = _payload.get("target_id")

        if not _sem_action or not _sem_target:
            return

        # S122 FIX: Боевая труба. Если игрок атакует — публикуем событие в EventBus,
        # чтобы CombatSubscriber (Фаза 8) вызвал ImpactEngine и нанёс физический урон.
        # Без этого NPC не получает боль/шок, и BehaviorManifestationService не генерирует моторные следы.
        if _sem_action.upper() == "ATTACK":
            import uuid

            from app.domain.events import EventDTO
            from app.services.events.event_types import EventType

            _attack_event = EventDTO(
                id=str(uuid.uuid4()),
                type=EventType.PLAYER_ATTACKED.value,
                source="player",
                timestamp=ctx.scene_state.get("game_time_seconds", 0.0),
                payload={
                    "target_id": _target_id,
                    "target_reference": _sem_target,
                    "intensity": _payload.get("social_pressure", 0.8),
                    "actor_id": "player",
                },
                visibility="public",
                radius=15.0,
                persistence_level="working",
            )
            self._event_bus.publish(_attack_event)

        # ADR-082: Регистронезависимое сравнение
        if _sem_action.upper() in ("MOVE", "THREATEN", "PERSUADE", "GIVE"):
            # S115 FIX: target_id может быть уже зарезолвлен (maid_lusya),
            # а target_reference пустовать. Ищем по любому из них.
            _search_ref = (_sem_target or _target_id or "").lower()
            _is_npc_target = (
                any(
                    _search_ref in n.get("name", "").lower()
                    or _search_ref in n.get("npc_id", "").lower()
                    for n in ctx.all_npcs_raw
                )
                if ctx.all_npcs_raw
                else False
            )

            if _is_npc_target:
                try:
                    import types

                    from app.services.social.directive_interpretation_subscriber import (
                        DirectiveInterpretationSubscriber,
                    )

                    _directive_payload = {
                        "semantic_action": _sem_action,
                        "target_reference": _sem_target or "",
                        "target_id": _target_id,  # S115 FIX: target_id обязателен, если уже зарезолвлен
                        "social_pressure": _payload.get("social_pressure", 0.8),
                    }
                    _mock_event = types.SimpleNamespace(payload=_directive_payload)
                    _directive_deltas = DirectiveInterpretationSubscriber().handle(
                        _mock_event, ctx.all_npcs_raw
                    )
                    if _directive_deltas:
                        ctx.delta_buffer.extend(_directive_deltas)
                        # S116 FIX: Применяем дельты напрямую к npc_dict, чтобы они не потерялись при агрегации.
                        for delta in _directive_deltas:
                            _npc_id = delta.npc_id
                            _npc_state = next(
                                (
                                    n
                                    for n in ctx.all_npcs_raw
                                    if n.get("npc_id") == _npc_id
                                ),
                                None,
                            )
                            if not _npc_state:
                                continue
                            if (
                                hasattr(delta.payload, "compliance_bias_delta")
                                and delta.payload.compliance_bias_delta != 0
                            ):
                                _pk = _npc_state.setdefault("perceptual_kernel", {})
                                _pk["compliance_bias"] = max(
                                    -1.0,
                                    min(
                                        1.0,
                                        _pk.get("compliance_bias", 0.0)
                                        + delta.payload.compliance_bias_delta,
                                    ),
                                )
                            if (
                                hasattr(delta.payload, "recent_directive_data")
                                and delta.payload.recent_directive_data
                            ):
                                _npc_state.setdefault("perceptual_kernel", {})[
                                    "recent_directive"
                                ] = delta.payload.recent_directive_data
                            if (
                                hasattr(delta.payload, "stress_delta")
                                and delta.payload.stress_delta != 0
                            ):
                                # V8-TICK-5 / V8-PSY-21 FIX: stress пишется в psyche sub-dict, а не в emotion (строка)
                                _psyche = _npc_state.setdefault("psyche", {})
                                _psyche["stress"] = max(0, min(100, _psyche.get("stress", 0.0) + delta.payload.stress_delta))
                            if (
                                hasattr(delta.payload, "fear_delta")
                                and delta.payload.fear_delta != 0
                            ):
                                _npc_state.setdefault("social_stats", {})[
                                    "fear_of_player"
                                ] = (
                                    _npc_state.get("social_stats", {}).get(
                                        "fear_of_player", 0.1
                                    )
                                    + delta.payload.fear_delta
                                )
                except Exception as e:
                    logger.error(
                        f"[CAUSALITY_CRASH] DirectiveInterpretationSubscriber failed: {e}",
                        exc_info=True,
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

    def _process_continuous_motion(
        self, ctx: _TickContext, _spatial_svc: Optional["SpatialService"] = None
    ) -> None:
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
        if not hasattr(self, "_tick_thick_changes"):
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
            _ready = (
                "READY" if _structural_drift == 0 and _total >= 100000 else "NOT_READY"
            )
            logger.info(
                f"[DUAL_RAIL] Drift summary after {_total} observations: "
                f"A(cosmetic)={_a} B(projection)={_b} C(topological)={_c} "
                f"D(causal)={_d} E(ontological)={_e} "
                f"phase3={_ready}"
            )

    def _phase_1_input(self, ctx: _TickContext) -> None:
        """Фильтрация воли игрока через WillpowerGate (ADR-031)."""
        from app.services.phases.input import Phase1InputDeps, run_phase_1_input

        deps = Phase1InputDeps()
        run_phase_1_input(ctx, deps)

        # Тело метода удалено. Логика перенесена в phases/input.py

# S118 FIX: Удалена мёртвая заглушка _publish_player_intent (Vulture).

    def _phase_2_event_bus_primary(self, ctx: _TickContext) -> None:
        """Первая волна EventBus: пространственные события от MovementEngine (Слой 4).

        SpatialEventDetector сравнивает позиции до/после фазы 0
        и публикует NPC_MOVED, NPC_PROXIMITY_CLOSE, NPC_PROXIMITY_LEAVE.
        Дополнение Б (п. Б.10.2): Активация Sound bleed для кросс-локационного звука.
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
            
            # Дополнение Б: Sound bleed
            try:
                from app.services.spatial.spatial_runtime import sound_bleeds_to_adjacent
                from app.domain.events import EventDTO
                from app.core.config import settings
                
                _loc_id = ctx.scene_state.get("location_id", "")
                _data_dir = str(settings.data_dir)
                
                # Находим соседние локации
                _adjacent_locs = sound_bleeds_to_adjacent(
                    scene_state=ctx.scene_state,
                    base_radius=10,
                    bleed_threshold=0.5,
                    data_dir=_data_dir
                )
                
                # Если есть соседи, пробиваем звук к ним
                if _adjacent_locs:
                    _event_bus = self._get_event_bus()
                    for _event in _spatial_events:
                        # Определяем "громкость" события (упрощенная модель для MVP)
                        _intensity = 0.8 if _event.type in ("NPC_ATTACKED", "PLAYER_ATTACKS") else 0.3
                        if _intensity >= 0.5:
                            for _adj_loc in _adjacent_locs:
                                # Проницаемость стены (упрощенно: 0.4 для двери)
                                _bleeded_intensity = _intensity * 0.4 * 0.5
                                if _bleeded_intensity >= 0.1:
                                    _bleeded_event = EventDTO.create(
                                        event_type="SOUND_BLEED",
                                        source=_event.source,
                                        payload={
                                            "origin_location": _loc_id,
                                            "perceived_at_location": _adj_loc,
                                            "intensity": _bleeded_intensity,
                                            "original_type": _event.type
                                        }
                                    )
                                    _event_bus.publish(_bleeded_event)
                                    logger.debug(f"[SOUND_BLEED] {_event.type} from {_loc_id} to {_adj_loc} (intensity={_bleeded_intensity:.2f})")
            except Exception as _bleed_err:
                logger.warning(f"[SOUND_BLEED] Failed to propagate sound: {_bleed_err}")

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

            from app.services.npc.topic_extractor import extract_topic

            topic = None

            # 0. Приоритет: Проверяем недавние диалоги в TaskScheduler (NPC_SPOKE)
            # Если к NPC обратились, он должен ответить, а не болтать "наблюдение".
            _recent_dialogues = []
            if ctx.task_scheduler:
                _recent_dialogues = ctx.task_scheduler.get_recent_dialogues(ctx.scene_state.get("game_time_seconds", 0.0))
            for dialogue in _recent_dialogues:
                if dialogue.get("target_id") == npc_id:
                    _speaker = dialogue.get("speaker_id", "кто-то")
                    _text = dialogue.get("text", "")
                    # S129: Тема содержит только семантику. Адресат передаётся структурно.
                    topic = f"ответить: {_text}"
                    ctx.response_targets[npc_id] = _speaker
                    break

            # 1. Проверяем spatial events затронувшие этого NPC
            if not topic:
                for event in ctx.phase_2_events:
                    from app.services.tick_utils import resolve_affected_npcs

                    affected = resolve_affected_npcs(event)
                    if npc_id in affected:
                        topic = extract_topic(
                            event_type=event.type,
                            raw_input=event.payload.get("to_node", ""),
                        )
                        break  # первый подошедший event достаточно

            # 2. Фоллбэк на состояние NPC (T-01: автономная тематическая жизнь)
            if not topic:
                topic = extract_topic(
                    event_type="idle",
                    npc_state=npc_dict,
                )

            # 3. Жёсткий фоллбэк — тема НЕ может быть пустой (Устав §3.2)
            if not topic:
                topic = "наблюдение"

            ctx.npc_topics[npc_id] = topic

        logger.debug(f"[TICK_ORCH] Фаза 4: {len(ctx.npc_topics)} topics извлечено")

    def _compute_effective_drives(
        self, npc_list: list[dict], tick_number: int, campaign_id: str
    ) -> Tuple[
        Dict[str, "EffectiveDrives"],
        Dict[str, Dict[str, float]],
        Dict[str, Dict[str, float]],
    ]:
        """STEP B + TSHL: Вычисление L3_raw и фильтрация в L3_stable через CalibrationEngine.
        Возвращает L3_stable (для DecisionHub), drives_updates и strain_updates (для StateApplicator).
        """
        from app.domain.identity_events import EffectiveDrives
        from app.services.npc.calibration_engine import CalibrationEngine

        effective_drives_map: Dict[str, EffectiveDrives] = {}
        drives_updates: Dict[str, Dict[str, float]] = {}
        strain_updates: Dict[str, Dict[str, float]] = {}

        if hasattr(self, "drive_resolver") and hasattr(self, "l1_chronicle"):
            from app.models.npc_state import personality_from_legacy

            # V8-PSY-29 FIX: CalibrationEngine — dead code (ADR-O-211), убрано создание неиспользуемого экземпляра

            for npc_dict in npc_list:
                _nid = npc_dict.get("id") or npc_dict.get("npc_id")
                if _nid:
                    _profile_l0 = personality_from_legacy(npc_dict)
                    _beliefs = self.crystallized_belief_store.get_beliefs(_nid)
                    _body_state = npc_dict.get("body_state", {})
                    # V8-PSY-9 FIX: Получаем L1 Identity из memory_manager
                    # BUG-CORE-002 FIX: self.memory_manager не существует (используем _get_memory_manager),
                    # ctx.campaign_id был недоступен (теперь передаётся как параметр campaign_id).
                    # Silent except: pass заменён на логирование, чтобы не терять ошибки L1 проекции.
                    _identity_l1 = None
                    try:
                        _mm = self._get_memory_manager()
                        _traits = _mm.get_identity_traits(campaign_id, _nid)
                        if _traits:
                            _identity_l1 = NPCIdentityL1(npc_id=_nid, active_traits=_traits)
                    except Exception as e:
                        logger.error(f"[L3_PROJECTION] identity traits load failed for npc={_nid}: {e}")

                    _projection = self.drive_resolver.resolve_drives(
                        _profile_l0, _beliefs, body_state=_body_state, identity_l1=_identity_l1
                    )

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
        logger.info(
            f"[PHASE_5_UNIFIED] ENTER: tick={ctx.tick_number}, interventions={len(ctx.interventions)}"
        )

        ctx.effective_drives_map, ctx.drives_updates, ctx.strain_updates = (
            self._compute_effective_drives(ctx.npc_states, ctx.tick_number, ctx.campaign_id)
        )

        # 2. Извлечение данных игрока (если есть)
        _dm_ctx = None
        for interv in ctx.interventions:
            if interv.source == "player" and "dm_ctx" in interv.payload:
                _dm_ctx = interv.payload["dm_ctx"]
                break

        # 3. Execute: Сборка TickState и вызов Pure Reducer
        # ADR-123: Death Lock. Мёртвые полностью исключаются из reasoning pipeline.
        _alive_npcs = [
            n
            for n in (ctx.all_npcs_raw or ctx.npc_states)
            if n.get("body_state", {}).get("life_status") != "DEAD"
        ]

        # DEEP-015 FIX: Мёртвый код ExpectationStore (Active Inference) удалён.
        # Хранилище никогда не инициализировалось, блоки всегда были no-op.
        # Оставляем пустой словарь, чтобы не ломать контракт build_tick_state.
        _pe_mods_map: dict[str, dict[str, float]] = {}

        # [S98] Сборка TickState и запуск Pipeline вынесены в pipeline_runner.py
        from app.services.phases.decision import assemble_preloaded_data
        from app.services.pipeline_runner import (
            build_npc_contexts_from_intents,
            build_tick_state,
            run_pipeline,
        )

        (
            _memory_weights_map,
            _narrative_cache_map,
            _social_modifiers_map,
            _reputation_modifiers_map,
            _economic_profiles_map,
            _crystallized_beliefs_map,
            _identity_traits_map,
        ) = assemble_preloaded_data(ctx, _alive_npcs)

        # [S99] Block 4 (Behavior Evaluation) вынесен в phases/decision.py
        # DEEP-FIX: Перенесено после assemble_preloaded_data, чтобы передать economic_profiles_map
        from app.services.phases.decision import evaluate_behavior_and_identity

        # Шаг 1.1: Извлекаем RelationshipStore (SSOT) из StateApplicator для расчёта social_pressure
        _rel_store = getattr(self._state_applicator, "_rel_store", None) if self._state_applicator else None

        evaluate_behavior_and_identity(
            npc_states=ctx.npc_states,
            campaign_id=ctx.campaign_id,
            tick_number=ctx.tick_number,
            game_day=getattr(ctx, "game_day", 0),
            memory_manager=self._get_memory_manager(),
            l1_chronicle=getattr(self, "l1_chronicle", None),
            economic_profiles_map=_economic_profiles_map,
            social_modifiers_map=_social_modifiers_map,
            relationship_store=_rel_store,  # Шаг 1.1: Передача SSOT
        )

        # P5 FIX: Передаём разрешённый spatial_service напрямую, чтобы избежать потери в npc_services
        _spatial_svc_for_pipeline = self._resolve_spatial_service(ctx)
        _spatial_query_for_pipeline = getattr(ctx.shared_context, "spatial_query", None) if ctx.shared_context else None
        # P5 FIX: Fallback для IPT/DriftLab, где shared_context может быть пустым. SpatialQueryService — чистый ридер scene_state.
        if not _spatial_query_for_pipeline and ctx.scene_state:
            from app.services.spatial.spatial_query_service import SpatialQueryService
            _spatial_query_for_pipeline = SpatialQueryService(
                npc_positions=ctx.scene_state.get("npc_positions", {}),
                scene_state=ctx.scene_state,
            )
        _life_engine = self._get_life_engine()
        _idle_pressure_map = _life_engine.get_idle_pressure_map() if _life_engine else {}

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
            spatial_service=_spatial_svc_for_pipeline,
            spatial_query=_spatial_query_for_pipeline,
            l1_chronicle=getattr(self, "l1_chronicle", None), # V8-PSY-1 FIX
            idle_pressure_map=_idle_pressure_map, # V8-SOC-5 FIX
        )

        _drf_ctx = DRFExecutionContext(tick_id=ctx.tick_number, bus=ctx.drf_bus)
        _mutation = run_pipeline(_tick_state, _drf_ctx, ctx.rng_factory)

        # V8-SOC-5 FIX: Обновляем idle_pressure в LifeEngine
        if _life_engine and _mutation.idle_pressure_updates:
            _life_engine.update_idle_pressure(_mutation.idle_pressure_updates)

        # 4. Committer: Применение мутаций к контексту
        build_npc_contexts_from_intents(ctx, _mutation)

        # V8-TICK-2/7 FIX: Применяем DRF scoring overlay к собранным интентам
        if ctx.communication_intents:
            self._apply_drf_scoring_overlay(ctx.communication_intents, ctx)

        # [S99] Block 5 (Movement Bridge) вынесен в phases/movement_bridge.py
        from app.services.phases.movement_bridge import process_movement_intents

        process_movement_intents(
            movement_intents=ctx.movement_intents, ctx=ctx, orchestrator=self
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

# S118 FIX: Удалены мёртвые заглушки _phase_9_player_integration и _phase_10_player_persistence (Vulture).

    # ── Фаза 0.5: Time-driven idle-сервисы (ВСЕГДА, время не останавливается) ──

    def _phase_0_5_idle_services(self, ctx: _TickContext) -> None:
        """Time-driven decay: social drift, reputation drift, affective decay.
        Выполняется КАЖДЫЙ тик (idle + player path).
        Время идёт непрерывно — эксплойты через движение исключены.
        Дельты собираются в ctx.delta_buffer → apply_batch() в Фазе 10.
        """
        from app.services.phases.idle_services import Phase0_5Deps, run_phase_0_5

        # ADR-002: Время не останавливается. Каждый тик продвигает часы на GAME_TICK_INTERVAL_SECONDS
        self._advance_idle_time(ctx)

        # ADR-O-315: TraversalExecutionSystem проецирует TraversalState в local_position.
        from app.services.spatial.traversal_execution_system import (
            TraversalExecutionSystem,
        )

        TraversalExecutionSystem.advance(ctx.scene_state, ctx.tick_number)

        deps = Phase0_5Deps(
            l1_chronicle=getattr(self, "l1_chronicle", None),
            dynamic_field=self._dynamic_field,
            homeostasis_sub=self._homeostasis_sub,
            social_input_proj=self._social_input_proj,
            idle_handlers=self._idle_handlers,
            life_engine=self._get_life_engine(),
        )
        run_phase_0_5(ctx, deps)

        # Тело метода удалено. Логика перенесена в phases/idle_services.py

    def _advance_idle_time(self, ctx: _TickContext) -> None:
        """Продвигает игровое время на GAME_TICK_INTERVAL_SECONDS (ADR-002: время не останавливается).
        Работает даже если shared_context=None (idle-путь), читая время из scene_state.
        """
        from app.core.calendar import Calendar
        from app.core.constants import GAME_TICK_INTERVAL_SECONDS

        # BUG-P0-01 FIX: Единственный источник абсолютного времени — scene_state["game_time_seconds"].
        # Чтение legacy time_of_day убивает дни/годы и залипает на "07:00" между тиками.
        current_seconds = ctx.scene_state.get("game_time_seconds", 0)
        if (
            current_seconds == 0
            and ctx.shared_context is not None
            and hasattr(ctx.shared_context, "game_time_seconds")
            and ctx.shared_context.game_time_seconds
        ):
            current_seconds = ctx.shared_context.game_time_seconds

        new_seconds = Calendar.advance(current_seconds, GAME_TICK_INTERVAL_SECONDS)

        # Обновляем оба источника данных
        if ctx.shared_context is not None and hasattr(
            ctx.shared_context, "game_time_seconds"
        ):
            ctx.shared_context.game_time_seconds = new_seconds

        # INV-DEF: Проверка инварианта времени (INV-TIME-FREEZE)
        _prev_game_time = ctx.scene_state.get("_prev_game_time_seconds", 0.0)
        if ctx.tick_number > 1 and new_seconds <= _prev_game_time:
            from app.errors import SimulationIntegrityError

            raise SimulationIntegrityError(
                invariant_id="INV-TIME-FREEZE",
                message=(
                    f"game_time_seconds не растёт: prev={_prev_game_time}, "
                    f"curr={new_seconds} на тике {ctx.tick_number}"
                ),
                suspect_files=[
                    "backend/app/core/calendar.py:advance()",
                    "backend/app/services/tick_orchestrator.py (_advance_idle_time)",
                ],
                file=__file__,
                line=1053,
            )
        ctx.scene_state["_prev_game_time_seconds"] = new_seconds

        # Сохраняем абсолютное время в scene_state для персистенции и фронтенда
        ctx.scene_state["game_time_seconds"] = new_seconds
        new_hhmm = Calendar.format_time(new_seconds)
        ctx.scene_state.setdefault("environment", {})["time_of_day"] = new_hhmm

    def _phase_8_drain_secondary(self, ctx: _TickContext) -> None:
        """ФАЗА 8: Layered Reduction — делегировано в phases/reduction.py (S100)."""
        from app.services.phases.reduction import execute_reduction_phase

        _l1 = getattr(self, "l1_chronicle", None)
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
        if not hasattr(self, "_manifest_svc"):
            from app.services.perception.behavior_manifestation_service import (
                BehaviorManifestationService,
            )
            from app.services.perception.phenomenology_projection_service import (
                PhenomenologyProjectionService,
            )

            self._manifest_svc = BehaviorManifestationService()
            self._project_svc = PhenomenologyProjectionService()

        from app.services.phases.integration import (
            Phase9IntegrationDeps,
            run_phase_9_integration,
        )

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
            project_svc=self._project_svc,
        )
        run_phase_9_integration(ctx, deps)

        # Тело метода удалено. Логика перенесена в phases/integration.py

    def _run_affective_pipeline(self, ctx: _TickContext) -> None:
        """ADR-049: Аффективный аккумулятор — накопление давления и фазовый переход эмоций.

        Вызывается из ОБЕИХ путей (idle + player turn).
        Без этого affective_load не растёт при player turn → emotion=NEUTRAL → _emotion_modifier()=0.0.
        """
        from app.services.phases.affective import Phase9Deps, run_affective_pipeline

        deps = Phase9Deps(
            crystallized_belief_store=self.crystallized_belief_store,
            drive_resolver=self.drive_resolver,
            l1_chronicle=self.l1_chronicle,
            pattern_detector=self.pattern_detector,
            belief_engine=self.belief_engine,
            state_applicator=self._state_applicator,
            snapshot_builder=self._get_snapshot_builder(),
            manifest_svc=getattr(self, "_manifest_svc", None),
            project_svc=getattr(self, "_project_svc", None),
        )
        run_affective_pipeline(ctx, deps)

        # Тело метода удалено. Логика перенесена в phases/affective.py

    def _phase_10_persistence(self, ctx: _TickContext) -> None:
        """Atomic commit: SQLite (runtime truth) + YAML (для человека)."""
        from app.services.phases.commit_phase import execute_persistence

        execute_persistence(ctx, self, is_player_turn=ctx.is_player_turn)

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
            if not hasattr(_intent, "npc_id"):
                continue
            _npc_id = _intent.actor_id
            _npc_claims = [
                c
                for c in _claims
                if c.get("target_npc") == _npc_id or c.get("npc_id") == _npc_id
            ]
            if not _npc_claims:
                continue

            _reason = getattr(_intent, "reason", "")

            # Аддитивный скоринг: base + Σ(energy × weight × alignment)
            _drf_bonus = 0.0
            for c in _npc_claims:
                _ptype = c.get("pressure_type", "ROUTINE")
                from app.services.drf_bus import _DRF_PRESSURE_WEIGHTS

                _weight = _DRF_PRESSURE_WEIGHTS.get(_ptype, 0.02)
                _energy = c.get("energy", 0.5)
                _vector = str(c.get("vector", ""))
                _aligned = _vector in _reason
                _DRF_ALIGNED = 1.2
                _DRF_MISALIGNED = 0.8
                _alignment_mult = _DRF_ALIGNED if _aligned else _DRF_MISALIGNED
                _drf_bonus += _energy * _weight * _alignment_mult

            _old_priority = _intent.priority
            _intent.priority = min(1.0, _intent.priority + _drf_bonus)
            if _drf_bonus > 0.01:
                logger.debug(
                    f"[DRF_VOTE] npc={_npc_id} base={_old_priority:.2f} bonus={_drf_bonus:.3f} final={_intent.priority:.2f}"
                )

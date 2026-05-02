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
ФАЗА 8: Handlers (TODO: явные подписчики)
ФАЗА 9: Integration (WorldSnapshotBuilder → WorldSnapshotDTO)
ФАЗА 10: Persistence (atomic commit через PersistencePort)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Union

from app.domain.tick import TickResultDTO
from app.services.events.event_types import EventType
from app.services.npc.life_engine import get_life_engine
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from app.services.npc.topic_extractor import extract_topic
from app.services.events.event_bus import get_event_bus
from app.services.events.intent_event_adapter import IntentEventAdapter
from app.services.spatial.spatial_event_detector import (
    SpatialEventDetector,
    _npc_positions_snapshot,
)
from app.services.spatial.transit_tracker import TransitTracker
from app.services.spatial.location_graph import load_graph
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
    # Фаза 10: данные для атомарного коммита
    # npc_states: полные стейты NPC после мутаций LifeEngine (фаза 0)
    npc_states: list[dict] = field(default_factory=list)
    # tick_events: все события тика для аудита (decision_events + spatial + handlers)
    tick_events: list[dict] | None = None


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
    npc_contexts: list = field(default_factory=list)
    snapshot: Optional[dict] = None
    events: List[Any] = field(default_factory=list)
    dirty_npcs: set = field(default_factory=set)
    activity_overrides: Dict[str, str] = field(default_factory=dict)
    max_npc_stress: float = 0.0


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
        # P1.1f: Social propagation — состояние тика переносим с GameLoop
        self._social_tick: int = 0
        self._social_engine_factory: Any = None  # callable(campaign_id) → SocialEngine

    def _get_life_engine(self):
        if self._life_engine is None:
            self._life_engine = get_life_engine()
        return self._life_engine

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
        """Внедрение фабрики SocialEngine — callable(campaign_id) → SocialEngine."""
        self._social_engine_factory = factory

    def execute(
        self,
        campaign_id: str,
        scene_state: dict,
        tick_number: int = 0,
        dm_ctx: Optional["DMContextDTO"] = None,
        npc_services: Optional[Any] = None,
    ) -> Union[TickResultDTO, TickPlayerResultDTO]:
        """Единственная точка входа для тика мира.

        Два режима:
        - idle (dm_ctx=None): полный 10-фазовый цикл без игрока
        - player (dm_ctx=...): фазы 3-6 через legacy pipeline, без 8-10
        """
        if scene_state is None:
            return TickResultDTO(status="no_scene")

        ctx = _TickContext(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=tick_number,
            dm_ctx=dm_ctx,
            npc_services=npc_services,
        )

        try:
            if dm_ctx is not None:
                # Player turn: фазы 0-2 уже выполнены в _run_pipeline
                self._phase_5_player_decision(ctx)
                self._phase_6_post_decision(ctx)
            else:
                # Idle tick: полный 10-фазовый цикл
                self._snapshot_positions_before(ctx)
                self._phase_0_simulation(ctx)
                self._phase_1_input(ctx)
                self._phase_2_event_bus_primary(ctx)
                self._phase_3_memory(ctx)
                self._phase_4_pre_decision(ctx)
                self._phase_5_decision(ctx)
                self._phase_6_post_decision(ctx)
                self._phase_8_handlers(ctx)
                self._phase_9_integration(ctx)
                self._phase_10_persistence(ctx)

        except Exception as e:
            logger.error(f"[TICK_ORCH] Ошибка в тике {campaign_id}: {e}")
            return TickResultDTO(status="error", error=str(e))

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
        result = self.execute(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=dm_ctx.current_tick,
            dm_ctx=dm_ctx,
            npc_services=npc_services,
        )
        # execute() при dm_ctx возвращает TickPlayerResultDTO
        return result  # type: ignore[return-value]

    # ── Player Turn: decision через legacy pipeline ───────────────────

    def _phase_5_player_decision(self, ctx: _TickContext) -> None:
        """Player turn: делегирует в run_npc_pipeline (topic, DecisionHub, StateApplicator).

        Фазы 0-2 уже выполнены в _run_pipeline (DM, EventBus, CharacterFilter).
        Фазы 8-10 выполнит _run_pipeline (finalize, commit).
        Здесь — только decision + state mutation + IntentEventAdapter.
        """
        from app.services.npc.npc_tick_contracts import NpcTickInput, NpcTickBuffer
        from app.services.npc.npc_tick_pipeline import run_npc_pipeline

        dm = ctx.dm_ctx
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
        )

    # ── Player Turn: perception + social ──────────────────────────────

    def apply_perception(
        self,
        all_npc_contexts: list[dict],
        shared_context: Any,
        campaign_id: str,
    ) -> None:
        """ФАЗА 5: PerceptionFilter — фильтрация NPC контекстов.

        Использует внедрённый event_bus вместо прямого аргумента (Устав §5.1).
        Мутирует shared_context.npc_contexts и shared_context.perceiving_npcs.
        """
        from app.services.game_loop.phase_5_perception import apply_perception_filter
        apply_perception_filter(
            all_npc_contexts, shared_context, campaign_id, self._get_event_bus(),
        )

    def propagate_social(
        self,
        shared_context: Any,
        all_npcs_raw: list[dict],
        tick_ctx: Any,
        campaign_id: str,
    ) -> None:
        """ШАГ D: Social Propagation — слухи доходят до непрямо воспринимающих NPC.

        Перенесено с GameLoop — TickOrchestrator владеет _social_tick (Устав §5.1).
        Мутирует all_npcs_raw (trust/stress) и tick_ctx.prop_dirty.
        """
        if self._social_engine_factory is None:
            logger.debug("[TICK_ORCH] propagate_social: нет social_engine_factory — пропускаем")
            return

        from app.services.social.propagation import propagate_social_rumors
        social_engine = self._social_engine_factory(campaign_id)
        self._social_tick = propagate_social_rumors(
            social_engine, self._social_tick, shared_context, all_npcs_raw, tick_ctx,
        )

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
        npc_state_updates = npc_result.get("npc_state_updates", [])
        if npc_state_updates:
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

        # Decay каждые 10 ходов
        from app.services.memory.working_memory_tick import run_decay_and_resonance
        _tick = (shared_context.scene_state or {}).get("snapshot_tick", 0)
        run_decay_and_resonance(
            self._get_memory_manager(), campaign_id, _tick,
            shared_context.active_npc_ids,
        )

        return npc_result

    def finalize_and_commit(
        self,
        tick_ctx: Any,  # TickBuffer — lazy import чтобы избежать циклической зависимости
        actions: list,
        shared_context: Any,
        campaign_id: str,
        rules_result: Dict[str, Any],
        r3_direct_mode: bool = True,
    ) -> dict:
        """ФАЗА 7-8 + ФАЗА 10: finalize + atomic commit.

        Заменяет run_finalize_phase + commit_tick в game_loop.
        TickOrchestrator владеет полным циклом finalize → commit (Устав §4.2.1).
        Гарантирует что dirty-флаги проверяются до коммита.
        """
        npc_result = self._phase_finalize(
            tick_ctx, actions, shared_context, campaign_id,
            rules_result, r3_direct_mode,
        )

        # ФАЗА 10: Единственная точка коммита (Устав §4.2.1)
        from app.services.game_loop.phase_8_commit import commit_tick
        commit_tick(self._scene_manager, campaign_id, shared_context.scene_state, tick_ctx)

        return npc_result

    # ── Слой 4: подготовка ────────────────────────────────────────────

    def _snapshot_positions_before(self, ctx: _TickContext) -> None:
        """Снимок позиций NPC ДО тика — для SpatialEventDetector (Слой 4).
        Также продвигает TransitTracker (NPC в пути двигаются на 1 шаг).
        """
        ctx.old_npc_positions = _npc_positions_snapshot(ctx.scene_state)

        # TransitTracker: NPC в пути продвигаются на 1 шаг ДО фазы 0
        tracker = self._get_transit_tracker()
        if tracker.active_count() > 0:
            location_id = ctx.scene_state.get("location_id", "")
            graphs = {}
            if location_id:
                try:
                    graphs[location_id] = load_graph(location_id)
                except Exception:
                    pass
            transit_changes = tracker.advance_all(graphs, ctx.tick_number)
            if transit_changes and self._scene_manager:
                self._scene_manager.apply_changes(ctx.campaign_id, transit_changes, ctx.scene_state)
                logger.debug(f"[TICK_ORCH] Transit: {len(transit_changes)} шагов")

    # ── ФАЗЫ ──────────────────────────────────────────────────────────

    def _phase_0_simulation(self, ctx: _TickContext) -> None:
        """LifeEngine: need-driven, schedule, random events. Чистый Python.
        
        Применяет изменения сразу — phase 5 (Decision) должен видеть свежий state.
        Передаёт TransitTracker в MovementEngine для регистрации новых путей.
        """
        engine = self._get_life_engine()
        runtime_path = self._get_npc_runtime_path(ctx.campaign_id)
        # Передаём transit_tracker чтобы MovementEngine мог регистрировать пути
        engine.set_transit_tracker(self._get_transit_tracker())
        changes = engine.tick(ctx.campaign_id, ctx.scene_state, runtime_path=runtime_path)
        ctx.scene_changes = changes or []
        # Заполняем полные стейты для фаз 3-6, 10 (Устав §3.1)
        ctx.npc_states = engine.get_npc_states(ctx.campaign_id)
        if changes and self._scene_manager:
            self._scene_manager.apply_changes(ctx.campaign_id, changes, ctx.scene_state)
            logger.debug(f"[TICK_ORCH] Фаза 0: {len(changes)} changes от LifeEngine")

    def _phase_1_input(self, ctx: _TickContext) -> None:
        """Сбор внешних событий (player action, combat и т.д.).
        
        В idle_tick нет внешнего ввода — фаза пустая.
        При player action сюда будут поступать IntentDTO.
        """
        pass

    def _phase_2_event_bus_primary(self, ctx: _TickContext) -> None:
        """Первая волна EventBus: пространственные события от MovementEngine (Слой 4).
        
        SpatialEventDetector сравнивает позиции до/после фазы 0
        и публикует NPC_MOVED, NPC_PROXIMITY_CLOSE, NPC_PROXIMITY_LEAVE.
        """
        if not ctx.old_npc_positions:
            return
        detector = SpatialEventDetector()
        _spatial_events = detector.detect_and_publish(
            old_positions=ctx.old_npc_positions,
            new_scene_state=ctx.scene_state,
        )
        if _spatial_events:
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

                mm.apply(new_event, npc_state, campaign_id=ctx.campaign_id)
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
            affected.append(event.payload.get("npc_a", ""))
            affected.append(event.payload.get("npc_b", ""))

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
        engine = self._get_life_engine()
        
        # Собираем identity L1 для каждого NPC — кристаллизованные черты личности
        mm = self._get_memory_manager()
        identities: dict[str, dict[str, float]] = {}
        for npc_dict in ctx.npc_states:
            npc_id = npc_dict.get("id")
            if npc_id:
                traits = mm.get_identity_traits(ctx.campaign_id, npc_id)
                if traits:
                    identities[npc_id] = traits
        
        decision_dicts, communication_intents = engine.tick_decisions(
            ctx.campaign_id, ctx.scene_state,
            topics=ctx.npc_topics, identities=identities,
        )
        ctx.decision_events = decision_dicts or []
        ctx.communication_intents = communication_intents or []
        if decision_dicts:
            logger.debug(f"[TICK_ORCH] Фаза 5: {len(decision_dicts)} decisions, {len(communication_intents)} intents")

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

    def _phase_8_handlers(self, ctx: _TickContext) -> None:
        """Явно подписанные обработчики: memory, social, scene, reaction.
        
        TODO: C6 — подписка через EventBus на конкретные EventType.
        """
        pass

    def _phase_9_integration(self, ctx: _TickContext) -> None:
        """WorldSnapshotBuilder: собирает WorldSnapshotDTO из финального state."""
        builder = self._get_snapshot_builder()
        ctx.world_snapshot = builder.build(
            scene_state=ctx.scene_state,
            tick=ctx.scene_state.get("snapshot_tick", ctx.tick_number),
        )

    def _phase_10_persistence(self, ctx: _TickContext) -> None:
        """Atomic commit: SQLite (runtime truth) + YAML (для человека).

        Единственная точка сохранения за тик (Устав §4.2.1).
        Делегирует в SceneStateManager.commit(), который вызывает PersistencePort.atomic_commit().
        """
        if self._scene_manager is None:
            logger.warning("[TICK_ORCH] Фаза 10: нет scene_manager — коммит пропущен")
            return

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
    def _get_npc_runtime_path(campaign_id: str) -> str:
        """Путь к runtime-данным NPC для кампании."""
        from app.core.config import settings
        return str(settings.RUNTIME_PATH / campaign_id)
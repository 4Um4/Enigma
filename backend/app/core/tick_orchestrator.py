# -*- coding: utf-8 -*-
"""
TickOrchestrator — единая точка входа для тика мира.

Строгая последовательность фаз из Архитектурного Устава §3.
Ни один сервис не вызывает другой напрямую — всё через фазы.

path: backend/app/core/tick_orchestrator.py
Назначение: Единая точка входа для тика мира. 10 фаз из Архитектурного Устава (§3).
Зависимости: domain.tick, domain.movement, services.events.event_bus, services.npc.life_engine, services.integration.world_snapshot_builder
Основные сущности: TickOrchestrator

ФАЗА 0: Simulation (LifeEngine — чистый Python, без LLM)
ФАЗА 1: Input (сбор событий из внешних источников)
ФАЗА 2: EventBus (первичная волна)
ФАЗА 3: Memory Phase (TODO: MemoryProcessor)
ФАЗА 4: Pre-Decision (TODO: TopicExtractor → тема для каждого NPC)
ФАЗА 5: Decision (DecisionHub → CommunicationIntent)
ФАЗА 6: Post-Decision (TODO: IntentEventAdapter → EventDTO)
ФАЗА 7: EventBus (вторичная волна)
ФАЗА 8: Handlers (TODO: явные подписчики)
ФАЗА 9: Integration (WorldSnapshotBuilder → WorldSnapshotDTO)
ФАЗА 10: Persistence (TODO: atomic commit)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.domain.tick import TickResultDTO

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
    # Фаза 5: решения DecisionHub
    decision_events: list = field(default_factory=list)
    # Фаза 9: финальный снимок
    world_snapshot: Optional[Any] = None


class TickOrchestrator:
    """
    Оркестратор тика мира.
    
    НЕ содержит бизнес-логику — только порядок вызовов фаз.
    Каждая фаза — отдельный сервис из services/.
    """

    def __init__(self, scene_manager=None) -> None:
        # scene_manager нужен для apply_changes внутри phase 0
        # (решения в phase 5 должны видеть обновлённый state)
        self._scene_manager = scene_manager
        # Ленивая инициализация — чтобы не тащить все сервисы при импорте
        self._life_engine = None
        self._event_bus = None
        self._snapshot_builder = None
        self._transit_tracker = None

    def _get_life_engine(self):
        if self._life_engine is None:
            from app.services.npc.life_engine import get_life_engine
            self._life_engine = get_life_engine()
        return self._life_engine

    def _get_event_bus(self):
        if self._event_bus is None:
            from app.services.events.event_bus import get_event_bus
            self._event_bus = get_event_bus()
        return self._event_bus

    def _get_snapshot_builder(self):
        if self._snapshot_builder is None:
            from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder
            self._snapshot_builder = WorldSnapshotBuilder()
        return self._snapshot_builder

    def _get_transit_tracker(self):
        if self._transit_tracker is None:
            from app.services.spatial.transit_tracker import TransitTracker
            self._transit_tracker = TransitTracker()
        return self._transit_tracker

    def execute(
        self,
        campaign_id: str,
        scene_state: dict,
        tick_number: int = 0,
    ) -> TickResultDTO:
        """
        Выполняет полный тик мира по 10 фазам.
        
        Args:
            campaign_id: идентификатор кампании
            scene_state: текущее состояние сцены (dict из SceneStateManager)
            tick_number: номер тика для логов и SceneChange
        
        Returns:
            TickResultDTO — готовый результат для API layer
        """
        if scene_state is None:
            return TickResultDTO(status="no_scene")

        ctx = _TickContext(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=tick_number,
        )

        try:
            self._snapshot_positions_before(ctx)
            self._phase_0_simulation(ctx)
            self._phase_1_input(ctx)
            self._phase_2_event_bus_primary(ctx)
            self._phase_3_memory(ctx)
            self._phase_4_pre_decision(ctx)
            self._phase_5_decision(ctx)
            self._phase_6_post_decision(ctx)
            self._phase_7_event_bus_secondary(ctx)
            self._phase_8_handlers(ctx)
            self._phase_9_integration(ctx)
            self._phase_10_persistence(ctx)

        except Exception as e:
            logger.error(f"[TICK_ORCH] Ошибка в тике {campaign_id}: {e}")
            return TickResultDTO(status="error", error=str(e))

        return TickResultDTO(
            status="ok",
            changes_count=len(ctx.scene_changes),
            significant_events=ctx.decision_events,
            world_snapshot=ctx.world_snapshot,
            # TODO: удалить после A1 — npc_positions уже внутри world_snapshot
            npc_positions=scene_state.get("npc_positions", {}),
        )

    # ── Слой 4: подготовка ────────────────────────────────────────────

    def _snapshot_positions_before(self, ctx: _TickContext) -> None:
        """Снимок позиций NPC ДО тика — для SpatialEventDetector (Слой 4).
        Также продвигает TransitTracker (NPC в пути двигаются на 1 шаг).
        """
        from app.services.spatial.spatial_event_detector import _npc_positions_snapshot
        ctx.old_npc_positions = _npc_positions_snapshot(ctx.scene_state)

        # TransitTracker: NPC в пути продвигаются на 1 шаг ДО фазы 0
        tracker = self._get_transit_tracker()
        if tracker.active_count() > 0:
            from app.services.spatial.location_graph import load_graph
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
        from app.services.spatial.spatial_event_detector import SpatialEventDetector
        detector = SpatialEventDetector()
        _spatial_events = detector.detect_and_publish(
            old_positions=ctx.old_npc_positions,
            new_scene_state=ctx.scene_state,
        )
        if _spatial_events:
            logger.debug(f"[TICK_ORCH] Фаза 2: {len(_spatial_events)} spatial events")

    def _phase_3_memory(self, ctx: _TickContext) -> None:
        """MemoryProcessor: обновляет NPCState ДО принятия решения (Устав §3.1).
        
        TODO: C2 — MemoryProcessor.apply(event, npc_state)
        """
        pass

    def _phase_4_pre_decision(self, ctx: _TickContext) -> None:
        """TopicExtractor: извлекает тему для каждого NPC (Устав §3.2).
        
        TODO: C3 — TopicExtractor читает STM + L2 → формирует topic
        Сейчас тема извлекается внутри DecisionHub, что нарушает Устав.
        """
        pass

    def _phase_5_decision(self, ctx: _TickContext) -> None:
        """DecisionHub: создаёт CommunicationIntent для каждого NPC."""
        engine = self._get_life_engine()
        decisions = engine.tick_decisions(ctx.campaign_id, ctx.scene_state)
        ctx.decision_events = decisions or []
        if decisions:
            logger.debug(f"[TICK_ORCH] Фаза 5: {len(decisions)} decisions")

    def _phase_6_post_decision(self, ctx: _TickContext) -> None:
        """IntentEventAdapter: CommunicationIntent → EventDTO (Устав §3.3).
        
        TODO: C5 — единственная точка превращения решения в событие.
        Сейчас DecisionHub возвращает dict напрямую — нарушает Устав.
        """
        pass

    def _phase_7_event_bus_secondary(self, ctx: _TickContext) -> None:
        """Вторая волна EventBus: события от NPC решений.
        
        TODO: когда IntentEventAdapter начнёт публиковать EventDTO.
        """
        pass

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
        
        TODO: C8 — PersistencePort.atomic_commit()
        Сейчас persist делается caller-ом в routes.py — нарушает Устав §4.2.1.
        """
        pass

    # ── Хелперы ───────────────────────────────────────────────────────

    @staticmethod
    def _get_npc_runtime_path(campaign_id: str) -> str:
        """Путь к runtime-данным NPC для кампании."""
        from app.core.config import settings
        return str(settings.RUNTIME_PATH / campaign_id)
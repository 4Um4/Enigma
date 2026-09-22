# path: backend/app/services/game_loop/turn_pipeline.py
"""
TurnPipeline — владелец фазовой машины player-turn (DEGOD Phase3-3A.3).

Отвечает на вопрос: «Как выполняется player turn?»
Фазы: init-context → avatar-load(DEATH-GATE) → scene-lock → DM+intent → NPC-orchestration → finalize(Rules/Avatar/R3).
Получает зависимости явными контрактами (DmPhaseDeps/NpcOrchDeps-фабрики — GameLoop) и DI-ссылками.
Не владеет: _background_tasks/_current_tick (GameLoop; доступ через провайдеры),
коммит результата (фасад), campaign lifecycle (HOLD).

Назначение: владелец фазовой машины player-turn (DEGOD Phase3-3A.3). Отвечает на вопрос «как выполняется player turn».
Зависимости: game_loop.pipeline_state, dm_phase, npc_orchestration, tick_context, phase_1_input, scene_init
Основные сущности: TurnPipeline, R3_DIRECT_MODE
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.models.schemas import ChatTurnRequest, ChatTurnResponse
from app.services.tick_orchestrator import TickPlayerResultDTO

from app.services.game_loop.pipeline_state import _PipelineState
from app.services.game_loop.tick_context import _TickContext

logger = logging.getLogger(__name__)

R3_DIRECT_MODE: bool = True


class TurnPipeline:
    """Фазовая машина player-turn. Один вопрос: как выполняется ход игрока."""

    def __init__(
        self,
        *,
        memory_manager,
        rel_store,
        scene_manager,
        avatar_service,
        dm_orchestrator,
        svc,
        mvp_controller,
        intent_compressor,
        tick_orch,
        character_service,
        world_scheduler,
        get_current_tick,
        get_life_engine,
        set_current_tick,
        spawn_world_tick_task,
        build_dm_phase_deps,
        build_npc_orch_deps,
    ) -> None:
        # Имена атрибутов = прежние self-имена => тела методов переезжают 1-в-1
        self.memory_manager = memory_manager
        self._rel_store = rel_store
        self.scene_manager = scene_manager
        self.avatar_service = avatar_service
        self.dm_orchestrator = dm_orchestrator
        self._svc = svc
        self.mvp_controller = mvp_controller
        self._intent_compressor = intent_compressor
        self._tick_orch = tick_orch
        self.character_service = character_service
        self.world_scheduler = world_scheduler
        self.get_current_tick = get_current_tick
        self._get_life_engine = get_life_engine
        self._set_current_tick = set_current_tick
        self._spawn_world_tick_task = spawn_world_tick_task
        self._build_dm_phase_deps = build_dm_phase_deps
        self._build_npc_orch_deps = build_npc_orch_deps

    # ── B-провайдеры (GameLoop-owned) ──────────────────────────────────────

    def _sync_shared_context_with_scene(
        self, scene_state: dict, shared_context: Any
    ) -> None:
        """<ТЕЛО ИЗ game_loop.py:2035–2050 1-в-1, кроме финальной строки>"""
        # ... (копия тела)
        # было: self._current_tick = scene_state.get("tick", 0) + 1
        self._set_current_tick(scene_state.get("tick", 0) + 1)

    # ── Фазы (тела переносятся 1-в-1 из game_loop.py) ─────────────────────

    async def _finalize_pipeline_and_build_dm_frame(
        self, shared_context, _ctx, campaign_id, actions, _player_result
    ) -> tuple[dict, dict]:
        """<ТЕЛО ИЗ game_loop.py:2052–2213 1-в-1, кроме:>
        # было: "relationship_store": self.memory_manager._relationships if self.memory_manager else None
        # стало: "relationship_store": self._rel_store,
        """

    async def _execute_dm_and_intent_resolution(
        self, actions, shared_context, scene_state, _ctx, campaign_id, location
    ) -> tuple[Any, Any]:
        """<ТЕЛО ИЗ game_loop.py:2215–2377 1-в-1, без изменений — все self-имена совпадают>"""

    def _prepare_and_lock_scene(
        self, campaign_id, location, shared_context, campaign_state, player_position
    ) -> dict:
        """<ТЕЛО ИЗ game_loop.py:2379–2416 1-в-1>"""

    async def _load_player_avatar(
        self, actions, campaign_id, location, shared_context
    ) -> "ChatTurnResponse | None":
        """<ТЕЛО ИЗ game_loop.py:2418–2544 1-в-1>"""

    def _init_pipeline_context(
        self, actions: list, campaign_id: str, world_id: str, location: str
    ) -> tuple[Any, dict]:
        """<ТЕЛО ИЗ game_loop.py:2546–2588, кроме блока 0 (world-tick task) — он в GameLoop._spawn_world_tick_task>
        # было: world_tick_meta = {"triggered": False, "events": []}; _task = asyncio.create_task(...)
        # стало: world_tick_meta = self._spawn_world_tick_task(world_id)
        # остальное тело (read_campaign_history + build_context) 1-в-1
        """

    async def execute(
        self,
        actions: list,
        campaign_id: str,
        world_id: str,
        location: str,
        campaign_state=None,
        is_session_start: bool = False,
        player_position: "tuple[float, float] | None" = None,
    ) -> "_PipelineState | ChatTurnResponse":
        """<ТЕЛО _run_pipeline ИЗ game_loop.py:2590–2681 1-в-1, сигнатура без changes>"""
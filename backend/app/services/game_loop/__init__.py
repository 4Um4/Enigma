# backend/app/services/game_loop/__init__.py
#
# Шаг 5 рефакторинга: единая точка входа для run_turn и stream_turn.
#
# Раньше: orchestrator.run_turn() и stream_turn() — ~400 строк дублирования.
# Теперь: один _pipeline() содержит общую логику.
#         run_turn()    — ждёт DM целиком, возвращает ChatTurnResponse.
#         stream_turn() — стримит DM токены через SSE.
#
# GameLoop не знает про FastAPI, HTTP, SSE-формат.
# Он только вызывает processor + engines + agents + memory.

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from app.models.schemas import (
    AgentTrace,
    ChatTurnRequest,
    ChatTurnResponse,
    PlayerAction,
)
from app.services.action.dm_orchestrator import DMOrchestrator
from app.services.events.event_bus import get_event_bus
from app.services.tick_orchestrator import TickOrchestrator, DMContextDTO, TickPlayerResultDTO
from app.domain.tick import TickResultDTO
# character_filter — используется только в npc_orchestration.py
from app.services.game_loop.agent_runner import run_agent_safe, AGENT_TIMEOUT_SEC, ERROR_CODES, yield_model_info

# ─────────────────────────────────────────────────────────────────────────────
# R3 DIRECT MODE: DM как единственный источник речи
# True = DecisionResult → SceneOutcome → DMFrame → DM (1 LLM вызов)
# False = legacy путь (удалён: npc_agent)
# ─────────────────────────────────────────────────────────────────────────────
R3_DIRECT_MODE: bool = True
from app.services.state.context_builder import build_context
from app.models.pipeline_context import PipelineContext
from app.services.scene_state_manager import SceneStateManager
# LayeredMemory удалён из GameLoop — все записи через MemoryManager (Закон 4.1.2)
# Старый model_router удалён — агенты сами управляют маршрутизацией через llm/router
from app.services.world_scheduler import WorldScheduler
from app.services.character_service import CharacterService
from app.services.verbalization.scene_continuity import SceneContinuity
from app.services.vram_monitor import get_vram_monitor
from app.services.error_interpreter import get_error_interpreter
from app.services.logging_tools import jsonl_log
from app.core.config import settings
from app.services.adventure_loader import AdventureLoader
from app.services.system_requirements import SystemRequirements
from app.models.schemas import CampaignLoadResponse

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────────
# Внутренний результат пайплайна (до DM-нарратива)
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class _PipelineState:
    """Всё что нужно знать агентам после Python-этапа."""
    shared_context:        PipelineContext
    classification_results: List[Dict[str, Any]]
    world_tick_meta:       Dict[str, Any]
    rules_result:          Dict[str, Any]  = field(default_factory=dict)
    npc_result:            Dict[str, Any]  = field(default_factory=dict)
    python_engines_result: Dict[str, Any]  = field(default_factory=dict)
    start_ms:              float           = field(default_factory=lambda: time.time() * 1000)


# ────────────────────────────────────────────────────────────────────────────────
# Re-exports из подмодулей
# ────────────────────────────────────────────────────────────────────────────────
from app.services.game_loop.tick_context import (
    TickInput,
    TickBuffer,
    TickOutput,
    _TickContext,  # backward compat alias
)
# commit_tick инлайн в TickOrchestrator.finalize_and_commit — phase_8_commit.py удалён
from app.services.game_loop.phase_1_input import publish_player_action
from app.services.game_loop.scene_init import init_scene_state
from app.services.game_loop.dm_phase import run_dm_phase
from app.services.game_loop.npc_orchestration import run_npc_orchestration
# run_finalize_phase удалён (мёртвый код) — логика в TickOrchestrator._phase_finalize


# ────────────────────────────────────────────────────────────────────────────────
# GameLoop
# ────────────────────────────────────────────────────────────────────────────────

class GameLoop:
    """
    Единая точка входа для одного игрового хода.

    run_turn()    → ChatTurnResponse   (REST)
    stream_turn() → AsyncIterator[dict] (SSE)
    """

    def __init__(
        self,
        *,
        data_dir: Path,
        memory_manager,          # MemoryManager — единая точка записи (Закон 4.1.2)
        dm_orchestrator: DMOrchestrator,
        scene_manager: SceneStateManager,
        world_scheduler: WorldScheduler,
        character_service: CharacterService,
        avatar_service,
        dm_agent,
        rules_agent,
        load_npcs_func,
        adventure_loader: AdventureLoader,
        system_requirements: SystemRequirements,
        saves_dir: Optional[Path] = None,
    ):
        self.data_dir         = data_dir
        self._saves_dir       = Path(saves_dir) if saves_dir else data_dir / "campaigns"
        self.memory_manager   = memory_manager
        self.dm_orchestrator  = dm_orchestrator
        self.scene_manager    = scene_manager
        self.world_scheduler  = world_scheduler
        self.character_service = character_service
        self.avatar_service = avatar_service
        # self.model_router удалён
        self.dm_agent         = dm_agent
        self.rules_agent      = rules_agent
        self._load_npcs           = load_npcs_func  # static только (для движков)
        # self._data_dir удалён — runtime через self._saves_dir, config через self.data_dir
        self.adventure_loader     = adventure_loader
        self.system_requirements  = system_requirements
        self._campaign_world_index: dict[str, str] = {}
        self._session_started_campaigns: set = set()    
        # B.3/B.4: SceneContinuity — эпизодическая фиксация сцены
        self._scene_continuities: Dict[str, SceneContinuity] = {}
        # _social_tick перенесён в SocialSubscriber (§5.1 EventBus подписки)
        # ФАЗА 3.1: Spatial Events — предыдущие расстояния для детекции переходов
        self._prev_player_distances: Dict[str, Dict[str, float]] = {}
        # ФАЗА 3.4: WorldTickEngine — проактивные действия NPC
        from app.services.world.world_tick_engine import WorldTickEngine
        self._world_tick_engine = WorldTickEngine()
        # Ленивые сервисы — вынесены в ServiceFactory
        from app.services.game_loop.service_factories import ServiceFactory
        self._svc = ServiceFactory(load_npcs_func=load_npcs_func, data_dir=data_dir)
        # P1.1b: TickOrchestrator с DI — GameLoop передаёт свои инстансы
        self._tick_orch = TickOrchestrator(
            scene_manager=scene_manager,
            memory_manager=memory_manager,
            event_bus=get_event_bus(),
        )
        # P1.1f: внедряем фабрику SocialEngine в TickOrchestrator
        self._tick_orch.set_social_engine_factory(self._svc.get_social_engine)

    def get_current_tick(self, campaign_id: str) -> int:
        """Единый источник тика — через TemporalEngine (Устав §3)."""
        return self._tick_orch.get_current_tick(campaign_id)


    # ────────────────────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ────────────────────────────────────────────────────────────────────────────

    def reset_session_flag(self, campaign_id: str) -> None:
        """Сбрасывает флаг начала сессии — следующий ход будет session_start.
        Вызывается при SESSION_REPLACED чтобы сбросить стресс NPC из прошлой сессии.
        """
        self._session_started_campaigns.discard(campaign_id)

    def _get_npc_runtime_path(self, campaign_id: str) -> Path:
        """Возвращает путь к npc_runtime.json для кампании."""
        return self._saves_dir / campaign_id / "npc_runtime.json"


    def _load_npcs_with_runtime(self, campaign_id: str) -> list:
        """Загружает NPC с наложением runtime (стресс, HP и т.д.).
        Используется в игровом цикле, не для инициализации движков.
        """
        from app.services.npc.npc_loader import load_npcs_merged
        _runtime_path = self._get_npc_runtime_path(campaign_id)
        return load_npcs_merged(runtime_path=_runtime_path)

    def idle_tick(self, campaign_id: str) -> TickResultDTO:
        """Idle tick — делегирует TickOrchestrator (10 фаз, Устав §3).

        Вызывается когда игрок бездействует (таймер pygame).
        Единая точка входа: GameLoopBridge и routes.py делегируют сюда.
        TickOrchestrator.execute(dm_ctx=None) — полный idle-цикл с
        WorldSnapshotBuilder на фазе 9.
        """
        _scene = self.scene_manager.get_scene_state(campaign_id, "")
        if _scene is None:
            return TickResultDTO(status="no_scene")

        return self._tick_orch.execute(
            campaign_id=campaign_id,
            scene_state=_scene,
            tick_number=self.get_current_tick(campaign_id),
        )

    async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
        """Блокирующий путь (REST). DM-нарратив собирается целиком."""
        self.assert_requirements()
        _is_session_start_rest = req.campaign_id not in self._session_started_campaigns
        if _is_session_start_rest:
            self._session_started_campaigns.add(req.campaign_id)
        state = await self._run_pipeline(req.actions, req.campaign_id,
                                         req.world_id, req.location,
                                         is_session_start=_is_session_start_rest,
                                         player_position=req.player_position)

        dm_result = await run_agent_safe(
            "dm", self.dm_agent,
            (
                req.location, req.actions,
                state.rules_result, state.npc_result,
                {"world_events": state.world_tick_meta.get("events", [])},
                False, state.shared_context,
            ),
            {},
        )
        # TODO: временный дебаг — удалить после починки LLM
        logger.warning(f"[DM_RESULT] type={type(dm_result).__name__}, keys={list(dm_result.keys()) if isinstance(dm_result, dict) else 'N/A'}, dm_resp={repr(dm_result.get('dm_response', '<NO KEY>')[:200]) if isinstance(dm_result, dict) else repr(dm_result)[:200]}")

        # R2.1: NarrativeExtractor R2.2.8 — синхронный путь (REST)
        try:
            from app.services.scene.narrative_extractor import get_extractor
            dm_text     = dm_result.get("dm_response", "")
            scene_state = state.shared_context.scene_state or {}
            if dm_text and scene_state:
                current_tick = self.get_current_tick(req.campaign_id)
                extraction   = get_extractor().extract(dm_text, scene_state, current_tick)
                if extraction.new_objects or extraction.new_events or extraction.updated_states:
                    self.scene_manager.apply_narrative_extractions(
                        req.campaign_id, scene_state, extraction
                    )
                    if current_tick % 50 == 0:
                        self.scene_manager.prune_dynamic_objects(
                            req.campaign_id, scene_state, current_tick
                        )
        except Exception as e:
            logger.warning(f"[R2.1] NarrativeExtractor REST error: {e}")

        # TODO: _write_memory удалён — persist_dm_response на строке ниже покрывает запись
        elapsed_ms = int(time.time() * 1000 - state.start_ms)
        traces = self._build_traces(state, dm_result, elapsed_ms)

        return ChatTurnResponse(
            dm_response=dm_result.get("dm_response", ""),
            npc_reactions=dm_result.get("npc_reactions", []),
            world_changes=dm_result.get("world_changes", []),
            journal_entry_id=self.memory_manager.persist_dm_response(
                req.campaign_id,
                world_id=req.world_id,
                location=req.location,
                actions=[a.model_dump() for a in req.actions],
                dm_text=dm_result.get("dm_response", ""),
            ),
            traces=traces,
        )

    async def stream_turn(
        self,
        campaign_id: str,
        player: str,
        action_text: str,
        location: str,
        campaign_state=None,
        player_position: tuple[float, float] | None = None,
    ) -> AsyncIterator[dict]:
        world_id = "manual"
        if campaign_state:
            world_id = campaign_state.metadata.get("world_id", "manual")

        actions = [PlayerAction(player_name=player, action=action_text)]

        is_session_start = campaign_id not in self._session_started_campaigns
        logger.warning(f"[SESSION_CHECK] campaign={campaign_id} known={self._session_started_campaigns} is_new={is_session_start}")
        if is_session_start:
            self._session_started_campaigns.add(campaign_id)

        # Немедленно отвечаем клиенту — ещё до pipeline
        yield {"type": "ping"}
        yield {"type": "status", "text": "Мастер думает..."}

        # Классификация — 0 мс, сразу отдаём тип действия
        action_type_str = self.dm_orchestrator.classify_action(action_text)
        yield {"type": "action_type", "value": action_type_str}

        # Теперь запускаем тяжёлый pipeline
        state = await self._run_pipeline(
            actions, campaign_id, world_id, location,
            campaign_state=campaign_state,
            is_session_start=is_session_start,
            player_position=player_position,
        )

        # Модели — метаинфо
        async for event in yield_model_info(state):
            yield event

        # NPC реакции — ДО токенов DM
        npc_reactions = (
            state.npc_result.get("npc_reactions", [])
            + state.npc_result.get("npc_actions", [])
        )
        if npc_reactions:
            yield {
                "type":  "npc",
                "data":  npc_reactions,
                "model": state.npc_result.get("model"),
            }

        # DM — стриминг токенов
        yield {"type": "status", "text": "Мастер рассказывает..."}
        token_count   = 0
        world_result  = {"world_events": []}
        dm_text_parts: list[str] = []   # R2.1: буфер для экстрактора

        try:
            async for token in self.dm_agent.stream_narrate(
                location=location,
                actions=actions,
                rules_result=state.rules_result,
                npc_result=state.npc_result,
                world_result=world_result,
                world_canon_exists=False,
                context=state.shared_context,
                is_session_start=is_session_start,
            ):
                token_count += 1
                dm_text_parts.append(token)   # R2.1
                yield {"type": "token", "text": token, "n": token_count}
        except Exception as e:
            yield {"type": "error", "text": str(e)}
            return

        elapsed_ms = int(time.time() * 1000 - state.start_ms)
        tps = round(token_count / (elapsed_ms / 1000), 1) if elapsed_ms > 0 else 0

        # Сохраняем DM-ответ в Campaign Memory ДО yield done — SSE не гарантирует выполнение после
        dm_full_text_for_mem = "".join(dm_text_parts)
        if dm_full_text_for_mem:
            self.memory_manager.persist_dm_response(
                campaign_id,
                world_id=world_id,
                location=location,
                actions=[a.model_dump() for a in actions],
                dm_text=dm_full_text_for_mem,
            )
            # Лог вопроса + ответа для отладки
            _player_msg = next((a.action for a in actions if a.action), "")
            _preview_q = _player_msg[:80] + "..." if len(_player_msg) > 80 else _player_msg
            _preview_a = dm_full_text_for_mem[:120] + "..." if len(dm_full_text_for_mem) > 120 else dm_full_text_for_mem
            logger.warning(f"[DM] {_preview_q}")
            logger.warning(f"[NPC] {_preview_a}")

        yield {
            "type": "done",
            "tokens": token_count,
            "ms": elapsed_ms,
            "tps": tps,
            "game_time_seconds": state.shared_context.game_time_seconds or 0,
        }

        # R2.1: NarrativeExtractor R2.2.8
        try:
            from app.services.scene.narrative_extractor import get_extractor
            dm_full_text = "".join(dm_text_parts)
            scene_state  = state.shared_context.scene_state or {}
            if dm_full_text and scene_state:
                current_tick = self.get_current_tick(campaign_id)
                extraction   = get_extractor().extract(dm_full_text, scene_state, current_tick)
                if extraction.new_objects or extraction.new_events or extraction.updated_states:
                    self.scene_manager.apply_narrative_extractions(
                        campaign_id, scene_state, extraction
                    )
                    # Фикс #6: prune каждые 50 тиков
                    if current_tick % 50 == 0:
                        self.scene_manager.prune_dynamic_objects(
                            campaign_id, scene_state, current_tick
                        )
                    logger.debug(
                        f"[R2.1] objects={len(extraction.new_objects)} "
                        f"events={len(extraction.new_events)} "
                        f"state_updates={len(extraction.updated_states)}"
                    )
        except Exception as e:
            logger.warning(f"[R2.1] NarrativeExtractor error: {e}")

    async def _run_pipeline(
        self,
        actions: list,
        campaign_id: str,
        world_id: str,
        location: str,
        campaign_state=None,
        is_session_start: bool = False,
        player_position: tuple[float, float] | None = None,
    ) -> _PipelineState:
        """Фазовый пайплайн: DM → NPC → Perception → Social → Rules → Finalize → Commit.

        Каждый блок — отдельный модуль в game_loop/. Подробнее: dm_phase, npc_orchestration.
        """
        start_ms = time.time() * 1000
        _ctx = _TickContext()

        # 0. World tick — асинхронный фон, не блокирует ответ игроку
        world_tick_meta = {"triggered": False, "events": []}
        asyncio.create_task(asyncio.to_thread(
            self.world_scheduler.maybe_tick, world_id, settings.world_tick_minutes,
        ))

        # 1. Базовый shared_context
        _raw_mem = self.memory_manager.read_campaign_history(campaign_id, limit=3)
        if _raw_mem:
            logger.warning(f"[RECENT_MEM] {len(_raw_mem)} entries, dm_fields={[bool(e.get('dm')) for e in _raw_mem]}")
        shared_context = build_context(
            campaign_id=campaign_id, world_id=world_id, location=location,
            player=actions[0].player_name if actions else "",
            scene_state={}, python_engines={},
            recent_memory=[e["dm"] for e in _raw_mem if e.get("dm")],
            reaction_order=[],
        )

        # 2. Загрузка аватара игрока
        _player_name = actions[0].player_name if actions else ""
        try:
            _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)
            _sheets = self.character_service.list_characters(campaign_id)
            _match = next((s for s in _sheets if s.name == _player_name), None)
            if _match and self.avatar_service.load_avatar(campaign_id, _player_name) is None:
                self.avatar_service.migrate_from_characters_json(campaign_id, _match)
                _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)
            from app.services.game_loop.phase_6_avatar import avatar_to_prompt
            shared_context.player_state = {_player_name: avatar_to_prompt(_avatar_state)}
        except Exception as _e:
            logger.warning(f"[AVATAR] ошибка загрузки: {_e}")

        scene_state = init_scene_state(self, campaign_id, location, shared_context, campaign_state,
                                       player_position=player_position)

        # ФАЗА 1-3: DM классификация + EventBus + STM + время
        try:
            dm_result = run_dm_phase(
                self, actions, shared_context, scene_state, _ctx, campaign_id, location,
            )
            logger.warning(f"[DEBUG DM] is_valid={dm_result.is_valid}, scene_context={dm_result.scene_context}, error={dm_result.error}")

            # ФАЗА 1 (сырая публикация) — действие игрока → EventBus ДО NPC (Закон 5.1)
            publish_player_action(
                _player_name, actions[0].action if actions else "",
                shared_context.action_type or "player_interacts", location,
            )

            # ФАЗА 3-6: NPC оркестрация → TickPlayerResultDTO (Устав §3)
            _player_result: TickPlayerResultDTO = TickPlayerResultDTO()
            if dm_result.is_valid and dm_result.scene_context:
                _player_result = run_npc_orchestration(
                    self, actions, shared_context, scene_state, _ctx,
                    campaign_id, location, is_session_start,
                    tick_orchestrator=self._tick_orch,
                )

            python_engines_result = {"dm_result": dm_result, "npc_contexts": _player_result.npc_contexts}
        except Exception as e:
            logger.error(f"[GAME_LOOP] DM/NPC phase error: {e}", exc_info=True)
            python_engines_result = {"dm_result": None, "npc_contexts": []}
            _player_result = TickPlayerResultDTO()

        shared_context.python_engines = python_engines_result

        # ФАЗА 7: Rules агент (асинхронный — не зависит от npc_contexts)
        _action_type = shared_context.action_type or "player_interacts"
        _rules_context = {"classification": [{
            "player": actions[0].player_name,
            "type": self.dm_orchestrator._router.get_rules_action_type(_action_type),
        }]}
        rules_result = await run_agent_safe(
            "rules", self.rules_agent, (actions, _rules_context), {},
        )
        logger.warning(f"[RULES] action_type={_action_type} → {_rules_context['classification'][0]['type']}")

        # ФАЗЫ 8-10: Perception + Social + Finalize + Commit (Устав §3 — единая последовательность)
        try:
            _player_result = self._tick_orch.execute_player_finalize(
                _player_result, _ctx, shared_context, actions, campaign_id,
                rules_result, r3_direct_mode=R3_DIRECT_MODE,
            )
            npc_result = _player_result.finalize_result or {}
        except Exception as _fin_err:
            logger.error(f"[GAME_LOOP] Finalize error: {_fin_err}", exc_info=True)
            npc_result = {}
            shared_context.npc_contexts = _player_result.npc_contexts

        # Avatar update — после perception (shared_context.npc_contexts отфильтрован)
        try:
            from app.services.game_loop.phase_6_avatar import update_avatar_from_npc_intents
            from app.models.npc_state import EmotionTag
            update_avatar_from_npc_intents(
                self.avatar_service, campaign_id, _player_name,
                shared_context.npc_contexts or [], EmotionTag,
            )
        except Exception as _av_err:
            logger.warning(f"[AVATAR] update error: {_av_err}")

        return _PipelineState(
            shared_context=shared_context,
            classification_results=[],
            world_tick_meta=world_tick_meta,
            rules_result=rules_result,
            npc_result=npc_result,
            python_engines_result=python_engines_result,
            start_ms=start_ms,
        )

    # ────────────────────────────────────────────────────────────────────────────
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ────────────────────────────────────────────────────────────────────────────

    def _get_character_dict(self, campaign_id: str, player_name: str) -> dict:
        try:
            characters = self.character_service.list_characters(campaign_id)
            for char in characters:
                if char.name == player_name:
                    return char.model_dump()
        except Exception as e:
            logger.warning(f"[GAME_LOOP] Персонаж '{player_name}' не найден: {e}")
        return {}

    def _build_traces(
        self, state: _PipelineState, dm_result: dict, elapsed_ms: int
    ) -> list:
        return [
            AgentTrace(agent="performance",     output={"turn_elapsed_ms": elapsed_ms}),
            AgentTrace(agent="world_scheduler", output=state.world_tick_meta),
            AgentTrace(agent="rules",           output=state.rules_result),
            AgentTrace(agent="npc",             output=state.npc_result),
            AgentTrace(agent="dm",              output=dm_result),
            AgentTrace(agent="python_engines",  output=state.python_engines_result),
            AgentTrace(agent="game_loop",       output={"pipeline_duration_ms": elapsed_ms}),
        ]

# ────────────────────────────────────────────────────────────────────────────────
    # УПРАВЛЕНИЕ КАМПАНИЕЙ + СИСТЕМНЫЕ ПРОВЕРКИ
    # ────────────────────────────────────────────────────────────────────────────────

    def assert_requirements(self) -> dict:
        report = self.system_requirements.check()
        if settings.enforce_system_requirements and not report.meets:
            raise RuntimeError(f"Недостаточно ресурсов: {report.details}")
        return {"meets": report.meets, **report.details}

    def load_campaign(self, campaign_id: str, world_id: str) -> CampaignLoadResponse:
        loaded = self.adventure_loader.load_campaign(campaign_id)
        self._campaign_world_index[campaign_id] = world_id
        for filename, payload in loaded.get("files", {}).items():
            self.memory_manager.persist_world_canon(
                world_id,
                campaign_id=campaign_id,
                source=filename,
                payload=payload,
            )
        self.memory_manager.persist_campaign_event(
            campaign_id,
            event="campaign_loaded",
            world_id=world_id,
            data={
                "loaded_files": list(loaded.get("files", {})),
                "status":       loaded["status"],
            },
        )
        return CampaignLoadResponse(
            campaign_id  = campaign_id,
            world_id     = world_id,
            status       = loaded["status"],
            loaded_files = list(loaded.get("files", {})),
        )

    def session_state(self, campaign_id: str):
        """Возвращает состояние сессии для UI."""
        world_id = self._resolve_world_id(campaign_id)

        class State:
            pass

        state = State()
        state.campaign_id         = campaign_id
        state.world_id            = world_id
        state.session_log         = []
        state.dice_input_required = False
        state.layers              = {}
        return state

    def _resolve_world_id(self, campaign_id: str) -> str:
        if campaign_id in self._campaign_world_index:
            return self._campaign_world_index[campaign_id]
        history = self.memory_manager.read_campaign_history(campaign_id, limit=100)
        for item in reversed(history):
            if item.get("event") == "campaign_loaded" and item.get("world_id"):
                self._campaign_world_index[campaign_id] = item["world_id"]
                return item["world_id"]
        return "manual"

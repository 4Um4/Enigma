# backend/app/services/game_loop.py
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
from app.services.character.character_filter_applicator import apply_character_filter
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
from app.services.game_loop.phase_8_commit import commit_tick
from app.services.game_loop.phase_1_input import publish_player_action, publish_player_speech, publish_classified_player_event
from app.services.game_loop.phase_2_world_tick import tick_world_proactive
from app.services.game_loop.time_advance import advance_game_time
from app.services.game_loop.scene_init import init_scene_state, ensure_scene_initialized
from app.services.game_loop.npc_state_helpers import apply_npc_state_updates, write_npc_memory
from app.services.spatial.player_target_pipeline import (
    PlayerTargetResult,
    extract_player_target,
    detect_and_publish_spatial_transitions,
    build_spatial_data_for_dm,
)
from app.services.memory.working_memory_tick import write_npc_reactions_to_memory, run_decay_and_resonance
from app.services.scene.scene_event_layer import emit_and_accumulate_scene_events
from app.services.npc.npc_tick_pipeline import run_npc_pipeline
from app.services.npc.npc_tick_contracts import NpcTickInput, NpcTickBuffer, NpcTickServices
from app.services.npc.decision_hub import EventContext as HubEventContext


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
        # ШАГ D: Social Propagation — ленивая инициализация при первом вызове
        self._social_tick: int = 0
        # ФАЗА 3.1: Spatial Events — предыдущие расстояния для детекции переходов
        self._prev_player_distances: Dict[str, Dict[str, float]] = {}
        # ФАЗА 3.4: WorldTickEngine — проактивные действия NPC
        from app.services.world.world_tick_engine import WorldTickEngine
        self._world_tick_engine = WorldTickEngine()
        # Ленивые сервисы — вынесены в ServiceFactory
        from app.services.game_loop.service_factories import ServiceFactory
        self._svc = ServiceFactory(load_npcs_func=load_npcs_func, data_dir=data_dir)


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

    async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
        """Блокирующий путь (REST). DM-нарратив собирается целиком."""
        self.assert_requirements()
        _is_session_start_rest = req.campaign_id not in self._session_started_campaigns
        if _is_session_start_rest:
            self._session_started_campaigns.add(req.campaign_id)
        state = await self._run_pipeline(req.actions, req.campaign_id,
                                         req.world_id, req.location,
                                         is_session_start=_is_session_start_rest)

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
                current_tick = scene_state.get("snapshot_tick", 0)
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
            dm_full_text = "".join(dm_text_parts)
            scene_state  = state.shared_context.scene_state or {}
            if dm_full_text and scene_state:
                current_tick = scene_state.get("snapshot_tick", 0)
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

    # ────────────────────────────────────────────────────────────────────────────
    # ОБЩИЙ ПАЙПЛАЙН (шаги 1–8 — одинаковы для REST и SSE)
    # ────────────────────────────────────────────────────────────────────────────

    async def _run_pipeline(
        self,
        actions: list,
        campaign_id: str,
        world_id: str,
        location: str,
        campaign_state=None,
        is_session_start: bool = False,
    ) -> _PipelineState:
        """
        Шаги 1–8: classify → physics → SceneState → PythonEngines → rules → npc.
        Возвращает _PipelineState — всё что нужно финальному DM-агенту.
        """
        start_ms = time.time() * 1000

        # Флаги мутаций — единый коммит в конце пайплайна
        _ctx = _TickContext()

        # 1. World tick — асинхронный фон, не блокирует ответ игроку
        world_tick_meta = {"triggered": False, "events": []}
        asyncio.create_task(
            asyncio.to_thread(
                self.world_scheduler.maybe_tick,
                world_id,
                settings.world_tick_minutes,
            )
        )

        # 3. Базовый shared_context
        _raw_mem = self.memory_manager.read_campaign_history(campaign_id, limit=3)
        if _raw_mem:
            logger.warning(f"[RECENT_MEM] {len(_raw_mem)} entries, dm_fields={[bool(e.get('dm')) for e in _raw_mem]}")
        shared_context = build_context(
            campaign_id         = campaign_id,
            world_id            = world_id,
            location            = location,
            player              = actions[0].player_name if actions else "",
            scene_state         = {},
            python_engines      = {},
            recent_memory       = [
                # Последние ответы DM — чтобы не повторять реакции NPC
                e["dm"] for e in _raw_mem if e.get("dm")
            ],
            reaction_order      = [],
        )

        # 3.5. Загрузка аватара игрока
        _player_name = actions[0].player_name if actions else ""
        try:
            _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)
            _sheets = self.character_service.list_characters(campaign_id)
            _match = next((s for s in _sheets if s.name == _player_name), None)
            if _match and self.avatar_service.load_avatar(campaign_id, _player_name) is None:
                self.avatar_service.migrate_from_characters_json(campaign_id, _match)
                _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)
            from app.services.game_loop.phase_6_avatar import avatar_to_prompt
            shared_context.player_state = {
                _player_name: avatar_to_prompt(_avatar_state)
            }
        except Exception as _e:
            logger.warning(f"[AVATAR] ошибка загрузки: {_e}")

        scene_state = init_scene_state(self, campaign_id, location, shared_context, campaign_state)

        # 5. PythonEngines
        try:
            # Извлекаем структурированные данные для нового DM
            # ВНИМАНИЕ: ключи shared_context могут немного отличаться, проверьте при первом запуске
            raw_input = actions[0].action if actions else ""
            
            # 4.5: Извлекаем цель игрока из текста — без этого target=None всегда
            try:
                _target = extract_player_target(
                    self._load_npcs, shared_context.scene_state or {}, raw_input,
                )
                if _target.target_id:
                    shared_context.player_target_id = _target.target_id
                    shared_context.player_target_name = _target.target_name

                # ФАЗА 3.1: Spatial Events — детекция переходов расстояний
                try:
                    _prev_dists = self._prev_player_distances.get(campaign_id, {})
                    _curr_dists = _target.player_dists or {}
                    _spatial_events = detect_and_publish_spatial_transitions(
                        _prev_dists, _curr_dists, location, campaign_id,
                    )
                    if _spatial_events:
                        shared_context.spatial_events = _spatial_events
                    # Сохраняем текущие для следующего хода
                    self._prev_player_distances[campaign_id] = dict(_curr_dists)
                except Exception as _se_err:
                    logger.warning(f"[SPATIAL] Transition detection failed: {_se_err}")
            except Exception as _te:
                logger.warning(f"[TARGET] Extract error: {_te}")
                pass
            
            # Строим spatial_data из scene_state для DM SceneBuilder
            _spatial_data = build_spatial_data_for_dm(location, shared_context.scene_state or {})
            
            # R1: DM видит прошлую речь NPC — из DialogueSession (Этап 1)
            try:
                _recent_speech = self.memory_manager.get_recent_speech_all_npcs(campaign_id)
                shared_context.npc_recent_speech = _recent_speech
            except Exception as _rs_err:
                logger.debug(f"[RECENT_SPEECH] error: {_rs_err}")

            # R1: DM видит недавние действия игрока — "что произошло" не из пустого
            # TODO: восстановить из EventDTO при необходимости
            shared_context.recent_player_actions = []

            dm_result = self.dm_orchestrator.process_player_action(
                raw_input=raw_input,
                player_data=shared_context.player or {},
                player_markers=shared_context.player_markers or [],
                target_npc_id=shared_context.player_target_id,
                spatial_data=_spatial_data,
                current_tick=shared_context.current_tick or 0,
            )
            
            # Передаём DM результат в контекст для NPC agent и Verbalization
            shared_context.dm_result = dm_result

            # Сохраняем классификацию из Router для DecisionHub и EventBus
            if dm_result.event_context:
                shared_context.action_type = dm_result.event_context.event_type
                logger.warning(f"[EVENT_TYPE] Router classified as: {dm_result.event_context.event_type}")

            # 5.1: Публикуем классифицированное событие в EventBus
            if dm_result.is_valid:
                _raw_type = shared_context.action_type or "dialogue"
                publish_classified_player_event(shared_context, location, campaign_id, raw_input)
                # STM: записываем реплику игрока в сессию целевого NPC
                if _raw_type in ("dialogue", "player_interacts") and shared_context.player_target_id:
                    self.memory_manager.add_dialogue_turn(
                        campaign_id=campaign_id,
                        npc_id=shared_context.player_target_id,
                        speaker="player",
                        text=raw_input,
                    )
                # STM: игрок ушёл — все диалоговые сессии обнуляются
                if _raw_type in ("move", "stealth"):
                    self.memory_manager.clear_all_dialogue_sessions(campaign_id)
                # Фаза 4 — время продвигается от действий, не от тиков
                advance_game_time(scene_state, _raw_type, raw_input, shared_context)

            # ── SCENE EVENT LAYER: единые события для восприятия всеми NPC ──
            _scene_events = emit_and_accumulate_scene_events(
                action_type=shared_context.action_type or "player_interacts",
                target_id=shared_context.player_target_id or "",
                location_id=location,
                tick=shared_context.current_tick or 0,
                action_text=raw_input,
                scene_state=scene_state,
            )
            shared_context.scene_events = _scene_events

            # Этап 4: Формируем NPC контексты для DecisionHub

            npc_contexts = []
            logger.warning(f"[DEBUG DM] is_valid={dm_result.is_valid}, scene_context={dm_result.scene_context}, error={dm_result.error}")
            if dm_result.is_valid and dm_result.scene_context:
                # Инжектируем line_of_sight в scene_state для SceneOutcomeBuilder
                if dm_result.scene_context.line_of_sight is not None:
                    scene_state["line_of_sight"] = dm_result.scene_context.line_of_sight

                # EventContext с intensity уже сформирован в dm_scene_builder.enrich_raw_event
                _ctx.hub_event = dm_result.event_context or HubEventContext(event_type="player_interacts", actor_id="player")

                _cf_result = apply_character_filter(self.character_service, campaign_id, actions[0].player_name if actions else '', _ctx.hub_event, shared_context)
                if _cf_result:
                    _ctx.hub_event = None

                # Если CharacterFilter заблокировал действие — пропускаем NPC цикл
                if _ctx.hub_event is None:
                    logger.warning("[CHAR_FILTER] Action blocked, skipping NPC decisions")

                # SceneContinuity нужен ДО NPC цикла (физические факты)
                if not hasattr(shared_context, "scene_continuity"):
                    shared_context.scene_continuity = self._scene_continuities.setdefault(campaign_id, SceneContinuity())

                # Инжект SceneContinuity в EventContext — NPC видит МИР, не только текущее действие
                _cont_inject = shared_context.scene_continuity
                if _cont_inject and _ctx.hub_event:
                    _ctx.hub_event.scene_flags = _cont_inject.active_flags
                    _ctx.hub_event.scene_facts = _cont_inject.scene_facts[-3:]

                # Загружаем ВСЕХ NPC один раз — мутации будут в этом списке
                _ctx.all_npcs_raw = self._load_npcs_with_runtime(campaign_id)

                # ── NPC фаза: Вариант C (Input/Buffer/Services) ──
                _npc_buf = NpcTickBuffer()
                if _ctx.hub_event is not None:
                    _npc_svc = NpcTickServices(
                        memory_manager=self.memory_manager,
                        relationship_store=self.memory_manager._relationships,
                        social_engine=self._svc.get_social_engine(campaign_id),
                        reputation_engine=self._svc.get_reputation_engine(),
                        economic_profiles=self._svc.get_or_create_economic_profiles(campaign_id),
                    )
                    _npc_inp = NpcTickInput(
                        campaign_id=campaign_id,
                        location=location,
                        scene_state=shared_context.scene_state or {},
                        player_target_id=shared_context.player_target_id,
                        hub_event=_ctx.hub_event,
                        is_session_start=is_session_start,
                        action_type=shared_context.action_type or "",
                        raw_input=raw_input,
                        current_tick=shared_context.current_tick or 0,
                        all_npcs_raw=_ctx.all_npcs_raw,
                        nearby_npcs=dm_result.scene_context.nearby_npcs,
                        scene_continuity=shared_context.scene_continuity,
                        spatial_events=shared_context.spatial_events or [],
                        line_of_sight=dm_result.scene_context.line_of_sight,
                    )
                    _npc_buf = run_npc_pipeline(_npc_inp, _npc_buf, _npc_svc)

                # Проекция результатов обратно в оркестратор
                _ctx.dirty_npcs.update(_npc_buf.dirty_npcs)
                npc_contexts.extend(_npc_buf.npc_contexts)
                _ctx.max_npc_stress = max(_ctx.max_npc_stress, _npc_buf.max_npc_stress)
                # Activity overrides → scene_state (единственная мутация scene_state из NPC фазы)
                for _nid, _activity in _npc_buf.activity_overrides.items():
                    if _nid in scene_state.get("npc_positions", {}):
                        scene_state["npc_positions"][_nid]["activity"] = _activity
                # ФАЗА 3.5: Reputation impact — влияние действий на репутацию фракций
                _rep_eng = self._svc.get_reputation_engine()
                if _rep_eng and _ctx.hub_event:
                    try:
                        _action_type_for_rep = shared_context.action_type or ""
                        _rep_deltas = _rep_eng.apply_event_impact(
                            event_type=_action_type_for_rep,
                            actor_npc_id=None,  # игрок — не NPC
                            target_npc_id=shared_context.player_target_id,
                        )
                        if _rep_deltas:
                            _rep_eng.apply_deltas(_rep_deltas)
                            logger.warning(f"[REPUTATION] {len(_rep_deltas)} faction deltas applied")
                    except Exception as _rep_err:
                        logger.warning(f"[REPUTATION] Impact error: {_rep_err}")
                # ФАЗА 3.4: WorldTickEngine — проактивные действия NPC
                tick_world_proactive(self._world_tick_engine, self._svc.get_reputation_engine(), self.memory_manager._relationships, self._svc.get_or_create_economic_profiles, campaign_id, location, shared_context, _ctx)

                # Salience Engine: передаём метаданные для фильтрации объектов в промпте
                _scene_for_dm = shared_context.scene_state or {}
                _scene_for_dm["_salience_event_type"] = getattr(_ctx.hub_event, "event_type", "player_interacts")
                _scene_for_dm["_salience_max_stress"] = _ctx.max_npc_stress
                _scene_for_dm["_salience_target_object"] = _scene_for_dm.get("player_target_object")
            
            python_engines_result = {
                "dm_result": dm_result,
                "npc_contexts": npc_contexts,  
            }
            
        except Exception as e:
            logger.error(f"[GAME_LOOP] DM Orchestrator error: {e}", exc_info=True)
            python_engines_result = {"dm_result": None, "npc_contexts": []}

        shared_context.python_engines = python_engines_result
        _all_npc_contexts = python_engines_result.get("npc_contexts", [])

        # 5.5: PerceptionFilter — фильтруем npc_contexts по воспринимающим NPC
        try:
            from app.services.game_loop.phase_5_perception import apply_perception_filter
            apply_perception_filter(
                _all_npc_contexts, shared_context, campaign_id, get_event_bus(),
            )

            # ФАЗА 6: Обновление аватара игрока — реакция на NPC
            from app.services.game_loop.phase_6_avatar import update_avatar_from_npc_intents, avatar_to_prompt
            from app.models.npc_state import EmotionTag
            _player_name = actions[0].player_name if actions else ""
            update_avatar_from_npc_intents(
                self.avatar_service, campaign_id, _player_name,
                shared_context.npc_contexts or [], EmotionTag,
            )

        except Exception as _pf_err:
            
            logger.warning(f"[PERCEPTION_FILTER] error: {_pf_err}")
            pass
            shared_context.npc_contexts = _all_npc_contexts

        # ШАГ D: Social Propagation — слухи доходят до непрямо воспринимающих NPC
        try:
            from app.services.social.propagation import propagate_social_rumors
            from app.services.scene.r3_direct_builder import build_r3_dm_frame
            from app.services.character.front_applicator import apply_front_engine
            # apply_character_filter перенесён в top-level imports (используется на линии 630)
            # run_agent_safe, AGENT_TIMEOUT_SEC, ERROR_CODES, yield_model_info перенесены в top-level imports
            self._social_tick = propagate_social_rumors(
                self._svc.get_social_engine(campaign_id),
                self._social_tick,
                shared_context,
                _ctx.all_npcs_raw,
                _ctx,
            )
        except Exception as _se_err:
            logger.warning(f"[SOCIAL] Propagation failed: {_se_err}")

        # 6. Rules агент — передаём классификацию из Router
        _action_type = shared_context.action_type or "player_interacts"
        _rules_context = {
            "classification": [{
                "player": actions[0].player_name,
                "type": self.dm_orchestrator._router.get_rules_action_type(_action_type), 
            }]
        }
        rules_result = await run_agent_safe(
            "rules", self.rules_agent, (actions, _rules_context), {}
        )
        logger.warning(f"[RULES] action_type={_action_type} → {_rules_context['classification'][0]['type']}")

        # 6.5 Действие игрока → EventBus (Закон 5.1)
        if actions and actions[0].action:
            publish_player_speech(
                actions[0].player_name,
                actions[0].action,
                _rules_context['classification'][0]['type'],
            )

        # 7. NPC агент / R3 Direct Mode
        if R3_DIRECT_MODE:
            npc_result = build_r3_dm_frame(shared_context, actions, rules_result)

        # Применяем trust/stress дельты
        npc_state_updates = npc_result.get("npc_state_updates", [])
        if npc_state_updates:
            apply_npc_state_updates(self, npc_state_updates, npc_dicts=_ctx.all_npcs_raw, campaign_id=campaign_id)
        # Записываем ход в память NPC
        write_npc_memory(
            loop          = self,
            npc_reactions = npc_result.get("npc_reactions", []),
            player        = actions[0].player_name if actions else "игрок",
            action_text   = actions[0].action if actions else "",
            npc_dicts     = _ctx.all_npcs_raw,
        )

        # ── R1 CONNECT: Working Memory ─────────────────────────────────────────
        _player_text = actions[0].action if actions else ""
        _player_name = actions[0].player_name if actions else "игрок"

        # action_type из классификатора (для ImportanceEngine)
        _act_type = shared_context.action_type or "unknown"

        # P0.1: действие игрока → EventBus (Закон 5.1)
        publish_player_action(_player_name, _player_text, _act_type, location)

        # P0.2: ответы NPC → Working Memory + STM
        write_npc_reactions_to_memory(
            self.memory_manager,
            npc_result.get("npc_reactions", []),
            _ctx.all_npcs_raw,
            campaign_id,
        )

        # P0.3: decay каждые 10 ходов
        _tick = (shared_context.scene_state or {}).get("snapshot_tick", 0)
        run_decay_and_resonance(
            self.memory_manager, campaign_id, _tick, shared_context.active_npc_ids,
        )
        # ────────────────────────────────────────────────────────────────────────
        # ФАЗА 8: Единственная точка коммита (Устав 4.2.1)
        commit_tick(self.scene_manager, campaign_id, shared_context.scene_state, _ctx)

        return _PipelineState(
            shared_context         = shared_context,
            classification_results = [],
            world_tick_meta        = world_tick_meta,
            rules_result           = rules_result,
            npc_result             = npc_result,
            python_engines_result  = python_engines_result,
            start_ms               = start_ms,
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

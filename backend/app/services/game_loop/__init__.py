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
from app.services.game_loop.phase_1_input import resolve_player_intent, publish_classified_player_event
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

        # Фаза 0.5: DI для idle-сервисов (social decay, reputation decay)
        _rep_engine = self._svc.get_reputation_engine()
        _rel_store = memory_manager._relationships if memory_manager else None
        _state_applicator = self._svc.get_state_applicator(
            relationship_store=_rel_store,
        ) if _rel_store else None

        if _state_applicator:
            self._tick_orch.set_state_applicator(_state_applicator)
        if _rep_engine:
            self._tick_orch.set_reputation_engine(_rep_engine)
            # ReputationDecayHandler — делегирует в ReputationEngine.compute_decay()
            from app.services.social.reputation_decay_handler import ReputationDecayHandler
            self._tick_orch.add_idle_handler(ReputationDecayHandler(_rep_engine))

        # SocialDecayHandler — дрейф trust → base
        from app.services.social.social_decay_handler import SocialDecayHandler
        self._tick_orch.add_idle_handler(SocialDecayHandler())

        # InjuryProcessor — мост Injury → Physiology (кровотечение из ран)
        from app.services.combat.injury_processor import InjuryProcessor
        self._tick_orch.add_idle_handler(InjuryProcessor())

        # PhysiologyDecayHandler — leaky integrator (экспоненциальное затухание боли/усталости)
        from app.services.combat.physiology_decay_handler import PhysiologyDecayHandler
        self._tick_orch.add_idle_handler(PhysiologyDecayHandler())

        # S74: Непрерывное время психики. Аффективный интеграл затухает в idle.
        from app.services.affective.affective_decay_handler import AffectiveDecayHandler
        self._tick_orch.add_idle_handler(AffectiveDecayHandler())

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


    def _get_life_engine(self):
        """Делегирует к TickOrchestrator (единственный владелец LifeEngine)."""
        return self._tick_orch._get_life_engine()

    def _load_npcs_with_runtime(self, campaign_id: str) -> list:
        """Загружает NPC с наложением runtime (стресс, HP и т.д.).
        Используется в игровом цикле, не для инициализации движков.
        ADR-030: Инъекция Аватара Игрока (Hybrid Consciousness Entity)
        """
        from app.services.player_session_service import player_session_service
        from app.services.character_service import CharacterService
        import logging

        # ADR-117: Приоритет LifeEngine кэша над файлом.
        # Без этого affective_load, emotion, body_state теряются между тиками —
        # каждый player turn загружает чистый статический конфиг с диска.
        engine = self._get_life_engine()
        npcs = engine.get_npc_states(campaign_id)
        if not npcs:
            from app.services.npc.npc_loader import load_npcs_merged
            _runtime_path = self._get_npc_runtime_path(campaign_id)
            npcs = load_npcs_merged(runtime_path=_runtime_path)
            # ADR-117: После загрузки с диска — немедленно обновить кэш.
            # Без этого каждый player turn перечитывает диск и затирает
            # вычисленные affective_load, emotion, body_state (Инвариант 1).
            if npcs:
                engine.update_cache(campaign_id, npcs)

        # ADR-030: Игрок становится полноправным NPC в симуляции
        session = player_session_service.get_session(campaign_id)
        if session and session.player_name and not any(n.get("id") == "player" or n.get("npc_id") == "player" for n in npcs):
            try:
                _char_svc = CharacterService(root=str(self._saves_dir))
                characters = _char_svc.list_characters(campaign_id)
                if player_char := next(
                    (c for c in characters if c.name == session.player_name),
                    None,
                ):
                    # Извлекаем Вектор Начальных Условий
                    # Используем getattr для совместимости со старыми Pydantic-моделями
                    # ADR-035: Инъекция живого состояния аватара (плоть и кровь)
                    # Шаблон персонажа (player_char) — это кости. Нам нужна живая ткань из avatar_service.
                    _avatar_state = self.avatar_service.load_state(campaign_id, player_char.name)
                    _live_body = getattr(_avatar_state, 'body_state', None) or {}
                    _live_psyche = {
                        "stress": getattr(_avatar_state, 'stress', 0.0),
                        "fear": getattr(_avatar_state, 'fear', 0.0),
                        "willpower": getattr(_avatar_state, 'willpower', 1.0),
                        "emotion": getattr(_avatar_state, 'emotion', 'NEUTRAL'),
                    }
                    
                    player_dict = {
                        "id": "player",
                        "npc_id": "player",
                        "name": player_char.name,
                        "type": "player_avatar",  # Маркер для WillpowerGate
                        "archetype": getattr(player_char, "archetype", "Drifter"),
                        "temperament": getattr(player_char, "temperament", "Stoic"),
                        "body_profile": getattr(player_char, "body_profile", {}),
                        "body_state": _live_body,  # Живая плоть: pain, blood_loss
                        "psyche": _live_psyche,    # Живой разум: stress, fear
                        "social_stats": {"trust": 50.0, "fear_of_player": 0.0, "debt": 0.0},
                        "status_profile": {"faction_rank": {}}
                    }
                    npcs.append(player_dict)
            except Exception as e:
                logging.getLogger(__name__).warning(f"[AVATAR_INJECT] Ошибка инъекции аватара: {e}")

        return npcs

    def idle_tick(self, campaign_id: str) -> dict:
        """Idle tick — делегирует TickOrchestrator (10 фаз, Устав §3).

        Вызывается когда игрок бездействует (таймер pygame).
        Единая точка входа: GameLoopBridge и routes.py делегируют сюда.
        TickOrchestrator.execute(dm_ctx=None) — полный idle-цикл с
        WorldSnapshotBuilder на фазе 9.

        Конвертация DTO→dict происходит ЗДЕСЬ, не в мосту (Устав §1.1).
        Frontend не должен знать про backend-классы.
        """
        # БАГ G-2 FIX: Гарантируем инициализацию сцены (стены, NPC, время)
        from app.services.game_loop.scene_init import ensure_scene_initialized
        _scene = ensure_scene_initialized(self, campaign_id)
        if _scene is None:
            return {"status": "no_scene", "npc_positions": {}}

        # ДИАГНОСТИКА: Проверяем — переживают ли traversals idle_tick
        _trav_before = list(_scene.get("active_traversals", {}).keys())
        print(f"[IDLE_TRACE] BEFORE tick={_scene.get('tick')} scene_id={id(_scene)} traversals={_trav_before}")

        # ADR-0XX: Temporal Authority Separation. Монотонный каузальный тик.
        # Только +1. Никогда не сбрасывается. Не зависит от календаря (game_time_seconds).
        _scene["tick"] = _scene.get("tick", 0) + 1

        # ADR-048: GameLoop собирает SpatialService и инжектит в TickOrchestrator.
        _loc_id = _scene.get("location_id", "")
        _spatial_svc = None
        if _loc_id:
            from app.services.spatial.spatial_service import SpatialService
            try:
                _spatial_svc = SpatialService.build_for_location(
                    campaign_id=campaign_id,
                    location_id=_loc_id,
                    scene_state=_scene
                )
            except Exception as e:
                logger.warning(f"[SPATIAL_AUTHORITY] SpatialService build failed: {e}")
        
        result: TickResultDTO = self._tick_orch.execute(
            campaign_id=campaign_id,
            scene_state=_scene,
            tick_number=_scene["tick"], # Авторитетный источник тика
            spatial_service=_spatial_svc, # ИНЪЕКЦИЯ
        )

        # ДИАГНОСТИКА: Проверяем — появились ли traversals после execute
        _trav_after = list(_scene.get("active_traversals", {}).keys())
        print(f"[IDLE_TRACE] AFTER tick={_scene.get('tick')} traversals={_trav_after}")

        # Конвертация WorldSnapshotDTO → dict для фронтенда
        from dataclasses import asdict
        from app.domain.snapshot import snapshot_npc_positions_to_dict

        _ws: dict | None = None
        _npc_pos_dict: dict = {}
        if result.world_snapshot is not None:
            _ws = asdict(result.world_snapshot)
            _npc_pos_dict = snapshot_npc_positions_to_dict(
                result.world_snapshot.npc_positions
            )
            _ws["npc_positions"] = _npc_pos_dict
            # UUID → строка для JSON-совместимости
            if _ws.get("last_event_id") is not None:
                _ws["last_event_id"] = str(_ws["last_event_id"])

        return {
            "status": result.status,
            "changes": result.changes_count,
            "npc_positions": _npc_pos_dict,  # DEPRECATED: читать из world_snapshot
            "events": result.significant_events,
            "world_snapshot": _ws,
            # ADR-075: Idle-тики не содержат Волевых конфликтов (нет действия игрока).
            "will_conflict_data": None,
        }

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
        # ADR-113: LLM Failure — честная ошибка + попытка рестарта
        if isinstance(dm_result, dict) and dm_result.get("error"):
            _err_msg = dm_result.get("human_msg", "LLM сервер недоступен")
            logger.error(f"[DM_RESULT] LLM FAILED: {_err_msg}")
            # Recovery: пробуем перезапустить llama-server и повторить запрос
            try:
                from app.main import _restart_llama_server
                if _restart_llama_server():
                    logger.info("[DM_RESULT] LLM рестартнул — повторяем запрос")
                    dm_result = self._run_dm(state)
                    if not (isinstance(dm_result, dict) and dm_result.get("error")):
                        # Рестарт помог — продолжаем нормальный путь
                        pass
                    else:
                        return GameActionResponse(
                            dm_response=f"[СИСТЕМА: LLM сервер недоступен — {_err_msg}]",
                            world_snapshot=state.shared_context.world_snapshot or {},
                            will_conflict_data=None,
                        )
                else:
                    return GameActionResponse(
                        dm_response=f"[СИСТЕМА: LLM сервер недоступен — {_err_msg}]",
                        world_snapshot=state.shared_context.world_snapshot or {},
                        will_conflict_data=None,
                    )
            except ImportError:
                return GameActionResponse(
                    dm_response=f"[СИСТЕМА: LLM сервер недоступен — {_err_msg}]",
                    world_snapshot=state.shared_context.world_snapshot or {},
                    will_conflict_data=None,
                )
        logger.debug(f"[DM_RESULT] type={type(dm_result).__name__}")

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

        # TASK 1: Force Merge — строим world_snapshot из актуального scene_state (ADR-0014)
        _ws_dict = None
        _npc_pos_dict = None
        if hasattr(state, 'shared_context') and state.shared_context and state.shared_context.scene_state:
            from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder
            from dataclasses import asdict
            _builder = WorldSnapshotBuilder()
            # ADR-092: Проброс perception из TickOrchestrator для action tick
            _pp = getattr(state.shared_context, 'player_perception', None)
            _anr = getattr(state.shared_context, 'all_npcs_raw_snapshot', None)
            print(f"[TRAV_CHECK_P2] before_snapshot: id(scene_state)={id(state.shared_context.scene_state)} active_traversals={list(state.shared_context.scene_state.get('active_traversals', {}).keys())}")
            if _ws := _builder.build(
                state.shared_context.scene_state,
                tick=self.get_current_tick(req.campaign_id),
                player_perception=_pp,
                all_npcs_raw=_anr,
            ):
                _ws_dict = asdict(_ws)
                # Критический адаптер: конвертируем List[NPCPositionDTO] в Dict[npc_id, dict]
                # иначе фронтенд не сможет найти NPC по ключу (предсказание Мастера Тай)
                _raw_pos = _ws_dict.get("npc_positions")
                if isinstance(_raw_pos, list):
                    _npc_pos_dict = {p.get("npc_id"): p for p in _raw_pos if isinstance(p, dict) and "npc_id" in p}
                    _ws_dict["npc_positions"] = _npc_pos_dict
                elif isinstance(_raw_pos, dict):
                    _npc_pos_dict = _raw_pos

        # ADR-SCENE-LOCK: Разблокируем тик — финальный персист кэша.
        self.scene_manager.unlock_tick(req.campaign_id)

        return ChatTurnResponse(
            dm_response=dm_result.get("dm_response", ""),
            npc_reactions=dm_result.get("npc_reactions", []),
            world_changes=dm_result.get("world_changes", []),
            world_snapshot=_ws_dict,
            npc_positions=_npc_pos_dict,
            # ADR-075: Строгий проброс Эмбодимента.
            will_conflict_data=state.shared_context.will_conflict_data if state.shared_context else None,
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
        if npc_reactions := (
            state.npc_result.get("npc_reactions", [])
            + state.npc_result.get("npc_actions", [])
        ):
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
        if dm_full_text_for_mem := "".join(dm_text_parts):
            self.memory_manager.persist_dm_response(
                campaign_id,
                world_id=world_id,
                location=location,
                actions=[a.model_dump() for a in actions],
                dm_text=dm_full_text_for_mem,
            )
            # Лог вопроса + ответа для отладки
            _player_msg = next((a.action for a in actions if a.action), "")
            _preview_q = f"{_player_msg[:80]}..." if len(_player_msg) > 80 else _player_msg
            _preview_a = f"{dm_full_text_for_mem[:120]}..." if len(dm_full_text_for_mem) > 120 else dm_full_text_for_mem
            logger.warning(f"[DM] {_preview_q}")
            logger.warning(f"[NPC] {_preview_a}")

        yield {
            "type": "done",
            "tokens": token_count,
            "ms": elapsed_ms,
            "tps": tps,
            "game_time_seconds": state.shared_context.game_time_seconds or 0,
            # ADR-075: Проброс Эмбодимента через SSE. Фронтенд собирает GameActionResponse из этого словаря.
            "will_conflict_data": state.shared_context.will_conflict_data if state.shared_context else None,
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
            
            # P0: ACTION ELIGIBILITY GATE — мёртвый игрок не может действовать (ADR-127, Rule 59)
            # Проверка ДО lock_for_tick, чтобы не загрязнять scene_state пост-смертной активностью
            _player_life = _avatar_state.body_state.get("life_status", "ALIVE") if _avatar_state and _avatar_state.body_state else "ALIVE"
            if _player_life == "DEAD":
                logger.warning(f"[DEATH_GATE] Player '{_player_name}' is DEAD. DM narrates death.")
                # P3: Проброс death state в DM-контракт (DM читает life_status, не вычисляет)
                from app.services.game_loop.phase_6_avatar import avatar_to_prompt
                shared_context.player_state = {_player_name: avatar_to_prompt(_avatar_state)}
                # S75: Проброс death feedback — мир продолжает жить, игрок теряет агентность
                _bs = _avatar_state.body_state if _avatar_state and _avatar_state.body_state else {}
                _death_avatar_dict = {
                    "physical_state": "dead",
                    "mental_state": "broken",
                    "perceptual_stability": 0.0,
                    "cognitive_coherence": 0.0,
                    "sensory_noise": 1.0,
                    "motor_disruption": 1.0,
                    "perceptual_latency": 1.0,
                    "reality_reconciliation_rate": 0.0,
                    "blood_visibility": min(1.0, float(_bs.get("blood_loss", 0.0)) * 1.5),
                    "breathing_profile": "none",
                    "posture_state": "collapsed",
                    "will_resistance": 0.0,
                    "embodied_vector": None,
                    "life_status": "DEAD",
                }
                # Мир продолжает жить: пробрасываем текущие NPC позиции из кэша
                # idle_tick обновит их дальше, но этот snapshot не даёт миру «замёрзнуть»
                _death_ws = {"avatar_state": _death_avatar_dict}
                try:
                    _cached = self.life_engine.get_npc_states(campaign_id)
                    if _cached:
                        _death_ws["npc_positions"] = {n.get("npc_id", n.get("id", f"npc_{i}")): n for i, n in enumerate(_cached) if isinstance(n, dict)}
                except Exception:
                    pass  # Мир без позиций лучше, чем краш Death Guard
                # P3: DM narrates смерть (LLM-интерпретация замороженной реальности, не хардкод)
                _death_dm_response = "Тьма поглощает тебя. Твоё тело безжизненно, а сознание растворяется в абсолютной тишине."
                try:
                    _death_result = await run_agent_safe(
                        "dm", self.dm_agent,
                        (location, actions, {}, {}, {}, False, shared_context),
                        {},
                    )
                    if isinstance(_death_result, dict) and _death_result.get("dm_response"):
                        _death_dm_response = _death_result["dm_response"]
                except Exception as _dg_err:
                    logger.warning(f"[DEATH_GATE] DM narration failed: {_dg_err}, using fallback")
                return ChatTurnResponse(
                    dm_response=_death_dm_response,
                    npc_reactions=[],
                    world_changes=[],
                    world_snapshot=_death_ws,
                    npc_positions=None,
                    will_conflict_data=None,
                    journal_entry_id="",
                    traces=[],
                )
            
            _sheets = self.character_service.list_characters(campaign_id)
            _match = next((s for s in _sheets if s.name == _player_name), None)
            if _match and self.avatar_service.load_avatar(campaign_id, _player_name) is None:
                self.avatar_service.migrate_from_characters_json(campaign_id, _match)
                _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)
            from app.services.game_loop.phase_6_avatar import avatar_to_prompt
            shared_context.player_state = {_player_name: avatar_to_prompt(_avatar_state)}
        except Exception as _e:
            logger.warning(f"[AVATAR] ошибка загрузки: {_e}")

        # ADR-SCENE-LOCK: Блокируем scene_state на время тика.
        # Все get_scene_state() внутри тика вернут ТОТ ЖЕ объект.
        # Без этого каждый вызов создаёт новый dict из persistence → traversals теряются.
        scene_state = self.scene_manager.lock_for_tick(campaign_id, location)
        if scene_state is None:
            scene_state = init_scene_state(self, campaign_id, location, shared_context, campaign_state,
                                           player_position=player_position)
            self.scene_manager._tick_scene = scene_state
            self.scene_manager._tick_locked = True
            self.scene_manager._tick_campaign_id = campaign_id
        else:
            # Обновляем player position + sync time на закэшированном объекте
            from app.services.game_loop.scene_init import _update_player_position, _sync_game_time
            _update_player_position(scene_state, player_position)
            _sync_game_time(scene_state, shared_context)

        # КРИТИЧЕСКИ: shared_context должен ссылаться на реальный scene_state, а не на пустой {}
        shared_context.scene_state = scene_state

        # ADR-121: Spatial perception spine — SpatialQueryService в shared_context
        # Без этого perception_filter получает spatial_query=None → все NPC слепы → fallback ALL
        # → ReactionSubscriber получает ALL NPC → эмоциональный каскад
        from app.services.spatial.spatial_query_service import SpatialQueryService
        shared_context.spatial_query = SpatialQueryService(
            npc_positions=scene_state.get("npc_positions", {}),
            scene_state=scene_state,
        )

        # ADR-0XX: Temporal Authority Separation. Монотонный каузальный тик.
        # Инкрементируется строго на +1 при ЛЮБОМ вводе (idle или player action).
        scene_state["tick"] = scene_state.get("tick", 0) + 1
        if hasattr(shared_context, 'current_tick'):
            shared_context.current_tick = scene_state["tick"]

        # ФАЗА 1-3: DM классификация + EventBus + STM + время
        try:
            dm_result = run_dm_phase(
                self, actions, shared_context, scene_state, _ctx, campaign_id, location,
            )
            logger.warning(f"[DEBUG DM] is_valid={dm_result.is_valid}, scene_context={dm_result.scene_context}, error={dm_result.error}")

            # ФАЗА 1: Semantic Translation (ADR-031 Fix).
            # game_loop не вычисляет волю и не публикует события. Только Intent → Pressure.
            _player_data_dict = _match.dict() if _match else None
            _resolution = resolve_player_intent(
                raw_action=actions[0].action if actions else "",
                action_type=shared_context.action_type or "player_interacts",
                target=shared_context.player_target_id or "",
                player_dict=_player_data_dict,
                scene_context=scene_state, # Слой 2 ищет имена в scene_state["npc_positions"]
            )
            
            # Передаем давление в контекст для TickOrchestrator (Causal Resolution)
            shared_context.intent_resolution = _resolution

            # FIX: Проброс semantic_action в hub_event.payload ПОСЛЕ intent_resolution,
            # но ДО run_npc_orchestration (где DecisionHub читает hub_event).
            # Без этого DecisionHub не видит MOVE и obedience boost не работает.
            if _ctx.hub_event and _resolution and _resolution.original_intent:
                _params = _resolution.original_intent.parameters
                logger.debug(f"[ARCHAE-PAYLOAD] params={_params} sa={getattr(_params, 'semantic_action', 'NO_SA') if _params else 'NO_PARAMS'}")
                if _params:
                    _sa = getattr(_params, 'semantic_action', None)
                    _tid = getattr(_params, 'target_id', None)
                    _tref = getattr(_params, 'target_reference', None)
                    _sem_payload = {}
                    if _sa:
                        _sem_payload["semantic_action"] = _sa
                    if _tid:
                        _sem_payload["target_id"] = _tid
                    if _tref:
                        _sem_payload["target_reference"] = _tref.lower()
                    if _sem_payload:
                        import dataclasses
                        _ctx.hub_event = dataclasses.replace(_ctx.hub_event, payload=_sem_payload)
                        logger.warning(f"[PAYLOAD_INJECT] hub_event.payload={_sem_payload} id={id(_ctx.hub_event)} event_type={_ctx.hub_event.event_type}")

            # ADR-091 FIX: Публикация ПОСЛЕ intent_resolution (иначе _semantic_action=None)
            # Раньше вызывался в run_dm_phase ДО resolve_player_intent → override не работал
            if dm_result.is_valid:
                publish_classified_player_event(
                    shared_context, location, campaign_id,
                    actions[0].action if actions else "",
                )

            # ФАЗА 3-6: NPC оркестрация → TickPlayerResultDTO (Устав §3)
            _player_result: TickPlayerResultDTO = TickPlayerResultDTO()
            logger.debug(f"[ARCHAE-PRE-ORCH] dm_valid={dm_result.is_valid} has_scene_ctx={dm_result.scene_context is not None} hub_event={_ctx.hub_event is not None}")
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

        # ADR-O-112: Actor-Agnostic Physiology. Инжектируем Аватар в all_npcs_raw для трубы урона.
        _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)
        from dataclasses import asdict, is_dataclass
        if is_dataclass(_avatar_state):
            _avatar_dict = asdict(_avatar_state)
            _avatar_dict["npc_id"] = "player"
            _avatar_dict["id"] = "player"  # ADR-O-112: load_profile_from_legacy_json требует "id"
            if hasattr(_ctx, 'all_npcs_raw') and _ctx.all_npcs_raw is not None:
                _ctx.all_npcs_raw = [n for n in _ctx.all_npcs_raw if n.get("npc_id") != "player"]
                _ctx.all_npcs_raw.append(_avatar_dict)

        # ФАЗЫ 8-10: Perception + Social + Finalize + Commit (Устав §3 — единая последовательность)
        try:
            _player_result = self._tick_orch.execute_player_finalize(
                _player_result, _ctx, shared_context, actions, campaign_id,
                rules_result, r3_direct_mode=R3_DIRECT_MODE,
            )
            npc_result = _player_result.finalize_result or {}
            # SCENE_IDENTITY: проверяем, что scene_state не потерял traversals после finalize
            print(f"[TRAV_CHECK_P1_5] after_finalize_return: id={id(shared_context.scene_state)} traversals={list(shared_context.scene_state.get('active_traversals', {}).keys())}")
            
            # ADR-O-112: Извлекаем физиологию Аватара (pain, shock, blood_loss) из пайплайна
            _updated_avatar_dict = next((n for n in getattr(_ctx, 'all_npcs_raw', []) if n.get("npc_id") == "player"), None)
            if _updated_avatar_dict and _avatar_state:
                _phys_changed = False
                if "body_state" in _updated_avatar_dict and _updated_avatar_dict["body_state"] != _avatar_state.body_state:
                    _avatar_state.body_state = _updated_avatar_dict["body_state"]
                    _phys_changed = True
                if "hp" in _updated_avatar_dict and _updated_avatar_dict["hp"] != _avatar_state.hp:
                    _avatar_state.hp = _updated_avatar_dict["hp"]
                    _phys_changed = True
                    
                if _phys_changed:
                    self.avatar_service.save_state(campaign_id, _avatar_state)
                    logger.warning(f"[AVATAR] PHYSIOLOGY APPLIED: pain={_avatar_state.body_state.get('pain', 0.0):.1f} shock={_avatar_state.body_state.get('shock_impulse', 0.0):.2f}")
                    
        except Exception as _fin_err:
            logger.error(f"[GAME_LOOP] Finalize error: {_fin_err}", exc_info=True)
            npc_result = {}
            # Защита: _player_result может быть None если execute_player_finalize вернул None
            shared_context.npc_contexts = getattr(_player_result, 'npc_contexts', []) or []

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

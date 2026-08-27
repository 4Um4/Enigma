"""
backend/app/services/game_loop/__init__.py

Шаг 5 рефакторинга: единая точка входа для run_turn и stream_turn.

Раньше: orchestrator.run_turn() и stream_turn() — ~400 строк дублирования.
Теперь: один _pipeline() содержит общую логику.
        run_turn()    — ждёт DM целиком, возвращает ChatTurnResponse.
        stream_turn() — стримит DM токены через SSE.

GameLoop не знает про FastAPI, HTTP, SSE-формат.
Он только вызывает processor + engines + agents + memory.
"""



from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from app.domain.tick import TickResultDTO
from app.models.schemas import (
    AgentTrace,
    ChatTurnRequest,
    ChatTurnResponse,
    PlayerAction,
)
from app.services.action.dm_orchestrator import DMOrchestrator
from app.services.events.event_bus import get_event_bus

# character_filter — используется только в npc_orchestration.py
from app.services.game_loop.agent_runner import (
    AGENT_TIMEOUT_SEC,
    run_agent_safe,
    yield_model_info,
)
from app.services.tick_orchestrator import (
    DMContextDTO,
    TickOrchestrator,
    TickPlayerResultDTO,
)

# ─────────────────────────────────────────────────────────────────────────────
# R3 DIRECT MODE: DM как единственный источник речи
# True = DecisionResult → SceneOutcome → DMFrame → DM (1 LLM вызов)
# False = legacy путь (удалён: npc_agent)
# ─────────────────────────────────────────────────────────────────────────────
R3_DIRECT_MODE: bool = True
from app.core.config import settings
from app.models.pipeline_context import PipelineContext
from app.models.schemas import CampaignLoadResponse
from app.services.character_service import CharacterService
from app.services.error_interpreter import get_error_interpreter
from app.services.logging_tools import jsonl_log
from app.services.scene_state_manager import SceneStateManager
from app.services.state.context_builder import build_context

# AdventureLoader удалён (ADR-O-146) — vestigial слой, нет файлов для загрузки
from app.services.system_requirements import SystemRequirements
from app.services.verbalization.scene_continuity import SceneContinuity
from app.services.vram_monitor import get_vram_monitor

# LayeredMemory удалён из GameLoop — все записи через MemoryManager (Закон 4.1.2)
# Старый model_router удалён — агенты сами управляют маршрутизацией через llm/router
from app.services.world_scheduler import WorldScheduler

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────────
# Внутренний результат пайплайна (до DM-нарратива)
# ────────────────────────────────────────────────────────────────────────────────


@dataclass
class _PipelineState:
    """Всё что нужно знать агентам после Python-этапа."""

    shared_context: PipelineContext
    classification_results: List[Dict[str, Any]]
    world_tick_meta: Dict[str, Any]
    rules_result: Dict[str, Any] = field(default_factory=dict)
    npc_result: Dict[str, Any] = field(default_factory=dict)
    python_engines_result: Dict[str, Any] = field(default_factory=dict)
    # N-02 FIX: Используем time.monotonic() для измерения реального времени (latency, TPS).
    # time.time() подменяется time_freezer во время replay, что ломает метрики.
    start_ms: float = field(default_factory=lambda: time.monotonic() * 1000)
    # Sprint P9: Факты, донесённые до игрока (для UI и DM)
    observed_facts: list = field(default_factory=list)
    world_snapshot: Optional[Any] = None  # BUG-FB-031 FIX: Проброс WorldSnapshotDTO из ядра


# ────────────────────────────────────────────────────────────────────────────────
# Re-exports из подмодулей
# ────────────────────────────────────────────────────────────────────────────────
from app.services.game_loop.dm_phase import run_dm_phase
from app.services.game_loop.npc_orchestration import run_npc_orchestration

# commit_tick инлайн в TickOrchestrator.finalize_and_commit — phase_8_commit.py удалён
from app.services.game_loop.phase_1_input import (
    publish_classified_player_event,
    resolve_player_intent,
)
from app.services.game_loop.scene_init import init_scene_state
from app.services.game_loop.tick_context import (
    TickBuffer,
    TickInput,
    TickOutput,
    _TickContext,  # backward compat alias
)

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
        memory_manager,  # MemoryManager — единая точка записи (Закон 4.1.2)
        dm_orchestrator: DMOrchestrator,
        scene_manager: SceneStateManager,
        world_scheduler: WorldScheduler,
        character_service: CharacterService,
        avatar_service,
        dm_agent,
        rules_agent,
        load_npcs_func,
        # adventure_loader удалён (ADR-O-146)
        system_requirements: SystemRequirements,
        saves_dir: Optional[Path] = None,
        store=None,
    ):
        self.data_dir = data_dir
        self._saves_dir = Path(saves_dir) if saves_dir else data_dir / "campaigns"
        self.memory_manager = memory_manager
        # S159: Инъекция NarrativeProjector для фильтрации реплик
        from app.services.perception.narrative_projector import NarrativeProjector
        self._narrative_projector = NarrativeProjector()

        # P7-MVP: Инициализация эпистемического фасада
        from pathlib import Path as PathLib

        # N1 FIX (v7): Используем BASE_DIR напрямую, чтобы найти config/canon/ от корня проекта
        from app.core.config import BASE_DIR
        from app.services.social.mvp_tavern_controller import MvpTavernController
        _canon_path = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"
        if _canon_path.exists():
            # P2 FIX: Проброс RelationshipStore в MVP-контроллер для эмерджентной драмы.
            _rel_store = memory_manager._relationships if memory_manager else None  # noqa: ENIGMA001
            self.mvp_controller = MvpTavernController(_canon_path, event_bus=get_event_bus(), relationship_store=_rel_store)
        else:
            logger.error(
                f"TruthState canon file not found at {_canon_path}. "
                f"DATA_DIR={self.data_dir}, BASE_DIR={BASE_DIR}. "
                "MVP epistemic pipeline DISABLED. End-Screen will be empty."
            )
            self.mvp_controller = None

        # P7-13: Опциональная персистентность мира. GameLoop выступает хранилищем diff'ов между кампаниями.
        self._campaign_diffs: Dict[str, "WorldStateDiff"] = {}
        self._diffs_path = self._saves_dir / "_world_diffs.json"
        self.dm_orchestrator = dm_orchestrator
        self.scene_manager = scene_manager
        self.world_scheduler = world_scheduler
        self.character_service = character_service
        self.avatar_service = avatar_service
        # self.model_router удалён
        self.dm_agent = dm_agent
        self.rules_agent = rules_agent
        self._load_npcs = load_npcs_func  # static только (для движков)
        # self._data_dir удалён — runtime через self._saves_dir, config через self.data_dir
        # ADR-O-146: AdventureLoader удалён — vestigial слой (нет файлов world_lore.txt/npc.json/locations.json).
        # load_campaign() инлайнит пустой результат вместо вызова загрузчика.
        self.system_requirements = system_requirements
        self._campaign_world_index: dict[str, str] = {}
        self._session_started_campaigns: set = set()
        # B.3/B.4: SceneContinuity — эпизодическая фиксация сцены
        self._scene_continuities: Dict[str, SceneContinuity] = {}
        # _social_tick перенесён в SocialSubscriber (§5.1 EventBus подписки)
        # ФАЗА 3.1: Spatial Events — предыдущие расстояния для детекции переходов
        self._prev_player_distances: Dict[str, Dict[str, float]] = {}
        # S118 FIX: Внедрение LLM Slow-Path компрессора (P0: BUG-S117.1)
        from app.services.input.intent_compressor import IntentCompressor
        from app.services.input.llm_compressor_client import LlamaCppCompressorClient
        self._intent_compressor = IntentCompressor(
            llm_client=LlamaCppCompressorClient()
        )
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
            store=store,
        )
        # P1.1f: внедряем фабрику SocialEngine в TickOrchestrator
        self._tick_orch.set_social_engine_factory(self._svc.get_social_engine)

        # S150 FIX: Принудительная инициализация TaskScheduler для прохождения INV-DIALOGUE-INIT/SCHEDULER-FAIL
        _ = self._get_task_scheduler()

        # Подсистема 2: Инициализация ReplayRecorder
        if settings.replay_mode != "off":
            settings.replay_record = True
            from app.services.replay.replay_recorder import ReplayRecorder
            from app.services.replay.replay_store import ReplayStore
            _replay_db_path = Path(data_dir) / "replay.db"
            _replay_store = ReplayStore(_replay_db_path)
            _session_id = _replay_store.start_session(
                campaign_id="Open_road",
                commit_hash="dev"
            )
            self._tick_orch._replay_recorder = ReplayRecorder(
                store=_replay_store,
                session_id=_session_id
            )
            logger.info(f"[GAME_LOOP] Replay Recorder started. Session ID: {_session_id}")

            # Инъекция контекста в ModelRouter для LLM Cache (Этап 2.3)
            _router = self.dm_agent.router
            _router.set_replay_context(store=_replay_store, session_id=_session_id)

        # Фаза 0.5: DI для idle-сервисов (social decay, reputation decay)
        _rep_engine = self._svc.get_reputation_engine()
        _rel_store = memory_manager._relationships if memory_manager else None  # noqa: ENIGMA001
        _state_applicator = (
            self._svc.get_state_applicator(  # noqa: ENIGMA001
                relationship_store=_rel_store,
            )
            if _rel_store
            else None
        )

        if _state_applicator:
            self._tick_orch.set_state_applicator(_state_applicator)
        if _rep_engine:
            self._tick_orch.set_reputation_engine(_rep_engine)
            # ReputationDecayHandler — делегирует в ReputationEngine.compute_decay()
            from app.services.social.reputation_decay_handler import (
                ReputationDecayHandler,
            )

            self._tick_orch.add_idle_handler(ReputationDecayHandler(_rep_engine))

        # SocialDecayHandler — дрейф trust → base
        from app.services.social.social_decay_handler import SocialDecayHandler

        # Регистрация NpcDialogueSubscriber для замыкания цикла NPC-NPC диалогов
        self._register_npc_dialogue_subscriber(memory_manager, _rel_store)

        # S189: Epistemic Core Integration (ADR-O-354).
        self._register_epistemic_core(_rel_store)

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

        # TZ-08 Addendum: Time Skip Executor (Observation Layer)
        from app.services.world.time_skip_executor import TimeSkipExecutor
        self._time_skip = TimeSkipExecutor(self._tick_orch)
        self._skip_locks: Dict[str, threading.Lock] = {}  # Real locks per campaign

    def _get_spatial_query_for_subscriber(self):
        """Провайдер SpatialQueryService для NpcDialogueSubscriber (eavesdrop).
        S196 FIX: Берёт актуальный SpatialQueryService из shared_context, 
        устраняя зависимость от mutable hidden state _current_spatial_query.
        S197 FIX: Если spatial_query отсутствует, конструирует его на лету из scene_state."""
        _shared_ctx = getattr(self._tick_orch, "_shared_context", None)  # noqa: ENIGMA002
        if _shared_ctx is not None:
            _sq = getattr(_shared_ctx, "spatial_query", None)  # noqa: ENIGMA002
            if _sq is not None:
                return _sq

        _sq = getattr(self, "_current_spatial_query", None)  # noqa: ENIGMA002
        if _sq is not None:
            return _sq

        # S197 FIX: Fallback - конструируем на лету, чтобы избежать INV-SPATIAL-QUERY при ранних событиях
        _campaign_id = getattr(self, "_current_campaign_id", "Open_road")
        _scene = self.scene_manager.get_scene_state(_campaign_id, "tavern")
        if not _scene:
            _scene = self.scene_manager.get_scene_state(_campaign_id, "city_gate")

        if _scene:
            from app.services.spatial.spatial_query_service import SpatialQueryService
            _new_sq = SpatialQueryService(
                npc_positions=_scene.get("npc_positions", {}),
                scene_state=_scene
            )
            self._current_spatial_query = _new_sq
            logger.warning("[SPATIAL_FALLBACK] SpatialQueryService was missing, constructed on-the-fly.")
            return _new_sq

        logger.error("SpatialQueryService missing in GameLoop for NpcDialogueSubscriber (eavesdrop).")
        raise RuntimeError("INV-SPATIAL-QUERY: Missing spatial_query during NPC_SPOKE handling and scene_state is unavailable.")

    def _on_npc_spoke_economy_tracker(self, event: Any) -> None:
        """S150 FIX: Регистрирует диалоги для EconomyTracker (потребность SOCIAL)."""
        try:
            _npc_id = getattr(event, "source", None)  # noqa: ENIGMA002
            if not _npc_id:
                return
            _campaign_id = getattr(self, "_current_campaign_id", "Open_road")
            _tick = self._tick_orch.get_current_tick(_campaign_id)
            self._svc.economy_tracker.record_talk(_npc_id, _tick)
        except Exception as e:
            logger.warning(f"[ECO_TRACKER] record_talk error: {e}")

    def _register_npc_dialogue_subscriber(self, memory_manager: Any, rel_store: Any) -> None:
        """Регистрирует NpcDialogueSubscriber на события NPC_SPOKE."""
        try:
            from app.services.events.event_bus import get_event_bus
            from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber

            if not memory_manager or not rel_store:
                logger.warning("[GAME_LOOP] Cannot register NpcDialogueSubscriber — missing memory or relationships")
                return

            from app.services.memory.dialogue_update_extractor import DialogueUpdateExtractor
            _extractor = DialogueUpdateExtractor(router=self.dm_agent.router)

            _subscriber = NpcDialogueSubscriber(
                memory_manager=memory_manager,
                relationship_store=rel_store,
                npc_states_provider=lambda: getattr(self._tick_orch, "_shared_context", None).all_npcs_raw if hasattr(self._tick_orch, "_shared_context") else [],  # noqa: ENIGMA002
                campaign_id_provider=lambda: getattr(self, "_current_campaign_id", "Open_road"),
                avatar_service=self.avatar_service,
                spatial_query_provider=self._get_spatial_query_for_subscriber,
                l1_chronicle=self._tick_orch.l1_chronicle,
                tick_provider=lambda: getattr(self, "_current_tick", 0),
                dialogue_update_extractor=_extractor,
            )

            # V8-DLG-06 FIX: Регистрируем DialogueMemorySubscriber для записи в L2
            from app.services.events.dialogue_memory_subscriber import DialogueMemorySubscriber
            _mem_subscriber = DialogueMemorySubscriber(
                memory_manager=memory_manager,
                npc_states_provider=lambda: getattr(self._tick_orch, "_shared_context", None).all_npcs_raw if hasattr(self._tick_orch, "_shared_context") else [],  # noqa: ENIGMA002
                campaign_id_provider=lambda: getattr(self, "_current_campaign_id", "Open_road"),
                spatial_query_provider=self._get_spatial_query_for_subscriber
            )

            from app.services.events.event_types import EventType
            _bus = get_event_bus()
            _bus.subscribe(EventType.NPC_SPOKE, _subscriber.on_npc_spoke)
            _bus.subscribe(EventType.NPC_SPOKE, _mem_subscriber.on_event) # V8-DLG-06
            _bus.subscribe(EventType.PLAYER_SPOKE, _mem_subscriber.on_event) # V8-DLG-06

            # S150 FIX: Подписываем EconomyTracker для учёта диалогов (SOCIAL need)
            _bus.subscribe(EventType.NPC_SPOKE, self._on_npc_spoke_economy_tracker)

            self._npc_dialogue_subscriber = _subscriber
            logger.info("[GAME_LOOP] NpcDialogueSubscriber and DialogueMemorySubscriber registered")
        except Exception as e:
            logger.exception(f"[GAME_LOOP] Failed to register NpcDialogueSubscriber: {e}")

    def _register_epistemic_core(self, rel_store: Any) -> None:
        """S189: Инициализирует Epistemic Core и регистрирует ClaimEventSubscriber (ADR-O-354)."""
        try:
            from app.services.events.claim_event_subscriber import ClaimEventSubscriber
            from app.services.events.event_bus import get_event_bus
            from app.services.events.event_types import EventType
            from app.services.npc.belief_revision_engine import BeliefRevisionEngine
            from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
            from app.services.npc.epistemic_store import EpistemicStore

            # ADR-O-357 enforcement: reliability вычисляет канонический провайдер,
            # инлайн в подписчике удалён (см. docs/audits/ADR-O-357_IMPACT.md, Addendum).
            from app.services.npc.trust_based_reliability_provider import TrustBasedReliabilityProvider

            _campaign_id = getattr(self, "_current_campaign_id", "Open_road")

            # S193: Загружаем убеждения из scene_state, если они там есть.
            _scene = self.scene_manager.get_scene_state(_campaign_id, "tavern")
            _epistemic_data = _scene.get("epistemic_records", []) if _scene else []
            _epistemic_store = EpistemicStore.from_dict(_epistemic_data)
            _reliability_provider = TrustBasedReliabilityProvider(rel_store, _campaign_id)
            _belief_engine = BeliefRevisionEngine(reliability_provider=_reliability_provider)
            _resolver = EpistemicContextResolver(store=_epistemic_store)

            _subscriber = ClaimEventSubscriber(
                engine=_belief_engine,
                store=_epistemic_store,
                spatial_query_provider=self._get_spatial_query_for_subscriber
            )
            _bus = get_event_bus()
            _bus.subscribe(EventType.COMMUNICATION_CLAIM, _subscriber.on_claim_event)
            # S199 (Фаза 8.3): Подписка на NPC_SPOKE для детерминированного fallback и интеграции игрока.
            _bus.subscribe(EventType.NPC_SPOKE, _subscriber.on_npc_spoke)

            # S201: Регистрация SocialActionSubscriber для маршрутизации SOCIAL_ACTION
            from app.services.events.social_action_subscriber import SocialActionSubscriber
            _social_sub = SocialActionSubscriber(_bus)
            _bus.subscribe(EventType.SOCIAL_ACTION, _social_sub.on_social_action)

            # ADR-O-360 (Phase C): ObservationSubscriber — второй канал убеждений
            # (THEFT → LOS-свидетели → EpistemicStore). Мембрана: SpatialQueryService
            # (event.radius НЕ используется — DEBT-R1). Tick — через оркестратор
            # (существующий метод, без фантомных импортов).
            from app.services.events.observation_subscriber import ObservationSubscriber
            _obs_sub = ObservationSubscriber(
                engine=_belief_engine,
                store=_epistemic_store,
                spatial_query_provider=self._get_spatial_query_for_subscriber,
                tick_provider=lambda: self._tick_orch.get_current_tick(_campaign_id),
            )
            _bus.subscribe(EventType.THEFT, _obs_sub.on_world_event)

            self._tick_orch.set_epistemic_services(_epistemic_store, _resolver)

            # S211 (§18): инъекция резолвера в ACCUSE-гейт компилятора
            # последствий (late binding: контроллер собирается раньше ядра).
            _mvp = getattr(self, "mvp_controller", None)
            _compiler = getattr(_mvp, "action_compiler", None) if _mvp else None
            if _compiler is not None and hasattr(_compiler, "set_epistemic_resolver"):
                _compiler.set_epistemic_resolver(_resolver)
                logger.info("[GAME_LOOP] EpistemicResolver injected into ActionConsequenceCompiler (ACCUSE gate)")

            logger.info("[GAME_LOOP] Epistemic Core (ClaimEventSubscriber) + SocialActionSubscriber registered")
        except Exception as e:
            logger.exception(f"[GAME_LOOP] Failed to register Epistemic Core: {e}")

    def _get_skip_lock(self, campaign_id: str) -> threading.Lock:
        """Возвращает lock для конкретной кампании, защищающий от параллельных skip/idle."""
        return self._skip_locks.setdefault(campaign_id, threading.Lock())

    @property
    def saves_dir(self) -> Path:
        """ADR-O-146: Публичный доступ к saves_dir. Единый runtime путь."""
        return self._saves_dir

    def get_current_tick(self, campaign_id: str) -> int:
        """Единый источник тика — через TemporalEngine (Устав §3)."""
        return self._tick_orch.get_current_tick(campaign_id)

    # ────────────────────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ────────────────────────────────────────────────────────────────────────────

    def _save_diff_to_disk(self, campaign_id: str, diff: "WorldStateDiff") -> None:
        """Сохраняет WorldStateDiff на диск, чтобы он пережил рестарт бэкенда."""
        import json
        from dataclasses import asdict

        try:
            all_diffs = {}
            if self._diffs_path.exists():
                with open(self._diffs_path, "r", encoding="utf-8") as f:
                    all_diffs = json.load(f)

            all_diffs[campaign_id] = asdict(diff)

            self._diffs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._diffs_path, "w", encoding="utf-8") as f:
                json.dump(all_diffs, f, ensure_ascii=False, indent=2)
            logger.info(f"[WORLD_DIFF] Saved diff for '{campaign_id}' to disk.")
        except Exception as e:
            logger.error(f"[WORLD_DIFF] Failed to save diff for '{campaign_id}': {e}")

    def _load_diff_from_disk(self, campaign_id: str) -> Optional["WorldStateDiff"]:
        """Загружает WorldStateDiff с диска, если он там есть."""
        import json

        from app.models.world_state_diff import WorldStateDiff

        try:
            if not self._diffs_path.exists():
                return None
            with open(self._diffs_path, "r", encoding="utf-8") as f:
                all_diffs = json.load(f)

            diff_data = all_diffs.get(campaign_id)
            if diff_data:
                return WorldStateDiff(**diff_data)
            return None
        except Exception as e:
            logger.error(f"[WORLD_DIFF] Failed to load diff for '{campaign_id}': {e}")
            return None

    # ADR-O-146: New Game Reset — сброс runtime мира при сохранении static
    def new_game(
        self,
        campaign_id: str,
        continuity_mode: "WorldContinuityMode" = None,
        source_campaign_id: Optional[str] = None
    ) -> dict:
        """Сбрасывает runtime состояние кампании к чистому static.
        Опционально применяет WorldStateDiff из source_campaign_id (если continuity_mode == CONTINUOUS).

        Полная очистка: SQLite + JSON + все кэши.
        Переинициализация: сцена из editor JSON + NPC со здоровым body_state.
        Источник чистого мира: config/npc/ + map_editor/campaigns/
        Оставляет: characters.json, character_profiles.json (выбор персонажа)

        Returns: {"reset": True, "campaign_id": str, "files_removed": [str]}
        """
        from app.models.world_continuity import WorldContinuityMode
        if continuity_mode is None:
            continuity_mode = WorldContinuityMode.ISOLATED

        import logging
        self._current_campaign_id = campaign_id

        logger = logging.getLogger(__name__)

        removed = []
        saves_campaign = self._saves_dir / campaign_id

        # === 1. ОЧИСТКА PERSISTENCE (SQLite: scene + runtime) ===
        # КОРЕНЬ БАГА: раньше не чистили SQLite → LifeEngine читал старый runtime
        try:
            persistence = self.scene_manager._persistence
            if persistence:
                persistence.delete_campaign(campaign_id)
                removed.append("sqlite:scene+runtime")
                logger.info(f"[NEW_GAME] SQLite cleared for '{campaign_id}'")
        except Exception as e:
            logger.warning(f"[NEW_GAME] SQLite cleanup failed: {e}")

        # === 2. ОЧИСТКА JSON ФАЙЛОВ в saves/<campaign_id>/ ===
        runtime_files = [
            "npc_runtime.json",
            "campaign_state.json",
            "player_avatar.json",
            "npc_relationships.json",
            "campaign_meta.json",
        ]
        for fname in runtime_files:
            fpath = saves_campaign / fname
            if fpath.exists():
                try:
                    fpath.unlink()
                except Exception as e:
                    logger.error(f"[NEW_GAME] Atomic commit: Failed to remove {fpath}: {e}")
                    continue
                removed.append(fname)
                logger.info(f"[NEW_GAME] Removed: {fpath}")

        # === 3. СБРОС ОТНОШЕНИЙ (RelationshipStore: кэш + диск) ===
        try:
            rel_store = self.memory_manager._relationships
            rel_store.reset_campaign(campaign_id)
            if campaign_id in rel_store._cache:
                del rel_store._cache[campaign_id]
        except Exception as e:
            logger.warning(f"[NEW_GAME] RelationshipStore reset failed: {e}")

        # === 4. СБРОС СЕССИИ ===
        try:
            from app.services.player_session_service import player_session_service

            player_session_service.deactivate_player(campaign_id)
            player_session_service._delete_session_from_disk(campaign_id)
        except Exception as e:
            logger.warning(f"[NEW_GAME] Session reset failed: {e}")

        # === 5. СБРОС + ПЕРЕИНИЦИАЛИЗАЦИЯ NPC (healthy body_state) ===
        # КОРЕНЬ БАГА: раньше только чистили кэш → NPC грузились без body_state
        # → Normalization Gate инжектил BODY_STATE_DISABLED (shock=1.0, pain=100)
        _npcs_for_commit = []
        try:
            engine = self._get_life_engine()
            _npcs_for_commit = engine.reset_campaign(campaign_id) or []
        except Exception as e:
            logger.warning(f"[NEW_GAME] LifeEngine NPC reset failed: {e}")

        # === 5.1 WORLD CONTINUITY (P7-13) ===
        # Если режим CONTINUOUS, применяем WorldStateDiff из source-кампании к чистым NPC до коммита
        if continuity_mode == WorldContinuityMode.CONTINUOUS and source_campaign_id and _npcs_for_commit:
            source_diff = self._campaign_diffs.get(source_campaign_id)
            if not source_diff:
                source_diff = self._load_diff_from_disk(source_campaign_id)
            if source_diff:
                from app.services.state.world_diff_applicator import WorldStateApplicator
                _applicator = WorldStateApplicator(mode=continuity_mode)
                # Превращаем list[dict] в dict[npc_id, dict] для мутации
                _npc_cache = {n.get("npc_id"): n for n in _npcs_for_commit if n.get("npc_id")}
                _applicator.apply(diff=source_diff, npc_cache=_npc_cache)
                _npcs_for_commit = list(_npc_cache.values())
                logger.info(f"[NEW_GAME] Applied WorldStateDiff from '{source_campaign_id}' to {campaign_id}")

        # === 6. ПЕРЕИНИЦИАЛИЗАЦИЯ СЦЕНЫ из editor JSON ===
        # КОРЕНЬ БАГА: раньше сцена не пересоздавалась → get_scene_state() = None
        _scene_for_commit = None
        try:
            _scene_for_commit = self.scene_manager.reinit_campaign(campaign_id)
        except Exception as e:
            logger.warning(f"[NEW_GAME] Scene reinit failed: {e}")

        # === 7. АТОМАРНЫЙ КОММИТ (scene + npcs) ===
        # BUG-AUDIT-13: Сохраняем сцену и NPC в одной транзакции, чтобы избежать рассинхрона.
        if _scene_for_commit and _npcs_for_commit:
            try:
                self.scene_manager.commit(
                    campaign_id=campaign_id,
                    scene_state=_scene_for_commit,
                    npc_dicts=_npcs_for_commit,
                    events=[],
                    significant_events=[],
                )
                logger.info(f"[NEW_GAME] Atomic commit OK for {campaign_id}")
            except Exception as e:
                logger.error(f"[NEW_GAME] Atomic commit FAILED for {campaign_id}: {e}")

        # === 7. СБРОС LRU-КЭША загрузчика ===
        if hasattr(self._load_npcs, "cache_clear"):
            self._load_npcs.cache_clear()

        # === 8. СБРОС preserved_tick (иначе scene_init восстановит старый) ===
        if hasattr(self, "_preserved_tick"):
            self._preserved_tick = None

        # === 9. СБРОС MemoryManager (narrative_cache + dialogue sessions) ===
        try:
            self.memory_manager.clear_all_dialogue_sessions(campaign_id)
            # Сброс тик-счётчика MemoryManager
            if hasattr(self.memory_manager, "_tick_counters"):
                self.memory_manager._tick_counters.pop(campaign_id, None)
            # P0 FIX: Очистка JSONL-файлов памяти кампании (data/campaign_memory_<id>.jsonl и session_memory_<id>.jsonl).
            # Без этого LLM получает контекст из прошлых забегов (отравление контекста).
            if hasattr(self.memory_manager, "_layered") and hasattr(
                self.memory_manager._layered, "store"
            ):
                store = self.memory_manager._layered.store
                # P1 FIX: Удаляем только хронику забега (playthrough). Канон (campaign_canon) переживает new_game.
                for collection in [f"playthrough_{campaign_id}"]:
                    if hasattr(store, "_collection_path"):
                        fpath = store._collection_path(collection)
                        if fpath.exists():
                            fpath.unlink()
                            logger.info(f"[NEW_GAME] Removed JSONL playthrough: {fpath}")
                    elif hasattr(store, "delete_campaign"):
                        store.delete_campaign(campaign_id)
                        logger.info(f"[NEW_GAME] SQLite playthrough cleared for '{campaign_id}'")
                if hasattr(store, "_recent_cache"):
                    store._recent_cache.clear()
        except Exception as e:
            logger.warning(f"[NEW_GAME] MemoryManager reset failed: {e}")

        # === 10. СБРОС TemporalEngine (tick=0 + удаление world_tick.json) ===
        try:
            engine_temporal = self._get_life_engine()._temporal
            # cleanup_campaign: чистит RAM кэши + _last_decay_tick
            engine_temporal.cleanup_campaign(campaign_id)
            # Явно ставим tick=0 в RAM (иначе _load_tick прочитает старый с диска)
            engine_temporal._tick_cache[campaign_id] = 0
            # Удаляем world_tick.json с диска — следующий _load_tick вернёт 0
            _wt_path = self._saves_dir / campaign_id / "world_tick.json"
            if _wt_path.exists():
                _wt_path.unlink()
                removed.append("world_tick.json")
        except Exception as e:
            logger.warning(f"[NEW_GAME] TemporalEngine reset failed: {e}")

        # === 11. СБРОС СЕССИИ АВАТАРА (player body_state из предыдущей игры) ===
        try:
            # Удаляем файл аватара — старый мёртвый body_state не переживает new_game
            _avatar_path = self._saves_dir / campaign_id / "player_avatar.json"
            if _avatar_path.exists():
                _avatar_path.unlink()
                removed.append("player_avatar.json")
            # Сброс RAM-кэша аватара (используем DI-инстанс, а не глобальный синглтон)
            if hasattr(self.avatar_service, "_cache"):
                self.avatar_service._cache.pop(campaign_id, None)
            # B1.3-FIX: Сброс RAM-кэша журнала диалогов при new_game (устранение утечки)
            self.avatar_service.clear_journal(campaign_id)
        except Exception as e:
            logger.warning(f"[NEW_GAME] Avatar session reset failed: {e}")

        # === 12. СБРОС ПАМЯТИ NPC (narrative_cache + campaign history) ===
        try:
            # Очистить все dialogue sessions (STM)
            self.memory_manager.clear_all_dialogue_sessions(campaign_id)
            # Сброс тик-счётчика MemoryManager
            if hasattr(self.memory_manager, "_tick_counters"):
                self.memory_manager._tick_counters.pop(campaign_id, None)
            # Очистить narrative_cache всех NPC в LifeEngine кэше
            engine = self._get_life_engine()
            cached_npcs = engine._npc_cache.get(campaign_id, [])
            for npc in cached_npcs:
                npc.pop("narrative_cache", None)
                npc.pop("wounds", None)
                npc.pop("conditions", None)
            if cached_npcs:
                engine.update_cache(campaign_id, cached_npcs)
        except Exception as e:
            logger.warning(f"[NEW_GAME] Memory reset failed: {e}")

        # === 12. ОЧИСТКА SQLITE ПАМЯТИ (старые воспоминания) ===
        try:
            _store = self.memory_manager._layered.store
            if hasattr(_store, "delete_campaign"):
                _deleted = _store.delete_campaign(campaign_id)
                removed.append(f"sqlite:memories({_deleted})")
                logger.info(f"[NEW_GAME] SQLite memories cleared: {_deleted} rows")
        except Exception as e:
            logger.warning(f"[NEW_GAME] SQLite memory cleanup failed: {e}")

        # P-MVP-1: Инициализация эпистемического фасада для новой кампании
        if self.mvp_controller:
            try:
                self.mvp_controller.init_campaign(campaign_id)
                logger.info(f"[NEW_GAME] MVP controller initialized for '{campaign_id}'")
            except Exception as e:
                logger.error(f"[NEW_GAME] MVP controller init failed: {e}")

        logger.info(
            f"[NEW_GAME] Campaign '{campaign_id}' fully reset. Removed: {removed}"
        )
        return {"reset": True, "campaign_id": campaign_id, "files_removed": removed}

    def reset_session_flag(self, campaign_id: str) -> None:
        """Сбрасывает флаг начала сессии — следующий ход будет session_start.
        Вызывается при SESSION_REPLACED чтобы сбросить стресс NPC из прошлой сессии.
        """
        self._session_started_campaigns.discard(campaign_id)

    def _get_life_engine(self):
        """Возвращает LifeEngine из TickOrchestrator."""
        return self._tick_orch._get_life_engine()

    def _resolve_npcs_snapshot(self, campaign_id: str) -> list:
        """ADR-TZ08-8: Explicit snapshot step.
        Гарантированно извлекает committed NPC states для PerceptionProjector.
        """
        engine = self._get_life_engine()
        if engine:
            return engine.get_npc_states(campaign_id) or []
        return []

    def _resolve_npcs_light_snapshot(self, campaign_id: str) -> list:
        """TZ-08 Addendum: Лёгкий срез для детекторов Time Skip.
        Делегирует в LifeEngine.get_npc_light_states, чтобы не нарушать инкапсуляцию кэша.
        """
        engine = self._get_life_engine()
        if engine:
            return engine.get_npc_light_states(campaign_id)
        return []

    def _project_perception(
        self, campaign_id: str, scene_state: dict, all_npcs_raw: list
    ):
        """ADR-TZ08-8: Вызов PerceptionProjector вне ядра."""
        from app.services.perception.perception_projector import PerceptionProjector

        _projector = PerceptionProjector()
        _tick = self.get_current_tick(campaign_id)
        logger.debug(f"[ARCHAE_PROJECTOR] scene_state={bool(scene_state)} all_npcs_raw={len(all_npcs_raw) if all_npcs_raw else 0}")
        _res = _projector.project(scene_state, all_npcs_raw, _tick)
        logger.debug(f"[ARCHAE_PROJECTOR] result={_res}")
        return _res

    def _load_npcs_with_runtime(self, campaign_id: str) -> list:
        """Загружает NPC с наложением runtime (стресс, HP и т.д.).
        Используется в игровом цикле, не для инициализации движков.
        ADR-030: Инъекция Аватара Игрока (Hybrid Consciousness Entity)
        """
        import logging

        from app.services.character_service import CharacterService
        from app.services.player_session_service import player_session_service

        # ADR-117: Приоритет LifeEngine кэша над файлом.
        # Без этого affective_load, emotion, body_state теряются между тиками —
        # каждый player turn загружает чистый статический конфиг с диска.
        engine = self._get_life_engine()
        npcs = engine.get_npc_states(campaign_id)
        if not npcs:
            from app.services.npc.npc_loader import load_npcs_merged
            from app.services.tick_utils import get_npc_runtime_path

            _runtime_path = get_npc_runtime_path(campaign_id)
            npcs = load_npcs_merged(runtime_path=_runtime_path)
            # ADR-117: После загрузки с диска — немедленно обновить кэш.
            # Без этого каждый player turn перечитывает диск и затирает
            # вычисленные affective_load, emotion, body_state (Инвариант 1).
            if npcs:
                engine.update_cache(campaign_id, npcs)

        # ADR-030: Игрок становится полноправным NPC в симуляции (Actor-Agnostic).
        # Удаляем протухшего аватара из кэша LifeEngine, если он там есть,
        # чтобы гарантированно инжектить свежий стейт из AvatarService.
        session = player_session_service.get_session(campaign_id)
        npcs = [
            n for n in npcs if n.get("id") != "player" and n.get("npc_id") != "player"
        ]
        if session and session.player_name:
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
                    _avatar_state = self.avatar_service.load_state(
                        campaign_id, player_char.name
                    )
                    from app.models.npc_state import BODY_STATE_HEALTHY

                    _live_body = getattr(_avatar_state, "body_state", None)  # noqa: ENIGMA002
                    if (
                        not _live_body
                    ):  # None или {} — новый аватар без сохранённой физиологии
                        _live_body = dict(BODY_STATE_HEALTHY)

                    # V8-WL-3 FIX: fear и willpower лежат внутри psyche dict, а не в корне NPCState
                    _avatar_psyche = getattr(_avatar_state, "psyche", {})  # noqa: ENIGMA002
                    _live_psyche = {
                        "stress": getattr(_avatar_state, "stress", 0.0),
                        "fear": _avatar_psyche.get("fear", 0.5),
                        "willpower": _avatar_psyche.get("willpower", 50.0),
                        "emotion": getattr(_avatar_state, "emotion", "NEUTRAL"),
                        "identity_rigidity": _avatar_psyche.get("identity_rigidity", 0.5),
                    }

                    player_dict = {
                        "id": "player",
                        "npc_id": "player",
                        "name": player_char.name,
                        "type": "player_avatar",  # Маркер для WillpowerGate
                        "archetype": getattr(player_char, "archetype", "Drifter"),
                        "temperament": getattr(player_char, "temperament", "Stoic"),
                        "body_profile": getattr(player_char, "body_profile", {}),  # noqa: ENIGMA002
                        "body_state": _live_body,  # Живая плоть: pain, blood_loss
                        "psyche": _live_psyche,  # Живой разум: stress, fear
                        "social_stats": {
                            "trust": 50.0,
                            "fear_of_player": 0.0,
                            "debt": 0.0,
                        },
                        "status_profile": {"faction_rank": {}},
                        "tier": "major", # P3 FIX: Игрок участвует в макро-симуляции (NeedEngine, Stress)
                    }
                    npcs.append(player_dict)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    f"[AVATAR_INJECT] Ошибка инъекции аватара: {e}"
                )

        # ADR-O-146: Страховка body_state для ВСЕХ NPC (не только аватара).
        # Если load_npcs_merged вернул static NPC без body_state — инжектим HEALTHY.
        # Без этого Normalization Gate впрыснет DISABLED (pain=100, shock=1.0) → смерть/кома.
        # BUG-P2-14: Проверяем наличие ключей, чтобы не перетирать пустой словарь раненого NPC.
        from app.models.npc_state import BODY_STATE_HEALTHY

        for _npc in npcs:
            _bs = _npc.get("body_state")
            if not _bs or not _bs.get("current_hp") or "life_status" not in _bs:
                _npc["body_state"] = dict(BODY_STATE_HEALTHY)

        return npcs

    def skip_time(self, campaign_id: str, ticks: int) -> dict:
        """Промотка времени через TimeSkipExecutor (TZ-08 Addendum).
        Использует Policy B (остановка на значимом событии).
        """
        lock = self._get_skip_lock(campaign_id)
        if not lock.acquire(blocking=False):
            return {"status": "skip_in_progress", "npc_positions": {}}

        try:
            from app.services.game_loop.scene_init import ensure_scene_initialized

            _prepped_scene = ensure_scene_initialized(self, campaign_id)
            _loc_id = _prepped_scene.get("location_id", "") if _prepped_scene else ""

            # BUG-FB-002 FIX: Блокируем конкретную локацию, а не пустую строку.
            _scene = self.scene_manager.lock_for_tick(campaign_id, _loc_id)
            if _scene is None:
                return {"status": "no_scene", "npc_positions": {}}

            _spatial_svc = None
            if _loc_id:
                from app.services.spatial.spatial_factory import SpatialFactory

                try:
                    _spatial_svc = SpatialFactory.build_for_campaign(
                        campaign_id=campaign_id, location_id=_loc_id, scene_state=_scene
                    )
                    from app.services.spatial.spatial_query_service import SpatialQueryService
                    self._current_spatial_query = SpatialQueryService(
                        npc_positions=_scene.get("npc_positions", {}),
                        scene_state=_scene,
                    )
                except Exception as e:
                    logger.warning(
                        f"[SPATIAL_AUTHORITY] SpatialService build failed: {e}"
                    )
                    self._current_spatial_query = None

            # AUDIT-003 §3.3: сервисный контекст NPC для тиков вне хода игрока
            from app.services.events.event_bus import get_event_bus
            from app.services.npc.npc_tick_contracts import NpcTickServices

            _npc_svc = NpcTickServices(
                memory_manager=self.memory_manager,
                relationship_store=self.memory_manager._relationships,
                social_engine=self._svc.get_social_engine(campaign_id),
                reputation_engine=self._svc.get_reputation_engine(),
                economic_profiles=self._svc.get_or_create_economic_profiles(campaign_id),
                event_bus=get_event_bus(),
                spatial_service=_spatial_svc,
                spatial_query=getattr(self, "_current_spatial_query", None),
                crystallized_belief_store=getattr(
                    getattr(self, "_tick_orch", None),
                    "crystallized_belief_store",
                    None,
                ),
            )
            result = self._time_skip.skip(
                campaign_id=campaign_id,
                scene_state=_scene,
                ticks=ticks,
                policy="B",  # Останавливаемся на значимых событиях
                spatial_service=_spatial_svc,
                get_npcs_callback=self._resolve_npcs_light_snapshot,  # Используем лёгкий срез
                npc_services=_npc_svc,  # AUDIT-003 §3.3
            )

            # Формируем world_snapshot для фронтенда
            _all_npcs = self._resolve_npcs_snapshot(campaign_id)

            # FIX: Очистка npc_dict от сложных объектов, которые не сериализуются в JSON.
            for _npc in _all_npcs:
                _npc.pop("beliefs", None)
                _npc.pop("belief_state", None)

            _ws = None
            if result.final_state:
                from app.services.integration.world_snapshot_builder import (
                    WorldSnapshotBuilder,
                )

            _builder = WorldSnapshotBuilder()
            _recent_d = self._get_task_scheduler().get_recent_dialogues(result.final_state.get("game_time_seconds", 0.0))
            logger.info(f"[IDLE_TICK_WS] recent_dialogues_count={len(_recent_d) if _recent_d else 0}")
            _player_eco_profile = self._svc.get_or_create_economic_profiles(campaign_id).get("player")

            # S159: Фильтрация реплик через NarrativeProjector
            from app.domain.presentation import AvatarPerceptionProfile, PerceptionContext
            _npc_pos = result.final_state.get("npc_positions", {})
            _p_pos_data = _npc_pos.get("player", {}).get("local_position", {})
            _sp_positions = {nid: (d.get("local_position", {}).get("x", 0.0), d.get("local_position", {}).get("y", 0.0)) for nid, d in _npc_pos.items() if nid != "player"}
            _p_stability = 1.0
            if result.world_snapshot and result.world_snapshot.avatar_state:
                _p_stability = result.world_snapshot.avatar_state.perceptual_stability
            _ctx = PerceptionContext(
                player_position=(_p_pos_data.get("x", 0.0), _p_pos_data.get("y", 0.0)),
                speaker_positions=_sp_positions,
                avatar_profile=AvatarPerceptionProfile(perceptual_stability=_p_stability)
            )
            _narratives = self._narrative_projector.project(_recent_d, _ctx)

            _ws = _builder.build(
                result.final_state,
                result.final_state.get("tick", 0),
                None,
                _all_npcs,
                perceived_narratives=_narratives,
                player_body_topology=result.final_state.get("player_body_topology"),
                eco_profile=_player_eco_profile,
            )

            # BUG-FB-002 FIX: Сохраняем мутированное состояние в persistence buffer,
            # иначе изменения от TimeSkipExecutor будут потеряны при следующем idle_tick.
            if result.final_state:
                self.scene_manager.commit_tick_result(campaign_id, result.final_state)

            return {
                "status": "ok",
                "stop_reason": result.stop_reason,
                "ticks_skipped": result.ticks_skipped,
                "world_snapshot": _ws,
                "events": result.stops,
            }
        finally:
            # BUG-FB-002 FIX: Снимаем блокировку scene_manager, иначе ядро зависнет навсегда.
            self.scene_manager.unlock_tick(campaign_id)
            lock.release()

    # E.2: Публичные методы для инкапсуляции внутренних сервисов
    def apply_changes(self, campaign_id: str, changes: list, scene_state: dict) -> None:
        """E.2: Инкапсуляция scene_manager.apply_changes"""
        self.scene_manager.apply_changes(campaign_id, changes, scene_state)

    def get_scene_state(self, campaign_id: str, location_id: str) -> dict:
        """E.2: Инкапсуляция scene_manager.get_scene_state"""
        return self.scene_manager.get_scene_state(campaign_id, location_id)

    def save_scene_state(self, campaign_id: str, scene_state: dict) -> None:
        """E.2: Инкапсуляция scene_manager.save_scene_state"""
        self.scene_manager.save_scene_state(campaign_id, scene_state)

    def find_starting_location(self, campaign_id: str) -> str:
        """E.2: Инкапсуляция scene_manager.find_starting_location"""
        return self.scene_manager.find_starting_location(campaign_id)

    def list_characters(self, campaign_id: str) -> list:
        """E.2: Инкапсуляция character_service.list_characters"""
        return self.character_service.list_characters(campaign_id)

    def idle_tick(self, campaign_id: str, location_id: Optional[str] = None, interventions: Optional[List["InterventionEvent"]] = None) -> dict:
        """Idle tick — делегирует TickOrchestrator (10 фаз, Устав §3).

        Вызывается когда игрок бездействует (таймер pygame).
        Единая точка входа: GameLoopBridge и routes.py делегируют сюда.
        TickOrchestrator.execute(dm_ctx=None) — полный idle-цикл с
        WorldSnapshotBuilder на фазе 9.

        Конвертация DTO→dict происходит ЗДЕСЬ, не в мосту (Устав §1.1).
        Frontend не должен знать про backend-классы.
        """
        # S83.1: idle_tick = tick boundary compliant path.
        # Одна точка входа в мир. Не второй мир — та же причинная система.

        # Шаг 1: Подготовка — гарантируем что сцена существует (стены, NPC, время)
        from app.core.constants import DEFAULT_LOCATION_ID
        from app.services.game_loop.scene_init import ensure_scene_initialized

        _prepped_scene = ensure_scene_initialized(self, campaign_id)
        # S-146 FIX: Поддержка принудительного тика для конкретной локации (для тестов)
        _active_loc = location_id or (_prepped_scene.get("location_id", "") if _prepped_scene else DEFAULT_LOCATION_ID)
        if not _active_loc:
            _active_loc = DEFAULT_LOCATION_ID

        # S186 FIX: Если запрошенная локация не была инициализирована в БД,
        # инициализируем её принудительно, чтобы TickOrchestrator смог её тикнуть.
        _active_scene = self.scene_manager.get_scene_state(campaign_id, _active_loc)
        if _active_scene is None:
            _active_scene = self.scene_manager.initialize_scene(campaign_id, _active_loc, "02:00")
            logger.info(f"[IDLE_TICK] Принудительная инициализация локации: {_active_loc}")

        # Дополнение Б: Получаем список всех локаций для глобального тика
        _location_ids = [_active_loc]
        try:
            from app.services.spatial.spatial_registry import SpatialRegistry
            _registry = SpatialRegistry.get_or_load(campaign_id)
            if _registry:
                _all_locs = _registry.get_all_location_ids()
                if _all_locs:
                    # S186 FIX: Гарантируем, что запрошенная локация всегда тикает,
                    # даже если SpatialRegistry не вернул её в списке всех локаций.
                    _location_ids = list(set(_all_locs + [_active_loc]))
        except Exception as e:
            logger.warning(f"[IDLE_TICK] Failed to get all locations: {e}")

        # Шаг 2: LOCK всех локаций (Дополнение Б, п. Б.6.1)
        self.scene_manager.lock_all_for_tick(campaign_id, _location_ids)

        # Шаг 3: WorldTick — единый вызов оркестратора для всех локаций (ADR-O-344)
        _scene = self.scene_manager.get_scene_state(campaign_id, _active_loc)
        if _scene is None:
            return {"status": "no_scene", "npc_positions": {}}

        # Spatial Oracle корректирует локацию только для активной сцены
        try:
            from app.services.campaign_state_service import get_campaign_state_service
            _campaign_svc = get_campaign_state_service()
            _cs = _campaign_svc.get_campaign_state(campaign_id) if _campaign_svc else None  # noqa: ENIGMA001
            if _cs:
                _saved_wx = _cs.metadata.get("player_world_x")
                _saved_wy = _cs.metadata.get("player_world_y")
                if _saved_wx is not None and _saved_wy is not None:
                    from app.services.spatial.spatial_registry import SpatialRegistry
                    _registry = SpatialRegistry.get_or_load(campaign_id)
                    if _registry is not None:
                        _actual_chunks = _registry.find_chunks(_saved_wx, _saved_wy)
                        if _actual_chunks:
                            _oracle_loc = _actual_chunks[0].location_id
                            if _oracle_loc != _active_loc:
                                logger.info(f"[SPATIAL_ORACLE_IDLE] location_id corrected: {_active_loc} → {_oracle_loc}")
                                _active_loc = _oracle_loc
                                _scene["location_id"] = _oracle_loc
        except Exception as e:
            logger.warning(f"[SPATIAL_ORACLE_IDLE] Oracle lookup failed: {e}")

        # ADR-048: GameLoop собирает SpatialService для активной локации
        _spatial_svc = None
        if _active_loc:
            from app.services.spatial.spatial_factory import SpatialFactory
            try:
                _spatial_svc = SpatialFactory.build_for_campaign(campaign_id=campaign_id, location_id=_active_loc, scene_state=_scene)
                from app.services.spatial.spatial_query_service import SpatialQueryService
                self._current_spatial_query = SpatialQueryService(npc_positions=_scene.get("npc_positions", {}), scene_state=_scene)
            except Exception as e:
                logger.warning(f"[SPATIAL_AUTHORITY] SpatialService build failed: {e}")
                self._current_spatial_query = None

        _player_eco_profile = self._svc.get_or_create_economic_profiles(campaign_id).get("player")

        # S198 FIX: Гарантируем, что idle_shared_context имеет relationship_store для SocialSubscriber
        _idle_ctx = getattr(self, "_idle_shared_context", None)
        if _idle_ctx and not getattr(_idle_ctx, "relationship_store", None):
            _idle_ctx.relationship_store = getattr(self, "_rel_store", None)

        # AUDIT-003 §3.3: контекст NPC для idle-тика — тот же паттерн сборки, что и путь игрока
        from app.services.events.event_bus import get_event_bus
        from app.services.npc.npc_tick_contracts import NpcTickServices

        _npc_svc = NpcTickServices(
            memory_manager=self.memory_manager,
            relationship_store=self.memory_manager._relationships,
            social_engine=self._svc.get_social_engine(campaign_id),
            reputation_engine=self._svc.get_reputation_engine(),
            economic_profiles=self._svc.get_or_create_economic_profiles(campaign_id),
            event_bus=get_event_bus(),
            spatial_service=_spatial_svc,
            spatial_query=getattr(self, "_current_spatial_query", None),
            crystallized_belief_store=getattr(
                getattr(self, "_tick_orch", None),
                "crystallized_belief_store",
                None,
            ),
        )
        result = self._tick_orch.execute(
            campaign_id=campaign_id,
            scene_state=_scene,
            tick_number=_scene.get("tick", 0) + 1,  # ADR-O-344: Оркестратор владеет инкрементом
            spatial_service=_spatial_svc,
            shared_context=_idle_ctx,  # noqa: ENIGMA002
            active_location_id=_active_loc,
            location_ids=_location_ids,
            eco_profile=_player_eco_profile,  # S151: Профиль игрока для EmbodiedStatusDTO
            mvp_controller=self.mvp_controller,  # ENIGMA SELF-HEALING: For probes
            interventions=interventions,  # M1: Внедрение событий игрока
            npc_services=_npc_svc,  # AUDIT-003 §3.3
        )

        # Коммит результатов оркестратора (если ядро не сделало это само)
        if result and result.final_scene_state is not None:
            # S193: Epistemic Persistence. Сохраняем убеждения в scene_state перед коммитом.
            if result.status == "ok" and hasattr(self._tick_orch, '_epistemic_store') and self._tick_orch._epistemic_store:
                result.final_scene_state["epistemic_records"] = self._tick_orch._epistemic_store.to_dict()
            self.scene_manager.commit_tick_result(campaign_id, result.final_scene_state)

        # S186 FIX: Обновляем HOT кэш LifeEngine после idle_tick.
        # Мержим результат с существующим кэшем, чтобы не стереть NPC из других локаций.
        if result and result.all_npcs_raw:
            _engine = self._get_life_engine()
            if _engine:
                _cached_npcs = _engine.get_npc_states(campaign_id) or []
                _updated_npcs = {n.get("npc_id", n.get("id")): n for n in _cached_npcs}
                for n in result.all_npcs_raw:
                    _nid = n.get("npc_id", n.get("id"))
                    if _nid:
                        _updated_npcs[_nid] = n
                _engine.update_cache(campaign_id, list(_updated_npcs.values()))

        if result is None:
            return {"status": "no_scene", "npc_positions": {}}

        # BUG-PERC-001 / BUG-CORE-006 FIX: GameLoop больше не перезаписывает perception.
        # Фаза 9 (integration.py) уже собрала корректный API DTO с observed_facts
        # и передала его в WorldSnapshotBuilder.build(), где прошла конвертацию.
        # Повторная проекция здесь приводила к потере observed_facts и структуры DTO.

        # S83.1 FIX: Ядро больше не вызывает commit_tick_result.
        # Дополнение Б: Мы уже закоммитили результат внутри цикла.
        # ДИАГНОСТИКА: Читаем из authoritative source (scene_manager._tick_scenes),
        # а не из устаревшей ссылки _scene (execute работает с deepcopy).
        _auth_scene = self.scene_manager._tick_scenes.get(_active_loc) if self.scene_manager else None  # noqa: ENIGMA001
        if _auth_scene is None:
            _auth_scene = result.final_scene_state or _scene
        _trav_after = (
            list(_auth_scene.get("active_traversals", {}).keys())
            if _auth_scene
            else list(_scene.get("active_traversals", {}).keys())
        )
        logger.debug(
            f"[IDLE_TRACE] AFTER tick={_scene.get('tick')} traversals={_trav_after} source={'tick_scene' if _auth_scene else 'stale_ref'}"
        )

        # ADR-O-313: Execution Framework. Материализация отложенных задач (LLM и др.)
        # Работаем с _auth_scene (_tick_scene), чтобы мутации подписчиков EventBus
        # (напр. SocialInputProjector) попали в финальный unlock_tick.
        if _auth_scene and _auth_scene.get("pending_tasks"):
            self._get_task_scheduler().execute_pending(_auth_scene, campaign_id)

        # S203.4 (ADR-O-365, D-2): БЕЗУСЛОВНЫЙ sync-дренаж outbox — тихие тики
        # (без pending_tasks) не создают backlog терминалов; окно до unlock_tick (F24).
        if _auth_scene:
            self._get_task_scheduler().drain_commitment_outbox(_auth_scene)

        # Конвертация WorldSnapshotDTO → dict для фронтенда
        from dataclasses import asdict

        _ws: dict | None = None
        _npc_pos_dict: dict = {}
        if result.world_snapshot is not None:
            _ws = asdict(result.world_snapshot)
            # A2-FIX: npc_positions уже Dict[str, NPCPositionDTO] (canonical). Адаптер удалён.
            _npc_pos_dict = _ws.get("npc_positions", {})
            # UUID → строка для JSON-совместимости
            if _ws.get("last_event_id") is not None:
                _ws["last_event_id"] = str(_ws["last_event_id"])

            # ADR-O-313: Внедряем кэш реплик для Speech Bubbles (UI)
            try:
                _recent_d = self._get_task_scheduler().get_recent_dialogues(_scene.get("game_time_seconds", 0.0))
                logger.info(f"[IDLE_TICK_WS] recent_dialogues_count={len(_recent_d) if _recent_d else 0}")
                from app.domain.presentation import AvatarPerceptionProfile, PerceptionContext
                from app.services.integration.legacy_dialogue_adapter import LegacyDialogueAdapter
                _npc_pos = _scene.get("npc_positions", {})
                _p_pos_data = _npc_pos.get("player", {}).get("local_position", {})
                _sp_positions = {nid: (d.get("local_position", {}).get("x", 0.0), d.get("local_position", {}).get("y", 0.0)) for nid, d in _npc_pos.items() if nid != "player"}
                _ctx = PerceptionContext(
                    player_position=(_p_pos_data.get("x", 0.0), _p_pos_data.get("y", 0.0)),
                    speaker_positions=_sp_positions
                )
                _narratives = self._narrative_projector.project(_recent_d, _ctx)
                _ws["perceived_narratives"] = [asdict(n) for n in _narratives]
                _ws["recent_dialogues"] = [asdict(d) for d in LegacyDialogueAdapter.to_legacy_dto(_narratives)]
            except Exception as e:
                logger.warning(f"[IDLE_TICK_WS] Failed to get recent dialogues: {e}")

            # S128 FIX: Инъекция dialog_journal (SSOT из AvatarService) для синхронизации UI в idle_tick
            _ws["dialog_journal"] = self.avatar_service.get_journal(campaign_id)

        # S83.1: UNLOCK — единственная точка persist для idle_tick.
        # commit_tick_result() уже обновил _tick_scene результатом тика.
        # unlock_tick сохраняет его на диск.
        self.scene_manager.unlock_tick(campaign_id)

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
        logger.debug(f"[ARCHAE_PLAYER_ENTRY] req={req}")
        """Блокирующий путь (REST). DM-нарратив собирается целиком."""
        self.assert_requirements()
        _is_session_start_rest = req.campaign_id not in self._session_started_campaigns
        if _is_session_start_rest:
            self._session_started_campaigns.add(req.campaign_id)
        state = await self._run_pipeline(
            req.actions,
            req.campaign_id,
            req.world_id,
            req.location,
            is_session_start=_is_session_start_rest,
            player_position=req.player_position,
        )

        # Death Guard: если pipeline вернул ранний ChatTurnResponse (игрок мёртв)
        from app.models.schemas import ChatTurnResponse as _CTR

        if isinstance(state, _CTR):
            return state

        # ADR-TZ08-8: Explicit snapshot step для PerceptionProjector
        # S122 FIX: Берём свежий all_npcs_raw из результата тика, а не из старого кэша.
        if state.shared_context:
            state.shared_context.all_npcs_raw = self._resolve_npcs_snapshot(req.campaign_id)
            # BUG-DLG-003 FIX: Проброс снимка NPC для DM-агента (Block 4.7: Контекст NPC).
            # Без этого DM LLM не получает описания NPC и генерит пустой нарратив.
            state.shared_context.all_npcs_raw_snapshot = state.shared_context.all_npcs_raw

        if state.shared_context and state.shared_context.scene_state:
            _perception = self._project_perception(
                req.campaign_id,
                state.shared_context.scene_state,
                state.shared_context.all_npcs_raw,
            )
            if _perception:
                state.shared_context.player_perception = _perception

        # Sprint P9: Проброс observed_facts в shared_context для DM-агента
        if hasattr(state, "observed_facts") and state.shared_context:
            state.shared_context.observed_facts = state.observed_facts

        # Sprint P9: Проброс observed_facts в DM-агент через world_result
        _dm_world_result = {
            "world_events": state.world_tick_meta.get("events", []),
            "observed_facts": getattr(state, "observed_facts", []),  # noqa: ENIGMA002
        }

        dm_result = await run_agent_safe(
            "dm",
            self.dm_agent,
            (
                req.location,
                req.actions,
                state.rules_result,
                state.npc_result,
                _dm_world_result,
                False,
                state.shared_context,
            ),
            {},
        )
        # ADR-113: LLM Failure — честная ошибка + попытка рестарта
        if isinstance(dm_result, dict) and dm_result.get("error"):
            _err_msg = dm_result.get("human_msg", "LLM сервер недоступен")
            logger.error(f"[DM_RESULT] LLM FAILED: {_err_msg}")
            # Recovery: пробуем перезапустить llama-server и повторить запрос
            try:
                from app.services.llm.server_lifecycle import restart_llama_server as _restart_llama_server

                if _restart_llama_server():
                    logger.info("[DM_RESULT] LLM рестартнул — повторяем запрос")
                    dm_result = self._run_dm(state)
                    if not (isinstance(dm_result, dict) and dm_result.get("error")):
                        # Рестарт помог — продолжаем нормальный путь
                        pass
                    else:
                        return {
                            "dm_response": f"[СИСТЕМА: LLM сервер недоступен — {_err_msg}]",
                            "world_snapshot": state.shared_context.world_snapshot or {},
                            "will_conflict_data": None,
                        }
                else:
                    return {
                        "dm_response": f"[СИСТЕМА: LLM сервер недоступен — {_err_msg}]",
                        "world_snapshot": state.shared_context.world_snapshot or {},
                        "will_conflict_data": None,
                    }
            except ImportError as e:
                logger.warning(f"LLM ImportError: {e}")
                return {
                    "dm_response": f"[СИСТЕМА: LLM сервер недоступен — {_err_msg}]",
                    "world_snapshot": state.shared_context.world_snapshot or {},
                    "will_conflict_data": None,
                }
        logger.debug(f"[DM_RESULT] type={type(dm_result).__name__}")

        # RCE: Reality Commit Extractor — извлекаем npc_reactions из DM-нарратива
        # Инвариант: ни один LLM-выход не считается состоянием мира, пока не прошёл RCE-коммит
        if isinstance(dm_result, dict) and dm_result.get("dm_response"):
            from app.services.memory.rce import extract_speech_events

            _anr_rce = getattr(state.shared_context, "all_npcs_raw_snapshot", None)  # noqa: ENIGMA002
            # Fallback: загружаем NPC из рантайма, если snapshot пуст
            if not _anr_rce:
                try:
                    _anr_rce = self._load_npcs_with_runtime(req.campaign_id)
                except Exception:
                    _anr_rce = []
            _target_id = getattr(state.shared_context, "player_target_id", None)  # noqa: ENIGMA002
            _player_name = req.actions[0].player_name if req.actions else None  # noqa: ENIGMA001
            _rce_reactions = extract_speech_events(
                dm_text=dm_result.get("dm_response", ""),
                target_npc_id=_target_id,
                all_npcs_raw=_anr_rce,
                player_name=_player_name,
            )

            if _rce_reactions:
                # Инжектим извлечённые реакции обратно в dm_result для downstream
                dm_result["npc_reactions"] = _rce_reactions
                # Записываем в STM — теперь мир помнит, что NPC говорил
                try:
                    from app.services.memory.working_memory_tick import (
                        write_npc_reactions_to_memory,
                    )

                    write_npc_reactions_to_memory(
                        self.memory_manager,
                        _rce_reactions,
                        _anr_rce if isinstance(_anr_rce, (dict, list)) else {},
                        req.campaign_id,
                    )
                except Exception as _rce_err:
                    logger.warning(f"[RCE] STM write failed: {_rce_err}")

        # R2.1: NarrativeExtractor R2.2.8 — синхронный путь (REST)
        try:
            from app.services.scene.narrative_extractor import get_extractor

            dm_text = dm_result.get("dm_response", "")
            scene_state = state.shared_context.scene_state or {}
            if dm_text and scene_state:
                current_tick = self.get_current_tick(req.campaign_id)
                extraction = get_extractor().extract(dm_text, scene_state, current_tick)
                if (
                    extraction.new_objects
                    or extraction.new_events
                    or extraction.updated_states
                ):
                    self.scene_manager.apply_narrative_extractions(
                        req.campaign_id, scene_state, extraction
                    )
                    if current_tick % 50 == 0:
                        self.scene_manager.prune_dynamic_objects(
                            req.campaign_id, scene_state, current_tick
                        )
        except Exception as e:
            logger.warning(f"[R2.1] NarrativeExtractor REST error: {e}")

        # N-02 FIX: time.monotonic() для корректного elapsed_ms во время replay.
        elapsed_ms = int(time.monotonic() * 1000 - state.start_ms)
        traces = self._build_traces(state, dm_result, elapsed_ms)

        # NEW-8 FIX: Устанавливаем player_recognition ДО commit_tick_result,
        # чтобы deepcopy внутри commit_tick_result захватил confidence=1.0.
        _target_id = getattr(state.shared_context, "player_target_id", None) if state.shared_context else None  # noqa: ENIGMA001, ENIGMA002
        if _target_id and hasattr(state, "shared_context") and state.shared_context and state.shared_context.scene_state:
            _recog_map = state.shared_context.scene_state.setdefault("player_recognition", {})
            _recog_entry = _recog_map.setdefault(_target_id, {"confidence": 0.0})
            _recog_entry["confidence"] = 1.0
            logger.info(f"[RECOG_MEMORY] Dialogue trigger (Pre-Commit): NPC {_target_id} confidence=1.0")

        # S128 FIX: Обязательный commit_tick_result после _run_pipeline.
        # Без этого unlock_tick сохраняет старый _tick_scene, затирая мутации ядра (player_recognition).
        if hasattr(state, "shared_context") and state.shared_context and state.shared_context.scene_state:
            self.scene_manager.commit_tick_result(req.campaign_id, state.shared_context.scene_state)

        # BUG-FB-030 FIX: Используем world_snapshot, собранный ядром в Phase 9, вместо Force Merge
        _ws_dict = None
        _npc_pos_dict = None
        if state.shared_context and state.shared_context.world_snapshot:
            from dataclasses import asdict
            _ws_dict = asdict(state.shared_context.world_snapshot)
            _npc_pos_dict = _ws_dict.get("npc_positions", {})
            # ADR-O-313: Внедряем кэш реплик для Speech Bubbles (UI)
            try:
                _scene = state.shared_context.scene_state or {}
                _recent_d = self._get_task_scheduler().get_recent_dialogues(_scene.get("game_time_seconds", 0.0))
                logger.info(f"[IDLE_TICK_WS] recent_dialogues_count={len(_recent_d) if _recent_d else 0}")
                from app.domain.presentation import AvatarPerceptionProfile, PerceptionContext
                from app.services.integration.legacy_dialogue_adapter import LegacyDialogueAdapter
                _npc_pos = _scene.get("npc_positions", {})
                _p_pos_data = _npc_pos.get("player", {}).get("local_position", {})
                _sp_positions = {nid: (d.get("local_position", {}).get("x", 0.0), d.get("local_position", {}).get("y", 0.0)) for nid, d in _npc_pos.items() if nid != "player"}
                _ctx = PerceptionContext(
                    player_position=(_p_pos_data.get("x", 0.0), _p_pos_data.get("y", 0.0)),
                    speaker_positions=_sp_positions
                )
                _narratives = self._narrative_projector.project(_recent_d, _ctx)
                _ws_dict["perceived_narratives"] = [asdict(n) for n in _narratives]
                _ws_dict["recent_dialogues"] = [asdict(d) for d in LegacyDialogueAdapter.to_legacy_dto(_narratives)]
            except Exception as e:
                logger.warning(f"[IDLE_TICK_WS] Failed to get recent dialogues: {e}")
            _ws_dict["dialog_journal"] = self.avatar_service.get_journal(req.campaign_id)

        # ADR-SCENE-LOCK: Разблокируем тик — финальный персист кэша.
        self.scene_manager.unlock_tick(req.campaign_id)

        # ADR-JOURNAL: Логирование реплик в буфер аватара (SSOT)
        # 1. Сначала логируем действие самого игрока
        for _a in req.actions:
            if _a.action:
                # B1.3-FIX: Передача campaign_id для привязки журнала к кампании
                self.avatar_service.append_journal(
                    campaign_id=req.campaign_id, speaker=_a.player_name, text=_a.action
                )

        _dm_text = dm_result.get("dm_response", "")
        if _dm_text:
            # B1.3-FIX: Передача campaign_id для привязки журнала к кампании
            self.avatar_service.append_journal(
                campaign_id=req.campaign_id, speaker="Рассказчик", text=_dm_text
            )

        # Инжект журнала в WorldSnapshot (если снапшот собран)
        if _ws_dict is not None:
            # B1.3-FIX: Передача campaign_id для получения журнала
            _ws_dict["dialog_journal"] = self.avatar_service.get_journal(
                req.campaign_id
            )

        _resp_facts = getattr(state, "observed_facts", [])  # noqa: ENIGMA002
        logger.debug(f"[DEBUG_RUN_TURN] state.observed_facts count={len(_resp_facts)}")
        _final_response = ChatTurnResponse(
            dm_response=dm_result.get("dm_response", ""),
            npc_reactions=dm_result.get("npc_reactions", []),
            world_changes=dm_result.get("world_changes", []),
            world_snapshot=_ws_dict,
            npc_positions=_npc_pos_dict,
            # ADR-075: Строгий проброс Эмбодимента.
            will_conflict_data=state.shared_context.will_conflict_data  # noqa: ENIGMA001
            if state.shared_context
            else None,
            # Sprint P9: Проброс ObservedFactsBundle для UI и DM
            observed_facts=_resp_facts,
            journal_entry_id=self.memory_manager.persist_dm_response(
                req.campaign_id,
                world_id=req.world_id,
                location=req.location,
                actions=[a.model_dump() for a in req.actions],
                dm_text=dm_result.get("dm_response", ""),
            ),
            traces=traces,
        )
        return _final_response

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
        logger.warning(
            f"[SESSION_CHECK] campaign={campaign_id} known={self._session_started_campaigns} is_new={is_session_start}"
        )
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
            actions,
            campaign_id,
            world_id,
            location,
            campaign_state=campaign_state,
            is_session_start=is_session_start,
            player_position=player_position,
        )

        # Death Guard: если pipeline вернул ранний ChatTurnResponse (игрок мёртв)
        # Аналог проверки в run_turn (строка ~451), но для SSE-потока
        from app.models.schemas import ChatTurnResponse as _CTR_STREAM

        if isinstance(state, _CTR_STREAM):
            # Для SSE — отправляем DM-ответ как токен и завершаем с флагом смерти
            if state.dm_response:
                yield {"type": "token", "text": state.dm_response, "n": 1}
            yield {
                "type": "done",
                "death": True,
                "tokens": 1,
                "ms": 0,
                "tps": 0.0,
                "game_time_seconds": 0,
                "will_conflict_data": None,
                "world_snapshot": state.world_snapshot,
            }
            return

        # Модели — метаинфо
        async for event in yield_model_info(state):
            yield event

        # NPC реакции — ДО токенов DM
        if npc_reactions := (
            state.npc_result.get("npc_reactions", [])
            + state.npc_result.get("npc_actions", [])
        ):
            yield {
                "type": "npc",
                "data": npc_reactions,
                "model": state.npc_result.get("model"),
            }

        # DM — стриминг токенов
        yield {"type": "status", "text": "Мастер рассказывает..."}
        token_count = 0
        world_result = {"world_events": []}
        dm_text_parts: list[str] = []  # R2.1: буфер для экстрактора

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
                dm_text_parts.append(token)  # R2.1
                yield {"type": "token", "text": token, "n": token_count}
        except Exception as e:
            yield {"type": "error", "text": str(e)}
            return

        # N-02 FIX: time.monotonic() для корректного elapsed_ms и TPS во время replay.
        elapsed_ms = int(time.monotonic() * 1000 - state.start_ms)
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
            _preview_q = (
                f"{_player_msg[:80]}..." if len(_player_msg) > 80 else _player_msg
            )
            _preview_a = (
                f"{dm_full_text_for_mem[:120]}..."
                if len(dm_full_text_for_mem) > 120
                else dm_full_text_for_mem
            )
            logger.warning(f"[DM] {_preview_q}")
            logger.warning(f"[NPC] {_preview_a}")

        _ss_scene = state.shared_context.scene_state or {}
        yield {
            "type": "done",
            "tokens": token_count,
            "ms": elapsed_ms,
            "tps": tps,
            # S139 FIX: SSOT — время читается из scene_state, а не из shared_context (mirror)
            "game_time_seconds": _ss_scene.get("game_time_seconds", 0),
            # ADR-075: Проброс Эмбодимента через SSE. Фронтенд собирает GameActionResponse из этого словаря.
            "will_conflict_data": state.shared_context.will_conflict_data  # noqa: ENIGMA001
            if state.shared_context
            else None,
            # BUG-FB-001 FIX: Проброс world_snapshot в финальном done-событии (как в ветке смерти)
            "world_snapshot": state.world_snapshot,
        }

        # R2.1: NarrativeExtractor R2.2.8
        try:
            from app.services.scene.narrative_extractor import get_extractor

            dm_full_text = "".join(dm_text_parts)
            scene_state = state.shared_context.scene_state or {}
            if dm_full_text and scene_state:
                current_tick = self.get_current_tick(campaign_id)
                extraction = get_extractor().extract(
                    dm_full_text, scene_state, current_tick
                )
                if (
                    extraction.new_objects
                    or extraction.new_events
                    or extraction.updated_states
                ):
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

    def _sync_shared_context_with_scene(
        self, scene_state: dict, shared_context: Any
    ) -> None:
        """Синхронизирует shared_context с заблокированным scene_state."""
        shared_context.scene_state = scene_state

        from app.services.spatial.spatial_query_service import SpatialQueryService

        shared_context.spatial_query = SpatialQueryService(
            npc_positions=scene_state.get("npc_positions", {}),
            scene_state=scene_state,
        )

        if hasattr(shared_context, "current_tick"):
            shared_context.current_tick = scene_state.get("tick", 0) + 1
        self._current_tick = scene_state.get("tick", 0) + 1

    async def _finalize_pipeline_and_build_dm_frame(
        self,
        shared_context: Any,
        _ctx: Any,
        campaign_id: str,
        actions: list,
        _player_result: TickPlayerResultDTO,
    ) -> tuple[dict, dict]:
        """ФАЗА 7 (Rules) + ФАЗЫ 8-10 (R3 Frame) + Avatar Sync."""
        _state_observed_facts = getattr(_player_result, "observed_facts", [])  # noqa: ENIGMA002
        logger.debug(
            f"[DEBUG_GAME_LOOP] _state_observed_facts count={len(_state_observed_facts)}"
        )

        from app.services.events.event_types import EventType
        from app.services.events.rules_subscriber import RulesSubscriber

        _action_type = shared_context.action_type or "player_interacts"
        _rules_action_type = self.dm_orchestrator._router.get_rules_action_type(
            _action_type
        )

        _rules_event = type(
            "Event",
            (),
            {
                "type": "player_attacks"
                if "attack" in _rules_action_type.lower()
                else "player_interacts",
                "payload": {"target_id": shared_context.player_target_id},
                "source": actions[0].player_name if actions else "player",
                "id": f"rules_{shared_context.current_tick}",
            },
        )()

        _rules_snapshot = {
            "all_npcs_raw": _ctx.all_npcs_raw or [],
            "tick_number": shared_context.current_tick or 0,
            "campaign_id": campaign_id,
            "relationship_store": self.memory_manager._relationships  # noqa: ENIGMA001
            if self.memory_manager
            else None,
            "raw_input": actions[0].action if actions else "",
        }

        _rules_sub = RulesSubscriber()
        _rules_delta = _rules_sub.handle(_rules_event, _rules_snapshot)

        rules_result = {"checks": _rules_delta.checks} if _rules_delta else {}
        logger.warning(
            f"[RULES] action_type={_action_type} → {_rules_action_type} (synchronous reducer)"
        )

        _player_name = actions[0].player_name if actions else ""
        _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)

        import copy

        _avatar_state_before = copy.deepcopy(_avatar_state) if _avatar_state else None  # noqa: ENIGMA001

        # Stage 0 Task 0.8: SSOT Economic. Прямая мутация аватара запрещена.
        # Дельта денег применяется через StateApplicator.apply_batch вместе с остальными NPC.
        if _rules_delta and _rules_delta.money_delta != 0.0:
            from app.models.delta_payloads import EconomicPayload
            from app.models.state_delta import DeltaDomain, StateDeltas

            _eco_delta = StateDeltas(
                npc_id="player",
                domain=DeltaDomain.ECONOMY,
                payload=EconomicPayload(money_delta=_rules_delta.money_delta)
            )
            _state_applicator = self._svc.get_state_applicator(campaign_id)
            _player_dict = next((n for n in _ctx.all_npcs_raw if n.get("npc_id") == "player"), None)
            if _player_dict and _state_applicator:
                _state_applicator.apply_batch([_eco_delta], _ctx.all_npcs_raw, campaign_id)
                logger.info(f"[TRADE_FIX] Applied money_delta={_rules_delta.money_delta} to avatar via StateApplicator.")

        from dataclasses import asdict, is_dataclass

        if is_dataclass(_avatar_state):
            _avatar_dict = asdict(_avatar_state)
            _avatar_dict["npc_id"] = "player"
            _avatar_dict["id"] = "player"
            if hasattr(_ctx, "all_npcs_raw") and _ctx.all_npcs_raw is not None:
                _ctx.all_npcs_raw = [
                    n for n in _ctx.all_npcs_raw if n.get("npc_id") != "player"
                ]
                _ctx.all_npcs_raw.append(_avatar_dict)

        shared_context.npc_contexts = getattr(_player_result, "npc_contexts", []) or []  # noqa: ENIGMA002
        try:
            from app.services.scene.r3_direct_builder import build_r3_dm_frame

            npc_result = (
                build_r3_dm_frame(shared_context, actions, rules_result)
                if R3_DIRECT_MODE
                else {}
            )

            logger.debug(
                f"[TRAV_CHECK_P1_5] after_finalize_return: id={id(shared_context.scene_state)} traversals={list(shared_context.scene_state.get('active_traversals', {}).keys()) if shared_context.scene_state else 'NONE'}"
            )

            _updated_avatar_dict = next(
                (
                    n
                    for n in getattr(_ctx, "all_npcs_raw", [])  # noqa: ENIGMA002
                    if n.get("npc_id") == "player"
                ),
                None,
            )
            from app.models.npc_state import NPCState
            if _updated_avatar_dict and isinstance(_avatar_state, NPCState):
                # S208 (P0-B): GameLoop — оркестратор, не писатель NPCState.
                # Каноническая граница мутации — AvatarStateApplicator.
                from app.services.avatar_state_applicator import AvatarStateApplicator

                AvatarStateApplicator.apply_pipeline_result(
                    _avatar_state, _updated_avatar_dict
                )

            if (
                _avatar_state
                and _avatar_state_before
                and _avatar_state != _avatar_state_before
            ):
                self.avatar_service.save_state(campaign_id, _avatar_state)
                _avatar_hp = getattr(_avatar_state, "effective_hp", getattr(_avatar_state, "hp", 0))
                logger.warning(
                    f"[AVATAR] STATE APPLIED: pain={_avatar_state.body_state.get('pain', 0.0):.1f} shock={_avatar_state.body_state.get('shock_impulse', 0.0):.2f} money={_avatar_state.body_state.get('money', 0.0):.1f} hp={_avatar_hp}"
                )

            _engine = self._get_life_engine()
            if (
                _engine
                and hasattr(_ctx, "all_npcs_raw")
                and _ctx.all_npcs_raw is not None
            ):
                _engine.update_cache(campaign_id, _ctx.all_npcs_raw)

        except Exception as _fin_err:
            logger.error(f"[GAME_LOOP] Finalize error: {_fin_err}", exc_info=True)
            # H-34 FIX: Не маскируем ошибку пустым npc_result, пробрасываем исключение (ADR-O-308)
            raise

        try:
            from app.models.npc_state import EmotionTag
            from app.services.game_loop.phase_6_avatar import (
                update_avatar_from_npc_intents,
            )

            update_avatar_from_npc_intents(
                self.avatar_service,
                campaign_id,
                _player_name,
                shared_context.npc_contexts or [],
                EmotionTag,
            )
        except Exception as _av_err:
            logger.warning(f"[AVATAR] update error: {_av_err}")

        return rules_result, npc_result

    async def _execute_dm_and_intent_resolution(
        self,
        actions: list,
        shared_context: Any,
        scene_state: dict,
        _ctx: Any,
        campaign_id: str,
        location: str,
    ) -> tuple[Any, Any]:
        """ФАЗА 1-3: Запуск DM-фазы и резолв интента игрока."""
        # H-32 FIX: Загружаем профиль игрока из avatar_service, а не используем None
        _player_name = shared_context.player_name or "player"
        _match = self.avatar_service.load_state(campaign_id, _player_name)
        try:
            dm_result = run_dm_phase(
                self, actions, shared_context, scene_state, _ctx, campaign_id, location
            )
            logger.warning(
                f"[DEBUG DM] is_valid={dm_result.is_valid}, scene_context={dm_result.scene_context}, error={dm_result.error}"
            )

            import dataclasses as _dc
            if _match and _dc.is_dataclass(_match):
                _player_data_dict = _dc.asdict(_match)
            elif _match and hasattr(_match, "model_dump"):
                _player_data_dict = _match.model_dump()
            else:
                _player_data_dict = None
            _raw_action = actions[0].action if actions else ""

            # S200: Получаем сессию диалога игрока с целевым NPC для контекстного резолва
            _target_npc = shared_context.player_target_id or "player"
            _dialogue_session = None
            if self.memory_manager and _target_npc != "player":
                try:
                    _dialogue_session = self.memory_manager.get_dialogue_session(
                        campaign_id=campaign_id,
                        npc_id=_target_npc,
                        partner_id="player"
                    )
                except Exception as _ds_err:
                    logger.warning(f"[S200] Failed to get dialogue session for {_target_npc}: {_ds_err}")

            _semantic_field = await self._intent_compressor.compress(
                raw_text=_raw_action,
                scene_context=scene_state,
                dialogue_session=_dialogue_session
            )

            # S201/S202: Публикуем SOCIAL_ACTION в EventBus для наблюдателей
            _action_val = _semantic_field.action.value if _semantic_field.action else "UNCERTAIN"
            if _action_val in ("ATTACK", "THREATEN", "DIALOGUE", "STEAL", "GIVE"):
                from app.domain.events import EventDTO
                from app.services.events.event_bus import get_event_bus
                from app.services.events.event_types import EventType

                _prop = None
                if _semantic_field.proposition:
                    _prop = {
                        "subject_id": _semantic_field.proposition.subject_id,
                        "predicate": _semantic_field.proposition.predicate.value,
                        "object_id": _semantic_field.proposition.object_id,
                        "polarity": _semantic_field.proposition.polarity
                    }

                _payload = {
                    "action": _action_val,
                    "actor": _semantic_field.actor or "player",
                    "target": _semantic_field.target or shared_context.player_target_id or "",
                    "speech_act": _semantic_field.speech_act.value if _semantic_field.speech_act else "assert",
                    "proposition": _prop,
                    "physical_force": _semantic_field.physical_force,
                    "emotional_charge": _semantic_field.emotional_charge,
                    "social_pressure": _semantic_field.social_pressure,
                    "tick": shared_context.current_tick
                }

                _event = EventDTO.create_social_action(
                    source=_semantic_field.actor or "player",
                    payload=_payload,
                    visibility="public",
                    radius=10.0
                )
                _bus = get_event_bus()
                _bus.publish(_event)

            _resolution = resolve_player_intent(
                raw_action=_raw_action,
                action_type=shared_context.action_type or "player_interacts",
                target=shared_context.player_target_id or "",
                player_dict=_player_data_dict,
                scene_context=scene_state,
                semantic_field=_semantic_field,
            )
            shared_context.intent_resolution = _resolution

            # ADR-O-330: Player MOVE action creates MacroMovementGoal for MovementEngine
            # Если игрок пишет "подойти к [NPC]", мы должны найти узел NPC и двигаться к нему.
            _sem_action_val = _semantic_field.action_type.value if _semantic_field else ""
            if _sem_action_val == "MOVE" and shared_context.player_target_id:
                _target_id = shared_context.player_target_id
                _target_pos = scene_state.get("npc_positions", {}).get(_target_id, {}).get("position", "")
                if _target_pos:
                    from app.domain.movement import MacroMovementGoal
                    _player_goal = MacroMovementGoal(
                        actor_id="player",
                        target_node_id=_target_pos,
                        location_id=location,
                        reason="player_action:approach",
                        priority=1.0
                    )
                    if not hasattr(_ctx, "movement_intents") or _ctx.movement_intents is None:
                        _ctx.movement_intents = []
                    _ctx.movement_intents.append(_player_goal)
                    logger.warning(f"[PLAYER_MOVE] Injected MacroMovementGoal for player -> {_target_pos}")

            if self.mvp_controller:
                # S199: Уничтожен раздвоенный semantic authority.
                # MvpTavernController теперь получает PlayerAction через bridge из расширенного IntentSemanticField.
                from app.services.player_cognition.legacy_bridge import intent_to_player_action
                _action = intent_to_player_action(
                    intent=_semantic_field,
                    tick=shared_context.current_tick,
                    truth_state=self.mvp_controller.truth_state
                )
                self.mvp_controller.action_compiler.process_action(_action)

            if _ctx.hub_event and _resolution and _resolution.original_intent:
                _params = _resolution.original_intent.parameters
                logger.debug(
                    f"[ARCHAE-PAYLOAD] params={_params} sa={getattr(_params, 'semantic_action', 'NO_SA') if _params else 'NO_PARAMS'}"
                )
                if _params:
                    _sa = getattr(_params, "semantic_action", None)  # noqa: ENIGMA002
                    _tid = getattr(_params, "target_id", None)  # noqa: ENIGMA002
                    _tref = getattr(_params, "target_reference", None)  # noqa: ENIGMA002
                    _sem_payload = {}
                    if _sa:
                        _sem_payload["semantic_action"] = _sa
                    if _tid:
                        _sem_payload["target_id"] = _tid
                    if _tref:
                        _sem_payload["target_reference"] = _tref.lower()
                    if _sem_payload:
                        import dataclasses

                        _ctx.hub_event = dataclasses.replace(
                            _ctx.hub_event, payload=_sem_payload
                        )
                        logger.warning(
                            f"[PAYLOAD_INJECT] hub_event.payload={_sem_payload} id={id(_ctx.hub_event)} event_type={_ctx.hub_event.event_type}"
                        )
        except Exception as e:
            logger.error(f"[DM_INTENT_PHASE] Error: {e}", exc_info=True)
            raise

        return dm_result, _resolution

    def _prepare_and_lock_scene(
        self,
        campaign_id: str,
        location: str,
        shared_context: Any,
        campaign_state: Any,
        player_position: tuple[float, float] | None,
    ) -> dict:
        """Блокирует scene_state на время тика, гарантируя единственный объект."""
        from app.services.game_loop.scene_init import ensure_scene_initialized

        _prepped_scene = ensure_scene_initialized(self, campaign_id)
        _loc_id = _prepped_scene.get("location_id", "") if _prepped_scene else location
        if not _loc_id:
            _loc_id = location

        scene_state = self.scene_manager.lock_for_tick(campaign_id, _loc_id)
        if scene_state is None:
            scene_state = init_scene_state(
                self,
                campaign_id,
                _loc_id,
                shared_context,
                campaign_state,
                player_position=player_position,
            )
            # BUG-CORE-008 FIX: ADR-SCENE-LOCK — _tick_scenes это Dict[str, dict].
            self.scene_manager._tick_scenes[_loc_id] = scene_state
            self.scene_manager._tick_locked = True
            self.scene_manager._tick_campaign_id = campaign_id
        else:
            from app.services.game_loop.scene_init import (
                _sync_game_time,
                _update_player_position,
            )

            _update_player_position(scene_state, player_position)
            _sync_game_time(scene_state, shared_context)

        return scene_state

    async def _load_player_avatar(
        self, actions: list, campaign_id: str, location: str, shared_context: Any
    ) -> Optional[ChatTurnResponse]:
        """Загружает аватар игрока. Если игрок мёртв, возвращает ответ смерти."""
        _player_name = actions[0].player_name if actions else ""
        try:
            _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)

            # P0: ACTION ELIGIBILITY GATE — мёртвый игрок не может действовать (ADR-127, Rule 59)
            _player_life = (
                _avatar_state.body_state.get("life_status", "ALIVE")
                if _avatar_state and _avatar_state.body_state
                else "ALIVE"
            )
            if _player_life == "DEAD":
                logger.warning(
                    f"[DEATH_GATE] Player '{_player_name}' is DEAD. DM narrates death."
                )
                from app.services.game_loop.phase_6_avatar import avatar_to_prompt

                shared_context.player_state = {
                    _player_name: avatar_to_prompt(_avatar_state)
                }
                _bs = (
                    _avatar_state.body_state
                    if _avatar_state and _avatar_state.body_state
                    else {}
                )
                _death_avatar_dict = {
                    "physical_state": "dead",
                    "mental_state": "broken",
                    "perceptual_stability": 0.0,
                    "cognitive_coherence": 0.0,
                    "sensory_noise": 1.0,
                    "motor_disruption": 1.0,
                    "perceptual_latency": 1.0,
                    "reality_reconciliation_rate": 0.0,
                    "blood_visibility": min(
                        1.0, float(_bs.get("blood_loss", 0.0)) * 1.5
                    ),
                    "breathing_profile": "none",
                    "posture_state": "collapsed",
                    "will_resistance": 0.0,
                    "embodied_vector": None,
                    "life_status": "DEAD",
                }
                _death_ws = {"avatar_state": _death_avatar_dict}
                try:
                    _cached = self.life_engine.get_npc_states(campaign_id)
                    if _cached:
                        _death_ws["npc_positions"] = {
                            n.get("npc_id", n.get("id", f"npc_{i}")): n
                            for i, n in enumerate(_cached)
                            if isinstance(n, dict)
                        }
                except Exception as e:
                    logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
                _death_dm_response = "Тьма поглощает тебя. Твоё тело безжизненно, а сознание растворяется в абсолютной тишине."
                try:
                    _death_result = await run_agent_safe(
                        "dm",
                        self.dm_agent,
                        (location, actions, {}, {}, {}, False, shared_context),
                        {},
                    )
                    if isinstance(_death_result, dict) and _death_result.get(
                        "dm_response"
                    ):
                        _death_dm_response = _death_result["dm_response"]
                except Exception as _dg_err:
                    logger.warning(
                        f"[DEATH_GATE] DM narration failed: {_dg_err}, using fallback"
                    )
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
            if (
                _match
                and self.avatar_service.load_avatar(campaign_id, _player_name) is None
            ):
                self.avatar_service.migrate_from_characters_json(campaign_id, _match)
                _avatar_state = self.avatar_service.load_state(
                    campaign_id, _player_name
                )
            from app.services.game_loop.phase_6_avatar import avatar_to_prompt

            shared_context.player_state = {
                _player_name: avatar_to_prompt(_avatar_state)
            }

            # ТЗ Presentation v2.0: Инициализация BodyTopology игрока
            from app.services.body.body_topology_service import BodyTopologyService

            _sheet_str = getattr(_match, "stats", {}) if _match else {}  # noqa: ENIGMA002
            _str_score = _sheet_str.get("STR", 10) if isinstance(_sheet_str, dict) else 10

            _topo_data = self.scene_manager._persistence.load_scene(campaign_id)
            if not _topo_data or not _topo_data.get("player_body_topology"):
                _topo = BodyTopologyService.create_topology("player", strength_score=_str_score)
                _old_inv = _topo_data.get("player_inventory_snapshot", {}) if _topo_data else {}
                if _old_inv:
                    _start_slot = _topo.hands.get("right_hand")
                    if _start_slot:
                        for item_id, qty in _old_inv.items():
                            for _ in range(qty if isinstance(qty, int) else 1):
                                from app.domain.body import Item
                                BodyTopologyService.add_item(_topo, "backpack_main", Item(item_id=item_id, name=item_id))
                _tmp_scene = self.scene_manager.lock_for_tick(campaign_id, location)
                if _tmp_scene:
                    _tmp_scene["player_body_topology"] = BodyTopologyService.serialize(_topo)
                    self.scene_manager.unlock_tick(campaign_id)
        except Exception as _e:
            logger.warning(f"[AVATAR] ошибка загрузки: {_e}")

        return None

    def _init_pipeline_context(
        self, actions: list, campaign_id: str, world_id: str, location: str
    ) -> tuple[Any, dict]:
        """Инициализирует shared_context и запускает фоновый world tick."""
        # 0. World tick — асинхронный фон, не блокирует ответ игроку
        world_tick_meta = {"triggered": False, "events": []}
        _task = asyncio.create_task(
            asyncio.to_thread(
                self.world_scheduler.maybe_tick,
                world_id,
                settings.world_tick_minutes,
            )
        )
        # H-35 FIX: Предотвращаем GC задачи и логируем исключения
        if not hasattr(self, "_background_tasks"):
            self._background_tasks = set()
        self._background_tasks.add(_task)

        def _on_task_done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if not t.cancelled() and t.exception():
                logger.error(f"[GAME_LOOP] Background task maybe_tick failed: {t.exception()}", exc_info=t.exception())

        _task.add_done_callback(_on_task_done)

        # 1. Базовый shared_context
        _raw_mem = self.memory_manager.read_campaign_history(campaign_id, limit=3)
        if _raw_mem:
            logger.warning(
                f"[RECENT_MEM] {len(_raw_mem)} entries, dm_fields={[bool(e.get('dm')) for e in _raw_mem]}"
            )
        shared_context = build_context(
            campaign_id=campaign_id,
            world_id=world_id,
            location=location,
            player=actions[0].player_name if actions else "",
            scene_state={},
            python_engines={},
            recent_memory=[e["dm"] for e in _raw_mem if e.get("dm")],
            reaction_order=[],
            relationship_store=getattr(self, "_rel_store", None), # Phase 8.2
        )
        return shared_context, world_tick_meta

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
        # N-02 FIX: time.monotonic() для корректного start_ms во время replay.
        start_ms = time.monotonic() * 1000
        _ctx = _TickContext(mvp_controller=self.mvp_controller)

        shared_context, world_tick_meta = self._init_pipeline_context(
            actions, campaign_id, world_id, location
        )

        # 2. Загрузка аватара игрока
        _death_response = await self._load_player_avatar(
            actions, campaign_id, location, shared_context
        )
        if _death_response is not None:
            return _death_response

        scene_state = self._prepare_and_lock_scene(
            campaign_id, location, shared_context, campaign_state, player_position
        )

        self._sync_shared_context_with_scene(scene_state, shared_context)

        dm_result, _resolution = await self._execute_dm_and_intent_resolution(
            actions, shared_context, scene_state, _ctx, campaign_id, location
        )

        try:
            # ADR-091 FIX: Публикация ПОСЛЕ intent_resolution (иначе _semantic_action=None)
            if dm_result.is_valid:
                publish_classified_player_event(
                    shared_context,
                    location,
                    campaign_id,
                    actions[0].action if actions else "",
                )

            # ФАЗА 3-6: NPC оркестрация → TickPlayerResultDTO (Устав §3)
            _player_result: TickPlayerResultDTO = TickPlayerResultDTO()

            logger.debug(
                f"[ARCHAE-PRE-ORCH] dm_valid={dm_result.is_valid} has_scene_ctx={dm_result.scene_context is not None} hub_event={_ctx.hub_event is not None}"
            )
            if dm_result.is_valid and dm_result.scene_context:
                _player_result = run_npc_orchestration(
                    self,
                    actions,
                    shared_context,
                    scene_state,
                    _ctx,
                    campaign_id,
                    location,
                    is_session_start,
                    tick_orchestrator=self._tick_orch,
                )

            python_engines_result = {
                "dm_result": dm_result,
                "npc_contexts": _player_result.npc_contexts,
            }
        except Exception as e:
            logger.error(f"[GAME_LOOP] DM/NPC phase error: {e}", exc_info=True)
            # H-33 FIX: Не маскируем ошибку пустым DTO, пробрасываем исключение (ADR-O-308)
            raise

        rules_result, npc_result = await self._finalize_pipeline_and_build_dm_frame(
            shared_context, _ctx, campaign_id, actions, _player_result
        )

        _state_observed_facts = getattr(_player_result, "observed_facts", [])  # noqa: ENIGMA002
        return _PipelineState(
            shared_context=shared_context,
            classification_results=[],
            world_tick_meta=world_tick_meta,
            rules_result=rules_result,
            npc_result=npc_result,
            python_engines_result=python_engines_result,
            start_ms=start_ms,
            observed_facts=_state_observed_facts,
        )

    # ────────────────────────────────────────────────────────────────────────────
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ────────────────────────────────────────────────────────────────────────────

    def _get_task_scheduler(self):
        """Ленивая инициализация TaskScheduler с инъекцией LLM-провайдера."""
        if not hasattr(self, "_task_scheduler"):
            from app.services.game_loop.task_scheduler import TaskScheduler

            # Инъекция ModelRouter и контекстного колбэка для Эпистемического Барьера
            _router = self.dm_agent.router
            _ctx = self._get_life_engine().get_npc_observed_state
            _et = self._svc.economy_tracker
            _cbs = getattr(self._tick_orch, "crystallized_belief_store", None)  # noqa: ENIGMA002
            if _cbs is None:
                logger.error("TickOrchestrator missing crystallized_belief_store. Check wiring.")
            _cp = getattr(self.mvp_controller, "confession_parser", None) if self.mvp_controller else None  # noqa: ENIGMA001, ENIGMA002
            if _cp is None and self.mvp_controller is not None:
                logger.error("MvpTavernController missing confession_parser. Check wiring.")
            _scheduler = TaskScheduler(router=_router, context_provider=_ctx, economy_tracker=_et, belief_store=_cbs, memory_manager=self.memory_manager, confession_parser=_cp)
            self._task_scheduler = _scheduler
        return self._task_scheduler

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
            AgentTrace(agent="performance", output={"turn_elapsed_ms": elapsed_ms}),
            AgentTrace(agent="world_scheduler", output=state.world_tick_meta),
            AgentTrace(agent="rules", output=state.rules_result),
            AgentTrace(agent="npc", output=state.npc_result),
            AgentTrace(agent="dm", output=dm_result),
            AgentTrace(agent="python_engines", output=state.python_engines_result),
            AgentTrace(agent="game_loop", output={"pipeline_duration_ms": elapsed_ms}),
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
        # ADR-O-146: AdventureLoader удалён. Файлов world_lore/npc.json/locations.json не существует.
        loaded: dict = {"status": "not_found", "files": {}}
        self._campaign_world_index[campaign_id] = world_id

        # Дополнение Б (п. Б.12): Детектор старых сейвов
        try:
            from app.services.state.save_format_detector import detect_legacy_saves
            _legacy_campaigns = detect_legacy_saves(self.saves_dir)
            if campaign_id in _legacy_campaigns:
                logger.warning(f"[SAVE_MIGRATION] Обнаружен сейв старого формата для кампании '{campaign_id}'. Удаление...")
                _old_save_file = self.saves_dir / campaign_id / "campaign_state.json"
                if _old_save_file.exists():
                    _old_save_file.unlink()
        except Exception as _migr_err:
            logger.error(f"[SAVE_MIGRATION] Ошибка при удалении старого сейва: {_migr_err}")
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
                "status": loaded["status"],
            },
        )
        return CampaignLoadResponse(
            campaign_id=campaign_id,
            world_id=world_id,
            status=loaded["status"],
            loaded_files=list(loaded.get("files", {})),
        )

    def session_state(self, campaign_id: str):
        """Возвращает состояние сессии для UI."""
        world_id = self._resolve_world_id(campaign_id)

        class State:
            pass

        state = State()
        state.campaign_id = campaign_id
        state.world_id = world_id
        state.session_log = []
        state.dice_input_required = False

        # S85: Получаем scene_state из SceneStateManager (SSOT), а не из JSON.
        # location_id="" означает, что нас интересует текущая локация без фильтрации.
        scene = self.scene_manager.get_scene_state(campaign_id, location_id="")
        state.scene_state = scene if scene else {}
        state.metadata = {}  # Заглушка, метаданные пока не используются фронтендом

        return state
        state.layers = {"scene_state": scene} if scene else {}

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

    def dispose(self) -> None:
        """Закрывает все ресурсы (SQLite connections, cached services).

        Вызывать при shutdown/teardown. После dispose() GameLoop непригоден.
        Закрывает:
        - SqlitePersistenceAdapter (enigma_runtime.db)
        - SqliteMemoryStore (enigma_memory.db)
        - TickOrchestrator cached SpatialService
        """
        # 1. Persistence adapter (enigma_runtime.db) — через scene_manager
        if hasattr(self, "scene_manager") and self.scene_manager is not None:
            _persistence = getattr(self.scene_manager, "_persistence", None)  # noqa: ENIGMA002
            if _persistence is not None and hasattr(_persistence, "close"):
                _persistence.close()

        # 2. Memory store (enigma_memory.db) — через memory_manager → layered → store
        if hasattr(self, "memory_manager") and self.memory_manager is not None:
            if not hasattr(self.memory_manager, "_layered"):
                raise TypeError("MemoryManager missing _layered attribute. Check wiring.")
            _layered = self.memory_manager._layered
            if not hasattr(_layered, "store"):
                raise TypeError("LayeredMemory missing store attribute. Check wiring.")
            _store = _layered.store
            if hasattr(_store, "close"):
                _store.close()

        # 3. Освобождаем cached spatial service
        if hasattr(self, "_tick_orch") and self._tick_orch is not None:
            self._tick_orch._spatial_service = None

        # 4. Обнуляем NPC loader — предотвращаем stale cache
        self._load_npcs = lambda runtime_path=None: []

        logger.info(
            "[GAME_LOOP] Disposed — all SQLite connections closed, services released"
        )

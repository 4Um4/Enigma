from __future__ import annotations

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
    ERROR_CODES,
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
    start_ms: float = field(default_factory=lambda: time.time() * 1000)
    # Sprint P9: Факты, донесённые до игрока (для UI и DM)
    observed_facts: list = field(default_factory=list)


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

        # Фаза 0.5: DI для idle-сервисов (social decay, reputation decay)
        _rep_engine = self._svc.get_reputation_engine()
        _rel_store = memory_manager._relationships if memory_manager else None
        _state_applicator = (
            self._svc.get_state_applicator(
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

        # TZ-08 Addendum: Time Skip Executor (Observation Layer)
        from app.services.world.time_skip_executor import TimeSkipExecutor
        self._time_skip = TimeSkipExecutor(self._tick_orch)
        self._skip_locks: Dict[str, threading.Lock] = {}  # Real locks per campaign

    def _get_spatial_query_for_subscriber(self):
        """Провайдер SpatialQueryService для NpcDialogueSubscriber (eavesdrop)."""
        # Возвращает текущий spatial_query из TickContext или None
        return getattr(self, "_current_spatial_query", None)

    def _register_npc_dialogue_subscriber(self, memory_manager: Any, rel_store: Any) -> None:
        """Регистрирует NpcDialogueSubscriber на события NPC_SPOKE."""
        try:
            from app.services.events.event_bus import get_event_bus
            from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber

            if not memory_manager or not rel_store:
                logger.warning("[GAME_LOOP] Cannot register NpcDialogueSubscriber — missing memory or relationships")
                return

            _subscriber = NpcDialogueSubscriber(
                memory_manager=memory_manager,
                relationship_store=rel_store,
                npc_states_provider=None,
                campaign_id_provider=lambda: getattr(self, "_current_campaign_id", "Open_road"),
                avatar_service=self.avatar_service,
                spatial_query_provider=self._get_spatial_query_for_subscriber,
                l1_chronicle=self._tick_orch.l1_chronicle,
            )

            from app.services.events.event_types import EventType
            _bus = get_event_bus()
            _bus.subscribe(EventType.NPC_SPOKE, _subscriber.on_npc_spoke)
            self._npc_dialogue_subscriber = _subscriber
            logger.info("[GAME_LOOP] NpcDialogueSubscriber registered for npc_spoke")
        except Exception as e:
            logger.exception(f"[GAME_LOOP] Failed to register NpcDialogueSubscriber: {e}")

    def _get_skip_lock(self, campaign_id: str) -> threading.Lock:
        """Возвращает lock для конкретной кампании, защищающий от параллельных skip/idle."""
        if campaign_id not in self._skip_locks:
            self._skip_locks[campaign_id] = threading.Lock()
        return self._skip_locks[campaign_id]

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

    # ADR-O-146: New Game Reset — сброс runtime мира при сохранении static
    def new_game(self, campaign_id: str) -> dict:
        """Сбрасывает runtime состояние кампании к чистому static.

        Полная очистка: SQLite + JSON + все кэши.
        Переинициализация: сцена из editor JSON + NPC со здоровым body_state.
        Источник чистого мира: config/npc/ + map_editor/campaigns/
        Оставляет: characters.json, character_profiles.json (выбор персонажа)

        Returns: {"reset": True, "campaign_id": str, "files_removed": [str]}
        """
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
                fpath.unlink()
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
        self._load_npcs.cache_clear() if hasattr(
            self._load_npcs, "cache_clear"
        ) else None

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
        print(f"[ARCHAE_PROJECTOR] scene_state={bool(scene_state)} all_npcs_raw={len(all_npcs_raw) if all_npcs_raw else 0}")
        _res = _projector.project(scene_state, all_npcs_raw, _tick)
        print(f"[ARCHAE_PROJECTOR] result={_res}")
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

                    _live_body = getattr(_avatar_state, "body_state", None)
                    if (
                        not _live_body
                    ):  # None или {} — новый аватар без сохранённой физиологии
                        _live_body = dict(BODY_STATE_HEALTHY)
                    _live_psyche = {
                        "stress": getattr(_avatar_state, "stress", 0.0),
                        "fear": getattr(_avatar_state, "fear", 0.0),
                        "willpower": getattr(_avatar_state, "willpower", 1.0),
                        "emotion": getattr(_avatar_state, "emotion", "NEUTRAL"),
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
                        "psyche": _live_psyche,  # Живой разум: stress, fear
                        "social_stats": {
                            "trust": 50.0,
                            "fear_of_player": 0.0,
                            "debt": 0.0,
                        },
                        "status_profile": {"faction_rank": {}},
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

            ensure_scene_initialized(self, campaign_id)

            _scene = self.scene_manager.lock_for_tick(campaign_id, "")
            if _scene is None:
                return {"status": "no_scene", "npc_positions": {}}

            _spatial_svc = None
            _loc_id = _scene.get("location_id", "")
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

            result = self._time_skip.skip(
                campaign_id=campaign_id,
                scene_state=_scene,
                ticks=ticks,
                policy="B",  # Останавливаемся на значимых событиях
                spatial_service=_spatial_svc,
                get_npcs_callback=self._resolve_npcs_light_snapshot,  # Используем лёгкий срез
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
            _ws = _builder.build(
                result.final_state,
                result.final_state.get("tick", 0),
                None,
                _all_npcs,
                recent_dialogues=_recent_d,
            )

            return {
                "status": "ok",
                "stop_reason": result.stop_reason,
                "ticks_skipped": result.ticks_skipped,
                "world_snapshot": _ws,
                "events": result.stops,
            }
        finally:
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

    def idle_tick(self, campaign_id: str) -> dict:
        print(f"[ARCHAE_IDLE_ENTRY] campaign_id={campaign_id}")
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
        from app.services.game_loop.scene_init import ensure_scene_initialized

        ensure_scene_initialized(self, campaign_id)

        # Шаг 2: location_id из campaign_state (S82 canonical source), не из get_scene_state()
        from app.services.campaign_state_service import get_campaign_state_service

        _campaign_svc = get_campaign_state_service()
        _cs = _campaign_svc.get_campaign_state(campaign_id) if _campaign_svc else None
        from app.core.constants import DEFAULT_LOCATION_ID

        _loc_id = (
            _cs.metadata.get("current_location", "") if _cs else ""
        ) or DEFAULT_LOCATION_ID

        # Шаг 3: LOCK — единственный источник truth для этого тика
        _scene = self.scene_manager.lock_for_tick(campaign_id, _loc_id)
        if _scene is None:
            return {"status": "no_scene", "npc_positions": {}}

        # Шаг 4: Монотонный каузальный тик
        _scene["tick"] = _scene.get("tick", 0) + 1

        # S83: Tick Coherence — idle_tick тоже использует Spatial Oracle.
        _loc_id = _scene.get("location_id", "")
        try:
            from app.services.campaign_state_service import get_campaign_state_service

            _campaign_svc = get_campaign_state_service()
            _cs = (
                _campaign_svc.get_campaign_state(campaign_id) if _campaign_svc else None
            )
            if _cs:
                _saved_wx = _cs.metadata.get("player_world_x")
                _saved_wy = _cs.metadata.get("player_world_y")
                # (0,0) — валидная координата. Проверяем is not None (запрет #311).
                if _saved_wx is not None and _saved_wy is not None:
                    from app.services.spatial.spatial_registry import SpatialRegistry

                    _registry = SpatialRegistry.get_or_load(campaign_id)
                    if _registry is not None:
                        _actual_chunks = _registry.find_chunks(_saved_wx, _saved_wy)
                        if _actual_chunks:
                            _oracle_loc = _actual_chunks[0].location_id
                            if _oracle_loc != _loc_id:
                                logger.info(
                                    f"[SPATIAL_ORACLE_IDLE] location_id corrected: "
                                    f"{_loc_id} → {_oracle_loc} "
                                    f"(world=({_saved_wx:.1f}, {_saved_wy:.1f}))"
                                )
                                _loc_id = _oracle_loc
                                _scene["location_id"] = _oracle_loc
        except Exception as e:
            logger.warning(
                f"[SPATIAL_ORACLE_IDLE] Oracle lookup failed, using saved location: {e}"
            )

        # ADR-048: GameLoop собирает SpatialService и инжектит в TickOrchestrator.
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
                logger.warning(f"[SPATIAL_AUTHORITY] SpatialService build failed: {e}")
                self._current_spatial_query = None

        result: TickResultDTO = self._tick_orch.execute(
            campaign_id=campaign_id,
            scene_state=_scene,
            tick_number=_scene["tick"],  # Авторитетный источник тика
            spatial_service=_spatial_svc,  # ИНЪЕКЦИЯ
            shared_context=getattr(
                self, "_idle_shared_context", None
            ),  # S116 FIX: Проброс shared_context для idle tick
        )

        # ADR-TZ08-8: Explicit snapshot step для PerceptionProjector
        # S122 FIX: Берём свежий all_npcs_raw из результата тика, а не из старого кэша.
        _all_npcs_raw = result.all_npcs_raw or self._resolve_npcs_snapshot(campaign_id)
        if result.world_snapshot:
            _perception = self._project_perception(campaign_id, _scene, _all_npcs_raw)
            if _perception:
                import dataclasses

                _new_ws = dataclasses.replace(
                    result.world_snapshot, player_perception=_perception
                )
                result = dataclasses.replace(result, world_snapshot=_new_ws)

        # S83.1 FIX: Ядро больше не вызывает commit_tick_result.
        # Обновляем _tick_scene явно, до materialization и unlock.
        # ВАЖНО: Ядро работает с deepcopy (create_tick_context), поэтому
        # мы должны коммитить result.final_scene_state, а не устаревший _scene.
        _scene_to_commit = result.final_scene_state or _scene
        if self.scene_manager and self.scene_manager._tick_campaign_id == campaign_id:
            try:
                _recog = _scene_to_commit.get("player_recognition", {})
                print(f"[DEBUG_IDLE_COMMIT] campaign={campaign_id} recog_keys={list(_recog.keys())}")
            except Exception as e:
                print(f"[DEBUG_IDLE_COMMIT] error: {e}")
            self.scene_manager.commit_tick_result(campaign_id, _scene_to_commit)

        # ДИАГНОСТИКА: Читаем из authoritative source (scene_manager._tick_scene),
        # а не из устаревшей ссылки _scene (execute работает с deepcopy).
        _auth_scene = self.scene_manager._tick_scene if self.scene_manager else None
        _trav_after = (
            list(_auth_scene.get("active_traversals", {}).keys())
            if _auth_scene
            else list(_scene.get("active_traversals", {}).keys())
        )
        logger.debug(
            f"[IDLE_TRACE] AFTER tick={_scene.get('tick')} traversals={_trav_after} source={'tick_scene' if _auth_scene else 'stale_ref'}"
        )

        # ADR-O-313: Execution Framework. Материализация отложенных задач (LLM и др.)
        # Работает с _auth_scene (_tick_scene), чтобы мутации подписчиков EventBus
        # (напр. SocialInputProjector) попали в финальный unlock_tick.
        if _auth_scene and _auth_scene.get("pending_tasks"):
            self._get_task_scheduler().execute_pending(_auth_scene, campaign_id)

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
                _ws["recent_dialogues"] = _recent_d
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
        print(f"[ARCHAE_PLAYER_ENTRY] req={req}")
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
            "observed_facts": getattr(state, "observed_facts", []),
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
                from app.main import _restart_llama_server

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
            except ImportError:
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

            _anr_rce = getattr(state.shared_context, "all_npcs_raw_snapshot", None)
            # Fallback: загружаем NPC из рантайма, если snapshot пуст
            if not _anr_rce:
                try:
                    _anr_rce = self._load_npcs_with_runtime(req.campaign_id)
                except Exception:
                    _anr_rce = []
            _target_id = getattr(state.shared_context, "player_target_id", None)
            _player_name = req.actions[0].player_name if req.actions else None
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

        # TODO: _write_memory удалён — persist_dm_response на строке ниже покрывает запись
        elapsed_ms = int(time.time() * 1000 - state.start_ms)
        traces = self._build_traces(state, dm_result, elapsed_ms)

        # NEW-8 FIX: Устанавливаем player_recognition ДО commit_tick_result,
        # чтобы deepcopy внутри commit_tick_result захватил confidence=1.0.
        _target_id = getattr(state.shared_context, "player_target_id", None) if state.shared_context else None
        if _target_id and hasattr(state, "shared_context") and state.shared_context and state.shared_context.scene_state:
            _recog_map = state.shared_context.scene_state.setdefault("player_recognition", {})
            _recog_entry = _recog_map.setdefault(_target_id, {"confidence": 0.0})
            _recog_entry["confidence"] = 1.0
            logger.info(f"[RECOG_MEMORY] Dialogue trigger (Pre-Commit): NPC {_target_id} confidence=1.0")

        # S128 FIX: Обязательный commit_tick_result после _run_pipeline.
        # Без этого unlock_tick сохраняет старый _tick_scene, затирая мутации ядра (player_recognition).
        if hasattr(state, "shared_context") and state.shared_context and state.shared_context.scene_state:
            self.scene_manager.commit_tick_result(req.campaign_id, state.shared_context.scene_state)

        # TASK 1: Force Merge — строим world_snapshot из актуального scene_state (ADR-0014)
        _ws_dict = None
        _npc_pos_dict = None
        # ADR-TZ09-2: Используем _tick_scene (обновлённое ядром), а не устаревший shared_context.scene_state
        _scene = self.scene_manager._tick_scene if self.scene_manager else None
        if _scene is None and hasattr(state, "shared_context") and state.shared_context:
            _scene = state.shared_context.scene_state
        if _scene:
            from dataclasses import asdict

            from app.services.integration.world_snapshot_builder import (
                WorldSnapshotBuilder,
            )

            _builder = WorldSnapshotBuilder()
            # ADR-092: Проброс perception из TickOrchestrator для action tick
            _pp = (
                getattr(state.shared_context, "player_perception", None)
                if state.shared_context
                else None
            )
            _anr = (
                getattr(state.shared_context, "all_npcs_raw_snapshot", None)
                if state.shared_context
                else None
            )
            logger.debug(
                f"[TRAV_CHECK_P2] before_snapshot: id(scene_state)={id(_scene)} active_traversals={list(_scene.get('active_traversals', {}).keys())}"
            )
            _recent_d = self._get_task_scheduler().get_recent_dialogues(_scene.get("game_time_seconds", 0.0))
            if _ws := _builder.build(
                _scene,
                tick=self.get_current_tick(req.campaign_id),
                player_perception=_pp,
                all_npcs_raw=_anr,
                recent_dialogues=_recent_d,
            ):
                _ws_dict = asdict(_ws)
                # A2-FIX: npc_positions уже Dict[str, NPCPositionDTO] (canonical). Адаптер удалён.
                _npc_pos_dict = _ws_dict.get("npc_positions")

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

        _resp_facts = getattr(state, "observed_facts", [])
        logger.debug(f"[DEBUG_RUN_TURN] state.observed_facts count={len(_resp_facts)}")
        _final_response = ChatTurnResponse(
            dm_response=dm_result.get("dm_response", ""),
            npc_reactions=dm_result.get("npc_reactions", []),
            world_changes=dm_result.get("world_changes", []),
            world_snapshot=_ws_dict,
            npc_positions=_npc_pos_dict,
            # ADR-075: Строгий проброс Эмбодимента.
            will_conflict_data=state.shared_context.will_conflict_data
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

        yield {
            "type": "done",
            "tokens": token_count,
            "ms": elapsed_ms,
            "tps": tps,
            "game_time_seconds": state.shared_context.game_time_seconds or 0,
            # ADR-075: Проброс Эмбодимента через SSE. Фронтенд собирает GameActionResponse из этого словаря.
            "will_conflict_data": state.shared_context.will_conflict_data
            if state.shared_context
            else None,
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
        asyncio.create_task(
            asyncio.to_thread(
                self.world_scheduler.maybe_tick,
                world_id,
                settings.world_tick_minutes,
            )
        )

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
        )

        # 2. Загрузка аватара игрока
        _player_name = actions[0].player_name if actions else ""
        try:
            _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)

            # P0: ACTION ELIGIBILITY GATE — мёртвый игрок не может действовать (ADR-127, Rule 59)
            # Проверка ДО lock_for_tick, чтобы не загрязнять scene_state пост-смертной активностью
            _player_life = (
                _avatar_state.body_state.get("life_status", "ALIVE")
                if _avatar_state and _avatar_state.body_state
                else "ALIVE"
            )
            if _player_life == "DEAD":
                logger.warning(
                    f"[DEATH_GATE] Player '{_player_name}' is DEAD. DM narrates death."
                )
                # P3: Проброс death state в DM-контракт (DM читает life_status, не вычисляет)
                from app.services.game_loop.phase_6_avatar import avatar_to_prompt

                shared_context.player_state = {
                    _player_name: avatar_to_prompt(_avatar_state)
                }
                # S75: Проброс death feedback — мир продолжает жить, игрок теряет агентность
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
                # Мир продолжает жить: пробрасываем текущие NPC позиции из кэша
                # idle_tick обновит их дальше, но этот snapshot не даёт миру «замёрзнуть»
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
                    logger.warning(
                        f"[B5-FIX] silent failure suppressed: {e}"
                    )  # Мир без позиций лучше, чем краш Death Guard
                # P3: DM narrates смерть (LLM-интерпретация замороженной реальности, не хардкод)
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
        except Exception as _e:
            logger.warning(f"[AVATAR] ошибка загрузки: {_e}")

        # ADR-SCENE-LOCK: Блокируем scene_state на время тика.
        # Все get_scene_state() внутри тика вернут ТОТ ЖЕ объект.
        # Без этого каждый вызов создаёт новый dict из persistence → traversals теряются.
        scene_state = self.scene_manager.lock_for_tick(campaign_id, location)
        if scene_state is None:
            scene_state = init_scene_state(
                self,
                campaign_id,
                location,
                shared_context,
                campaign_state,
                player_position=player_position,
            )
            self.scene_manager._tick_scene = scene_state
            self.scene_manager._tick_locked = True
            self.scene_manager._tick_campaign_id = campaign_id
        else:
            # Обновляем player position + sync time на закэшированном объекте
            from app.services.game_loop.scene_init import (
                _sync_game_time,
                _update_player_position,
            )

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
        if hasattr(shared_context, "current_tick"):
            shared_context.current_tick = scene_state["tick"]

        # ФАЗА 1-3: DM классификация + EventBus + STM + время
        _match = None  # Инициализация во избежание UnboundLocalError
        try:
            dm_result = run_dm_phase(
                self,
                actions,
                shared_context,
                scene_state,
                _ctx,
                campaign_id,
                location,
            )
            logger.warning(
                f"[DEBUG DM] is_valid={dm_result.is_valid}, scene_context={dm_result.scene_context}, error={dm_result.error}"
            )

            # ФАЗА 1: Semantic Translation (ADR-031 Fix).
            # game_loop не вычисляет волю и не публикует события. Только Intent → Pressure.
            _player_data_dict = _match.dict() if _match else None

            # S118 FIX: LLM Slow-Path вызывается ЗДЕСЬ (в оркестраторе), а не в ядре (§7.20, ADR-O-313)
            _raw_action = actions[0].action if actions else ""
            _semantic_field = await self._intent_compressor.compress(
                raw_text=_raw_action, scene_context=scene_state
            )

            _resolution = resolve_player_intent(
                raw_action=_raw_action,
                action_type=shared_context.action_type or "player_interacts",
                target=shared_context.player_target_id or "",
                player_dict=_player_data_dict,
                scene_context=scene_state,  # Слой 2 ищет имена в scene_state["npc_positions"]
                semantic_field=_semantic_field,  # Передача готового поля из оркестратора
            )

            # Передаем давление в контекст для TickOrchestrator (Causal Resolution)
            shared_context.intent_resolution = _resolution

            # FIX: Проброс semantic_action в hub_event.payload ПОСЛЕ intent_resolution,
            # но ДО run_npc_orchestration (где DecisionHub читает hub_event).
            # Без этого DecisionHub не видит MOVE и obedience boost не работает.
            if _ctx.hub_event and _resolution and _resolution.original_intent:
                _params = _resolution.original_intent.parameters
                logger.debug(
                    f"[ARCHAE-PAYLOAD] params={_params} sa={getattr(_params, 'semantic_action', 'NO_SA') if _params else 'NO_PARAMS'}"
                )
                if _params:
                    _sa = getattr(_params, "semantic_action", None)
                    _tid = getattr(_params, "target_id", None)
                    _tref = getattr(_params, "target_reference", None)
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

            # ADR-091 FIX: Публикация ПОСЛЕ intent_resolution (иначе _semantic_action=None)
            # Раньше вызывался в run_dm_phase ДО resolve_player_intent → override не работал
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
            python_engines_result = {"dm_result": None, "npc_contexts": []}
            _player_result = TickPlayerResultDTO()

        shared_context.python_engines = python_engines_result
        # Sprint P9: Проброс observed_facts из тика в state
        _state_observed_facts = getattr(_player_result, "observed_facts", [])
        logger.debug(
            f"[DEBUG_GAME_LOOP] _state_observed_facts count={len(_state_observed_facts)}"
        )

        # ФАЗА 7: RulesSubscriber (pure reducer) — вычисляет D&D механику (TZ-08 v0.2)
        from app.services.events.event_types import EventType
        from app.services.events.rules_subscriber import RulesSubscriber

        _action_type = shared_context.action_type or "player_interacts"
        _rules_action_type = self.dm_orchestrator._router.get_rules_action_type(
            _action_type
        )

        # Формируем event для подписчика
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

        # Формируем snapshot для подписчика
        _rules_snapshot = {
            "all_npcs_raw": _ctx.all_npcs_raw or [],
            "tick_number": shared_context.current_tick or 0,
            "campaign_id": campaign_id,
            "relationship_store": self.memory_manager._relationships
            if self.memory_manager
            else None,
            "raw_input": actions[0].action if actions else "",
        }

        _rules_sub = RulesSubscriber()
        _rules_delta = _rules_sub.handle(_rules_event, _rules_snapshot)

        # Преобразуем RulesDelta в формат, ожидаемый DM-агентом
        rules_result = {"checks": _rules_delta.checks} if _rules_delta else {}
        logger.warning(
            f"[RULES] action_type={_action_type} → {_rules_action_type} (synchronous reducer)"
        )

        # ADR-O-112: Actor-Agnostic Physiology. Инжектируем Аватар в all_npcs_raw для трубы урона.
        _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)

        # S115 FIX: Сохраняем копию состояния ДО мутаций, чтобы корректно сравнить в конце.
        import copy

        _avatar_state_before = copy.deepcopy(_avatar_state) if _avatar_state else None

        # БАГ 5 FIX: Применяем money_delta от RulesSubscriber к аватару.
        # Раньше RulesSubscriber мутировал временный снапшот, который перезатирался load_state.
        if _rules_delta and _rules_delta.money_delta != 0.0 and _avatar_state:
            if not _avatar_state.body_state:
                _avatar_state.body_state = {}
            _current_money = float(_avatar_state.body_state.get("money", 0.0))
            _avatar_state.body_state["money"] = max(
                0.0, _current_money + _rules_delta.money_delta
            )
            logger.info(
                f"[TRADE_FIX] Applied money_delta={_rules_delta.money_delta} to avatar. New total: {_avatar_state.body_state['money']}"
            )

        from dataclasses import asdict, is_dataclass

        if is_dataclass(_avatar_state):
            _avatar_dict = asdict(_avatar_state)
            _avatar_dict["npc_id"] = "player"
            _avatar_dict["id"] = (
                "player"  # ADR-O-112: load_profile_from_legacy_json требует "id"
            )
            if hasattr(_ctx, "all_npcs_raw") and _ctx.all_npcs_raw is not None:
                _ctx.all_npcs_raw = [
                    n for n in _ctx.all_npcs_raw if n.get("npc_id") != "player"
                ]
                _ctx.all_npcs_raw.append(_avatar_dict)

        # ФАЗЫ 8-10: Ядро (execute) уже выполнило все фазы симуляции и сформировало perception_snapshot.
        # Здесь game_loop только строит нарративную проекцию (dm_frame) для DM-агента.
        # SHI-FIX: shared_context.npc_contexts должен быть заполнен ДО build_r3_dm_frame,
        # иначе R3_DIRECT видит 0 decisions (старый/пустой список).
        shared_context.npc_contexts = getattr(_player_result, "npc_contexts", []) or []
        try:
            from app.services.scene.r3_direct_builder import build_r3_dm_frame

            npc_result = (
                build_r3_dm_frame(shared_context, actions, rules_result)
                if R3_DIRECT_MODE
                else {}
            )

            # SCENE_IDENTITY: проверяем, что scene_state не потерял traversals после finalize
            logger.debug(
                f"[TRAV_CHECK_P1_5] after_finalize_return: id={id(shared_context.scene_state)} traversals={list(shared_context.scene_state.get('active_traversals', {}).keys())}"
            )

            # S115 FIX: Синхронизация мутаций из ядра обратно в _avatar_state.
            # Ядро работает со словарем в _ctx.all_npcs_raw, нам нужно перенести изменения в объект.
            _updated_avatar_dict = next(
                (
                    n
                    for n in getattr(_ctx, "all_npcs_raw", [])
                    if n.get("npc_id") == "player"
                ),
                None,
            )
            if _updated_avatar_dict and _avatar_state:
                if "body_state" in _updated_avatar_dict:
                    _avatar_state.body_state = _updated_avatar_dict["body_state"]
                if "hp" in _updated_avatar_dict:
                    # ADR-HP-UNIFICATION: Пишем напрямую в body_state (SSOT)
                    if _avatar_state.body_state:
                        _avatar_state.body_state["current_hp"] = (
                            _updated_avatar_dict.get(
                                "hp", _updated_avatar_dict.get("current_hp", 0)
                            )
                        )
                    else:
                        # BUG-AUDIT-01 (HP Double Truth): Инициализируем BODY_STATE_DISABLED_DATA 
                        # при пустом body_state, чтобы не потерять pain/shock/fatigue.
                        from app.models.npc_state import BODY_STATE_DISABLED_DATA
                        _avatar_state.body_state = dict(BODY_STATE_DISABLED_DATA)
                        _avatar_state.body_state["current_hp"] = _updated_avatar_dict["hp"]

            # S115 FIX: Сравниваем полное состояние до и после. Если есть разница — сохраняем.
            if (
                _avatar_state
                and _avatar_state_before
                and _avatar_state != _avatar_state_before
            ):
                self.avatar_service.save_state(campaign_id, _avatar_state)
                logger.warning(
                    f"[AVATAR] STATE APPLIED: pain={_avatar_state.body_state.get('pain', 0.0):.1f} shock={_avatar_state.body_state.get('shock_impulse', 0.0):.2f} money={_avatar_state.body_state.get('money', 0.0):.1f} hp={_avatar_state.effective_hp}"
                )

            # S115 FIX: Обновляем кэш LifeEngine с мутированным all_npcs_raw.
            # Без этого _resolve_npcs_snapshot возвращает старые данные (без денег/урона).
            _engine = self._get_life_engine()
            if (
                _engine
                and hasattr(_ctx, "all_npcs_raw")
                and _ctx.all_npcs_raw is not None
            ):
                _engine.update_cache(campaign_id, _ctx.all_npcs_raw)

        except Exception as _fin_err:
            logger.error(f"[GAME_LOOP] Finalize error: {_fin_err}", exc_info=True)
            npc_result = {}
            # Защита: _player_result может быть None
            shared_context.npc_contexts = (
                getattr(_player_result, "npc_contexts", []) or []
            )

        # Avatar update — после perception (shared_context.npc_contexts отфильтрован)
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
            _cbs = getattr(self._tick_orch, "crystallized_belief_store", None)
            _scheduler = TaskScheduler(router=_router, context_provider=_ctx, economy_tracker=_et, belief_store=_cbs)
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
            _persistence = getattr(self.scene_manager, "_persistence", None)
            if _persistence is not None and hasattr(_persistence, "close"):
                _persistence.close()

        # 2. Memory store (enigma_memory.db) — через memory_manager → layered → store
        if hasattr(self, "memory_manager") and self.memory_manager is not None:
            _layered = getattr(self.memory_manager, "_layered", None)
            if _layered is not None:
                _store = getattr(_layered, "store", None)
                if _store is not None and hasattr(_store, "close"):
                    _store.close()

        # 3. Освобождаем cached spatial service
        if hasattr(self, "_tick_orch") and self._tick_orch is not None:
            self._tick_orch._spatial_service = None

        # 4. Обнуляем NPC loader — предотвращаем stale cache
        self._load_npcs = lambda runtime_path=None: []

        logger.info(
            "[GAME_LOOP] Disposed — all SQLite connections closed, services released"
        )

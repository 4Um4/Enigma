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
from app.services.events.event_types import GameEvent, EventType
from app.services.events.event_bus import get_event_bus
from app.services.action.player_target_extractor import PlayerTargetExtractor

# ─────────────────────────────────────────────────────────────────────────────
# R3 DIRECT MODE: DM как единственный источник речи
# True = DecisionResult → SceneOutcome → DMFrame → DM (1 LLM вызов)
# False = legacy путь (удалён: npc_agent)
# ─────────────────────────────────────────────────────────────────────────────
R3_DIRECT_MODE: bool = True
from app.services.state.context_builder import build_context, patch_scene_state
from app.services.scene_state_manager import SceneStateManager
from app.services.memory import LayeredMemory
# Старый model_router удалён — агенты сами управляют маршрутизацией через llm/router
from app.services.world_scheduler import WorldScheduler
from app.services.npc.npc_loader import materialize_inventory, get_item_display_name
from app.services.character_service import CharacterService
from app.services.verbalization.scene_continuity import SceneContinuity
from app.services.npc.life_engine import get_life_engine
from app.services.vram_monitor import get_vram_monitor
from app.services.error_interpreter import get_error_interpreter
from app.services.logging_tools import jsonl_log
from app.core.config import settings
from app.services.adventure_loader import AdventureLoader
from app.services.system_requirements import SystemRequirements
from app.models.schemas import CampaignLoadResponse

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SEC = 35

ERROR_CODES = {
    "AGENT_SUCCESS":              "SUCCESS",
    "AGENT_TIMEOUT":              "TIMEOUT",
    "AGENT_MODEL_FAIL":           "MODEL_FAIL",
    "ORCHESTRATOR_PIPELINE_FAIL": "PIPELINE_FAIL",
}


# ────────────────────────────────────────────────────────────────────────────────
# Внутренний результат пайплайна (до DM-нарратива)
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class _PipelineState:
    """Всё что нужно знать агентам после Python-этапа."""
    shared_context:        Dict[str, Any]
    classification_results: List[Dict[str, Any]]
    world_tick_meta:       Dict[str, Any]
    rules_result:          Dict[str, Any]  = field(default_factory=dict)
    npc_result:            Dict[str, Any]  = field(default_factory=dict)
    python_engines_result: Dict[str, Any]  = field(default_factory=dict)
    start_ms:              float           = field(default_factory=lambda: time.time() * 1000)


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
        layered_memory: LayeredMemory,
        memory_manager,          # MemoryManager — подключён к DecisionHub и identity_cache
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
        self.layered_memory   = layered_memory
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
        self._social_engine = None
        self._social_tick: int = 0
        # ФАЗА 3.1: Spatial Events — предыдущие расстояния для детекции переходов
        self._prev_player_distances: Dict[str, Dict[str, float]] = {}
        # ФАЗА 2.4-ECO: Economic profiles — кэш по campaign_id
        self._economic_profiles: Dict[str, Dict[str, 'EconomicProfile']] = {}
        # ФАЗА 2.4-ECO: EconomyTracker — трекинг доходов и дневных проверок
        from app.services.economy.economy_tracker import EconomyTracker
        self._economy_tracker = EconomyTracker()
        # ФАЗА 3.4: WorldTickEngine — проактивные действия NPC
        from app.services.world.world_tick_engine import WorldTickEngine
        self._world_tick_engine = WorldTickEngine()
        # ФАЗА 3.5: ReputationEngine — ленивая инициализация
        self._reputation_engine = None
        # Удалён дубль: self._data_dir = data_dir — заменён на self._saves_dir

    def _get_social_engine(self, campaign_id: str):
        """Ленивая инициализация SocialEngine из config/npc/social/."""
        if self._social_engine is not None:
            return self._social_engine
        try:
            from app.services.npc.npc_loader import load_social_base
            from app.services.social.social_engine import SocialEngine

            _config = load_social_base()
            if not _config.get("relations"):
                logger.info("[SOCIAL] No relations in config, engine disabled")
                return None

            # name_map для continuity_note (npc_id → имя)
            _all_npcs = self._load_npcs()
            _name_map = {
                n.get("id", ""): n.get("name", "")
                for n in _all_npcs if n.get("id")
            }
            self._social_engine = SocialEngine.from_config(_config, name_map=_name_map)
            logger.info(
                "[SOCIAL] Engine initialized (%d NPCs in graph)",
                len(self._social_engine.get_all_npc_ids()),
            )
            return self._social_engine
        except Exception as e:
            logger.warning(f"[SOCIAL] Init failed: {e}")
            return None

    def _get_economic_profile(self, npc_id: str) -> Optional['EconomicProfile']:
        """
        Возвращает EconomicProfile для NPC.
        Сначала ищет в кэше, затем загружает из persistence, затем создаёт дефолтный.
        """
        from app.models.economy import EconomicProfile
        
        # Пытаем найти в кэше
        for campaign_profiles in self._economic_profiles.values():
            if npc_id in campaign_profiles:
                return campaign_profiles[npc_id]
        
        # Не найдено — возвращаем None (пока без persistence, NPC без экономики)
        # При необходимости: загрузить из saves/session/{id}/economic_profiles.json
        return None

    def _get_reputation_engine(self) -> Optional[Any]:
        """Ленивая инициализация ReputationEngine из config/world/factions.json."""
        if self._reputation_engine is not None:
            return self._reputation_engine
        try:
            from app.services.social.reputation_engine import ReputationEngine
            _config_path = self.data_dir / "config" / "world" / "factions.json"
            # Fallback: ищем в корне проекта
            if not _config_path.exists():
                from pathlib import Path as _Path
                _config_path = _Path("config/world/factions.json")
            if not _config_path.exists():
                logger.info("[REPUTATION] factions.json not found, engine disabled")
                return None
            self._reputation_engine = ReputationEngine(config_path=str(_config_path))
            logger.info("[REPUTATION] Engine initialized")
            return self._reputation_engine
        except Exception as e:
            logger.warning(f"[REPUTATION] Init failed: {e}")
            return None

    def _get_or_create_economic_profiles(self, campaign_id: str) -> Dict[str, 'EconomicProfile']:
        """
        Ленивая инициализация экономических профилей для кампании.
        Создаёт дефолтные профили для всех NPC из config.
        """
        if campaign_id in self._economic_profiles:
            return self._economic_profiles[campaign_id]
        
        from app.models.economy import EconomicProfile, Need, NeedType
        
        _profiles: Dict[str, EconomicProfile] = {}
        _all_npcs = self._load_npcs()
        
        from app.services.economy.profile_factory import create_profile_from_npc
        from app.services.world.world_ontology import is_physical_object

        for _npc in _all_npcs:
            _nid = _npc.get("id")
            if not _nid:
                continue
            
            # Товары из carried_objects (физические предметы)
            _goods = {}
            for _item in _npc.get("carried_objects", []):
                if is_physical_object(_item):
                    _goods[_item] = 1
            
            _profiles[_nid] = create_profile_from_npc(
                npc_data=_npc,
                goods=_goods,
            )
        
        self._economic_profiles[campaign_id] = _profiles
        logger.info(f"[ECO] Initialized {len(_profiles)} economic profiles for {campaign_id}")
        return _profiles

    def _collect_base_drives(self, campaign_id: str) -> Dict[str, Dict[str, float]]:
        """
        Извлекает базовые драйвы (control, desire, fear, significance) из всех NPC.
        Нужны для EconomyTracker: расчёт savings_tendency без динамического _psycho.
        """
        from app.services.npc.npc_loader import load_profile_from_legacy_json
        
        _all_npcs = self._load_npcs()
        _drives: Dict[str, Dict[str, float]] = {}
        
        for _npc in _all_npcs:
            _nid = _npc.get("id")
            if not _nid:
                continue
            try:
                _l0 = load_profile_from_legacy_json(_npc)
                _drives[_nid] = _l0.drives_base
            except Exception:
                _drives[_nid] = {"control": 0.25, "desire": 0.25, "fear": 0.25, "significance": 0.25}
        
        return _drives

    # ────────────────────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ────────────────────────────────────────────────────────────────────────────

    def reset_session_flag(self, campaign_id: str) -> None:
        """Сбрасывает флаг начала сессии — следующий ход будет session_start.
        Вызывается при SESSION_REPLACED чтобы сбросить стресс NPC из прошлой сессии.
        """
        self._session_started_campaigns.discard(campaign_id)

    def ensure_scene_initialized(self, campaign_id: str) -> dict:
        """Гарантирует что scene_state существует и содержит стены из editor JSON.
        Если сцена есть но стены пустые — только добавляет стены, не трогает NPC и location_id.
        """
        from app.services.campaign_state_service import get_campaign_state_service
        import json
        campaign_state = get_campaign_state_service().get_campaign_state(campaign_id)
        
        # Определяем текущую локацию из сохранения
        location = "tavern_silver_wolf"  # fallback
        try:
            existing = self.scene_manager._read_campaign_json(campaign_id)
            loc_id = existing.get("scene_state", existing).get("location_id")
            if loc_id:
                location = loc_id
        except Exception as e:
            print(f"[GAME_LOOP] Ошибка получения location_id: {e}")
        
        scene_state = self.scene_manager.get_scene_state(campaign_id, location)
        
        # Сцена не существует — полная инициализация
        if scene_state is None:
            time_of_day = campaign_state.metadata.get("time_of_day", "12:00") if campaign_state else "12:00"
            return self.scene_manager.initialize_scene(campaign_id, location, time_of_day)
        
        # Сцена есть — проверяем стены
        if scene_state.get("spatial_walls"):
            return scene_state
        
        # Стены пустые — добавляем из editor JSON без переинициализации
        editor_data = self.scene_manager._find_editor_location(campaign_id, location)
        if editor_data is None:
            editor_data = self.scene_manager._find_first_editor_location(campaign_id)
        
        if editor_data:
            walls = []
            for wall in editor_data.get("walls", []):
                walls.append({"x1": wall["x1"], "y1": wall["y1"], "x2": wall["x2"], "y2": wall["y2"]})
            # Объекты из editor
            for i, obj in enumerate(editor_data.get("objects", [])):
                obj_id = obj.get("id", f"obj_{i}")
                if obj_id not in scene_state.get("objects", {}):
                    scene_state.setdefault("objects", {})[obj_id] = {
                        "name": obj.get("name", obj.get("type", "объект")),
                        "type": obj.get("type", ""),
                        "state": obj.get("properties", {}).get("open", True) and "intact" or "closed",
                        "position": obj.get("position", {}),
                        "size": obj.get("size", {}),
                        "interactable": True,
                    }
            if walls:
                scene_state["spatial_walls"] = walls
                self.scene_manager.save_scene_state(campaign_id, scene_state)
        
        return scene_state

    def _get_npc_runtime_path(self, campaign_id: str) -> Path:
        """Возвращает путь к npc_runtime.json для кампании."""
        return self._saves_dir / campaign_id / "npc_runtime.json"

    def _avatar_to_prompt(self, state) -> dict:
        """Формирует краткое описание состояния аватара для DM промпта."""
        wounds_str = "нет"
        if state.wounds:
            wounds_str = ", ".join(
                f"{w.body_part}({w.severity if isinstance(w.severity, str) else w.severity.value})"
                for w in state.wounds
            )
        conds_str = "нет"
        if state.conditions:
            conds_str = ", ".join(
                f"{k}({v.severity:.0%})" for k, v in state.conditions.items()
            )
        return {
            "hp": f"{state.hp}/{state.max_hp}" if state.max_hp > 0 else "не задано",
            "stress": round(state.stress, 1),
            "emotion": state.emotion.value if hasattr(state.emotion, "value") else str(state.emotion),
            "will_state": state.will_state.value if hasattr(state.will_state, "value") else str(state.will_state),
            "posture": state.posture,
            "wounds": wounds_str,
            "conditions": conds_str,
            "identity_integrity": round(state.identity_integrity, 2),
        }

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

        dm_result = await self._run_agent_safe(
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
        print(f"[DM_RESULT] type={type(dm_result).__name__}, keys={list(dm_result.keys()) if isinstance(dm_result, dict) else 'N/A'}, dm_resp={repr(dm_result.get('dm_response', '<NO KEY>')[:200]) if isinstance(dm_result, dict) else repr(dm_result)[:200]}")

        # R2.1: NarrativeExtractor R2.2.8 — синхронный путь (REST)
        try:
            from app.services.scene.narrative_extractor import get_extractor
            dm_text     = dm_result.get("dm_response", "")
            scene_state = state.shared_context.get("scene_state", {})
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
            print(f"[R2.1] NarrativeExtractor REST error: {e}")

        self._write_memory(
            req, state, dm_result,
            state.python_engines_result,
        )

        elapsed_ms = int(time.time() * 1000 - state.start_ms)
        traces = self._build_traces(state, dm_result, elapsed_ms)

        return ChatTurnResponse(
            dm_response=dm_result.get("dm_response", ""),
            npc_reactions=dm_result.get("npc_reactions", []),
            world_changes=dm_result.get("world_changes", []),
            journal_entry_id=self.layered_memory.write_campaign_memory(
                req.campaign_id,
                {
                    "world_id": req.world_id,
                    "location": req.location,
                    "actions":  [a.model_dump() for a in req.actions],
                    "dm":       dm_result.get("dm_response", ""),
                },
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
        print(f"[SESSION_CHECK] campaign={campaign_id} known={self._session_started_campaigns} is_new={is_session_start}")
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
        async for event in self._yield_model_info(state):
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
            self.layered_memory.write_campaign_memory(
                campaign_id,
                {
                    "world_id": world_id,
                    "location": location,
                    "actions":  [a.model_dump() for a in actions],
                    "dm":       dm_full_text_for_mem,
                },
            )
            # Лог вопроса + ответа для отладки
            _player_msg = next((a.action for a in actions if a.action), "")
            _preview_q = _player_msg[:80] + "..." if len(_player_msg) > 80 else _player_msg
            _preview_a = dm_full_text_for_mem[:120] + "..." if len(dm_full_text_for_mem) > 120 else dm_full_text_for_mem
            print(f"[DM] {_preview_q}")
            print(f"[NPC] {_preview_a}")

        yield {
            "type": "done",
            "tokens": token_count,
            "ms": elapsed_ms,
            "tps": tps,
            "game_time_seconds": state.shared_context.get("game_time_seconds", 0),
        }

        # R2.1: NarrativeExtractor R2.2.8
        try:
            from app.services.scene.narrative_extractor import get_extractor
            dm_full_text = "".join(dm_text_parts)
            scene_state  = state.shared_context.get("scene_state", {})
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
                    print(
                        f"[R2.1] objects={len(extraction.new_objects)} "
                        f"events={len(extraction.new_events)} "
                        f"state_updates={len(extraction.updated_states)}"
                    )
        except Exception as e:
            print(f"[R2.1] NarrativeExtractor error: {e}")

    def _advance_game_time(
        self,
        scene_state: dict,
        action_type: str,
        raw_input: str,
        shared_context: dict | None = None,
    ) -> None:
        """
        Фаза 4 — время продвигается от действий, не от тиков.
        Обновляет total_seconds в shared_context и time_of_day в scene_state.
        """
        from app.core.constants import (
            TIME_DIALOG_BASE,
            TIME_DIALOG_PER_CHAR,
            TIME_DIALOG_MAX,
            TIME_DELTA_WALK_INDOOR,
            TIME_DELTA_TELEGRAPH,
        )
        from app.core.calendar import Calendar
        import re

        # Время диалога: базовое + длина ввода игрока (скорость речи NPC ~10 симв/с)
        if action_type in ("dialogue", "player_interacts"):
            _input_len = len(raw_input) if raw_input else 0
            _delta_seconds = min(TIME_DIALOG_BASE + int(_input_len * TIME_DIALOG_PER_CHAR), TIME_DIALOG_MAX)
        elif action_type in ("move", "stealth", "player_moves"):
            _location = scene_state.get("location_id", "")
            if "tavern" in _location.lower() or "inn" in _location.lower():
                _delta_seconds = TIME_DELTA_WALK_INDOOR
            else:
                _delta_seconds = TIME_DELTA_WALK_INDOOR * 3
        elif "TELEGRAPH" in raw_input:
            _delta_seconds = TIME_DELTA_TELEGRAPH
        else:
            _delta_seconds = 0

        # Явные запросы времени в тексте игрока
        _wait_match = re.search(r"жд[уаю]\s+(\d+)\s+(час|минут|секунд)", raw_input, re.I)
        if _wait_match:
            _amount = int(_wait_match.group(1))
            _unit = _wait_match.group(2)
            if "час" in _unit:
                _delta_seconds = _amount * 3600
            elif "минут" in _unit:
                _delta_seconds = _amount * 60
            else:
                _delta_seconds = _amount

        if _delta_seconds == 0:
            return

        # Текущее время из shared_context (новый путь) или из строки (legacy)
        if shared_context and "game_time_seconds" in shared_context:
            _current_total = shared_context["game_time_seconds"]
        else:
            _env_time = scene_state.get("environment", {}).get("time_of_day", "07:00")
            _seconds_in_day = Calendar.parse_hhmm(_env_time)
            _current_total = _seconds_in_day  # legacy: без дня/года

        _new_total = Calendar.advance(_current_total, _delta_seconds)

        # Обновляем shared_context
        if shared_context is not None:
            shared_context["game_time_seconds"] = _new_total

        # Обновляем time_of_day в scene_state для совместимости
        # (scene_state_manager._select_time_variant читает строку)
        _old_hhmm = Calendar.format_time(_current_total)
        _new_hhmm = Calendar.format_time(_new_total)
        scene_state.setdefault("environment", {})["time_of_day"] = _new_hhmm

        if _delta_seconds >= 60:
            print(f"[TIME_ADVANCE] {_old_hhmm} → {_new_hhmm} (+{_delta_seconds // 60} мин)")

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
        _raw_mem = self.layered_memory.read_campaign_memory(campaign_id, limit=3)
        if _raw_mem:
            print(f"[RECENT_MEM] {len(_raw_mem)} entries, dm_fields={[bool(e.get('dm')) for e in _raw_mem]}")
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
            shared_context["player_state"] = {
                _player_name: self._avatar_to_prompt(_avatar_state)
            }
        except Exception as _e:
            print(f"[AVATAR] ошибка загрузки: {_e}")

        # 4. SceneState
        try:
            scene_state = self.scene_manager.get_scene_state(campaign_id, location)
            if scene_state is None:
                time_of_day = "07:00"
                if campaign_state:
                    time_of_day = campaign_state.metadata.get("time_of_day", "07:00")
                scene_state = self.scene_manager.initialize_scene(
                    campaign_id, location, time_of_day
                )
                # Материализуем инвентарь NPC из вероятностных правил L0.
                # Только для новой сцены — при рестарте стейт уже содержит objects.
                _npc_scene_ids = set(scene_state.get("npc_positions", {}).keys())
                for _raw_npc in self._load_npcs():
                    _npc_id = _raw_npc.get("id") or _raw_npc.get("npc_id")
                    if _npc_id not in _npc_scene_ids:
                        continue
                    if not _raw_npc.get("carried_objects"):
                        continue
                    try:
                        _inv = materialize_inventory(_raw_npc)
                        for _item_id, _qty in _inv.items():
                            _obj_key = f"{_item_id}_owned_by_{_npc_id}"
                            if _obj_key not in scene_state["objects"]:
                                scene_state["objects"][_obj_key] = {
                                    "name":         get_item_display_name(_item_id),
                                    "state":        "present",
                                    "interactable": True,
                                    "owner":        _npc_id,
                                    "count":        _qty,
                                }
                    except Exception as _e:
                        print(f"[GAME_LOOP] Ошибка материализации инвентаря {_npc_id}: {_e}")
                self.scene_manager.save_scene_state(campaign_id, scene_state)
                logger.info(f"[GAME_LOOP] Новая сцена: {location}")
            patch_scene_state(shared_context, scene_state)
            
            # Инициализация game_time_seconds из scene_state
            # Новая игра → "07:00" (DEFAULT_START_HOUR), загрузка → сохранённая строка
            from app.core.calendar import Calendar
            _env_time = scene_state.get("environment", {}).get("time_of_day", "07:00")
            _seconds_in_day = Calendar.parse_hhmm(_env_time)
            # Старые сейвы не хранят день/год — начинаем с эпохи (день 1, год 1)
            shared_context["game_time_seconds"] = _seconds_in_day
        except Exception as e:
            logger.warning(f"[GAME_LOOP] SceneState error: {e}")

        # 4.1. LifeEngine — тик расписания NPC (без LLM, чистая логика)
        # Двигает NPC по расписанию, меняет routine, скрывает/показывает по LOS.
        # Вызывается каждый ход — SceneChange применяются атомарно.
        try:
            _life_engine = get_life_engine()
            # Catch-up: догоняем пропущенные тики (пока игрок отсутствовал)
            from app.core.constants import MAX_CATCH_UP_TICKS
            _world_elapsed = _life_engine.get_world_ticks_elapsed(campaign_id)
            _sim_tick = _life_engine.get_current_tick(campaign_id)
            _delta = max(0, _world_elapsed - _sim_tick)
            _catch_up = min(_delta, MAX_CATCH_UP_TICKS)
            print(f"[TICK_CATCHUP] world={_world_elapsed} sim={_sim_tick} delta={_delta} applying={_catch_up}")
            _life_changes = []
            for _ in range(max(1, _catch_up)):
                _life_changes += _life_engine.tick(campaign_id, scene_state, runtime_path=self._get_npc_runtime_path(campaign_id))
            if _life_changes:
                self.scene_manager.apply_changes(campaign_id, _life_changes, scene_state)
                print(f"[LIFE_ENGINE] {len(_life_changes)} изменений применено")
                # Сообщаем DM о прибывших NPC — дедуплицируем (catch-up может дать N одинаковых)
                _arrivals = list({
                    c.target for c in _life_changes
                    if c.type.value == "npc_position"
                    and c.field == "location"
                    and c.value == location
                })
                if _arrivals:
                    shared_context["npc_arrivals"] = _arrivals
                    print(f"[LIFE_ENGINE] Прибыли в сцену: {_arrivals}")
        except Exception as _le:
            print(f"[LIFE_ENGINE] Ошибка тика: {_le}")

        # 4.2. EconomyTracker — дневная проверка INCOME/SOCIAL (раз в TICKS_PER_DAY)
        try:
            from app.core.constants import TICKS_PER_DAY
            _eco_profiles = self._economic_profiles.get(campaign_id)
            if _eco_profiles:
                # Текущий тик после catch-up
                _current_tick = _life_engine.get_current_tick(campaign_id)
                if _current_tick > 0 and _current_tick % TICKS_PER_DAY == 0:
                    _base_drives = self._collect_base_drives(campaign_id)
                    _inc_sat, _soc_sat = self._economy_tracker.check_daily_needs(
                        profiles=_eco_profiles,
                        npc_drives=_base_drives,
                        tick=_current_tick,
                        # TODO: временная заглушка — нужно определить из scene_state (editor JSON)
                        # будет удалено после: добавление флага "locked_location" в структуру локации
                        location_locked=False,
                    )
                    self._economy_tracker.reset_daily()
                    if _inc_sat or _soc_sat:
                        print(f"[ECO_TRACKER] day_end: income={_inc_sat} social={_soc_sat} satisfied")
        except Exception as _et_err:
            print(f"[ECO_TRACKER] Error (non-blocking): {_et_err}")

        # 5. PythonEngines
        fake_req = _FakeRequest(campaign_id, world_id, location, actions)
        try:
            # Извлекаем структурированные данные для нового DM
            # ВНИМАНИЕ: ключи shared_context могут немного отличаться, проверьте при первом запуске
            raw_input = actions[0].action if actions else ""
            
            # 4.5: Извлекаем цель игрока из текста — без этого target=None всегда
            try:
                _scene_pre = shared_context.get("scene_state") or {}
                _npc_ids = list((_scene_pre.get("npc_positions") or {}).keys())
                # Загружаем name_forms из NPC JSON — extract() ищет по ним
                _all_npcs_raw = self._load_npcs()
                _npc_ctx_list = []
                for _n in _all_npcs_raw:
                    _nid = _n.get("id") or _n.get("npc_id")
                    if _nid and _nid in _npc_ids:
                        _npc_ctx_list.append({
                            "npc_id": _nid,
                            "npc_name": _n.get("name", ""),
                            "name_forms": _n.get("name_forms", []),
                        })
                _target_extractor = PlayerTargetExtractor()
                _target_id, _target_name, _, _player_pos, _player_dists = _target_extractor.extract(
                    action_text=raw_input or "",
                    npc_contexts=_npc_ctx_list,
                    scene_state=_scene_pre if isinstance(_scene_pre, dict) else {},
                )
                # Сохраняем расстояния обратно в scene_state — иначе spatial система всегда видит 5.0
                if _player_dists and isinstance(_scene_pre, dict):
                    _scene_pre["player_distances"] = _player_dists
                if _player_pos and isinstance(_scene_pre, dict):
                    _scene_pre["player_position"] = _player_pos
                if _target_id:
                    shared_context["player_target_id"] = _target_id
                    shared_context["player_target_name"] = _target_name
                    print(f"[TARGET] Extracted: {_target_name} ({_target_id})")

                # ФАЗА 3.1: Spatial Events — детекция переходов расстояний
                try:
                    from app.services.spatial.spatial_events import detect_transitions
                    _prev_dists = self._prev_player_distances.get(campaign_id, {})
                    _curr_dists = _player_dists if _player_dists else {}
                    _spatial_events = detect_transitions(_prev_dists, _curr_dists)
                    if _spatial_events:
                        shared_context["spatial_events"] = _spatial_events
                        print(f"[SPATIAL] {len(_spatial_events)} transitions: "
                              f"{[(e.npc_id, e.event_type) for e in _spatial_events]}")
                        # ФАЗА 3.4: Публикуем spatial events в EventBus — DecisionHub видит proximity
                        for _sp in _spatial_events:
                            _evt_type = (
                                EventType.PROXIMITY_CLOSE
                                if _sp.event_type == "proximity_close"
                                else EventType.PROXIMITY_LEAVE
                            )
                            _ge = GameEvent(
                                event_type=_evt_type,
                                actor_id="player",
                                location=location,
                                campaign_id=campaign_id,
                                target_id=_sp.npc_id,
                                parameters={
                                    "prev_distance": _sp.prev_distance,
                                    "new_distance": _sp.new_distance,
                                },
                            )
                            get_event_bus().publish(_ge)
                    # Сохраняем текущие для следующего хода
                    self._prev_player_distances[campaign_id] = dict(_curr_dists)
                except Exception as _se_err:
                    logger.warning(f"[SPATIAL] Transition detection failed: {_se_err}")
            except Exception as _te:
                import traceback
                print(f"[TARGET] Extract error: {_te}")
                traceback.print_exc()
            
            # Строим spatial_data из scene_state для DM SceneBuilder
            _scene = shared_context.get("scene_state", {})
            _npc_positions = _scene.get("npc_positions", {})
            print(f"[DEBUG SPATIAL] location={location}, npc_positions keys={list(_npc_positions.keys())}")
            _npcs_for_builder = []
            _player_distances = _scene.get("player_distances", {})
            for _nid, _npos in _npc_positions.items():
                # Реальное расстояние если известно, иначе 5.0 (NPC в той же локации)
                _dist = _player_distances.get(_nid, 5.0)
                _npcs_for_builder.append({
                    "npc_id": _nid,
                    "location_id": location,
                    "distance_to_player": _dist,
                    "facing_towards_player": True,
                })
            _spatial_data = {
                "location_id": location,
                "npcs": _npcs_for_builder,
                "objects": _scene.get("objects", []),
                "light_level": _scene.get("environment", {}).get("light", 1.0),
            }
            
            # R1: DM видит прошлую речь NPC — извлекаем из WorkingMemory
            # На текущем тике буфер содержит речь с предыдущего тика
            print("[WM_CHECK_START]")
            print(f"[WM_CHECK] campaign={campaign_id}, wm_keys={list(self.memory_manager.working_memory._buffers.keys())}")
            _recent_speech = []
            try:
                # Чтение напрямую из изолированного буфера диалогов (без O(N) фильтра)
                for _evt in self.memory_manager.working_memory.get(f"{campaign_id}:dialogue"):
                    if _evt.get("content"):
                        _recent_speech.append(f"{_evt.get('actor', 'NPC')}: {_evt['content']}")
                shared_context["npc_recent_speech"] = _recent_speech[-5:]
                if _recent_speech:
                    print(f"[RECENT_SPEECH] {_recent_speech[-5:]}")
            except Exception as _rs_err:
                print(f"[RECENT_SPEECH] error: {_rs_err}")

            # R1: DM видит недавние действия игрока — "что произошло" не из пустого
            _recent_player_actions = []
            _SEMANTIC_MAP = {
                "COMBAT": "применяял силу",
                "SANDBOX_PHYSICAL": "физически воздействовал",
                "SANDBOX_SOCIAL": "проявлял агрессию/угрозы",
                "SANDBOX_MILD": "вступал в контакт",
                "FLEE": "пытался сбежать",
            }
            try:
                # Чтение из изолированного буфера диалогов
                for _evt in self.memory_manager.working_memory.get(f"{campaign_id}:dialogue"):
                    if _evt.get("type") == "player_speech":
                        _actor = _evt.get("actor", "Игрок")
                        _raw_type = _evt.get("action_type", "SANDBOX_MILD")
                        _semantic = _SEMANTIC_MAP.get(_raw_type, "действовал")
                        _recent_player_actions.append(f"{_actor}: {_semantic}")
                shared_context["recent_player_actions"] = _recent_player_actions[-3:]
                if _recent_player_actions:
                    print(f"[RECENT_ACTIONS_SEMANTIC] {_recent_player_actions[-3:]}")
            except Exception as _ra_err:
                print(f"[RECENT_ACTIONS] error: {_ra_err}")

            dm_result = self.dm_orchestrator.process_player_action(
                raw_input=raw_input,
                player_data=shared_context.get("player", {}),
                player_markers=shared_context.get("player_markers", []),
                target_npc_id=shared_context.get("player_target_id"),
                spatial_data=_spatial_data,
                current_tick=shared_context.get("current_tick", 0),
            )
            
            # Передаём DM результат в контекст для NPC agent и Verbalization
            shared_context["dm_result"] = dm_result

            # Сохраняем классификацию из Router для DecisionHub и EventBus
            if dm_result.event_context:
                shared_context["action_type"] = dm_result.event_context.event_type
                print(f"[EVENT_TYPE] Router classified as: {dm_result.event_context.event_type}")

            # 5.1: Публикуем событие в EventBus — без этого PerceptionFilter слепой
            if dm_result.is_valid:
                _evt_map = {
                    "dialogue": EventType.PLAYER_SPOKE,
                    "player_interacts": EventType.PLAYER_SPOKE,
                    "attack": EventType.PLAYER_ATTACKED,
                    "player_attacks": EventType.PLAYER_ATTACKED,
                    "move": EventType.PLAYER_MOVED,
                    "stealth": EventType.PLAYER_MOVED,
                }
                _raw_type = shared_context.get("action_type", "dialogue")
                _resolved_type = _evt_map.get(_raw_type, EventType.PLAYER_SPOKE)
                # Атака — звуковое событие с ограниченным радиусом слышимости
                _evt_radius = 15.0 if _resolved_type == EventType.PLAYER_ATTACKED else 999.0
                _game_evt = GameEvent(
                    event_type=_resolved_type,
                    actor_id="player",
                    location=location,
                    campaign_id=campaign_id,
                    target_id=shared_context.get("player_target_id"),
                    radius=_evt_radius,
                    parameters={"raw_input": raw_input, "action_type": _raw_type},
                )
                get_event_bus().publish(_game_evt)
                # Фаза 4 — время продвигается от действий, не от тиков
                self._advance_game_time(scene_state, _raw_type, raw_input, shared_context)
                print(f"[EVENT_BUS] Published: {_game_evt.event_type.name}, target={_game_evt.target_id}")

            # ── SCENE EVENT LAYER: единые события для восприятия всеми NPC ──
            _scene_events = []
            try:
                from app.services.scene.scene_event_emitter import SceneEventEmitter
                _emitter = SceneEventEmitter()
                _action_type = shared_context.get("action_type", "player_interacts")
                _target_id = shared_context.get("player_target_id", "")
                _tick = shared_context.get("current_tick", 0)
                
                if _action_type in ("player_attacks", "player_steals", "player_grapples"):
                    # Физическое действие — ищем результат в npc_contexts позже
                    _scene_events = _emitter.emit_from_physical(
                        action_type=_action_type,
                        actor_id="player",
                        target_id=_target_id,
                        location_id=location,
                        tick=_tick,
                        action_text=raw_input,
                    )
                else:
                    # Вербальное действие
                    _scene_events = _emitter.emit_from_verbal(
                        actor_id="player",
                        location_id=location,
                        tick=_tick,
                        action_text=raw_input,
                        target_id=_target_id,
                    )
                
                shared_context["scene_events"] = _scene_events
                if _scene_events:
                    print(f"[SCENE_EVENTS] {len(_scene_events)} events emitted: {[e.event_type.value for e in _scene_events]}")
                    # Накопление в scene_state для cross-tick восприятия (БАГ 2)
                    from dataclasses import asdict
                    _se_accum = scene_state.setdefault("raw_scene_events", [])
                    _se_accum.extend(asdict(e) for e in _scene_events)
                    if len(_se_accum) > 30:
                        scene_state["raw_scene_events"] = _se_accum[-30:]
                    print(f"[SCENE_ACCUM] total={len(_se_accum)} events in scene_state")
            except Exception as _se_err:
                print(f"[SCENE_EVENTS] error: {_se_err}")

            # Этап 4: Формируем NPC контексты для DecisionHub

            from app.services.npc.npc_loader import load_profile_from_legacy_json, load_l2_state_from_runtime_dict
            from app.services.verbalization.verbalization_context import VerbalizationContext, generate_emotional_nuance
            from app.services.npc.decision_hub import DecisionHub, EventContext as HubEventContext

            npc_contexts = []
            print(f"[DEBUG DM] is_valid={dm_result.is_valid}, scene_context={dm_result.scene_context}, error={dm_result.error}")
            if dm_result.is_valid and dm_result.scene_context:
                # Инжектируем line_of_sight в scene_state для SceneOutcomeBuilder
                if dm_result.scene_context.line_of_sight is not None:
                    scene_state["line_of_sight"] = dm_result.scene_context.line_of_sight

                # EventContext с intensity уже сформирован в dm_scene_builder.enrich_raw_event
                hub_event = dm_result.event_context or HubEventContext(event_type="player_interacts", actor_id="player")

                # ── CHARACTER FILTER (Фаза 2.0.4) ──
                # Фильтрует действие через психологию персонажа (один раз на ход)
                _player_name = actions[0].player_name if actions else ""
                _filter_result = None
                try:
                    from app.services.character.character_filter import CharacterFilter as CharFilter
                    _profile = self.character_service.get_or_create_profile(campaign_id, _player_name)
                    # Если профиль пустой (аватар без ценностей) — пропускаем фильтр
                    if _profile.values.weights:
                        _cf = CharFilter()
                        _filter_result = _cf.compute_resistance(
                            profile=_profile,
                            event_type=hub_event.event_type,
                            intensity=getattr(hub_event, 'intensity', 0.5) or 0.5,
                        )
                        # Применяем эрозию если была
                        if _filter_result.erosion_applied > 0:
                            _profile.apply_erosion(
                                _filter_result.erosion_applied,
                                f"{hub_event.event_type}: {_filter_result.outcome.value}",
                            )
                            self.character_service.upsert_profile(campaign_id, _profile)
                        
                        print(f"[CHAR_FILTER] {_player_name}: {_filter_result.outcome.value} "
                              f"(res={_filter_result.resistance:.2f}, mod={_filter_result.action_modifier:.2f})")
                        
                        # RESIST/REFUSE — передаём контекст DM, пропускаем NPC решения
                        if _filter_result.outcome.value in ("resist", "refuse"):
                            shared_context["character_filter"] = _filter_result.to_dict()
                            # DM увидит описание в prompt, NPC решения не нужны
                            hub_event = None
                except Exception as _cfe:
                    import traceback
                    print(f"[CHAR_FILTER] Error (non-blocking): {_cfe}")
                    traceback.print_exc()

                # Фаза 5.1: FrontEngine — давление мира на персонажа (каждый тик)
                try:
                    from app.services.character.front_engine import FrontEngine
                    _front_eng = FrontEngine()
                    _player_profile = self.character_service.get_or_create_profile(
                        campaign_id, actions[0].player_name if actions else ""
                    )
                    # Собираем сигналы давления из систем
                    _rep_eng = self._get_reputation_engine()
                    _player_rep = 0.0
                    if _rep_eng:
                        # Берём среднюю репутацию по всем фракциям персонажа
                        _rep_states = _rep_eng.get_all_faction_states()
                        if _rep_states:
                            _player_rep = sum(s["reputation"] for s in _rep_states.values()) / len(_rep_states)
                    _world_pressure = _front_eng.compute_pressure(
                        profile=_player_profile,
                        player_reputation=_player_rep,
                    )
                    _front_decision = _front_eng.decide(
                        profile=_player_profile,
                        pressure=_world_pressure,
                        current_tick=shared_context.get("current_tick", 0),
                    )
                    # Применяем решение к профилю
                    if _front_decision.action == "adopt":
                        if _player_profile.front is None:
                            from app.models.front import FrontState
                            _player_profile.front = FrontState()
                        _player_profile.front.adopt(
                            _front_decision.front_type,
                            tick=shared_context.get("current_tick", 0),
                            intensity=_world_pressure.total_pressure,
                        )
                    elif _front_decision.action == "intensify" and _player_profile.front:
                        _player_profile.front.intensity = min(1.0, _player_profile.front.intensity + 0.1)
                    elif _front_decision.action in ("drop", "break") and _player_profile.front:
                        if _front_decision.action == "break":
                            _player_profile.front.breaks.append(
                                f"tick={shared_context.get('current_tick', 0)}: {_front_decision.front_description}"
                            )
                        _player_profile.front.drop()
                    # Стоимость поддержания маски — эрозия целостности
                    if _front_decision.integrity_cost > 0:
                        _player_profile.apply_erosion(
                            _front_decision.integrity_cost,
                            f"front_{_front_decision.front_type.value}",
                        )
                    self.character_service.upsert_profile(campaign_id, _player_profile)
                    # Передаём DM описание маски
                    if _front_decision.front_description:
                        shared_context["front_description"] = _front_decision.front_description
                        shared_context["front_type"] = _front_decision.front_type.value
                    if _world_pressure.total_pressure > 0.1:
                        shared_context["world_pressure"] = round(_world_pressure.total_pressure, 3)
                    print(f"[FRONT] action={_front_decision.action}, "
                          f"pressure={_world_pressure.total_pressure:.2f}, "
                          f"cost={_front_decision.integrity_cost:.4f}")
                except Exception as _fe_err:
                    logger.warning(f"[FRONT] Error: {_fe_err}")

                # Если CharacterFilter заблокировал действие — пропускаем NPC цикл
                if hub_event is None:
                    print(f"[CHAR_FILTER] Action blocked, skipping NPC decisions")

                # SceneContinuity нужен ДО NPC цикла (физические факты)
                if "scene_continuity" not in shared_context:
                    shared_context["scene_continuity"] = self._scene_continuities.setdefault(campaign_id, SceneContinuity())

                # Инжект SceneContinuity в EventContext — NPC видит МИР, не только текущее действие
                _cont_inject = shared_context.get("scene_continuity")
                if _cont_inject and hub_event:
                    hub_event.scene_flags = _cont_inject.active_flags
                    hub_event.scene_facts = _cont_inject.scene_facts[-3:]

                # Загружаем ВСЕХ NPC один раз — мутации будут в этом списке
                _all_npcs_raw = self._load_npcs_with_runtime(campaign_id)
                _dirty_npcs: set = set()  # ID изменённых dict'ов для сохранения
                _max_npc_stress: float = 0.0  # Salience: максимальный стресс среди NPC
                for npc in dm_result.scene_context.nearby_npcs:
                    if hub_event is None:
                        break  # CharacterFilter заблокировал — NPC не реагируют
                    npc_id = npc.get("npc_id")
                    if npc_id and dm_result.scene_context.line_of_sight.get(npc_id, False):
                        
                        # 1. Ищем профиль NPC в уже загруженном списке
                        _npc_profile = None
                        for _n in _all_npcs_raw:
                            if _n.get("id") == npc_id or _n.get("npc_id") == npc_id:
                                _npc_profile = _n
                                break
                        if not _npc_profile:
                            print(f"[GAME_LOOP] Profile not found for {npc_id}")
                            continue
                        # Сохраняем ссылку на dict для записи после StateApplicator
                        _npc_dict_for_write = _npc_profile
                        
                        # 2. Мост: Грязный Dict -> Чистые L0/L2 типы
                        profile_l0 = load_profile_from_legacy_json(_npc_profile)
                        state_l2 = load_l2_state_from_runtime_dict(_npc_profile)

                        # Фаза 4-ROLE.2: Aging temporary drives (каждый тик)
                        _drives = getattr(state_l2, "temporary_drives", [])
                        if _drives:
                            from app.models.npc_state import age_drives
                            _aged = age_drives(_drives)
                            # Пишем обратно в dict для persistence
                            if hasattr(state_l2, '__dict__'):
                                state_l2.temporary_drives = _aged
                                _npc_dict_for_write["temporary_drives"] = [
                                    {"drive_type": d.drive_type, "urgency": d.urgency,
                                     "reason": d.reason, "source_npc_id": d.source_npc_id,
                                     "tick_born": d.tick_born, "tick_age": d.tick_age}
                                    for d in _aged
                                ]
                            if len(_aged) != len(_drives):
                                print(f"[DRIVE] {npc_id}: {len(_drives)}→{len(_aged)} drives (expired)")

                        # ── ПРИЧИННЫЙ СЛОЙ: Physical Resolution (до DecisionHub) ──
                        # Только для target NPC при PHYSICAL действии
                        _reflex_constraints = None
                        _target_id = shared_context.get("player_target_id")
                        _action_type = shared_context.get("action_type", "")
                        
                        # Определяем PHYSICAL через event_type (DMResult не хранит raw_event)
                        _PHYSICAL_EVENTS = frozenset({
                            "player_attacks", "player_steals", "player_grapples",
                            "player_casts", "player_shoots",
                        })
                        _is_physical = _action_type in _PHYSICAL_EVENTS
                        
                        if npc_id == _target_id:
                            print(f"[PHYSICAL_DBG] npc={npc_id} target={_target_id} physical={_is_physical} max_hp={state_l2.max_hp}")

                        if _is_physical and npc_id == _target_id and state_l2.max_hp > 0:
                            try:
                                from app.services.resolution.physical_resolver import PhysicalResolver
                                from app.services.reaction.reflex_resolver import ReflexResolver
                                from app.services.npc.state_applicator import StateApplicator
                                from app.models.event_resolution import EventResolutionResult
                                
                                _combat = _npc_profile.get("combat_stats", {})
                                _target_ac = _combat.get("ac", 10)
                                
                                _resolver = PhysicalResolver()
                                _phys_outcome = _resolver.resolve_attack(
                                    attack_bonus=2,
                                    target_ac=_target_ac,
                                    damage_formula=_combat.get("damage", "1d4"),
                                    attacker_id="player",
                                )
                                
                                # StateApplicator: применить урон к NPCState
                                _rel_store = self.memory_manager._relationships
                                _applicator = StateApplicator(relationship_store=_rel_store)
                                state_l2, _phys_changes = _applicator.apply_physical(
                                    state=state_l2,
                                    outcome=_phys_outcome,
                                    current_tick=shared_context.get("current_tick", 0),
                                )
                                # Записать изменённый стейт обратно в dict
                                from app.models.npc_state import NPCState
                                NPCState.write_to_legacy(state_l2, _npc_dict_for_write)
                                
                                # ReflexResolver: генерирует SceneEvents + DecisionSignals
                                _reflex = ReflexResolver()
                                _reflex_result = _reflex.resolve(
                                    outcome=_phys_outcome,
                                    npc_id=npc_id,
                                    current_hp=state_l2.hp,
                                    max_hp=state_l2.max_hp,
                                )
                                
                                # Сохранить constraints для DecisionHub
                                if _reflex_result.has_constraint:
                                    for sig in _reflex_result.decision_signals:
                                        if sig.signal_type == "constraint" and sig.constraint:
                                            _reflex_constraints = sig.constraint.to_dict()
                                
                                # Факт о физическом ударе — ВСЕГДА при hit (переживает между тиками)
                                _continuity = shared_context.get("scene_continuity")
                                if _phys_outcome.hit and _continuity:
                                    _npc_display_name = _npc_profile.get("name", npc_id)
                                    # Наблюдаемость: есть ли свидетели кроме цели
                                    _scene_state = shared_context.get("scene_state", {})
                                    _los = _scene_state.get("line_of_sight", {})
                                    _witnesses = [nid for nid, vis in _los.items() if vis and nid != npc_id]
                                    _vis_tag = "на глазах у присутствующих " if _witnesses else ""
                                    _fact = f"Игрок {_vis_tag}ударил {_npc_display_name}: {_phys_outcome.damage} урона ({_phys_outcome.damage_type.value})"
                                    if _phys_outcome.critical:
                                        _fact += ", КРИТИЧЕСКИЙ УДАР"
                                    _continuity.add_fact(_fact)

                                # SceneEvents → SceneContinuity (описания рефлексов)
                                if _reflex_result.scene_events:
                                    _phys_labels = {
                                        "flinched": "дрогнул(а)",
                                        "staggered": "отшатнулся(лся) от удара",
                                        "cry_of_pain": "вскрикнул(а) от боли",
                                        "blood_spatter": "появилась кровь",
                                        "weapon_dropped_force": "выронил(а) оружие от удара",
                                        "fell_to_ground": "упал(а) на землю",
                                    }
                                    _desc_parts = []
                                    for _me in _reflex_result.scene_events:
                                        _label = _phys_labels.get(_me.event_type.value, _me.event_type.value)
                                        _desc_parts.append(_label)
                                        if _continuity:
                                            _continuity.add_event(f"{_me.event_type.value}_{_me.npc_id}")
                                    # Дополняем факт описаниями рефлексов
                                    if _desc_parts and _continuity:
                                        _existing = _continuity.scene_facts[-1] if _continuity.scene_facts else ""
                                        _continuity.scene_facts[-1] = _existing + ", " + ", ".join(_desc_parts)
                                
                            except Exception as _phys_err:
                                import traceback
                                print(f"[PHYSICAL] Error (non-blocking): {_phys_err}")
                                traceback.print_exc()

                        # ── ПРИЧИННЫЙ СЛОЙ: ConditionEngine (всегда, не только PHYSICAL) ──
                        if state_l2.conditions:
                            try:
                                from app.services.npc.condition_engine import ConditionEngine
                                _cond_engine = ConditionEngine()
                                _cond_changes, _cond_events = _cond_engine.tick(
                                    state=state_l2,
                                    current_tick=shared_context.get("current_tick", 0),
                                )
                                # StateChanges: применить к state_l2
                                for _sc in _cond_changes:
                                    if _sc.field == "hp":
                                        state_l2 = state_l2.__class__(
                                            **{**state_l2.__dict__, "hp": max(0, state_l2.hp + _sc.delta)}
                                        )
                                        from app.models.npc_state import NPCState as _NPCState
                                        _NPCState.write_to_legacy(state_l2, _npc_dict_for_write)
                                # SceneEvents → SceneContinuity
                                if _cond_events:
                                    _continuity = shared_context.get("scene_continuity")
                                    if _continuity:
                                        for _me in _cond_events:
                                            _continuity.add_event(
                                                f"{_me.event_type.value}_{_me.npc_id}"
                                            )
                            except Exception as _cond_err:
                                print(f"[CONDITION] Error (non-blocking): {_cond_err}")

                        # Сброс динамического состояния при старте новой сессии
                        # R8: без этого stale emotion_tag даёт +0.35 к FLEE
                        # НЕ сбрасываем stress — он копится от событий
                        if is_session_start:
                            state_l2.intent_duration = 0
                            state_l2.intent_duration = 0
                            state_l2.intent_formed_at = 0
                            state_l2.emotion_delta = 0.0
                            # Intent и Emotion сбрасываются через импорт — локальный
                            from app.models.npc_state import Intent as _Intent, EmotionTag as _EmotionTag
                            from app.models.behavior_mask import BehaviorMaskState
                            state_l2.intent = _Intent.IDLE
                            state_l2.emotion = _EmotionTag.NEUTRAL
                            # R8: сброс маски поведения — новый игрок не должен видеть старую
                            state_l2.behavior_mask = BehaviorMaskState()
                            print(f"[SESSION_RESET] {npc_id}: stress=0 emotion=NEUTRAL mask=NONE")

                        # 1.5. Обогащаем relationship_cache из MemoryManager (РАЗРЫВ #1 закрыт)
                        # DecisionHub теперь принимает решения с учётом реальной истории отношений
                        try:
                            mem_weights = self.memory_manager.get_weights_for_decision(
                                campaign_id=campaign_id,
                                npc_id=npc_id,
                                target_id="player",
                            )
                            state_l2.relationship_cache.update(mem_weights)
                        except Exception as _mem_e:
                            print(f"[MEMORY] get_weights failed for {npc_id}: {_mem_e}")

                        # 1.6. CognitiveDistortion: модификаторы для DecisionHub (ШАГ C.1)
                        # Distortion НЕ искажает state — возвращает модификаторы score
                        # Реализм сохраняется: NPC ведёт себя искажённо через score, вербализируется через bias
                        from app.services.npc.cognitive_distortion import CognitiveDistortionEngine
                        _clean_state, _distortion_bias, _distortion_modifiers = CognitiveDistortionEngine().apply(
                            state_l2, actor_is_player=True
                        )


                        # 2. Этап 5: Запуск DecisionHub с L1 чертами + distortion модификаторы
                        _identity_traits = self.memory_manager.get_identity_traits(
                            campaign_id=campaign_id,
                            npc_id=npc_id,
                        )
                        from app.models.npc_state import NPCIdentityL1
                        _identity = NPCIdentityL1(
                            npc_id=npc_id,
                            active_traits=_identity_traits,
                        )
                        # ФАЗА 3.2: социальные модификаторы (ревность, защита союзника)
                        _social_mods = {}
                        try:
                            _se3 = self._get_social_engine(campaign_id)
                            if _se3:
                                _player_dists_snap = shared_context.get(
                                    "scene_state", {}
                                ).get("player_distances", {})
                                # Собираем spatial event types для социальных триггеров (ревность по proximity)
                                _spatial_evts = shared_context.get("spatial_events", [])
                                _extra_evt_types = [sp.event_type for sp in _spatial_evts] if _spatial_evts else None
                                _social_mods = _se3.compute_social_modifiers(
                                    npc_id=npc_id,
                                    player_distances=_player_dists_snap,
                                    event_type=hub_event.event_type,
                                    event_target=shared_context.get("player_target_id"),
                                    extra_event_types=_extra_evt_types,
                                )
                        except Exception as e:
                            print(f"[GAME_LOOP] Ошибка decision_hub.compute: {e}")  # non-blocking

                        # Фаза 2.4-ECO: экономические модификаторы от потребностей
                        _eco_modifiers = {}
                        try:
                            from app.services.economy.need_engine import NeedEngine
                            from app.services.economy.economic_modifier import EconomicModifier
                            _eco_profiles = self._get_or_create_economic_profiles(campaign_id)
                            _eco_profile = _eco_profiles.get(npc_id)
                            if _eco_profile:
                                _ne = NeedEngine()
                                _drives = _ne.tick(_eco_profile)
                                _em = EconomicModifier()
                                _eco_result = _em.calculate(_eco_profile, _drives)
                                _eco_modifiers = _eco_result.modifiers
                                if _eco_modifiers:
                                    print(f"[ECO] {npc_id}: {len(_eco_modifiers)} mods, drives={_eco_result.active_drives}")
                                # Стресс от экономики/потребностей (единый расчёт)
                                from app.services.economy.stress_calculator import calculate_economic_stress
                                _eco_stress, _eco_reason = calculate_economic_stress(_eco_profile, _ne)
                                if _eco_stress > 0:
                                    state_l2.stress = min(100.0, state_l2.stress + _eco_stress)
                                    print(f"[ECO] {npc_id}: +{_eco_stress:.3f} ({_eco_reason})")
                        except Exception as _eco_e:
                            print(f"[ECO] Error (non-blocking): {_eco_e}")

                        # Объединяем все модификаторы для DecisionHub
                        _all_modifiers = {**_distortion_modifiers}
                        if _eco_modifiers:
                            for _intent, _mod in _eco_modifiers.items():
                                _all_modifiers[_intent] = _all_modifiers.get(_intent, 0.0) + _mod

                        # Фаза 3.5: Reputation modifiers
                        _rep_modifiers_for_hub = None
                        _rep_eng = self._get_reputation_engine()
                        if _rep_eng:
                            _rep_mod = _rep_eng.compute_reputation_modifier(npc_id)
                            if _rep_mod:
                                _rep_modifiers_for_hub = _rep_mod

                        # Фаза 4-ROLE.2: TemporaryDrive modifiers
                        _drive_modifiers_for_hub = None
                        _drives = getattr(state_l2, "temporary_drives", [])
                        if _drives:
                            from app.models.npc_state import compute_drive_modifiers
                            _drive_mods = compute_drive_modifiers(_drives)
                            if _drive_mods:
                                _drive_modifiers_for_hub = _drive_mods

                        decision = DecisionHub().compute(
                            state=_clean_state,
                            personality=profile_l0,
                            event=hub_event,
                            identity=_identity,
                            eco_modifiers=_all_modifiers if _all_modifiers else None,
                            social_modifiers=_social_modifiers if _social_mods else None,
                            reputation_modifiers=_rep_modifiers_for_hub,
                            drive_modifiers=_drive_modifiers_for_hub,
                            reflex_constraints=_reflex_constraints,
                        )
                        
                        # 3. StateApplicator: Вычисляем реальные последствия (Read -> Write)
                        # ВНИМАНИЕ: Мы пока не пишем это в SceneState, а используем ТОЛЬКО для LLM-промпта
                        state_to_use_for_llm = state_l2
                        try:
                            from app.services.npc.state_applicator import StateApplicator
                            rel_store = self.memory_manager._relationships
                            applicator = StateApplicator(relationship_store=rel_store)
                            state_to_use_for_llm = applicator.apply(
                                state=state_l2,
                                result=decision,
                                campaign_id=campaign_id
                            )
                            # Собираем недавние события NPC для DecisionHub (память = контекст)
                            hub_event.npc_recent = []
                            if hasattr(state_to_use_for_llm, "narrative_cache"):
                                for e in state_to_use_for_llm.narrative_cache:
                                    if hasattr(e, "summary") and e.npc_id == npc_id and e.summary:
                                        hub_event.npc_recent.append(e.summary)
                                        if len(hub_event.npc_recent) >= 3:
                                            break
                            # Salience: обновляем max_stress для фильтрации объектов
                            _max_npc_stress = max(_max_npc_stress, getattr(state_to_use_for_llm, "stress", 0.0))

                            # ФАЗА 1: NPC становятся живыми — запоминаем взаимодействия
                            _new_mem = None  # инициализация до условия — иначе UnboundLocalError
                            try:
                                _evt_type = hub_event.event_type if hub_event else ""
                                _evt_actor = hub_event.actor_id or "player"
                                _evt_target = shared_context.get("player_target_id") or ""
                                _intent_val = getattr(decision.intent, "value", "") if decision.intent else ""
                                _has_target = bool(_evt_target)
                                _deltas = decision.deltas

                                # Whitelist: социальные интенты, не навигация
                                _social_intents = ("TALK", "TRADE", "HELP", "ATTACK", "FLEE", "GIVE", "ASK", "THREATEN")
                                _is_npc_npc = _evt_type in ("npc_interacts_npc", "npc_proximity_close")
                                _intent_upper = _intent_val.upper() if _intent_val else ""
                                
                                _importance = None
                                _summary = ""
                                
                                if _is_npc_npc:
                                    # NPC-NPC: "Люся спросила у Торнина про поставки"
                                    _actor_name = _evt_actor
                                    _target_name = _evt_target
                                    _summary = f"{_actor_name} → {_target_name}: {_intent_val}"
                                    _importance = 0.6  # NPC-NPC менее значимы для LLM чем player-NPC
                                elif _evt_type == "player_interacts" and _has_target:
                                    # Player-NPC: записываем всегда, даже если NPC ответил observe
                                    _actor_name = _evt_actor
                                    _target_name = _evt_target
                                    _player_text = actions[0].action if actions else ""
                                    _summary = f"{_actor_name} → {_target_name}: {_player_text[:60]}"
                                    _BASE_IMPORTANCE = {
                                        "TALK": 0.6, "TRADE": 0.7, "HELP": 0.8,
                                        "ATTACK": 0.9, "FLEE": 0.8, "GIVE": 0.5,
                                        "ASK": 0.5, "THREATEN": 0.85, "OBSERVE": 0.3,
                                    }
                                    _base = _BASE_IMPORTANCE.get(_intent_upper, 0.4)
                                    _emotion_boost = min(abs(_deltas.emotion_delta) / 5.0, 1.0) * 0.3
                                    _importance = min(_base + _emotion_boost, 1.0)
                                elif _has_target and _intent_upper in _social_intents:
                                    # Player-NPC: "Игрок купил еду у Люси"
                                    _actor_name = _evt_actor
                                    _target_name = _evt_target
                                    _player_text = actions[0].action if actions else ""
                                    _summary = f"{_actor_name} → {_target_name}: {_player_text[:60]}"
                                    # Базовая важность по типу интента
                                    _BASE_IMPORTANCE = {
                                        "TALK": 0.6, "TRADE": 0.7, "HELP": 0.8,
                                        "ATTACK": 0.9, "FLEE": 0.8, "GIVE": 0.5,
                                        "ASK": 0.5, "THREATEN": 0.85,
                                    }
                                    _base = _BASE_IMPORTANCE.get(_intent_upper, 0.0)
                                    # emotion_delta как множитель (шкала ~20, /5.0 = до +30%)
                                    _emotion_boost = min(abs(_deltas.emotion_delta) / 5.0, 1.0) * 0.3
                                    _importance = min(_base + _emotion_boost, 1.0)
                                    

                                if _importance is not None:
                                    _emotion = getattr(state_to_use_for_llm.emotion, "value", "neutral") if state_to_use_for_llm.emotion else "neutral"
                                    _new_mem = self.memory_manager.create_event_memory(
                                        campaign_id=campaign_id,
                                        npc_id=npc_id,
                                        event={
                                            "type": _evt_type,
                                            "actor": _evt_actor,
                                            "target": _evt_target,
                                            "action_type": _intent_upper,
                                        },
                                        scene_state=scene_state,
                                        npc_stress=getattr(state_to_use_for_llm, "stress", 0.0),
                                        emotion_tag=_emotion,
                                        summary=_summary,
                                        importance=_importance,
                                    )
                                # R1: записываем в narrative_cache — иначе память теряется
                                if _new_mem is not None:
                                    from app.core.constants import NARRATIVE_CACHE_MAX
                                    _cache = list(state_to_use_for_llm.narrative_cache)
                                    _cache.append(_new_mem)
                                    _cache.sort(key=lambda f: f.importance, reverse=True)
                                    state_to_use_for_llm.narrative_cache = tuple(_cache[:NARRATIVE_CACHE_MAX])
                            except Exception as _mem_err:
                                    print(f"[MEMORY] create_event_memory failed for {npc_id}: {_mem_err}")

                            # ЗАМЫКАНИЕ: Записываем состояние в dict ПОСЛЕ всех мутаций (включая память)
                            from app.models.npc_state import NPCState
                            NPCState.write_to_legacy(state_to_use_for_llm, _npc_dict_for_write)
                            _dirty_npcs.add(id(_npc_dict_for_write))

                            # Фаза 1: activity вычисляется из intent, не хранится как константа.
                            # Это связывает психологический движок с тем что видит LLM в сцене.
                            _INTENT_TO_ACTIVITY = {
                                "COMBAT":       "fighting",
                                "FLEE":         "fleeing",
                                "TALK":         "talking",
                                "OBSERVE":      "observing",
                                "HELP":         "helping",
                                "INTIMIDATE":   "intimidating",
                                "IDLE":         "",  # пустая строка → не перезаписываем дефолт
                            }
                            _new_activity = _INTENT_TO_ACTIVITY.get(
                                state_to_use_for_llm.intent.value, ""
                            )
                            if _new_activity and npc_id in scene_state.get("npc_positions", {}):
                                scene_state["npc_positions"][npc_id]["activity"] = _new_activity
                        except Exception as e:
                            logger.warning(f"[DM_FACADE] StateApplicator failed for {npc_id}, using raw state: {e}")
                        
                        # 3.5 Reaction Layer: DecisionResult → MicroEvents (ШАГ 0.5)
                        # Без этого: DecisionHub говорит "испуган", но ничего не падает
                        _micro_events = []
                        try:
                            from app.services.reaction.reaction_resolver import ReactionResolver
                            _resolver = ReactionResolver()
                            _composure = 1.0 - state_to_use_for_llm.stress / 100.0
                            _current_activity = _npc_dict_for_write.get("routine", {}).get("current", "")
                            _hands_occupied = _current_activity in ("serving", "working", "crafting", "cooking", "serving_tables", "cleaning_tables")
                            
                            _micro_events = _resolver.resolve(
                                decision=decision,
                                event=hub_event,
                                composure=_composure,
                                hands_occupied=_hands_occupied,
                                current_activity=_current_activity,
                            )
                            print(f"[REACTION] {npc_id}: composure={_composure:.2f} hands={_hands_occupied} act='{_current_activity}' events={[e.event_type.value for e in _micro_events]}")
                        except Exception as e:
                            logger.warning(f"[REACTION] Failed for {npc_id}: {e}")
                        
                        # 4. Упаковка в VerbalizationContext (Enum -> Строки для LLM)
                        # ИСПОЛЬЗУЕМ state_to_use_for_llm, чтобы LLM увидел последствия решения!
                        _dominant_drive = max(profile_l0.drives_base.items(), key=lambda x: x[1])[0]
                        # Формируем контекст события для NPC (что именно происходит)
                        _scene_hint = raw_input[:500].strip() if raw_input else ""
                        
                        # Выводим can_speak/can_move через StateInterpreter
                        from app.services.verbalization.state_interpreter import StateInterpreter
                        _interpreter = StateInterpreter()
                        verb_ctx = VerbalizationContext(
                            npc_id=profile_l0.id,
                            npc_name=profile_l0.name,
                            tier=profile_l0.tier,
                            emotion=state_to_use_for_llm.emotion.value,
                            will_state=state_to_use_for_llm.will_state.value,
                            intent=decision.intent.value,
                            intent_target=decision.intent_target,
                            scene_hint=_scene_hint,
                            emotional_nuance=generate_emotional_nuance(state_to_use_for_llm),
                            speech_style=_dominant_drive,
                            voice_profile=profile_l0.voice_profile,
                            backstory=profile_l0.backstory,
                            author_notes=profile_l0.author_notes,
                            can_speak=_interpreter.derive_can_speak(state_to_use_for_llm.posture, state_to_use_for_llm.conditions),
                            can_move=_interpreter.derive_can_move(state_to_use_for_llm.posture, state_to_use_for_llm.conditions, state_to_use_for_llm.hp),
                            gender=profile_l0.gender,
                            # ФАЗА 0: передаём narrative_cache как hints для LLM
                            narrative_hints=state_to_use_for_llm.narrative_cache,
                        )
                        
                        # Формируем единый контекст NPC
                        _stress_d = 0.0
                        _trust_d = 0.0
                        try:
                            _stress_d = decision.deltas.stress_delta_effective
                            _trust_d = decision.deltas.trust_delta
                        except Exception as e:
                            logger.warning(f"[DM_FACADE] Failed to parse deltas for {npc_id}: {e}")
                        
                        # Scene Event Layer: NPC видит все события в сцене
                        _perceived = scene_state.get("raw_scene_events", [])
                        npc_contexts.append({
                            "npc_id": npc_id,
                            "tier": profile_l0.tier,
                            "profile_l0": profile_l0,           # ФАЗА 0: для voice/backstory/author_notes
                            "verbalization_ctx": verb_ctx,   # КЛЮЧ: Переключает агента на путь R3!
                            "decision_result": decision,      # Для будущего StateApplicator
                            "distortion_bias": _distortion_bias,  # Для ProjectionLayer (речь)
                            "real_state": _npc_dict_for_write,   # Legacy dict для ProjectionLayer
                            "trust_delta": _trust_d,          # Для StateApplicator
                            "stress_delta": _stress_d,        # Для StateApplicator
                            "micro_events": _micro_events,    # ШАГ 0.5: физические реакции
                            "perceived_events": _perceived,   # Scene Event Layer: что NPC воспринимает
                        })
                # Сохраняем через commit boundary (Пробой 7 закрыт)
                if _dirty_npcs:
                    self.scene_manager.commit(
                        campaign_id=campaign_id,
                        scene_state=shared_context["scene_state"],
                        npc_dicts=_all_npcs_raw,  # тот же список с мутациями
                    )

                # ФАЗА 3.5: Reputation impact — влияние действий на репутацию фракций
                _rep_eng = self._get_reputation_engine()
                if _rep_eng and hub_event:
                    try:
                        _action_type_for_rep = shared_context.get("action_type", "")
                        _rep_deltas = _rep_eng.apply_event_impact(
                            event_type=_action_type_for_rep,
                            actor_npc_id=None,  # игрок — не NPC
                            target_npc_id=shared_context.get("player_target_id"),
                        )
                        if _rep_deltas:
                            _rep_eng.apply_deltas(_rep_deltas)
                            print(f"[REPUTATION] {len(_rep_deltas)} faction deltas applied")
                    except Exception as _rep_err:
                        logger.warning(f"[REPUTATION] Impact error: {_rep_err}")
                # ФАЗА 3.4: WorldTickEngine — проактивные действия NPC
                if self._world_tick_engine.should_tick(campaign_id):
                    try:
                        from app.services.npc.npc_loader import load_profile_from_legacy_json, load_l2_state_from_runtime_dict
                        _all_raw = self._load_npcs_with_runtime(campaign_id)
                        _proactive_npc_data = []
                        for _n in _all_raw:
                            _pid = _n.get("id") or _n.get("npc_id")
                            if not _pid:
                                continue
                            _ptier = _n.get("tier", "minor")
                            if _ptier != "major":
                                continue
                            _p_l0 = load_profile_from_legacy_json(_n)
                            _p_l2 = load_l2_state_from_runtime_dict(_n)
                            if _p_l2.hp <= 0:
                                continue
                            _proactive_npc_data.append((_pid, _p_l2, _p_l0))
                        if _proactive_npc_data:
                            _rep_eng = self._get_reputation_engine()
                            _rep_mods = {}
                            if _rep_eng:
                                for _pid, _, _ in _proactive_npc_data:
                                    _rm = _rep_eng.compute_reputation_modifier(_pid)
                                    if _rm:
                                        _rep_mods[_pid] = _rm
                            _tick_result = self._world_tick_engine.compute_proactive_decisions(
                                campaign_id=campaign_id,
                                location=location,
                                npc_data=_proactive_npc_data,
                                scene_state=shared_context.get("scene_state", {}),
                                reputation_modifiers=_rep_mods if _rep_mods else None,
                            )
                            shared_context["world_tick_result"] = _tick_result
                            if _tick_result.decisions:
                                print(f"[WORLD_TICK] {len(_tick_result.decisions)} proactive decisions")

                            # Применяем deltas от world_tick к NPC стейту
                            from app.services.npc.state_applicator import StateApplicator
                            from app.models.npc_state import NPCState
                            _wt_applicator = StateApplicator(relationship_store=self.memory_manager._relationships)
                            _wt_dirty = False
                            _wt_tick = shared_context.get("current_tick", 0)

                            # 1. Recovery для ВСЕХ major NPC (не только с решениями)
                            for _pid, _p_l2, _ in _proactive_npc_data:
                                _wt_npc_raw = next((_n for _n in _all_raw if (_n.get("id") or _n.get("npc_id")) == _pid), None)
                                if not _wt_npc_raw:
                                    continue
                                _wt_state = load_l2_state_from_runtime_dict(_wt_npc_raw)
                                _wt_state = _wt_applicator.apply_tick_recovery(_wt_state, is_sleeping=False)
                                NPCState.write_to_legacy(_wt_state, _wt_npc_raw)
                                _wt_dirty = True

                            # 2. Deltas от конкретных proactive решений
                            for _pd in _tick_result.decisions:
                                _wt_npc_raw = next((_n for _n in _all_raw if (_n.get("id") or _n.get("npc_id")) == _pd.npc_id), None)
                                if not _wt_npc_raw:
                                    continue
                                _wt_state = load_l2_state_from_runtime_dict(_wt_npc_raw)

                                # Применяем stress_delta из решения
                                _wt_deltas = _pd.deltas_dict or {}
                                _wt_stress_d = _wt_deltas.get("stress_delta", 0.0)
                                if _wt_stress_d:
                                    _wt_state.stress = min(100.0, max(0.0, _wt_state.stress + _wt_stress_d))

                                # Эмоция из deltas
                                _wt_emotion = _wt_deltas.get("emotion_tag")
                                if _wt_emotion:
                                    _wt_state.emotion = _wt_emotion

                                NPCState.write_to_legacy(_wt_state, _wt_npc_raw)
                                _wt_dirty = True

                            # NeedEngine.tick() — потребности растут даже без игрока
                            try:
                                from app.services.economy.need_engine import NeedEngine
                                _wt_eco_profiles = self._get_or_create_economic_profiles(campaign_id)
                                _wt_ne = NeedEngine()
                                for _pid, _, _ in _proactive_npc_data:
                                    _wt_ep = _wt_eco_profiles.get(_pid)
                                    if _wt_ep:
                                        _wt_ne.tick(_wt_ep)
                                _wt_dirty = True
                            except Exception as _wt_ne_err:
                                logger.warning(f"[WORLD_TICK] NeedEngine error: {_wt_ne_err}")

                            # Коммитим изменения world_tick
                            if _wt_dirty:
                                self.scene_manager.commit(
                                    campaign_id=campaign_id,
                                    scene_state=shared_context["scene_state"],
                                    npc_dicts=self._load_npcs_with_runtime(campaign_id),
                                )
                                print(f"[WORLD_TICK] state committed for {len(_tick_result.decisions)} NPCs")

                    except Exception as _wt_err:
                        logger.warning(f"[WORLD_TICK] Error: {_wt_err}")

                # Salience Engine: передаём метаданные для фильтрации объектов в промпте
                _scene_for_dm = shared_context.get("scene_state", {})
                _scene_for_dm["_salience_event_type"] = getattr(hub_event, "event_type", "player_interacts")
                _scene_for_dm["_salience_max_stress"] = _max_npc_stress
                _scene_for_dm["_salience_target_object"] = _scene_for_dm.get("player_target_object")
            
            python_engines_result = {
                "dm_result": dm_result,
                "npc_contexts": npc_contexts,  
            }
            
        except Exception as e:
            logger.error(f"[GAME_LOOP] DM Orchestrator error: {e}")
            python_engines_result = {"dm_result": None, "npc_contexts": []}

        shared_context["python_engines"] = python_engines_result
        _all_npc_contexts = python_engines_result.get("npc_contexts", [])

        # 5.5: PerceptionFilter — фильтруем npc_contexts по воспринимающим NPC
        try:
            from app.services.npc.perception_filter import filter_perceiving_npcs

            _all_npc_ids = [ctx["npc_id"] for ctx in _all_npc_contexts]
            _recent = get_event_bus().get_recent_events(limit=1, campaign_id=campaign_id)

            if _recent and _all_npc_ids:
                _perceiving_ids = set(filter_perceiving_npcs(
                    npc_ids     = _all_npc_ids,
                    event       = _recent[0],
                    scene_state = shared_context.get("scene_state", {}),
                ))
                # Адресат всегда воспринимает + свидетели по perception
                # Свидетели получают ослабленный сигнал через distance/clarity
                _explicit_target = shared_context.get("player_target_id")
                if _explicit_target:
                    _perceiving_ids.add(_explicit_target)
                
                # ФИЛЬТРУЕМ — только воспринимающие NPC получают вербализацию
                _filtered_ctxs = [c for c in _all_npc_contexts if c.get("npc_id") in _perceiving_ids]
                shared_context["npc_contexts"] = _filtered_ctxs
                shared_context["perceiving_npcs"] = list(_perceiving_ids)
                _target_note = f" (target={_explicit_target})" if _explicit_target else ""
                print(f"[PERCEPTION_FILTER] {len(_perceiving_ids)}/{len(_all_npc_ids)} NPC{_target_note}: {list(_perceiving_ids)}")
            else:
                shared_context["npc_contexts"] = _all_npc_contexts
                print(f"[PERCEPTION_FILTER] skip: recent={len(_recent) if _recent else 0}, npcs={len(_all_npc_ids)}")

                # ФАЗА 3.4.5: Обновление аватара игрока — реакция на NPC
                _player_name = actions[0].player_name if actions else ""
                _ctxs_for_avatar = shared_context.get("npc_contexts", [])
                if _player_name and _ctxs_for_avatar:
                    try:
                        _avatar_state = self.avatar_service.load_state(campaign_id, _player_name)
                        _avatar_changed = False

                        for _npc_ctx in _ctxs_for_avatar:
                            _npc_intent = _npc_ctx.get("decision_result")
                            if not _npc_intent:
                                continue
                            _intent_val = getattr(_npc_ctx["decision_result"], "intent", None)
                            if _intent_val is None:
                                continue

                            if _intent_val.value == "attack":
                                _avatar_state.stress = min(100.0, _avatar_state.stress + 5.0)
                                if _avatar_state.emotion in (_EmotionTag.NEUTRAL, _EmotionTag.HAPPY):
                                    _avatar_state.emotion = _EmotionTag.FEARFUL
                                _avatar_changed = True

                                # Физический урон: NPC атакует игрока через PhysicalResolver
                                try:
                                    from app.services.resolution.physical_resolver import PhysicalResolver

                                    _npc_real = _npc_ctx.get("real_state", {})
                                    _npc_combat = _npc_real.get("combat_stats", {})
                                    _npc_damage = _npc_combat.get("damage", "1d4")
                                    _npc_atk_bonus = _npc_combat.get("attack_bonus", 2)

                                    _player_sheet = self.avatar_service.load_sheet(campaign_id, _player_name)
                                    _player_ac = _player_sheet.ac

                                    # Резолвим только если игрок жив и имеет HP
                                    if _avatar_state.max_hp > 0 and _avatar_state.hp > 0:
                                        _phys_resolver = PhysicalResolver()
                                        _phys_outcome = _phys_resolver.resolve_attack(
                                            attack_bonus=_npc_atk_bonus,
                                            target_ac=_player_ac,
                                            damage_formula=_npc_damage,
                                            attacker_id=_npc_ctx["npc_id"],
                                        )
                                        if _phys_outcome.hit and _phys_outcome.damage > 0:
                                            _avatar_state.hp = max(0, _avatar_state.hp - _phys_outcome.damage)
                                            _avatar_changed = True
                                            print(f"[AVATAR_DAMAGE] {npc_id} → player: dmg={_phys_outcome.damage} crit={_phys_outcome.critical} hp={_avatar_state.hp}/{_avatar_state.max_hp}")
                                        else:
                                            print(f"[AVATAR_DAMAGE] {npc_id} → player: MISS")
                                except Exception as _phys_err:
                                    print(f"[AVATAR_DAMAGE] error: {_phys_err}")
                            elif _intent_val.value == "intimidate":
                                _avatar_state.stress = min(100.0, _avatar_state.stress + 2.0)
                                if _avatar_state.emotion == _EmotionTag.NEUTRAL:
                                    _avatar_state.emotion = _EmotionTag.SUSPICIOUS
                                _avatar_changed = True
                            elif _intent_val.value == "help":
                                _avatar_state.stress = max(0.0, _avatar_state.stress - 3.0)
                                if _avatar_state.emotion in (_EmotionTag.FEARFUL, _EmotionTag.SAD):
                                    _avatar_state.emotion = _EmotionTag.NEUTRAL
                                _avatar_changed = True

                        if _avatar_changed:
                            self.avatar_service.save_state(campaign_id, _avatar_state)
                            print(f"[AVATAR] stress={_avatar_state.stress:.1f} emotion={_avatar_state.emotion.value}")
                    except Exception as _av_err:
                        print(f"[AVATAR] update error: {_av_err}")

        except Exception as _pf_err:
            import traceback
            print(f"[PERCEPTION_FILTER] error: {_pf_err}")
            traceback.print_exc()
            shared_context["npc_contexts"] = _all_npc_contexts

        # ШАГ D: Social Propagation — слухи доходят до непрямо воспринимающих NPC
        try:
            _se = self._get_social_engine(campaign_id)
            _dm_res = python_engines_result.get("dm_result")
            _target_id = shared_context.get("player_target_id")

            if _se and _dm_res and _dm_res.event_context and _target_id:
                _evt = _dm_res.event_context
                if _evt.intensity >= _se.MIN_ORIGIN_INTENSITY:
                    self._social_tick += 1
                    # Свидетели = NPC, получившие прямую вербализацию
                    _witness_ids = {
                        c.get("npc_id")
                        for c in shared_context.get("npc_contexts", [])
                        if c.get("npc_id")
                    }
                    _social_results = _se.propagate(
                        event_type=_evt.event_type,
                        intensity=_evt.intensity,
                        actor=_evt.actor_id,
                        target=_target_id,
                        witnesses=list(_witness_ids - {_target_id}),
                        current_tick=self._social_tick,
                    )

                    if _social_results:
                        _prop_dirty = False
                        _all_npcs = self._load_npcs_with_runtime(campaign_id)
                        for pr in _social_results:
                            # Не перезаписываем прямых свидетелей — они уже получили дельты
                            if pr.npc_id in _witness_ids:
                                continue
                            for _npc_d in _all_npcs:
                                if _npc_d.get("id") == pr.npc_id:
                                    # trust хранится в -100..100, delta в -1..1
                                    _rc = _npc_d.setdefault("relationship_cache", {})
                                    _rc["trust"] = max(-100.0, min(
                                        100.0,
                                        _rc.get("trust", 0.0) + pr.trust_delta * 100,
                                    ))
                                    # stress в 0..100, delta в 0..1
                                    _cur_stress = _npc_d.get("stress", 0.0)
                                    _npc_d["stress"] = max(0.0, min(
                                        100.0,
                                        _cur_stress + pr.stress_delta * 100,
                                    ))
                                    _prop_dirty = True
                                    print(
                                        f"[SOCIAL] {pr.npc_id}: "
                                        f"trust{pr.trust_delta:+.3f} "
                                        f"stress{pr.stress_delta:+.3f} "
                                        f"({pr.rumor.hop} hops)"
                                    )
                                    break

                        if _prop_dirty:
                            self.scene_manager.commit(
                                campaign_id=campaign_id,
                                scene_state=shared_context["scene_state"],
                                npc_dicts=self._load_npcs_with_runtime(campaign_id),
                            )
                        shared_context["social_propagation"] = _social_results
        except Exception as _se_err:
            logger.warning(f"[SOCIAL] Propagation failed: {_se_err}")

        # 6. Rules агент — передаём классификацию из Router
        _action_type = shared_context.get("action_type", "player_interacts")
        _rules_context = {
            "classification": [{
                "player": actions[0].player_name,
                "type": self.dm_orchestrator._router.get_rules_action_type(_action_type), 
            }]
        }
        rules_result = await self._run_agent_safe(
            "rules", self.rules_agent, (actions, _rules_context), {}
        )
        print(f"[RULES] action_type={_action_type} → {_rules_context['classification'][0]['type']}")

        # 6.5 Запись действия игрока в буфер диалогов для семантической памяти
        if actions and actions[0].action:
            self.memory_manager.record_event(f"{campaign_id}:dialogue", {
                "type":        "player_speech",
                "actor":       actions[0].player_name or "Игрок",
                "content":     actions[0].action[:120],
                "action_type": _rules_context['classification'][0]['type'],
            })

        # 7. NPC агент / R3 Direct Mode
        if R3_DIRECT_MODE:
            # ── Новый путь: DecisionResult → DMFrame, npc_agent BYPASSED ──
            from app.services.verbalization.scene_outcome_builder import (
                SceneOutcomeBuilder,
                SceneContext,
            )
            
            _builder = SceneOutcomeBuilder()
            _filtered_ctxs = shared_context.get("npc_contexts", [])
            
            # Собираем DecisionResult[] из отфильтрованных контекстов
            _decisions = []
            for ctx in _filtered_ctxs:
                dr = ctx.get("decision_result")
                if dr is not None:
                    _decisions.append(dr)
            
            # Собираем SceneContext для salience/visibility
            _scene_state = shared_context.get("scene_state", {})
            _distances = _scene_state.get("player_distances", {})
            _visible = {
                npc_id for npc_id, is_visible 
                in _scene_state.get("line_of_sight", {}).items() 
                if is_visible
            }
            _tiers = {ctx["npc_id"]: ctx.get("tier", "minor") for ctx in _filtered_ctxs}
            
            # R5: Определяем успех физического действия из rules_agent
            _player_success = True  # VERBAL действия всегда "успешны" (нет броска)
            if rules_result and isinstance(rules_result, dict):
                _checks = rules_result.get("checks", [])
                if _checks:
                    _first_check = _checks[0] if isinstance(_checks[0], dict) else _checks[0].to_dict() if hasattr(_checks[0], 'to_dict') else {}
                    if _first_check.get("needs_roll", False):
                        _result_str = _first_check.get("result", "").lower()
                        _player_success = "успех" in _result_str or "крит" in _result_str
                        print(f"[R5] Physical action: success={_player_success} result={_result_str}")
            
            _scene_ctx = SceneContext(
                distances=_distances,
                visible_npcs=_visible,
                npc_tiers=_tiers,
                player_action_text=actions[0].action if actions else "",
                player_success=_player_success,
                player_target_id=shared_context.get("player_target_id", ""),
            )
            
            # Собираем снапшоты для ProjectionLayer (реальное состояние + искажения)
            _state_snapshots = {
                ctx["npc_id"]: ctx["real_state"]
                for ctx in _filtered_ctxs
                if ctx.get("real_state")
            }
            _distortion_biases = {
                ctx["npc_id"]: ctx["distortion_bias"]
                for ctx in _filtered_ctxs
                if ctx.get("distortion_bias")
            }
            # ФАЗА 0: профили NPC для voice_profile, backstory, author_notes
            _npc_profiles = {
                ctx["npc_id"]: ctx["profile_l0"]
                for ctx in _filtered_ctxs
                if ctx.get("profile_l0")
            }

            # Строим SceneOutcome → DMFrame (с психологической проекцией)
            _scene = _builder.build(
                _decisions, _scene_ctx,
                state_snapshots=_state_snapshots,
                distortion_biases=_distortion_biases,
                npc_profiles=_npc_profiles,
            )

            # Диагностика ProjectionLayer + DecisionHub
            for actor in _scene.actors:
                if actor.psychological:
                    p = actor.psychological
                    print(f"[PROJECTION] {actor.npc_id}: {p.regime.value} (int={p.intensity}, stab={p.stability})")
            # Дельты от DecisionHub
            for d in _decisions:
                dl = d.deltas
                print(f"[DELTA] {d.npc_id}: intent={d.intent.value} stress_d={dl.stress_delta} trust_d={dl.trust_delta} fear_d={dl.fear_delta}")
            
            # B.3/B.4: Обновляем SceneContinuity из дельт
            _cont = shared_context.get("scene_continuity") or self._scene_continuities.get(campaign_id)
            if not _cont:
                _cont = SceneContinuity()
                self._scene_continuities[campaign_id] = _cont
            _total_stress_d = sum(d.deltas.stress_delta for d in _decisions)
            _total_trust_d = sum(d.deltas.trust_delta for d in _decisions)
            _cont.update_tension(_total_stress_d / 100.0)  # нормализация в 0..1
            _cont.update_emotional_vector({
                "trust": _total_trust_d / 50.0,   # нормализация
                "tension": _total_stress_d / 50.0,
                "confusion": 0.3 if len(_decisions) > 2 else 0.0,  # много NPC = хаос
            })
            # Флаги ключевых событий
            _event_type = shared_context.get("action_type", "")
            if "insult" in _event_type:
                _cont.add_flag("insult_occurred")
                _cont.add_event(f"Игрок оскорбил {_target_id or 'NPC'}")
            if "threaten" in _event_type:
                _cont.add_flag("threat_made")
                _cont.add_event(f"Игрок угрожал {_target_id or 'NPC'}")
            if "attack" in _event_type:
                _cont.add_flag("combat_started")
                _cont.add_event("Началась драка")
            
            # ФАЗА 3.4: Proactive decisions → SceneContinuity (DM видит проактивные действия)
            _tick_result = shared_context.get("world_tick_result")
            if _tick_result and _tick_result.decisions:
                for _pd in _tick_result.decisions:
                    _intent_labels = {
                        "block_path": "преградил(а) дорогу",
                        "ambush": "пытается устроить засаду",
                        "seek_ally": "отправился(ась) искать союзника",
                        "offer_job": "предлагает работу",
                        "request_service": "просит об услуге",
                        "spread_rumor": "распространяет слух",
                        "call_for_help": "зовёт на помощь",
                        "change_role": "меняет роль",
                    }
                    _label = _intent_labels.get(_pd.intent.value, _pd.intent.value)
                    _target_str = f" → {_pd.intent_target}" if _pd.intent_target else ""
                    _cont.add_event(f"{_pd.npc_id}: {_label}{_target_str}")
                    _cont.add_flag(f"proactive_{_pd.intent.value}_{_pd.npc_id}")
                print(f"[WORLD_TICK→CONTINUITY] {len(_tick_result.decisions)} proactive → DM context")
            
            # ШАГ 0.5: MicroEvents → SceneContinuity флаги/события
            for ctx in _filtered_ctxs:
                for me in ctx.get("micro_events", []):
                    _npc_name = ctx.get("verbalization_ctx")
                    _name = _npc_name.npc_name if _npc_name else me.npc_id
                    if me.event_type.value == "object_dropped":
                        _cont.add_flag(f"{_name}_dropped_object")
                        _cont.add_event(f"{_name} уронил(а) предмет")
                    elif me.event_type.value == "interaction_disrupted":
                        _cont.add_flag(f"{_name}_disrupted")
                        _cont.add_event(f"Действие {_name} прервано")
                    elif me.event_type.value == "grip_tightened":
                        _cont.add_flag(f"{_name}_grip_tightened")
                        # Без add_event — слишком мелкое для нарратива
            
            # ШАГ D: Social Propagation → SceneContinuity (факты для DM)
            for _pr in shared_context.get("social_propagation", []):
                _cont.add_event(_pr.continuity_note)

            # ФАЗА 3.1: Spatial Events → SceneContinuity
            for _sp_ev in shared_context.get("spatial_events", []):
                _sp_name = _sp_ev.npc_id
                if _sp_ev.event_type == "proximity_close":
                    _cont.add_event(f"Игрок подошёл к {_sp_name}")
                    _cont.add_flag(f"proximity_close_{_sp_name}")
                elif _sp_ev.event_type == "proximity_leave":
                    _cont.add_event(f"Игрок отошёл от {_sp_name}")
                    _cont.add_flag(f"proximity_leave_{_sp_name}")

            _dm_frame = _builder.build_dm_frame(_scene)
            
            # Конвертируем DMFrame в формат совместимый с dm_agent
            npc_result = {
                "npc_reactions": [],       # Пусто — DM генерирует сам
                "npc_actions": [],         # Пусто — DM генерирует сам
                "dm_frame": _dm_frame,     # КЛЮЧ: DM использует этот путь
            }
            
            # B.3/B.4: Передаём SceneContinuity в контекст для DM prompt
            shared_context["scene_continuity"] = _cont
            
            print(f"[R3_DIRECT] {len(_decisions)} decisions → DMFrame (focus={len(_dm_frame.focus_npcs)}, bg={len(_dm_frame.background_npcs)})")

        # Применяем trust/stress дельты
        npc_state_updates = npc_result.get("npc_state_updates", [])
        if npc_state_updates:
            self._apply_npc_state_updates(npc_state_updates, campaign_id=campaign_id, scene_state=shared_context.get("scene_state", {}))
        # Записываем ход в память NPC
        self._write_npc_memory(
            npc_reactions = npc_result.get("npc_reactions", []),
            player        = actions[0].player_name if actions else "игрок",
            action_text   = actions[0].action if actions else "",
            scene_state   = shared_context.get("scene_state", {}),
        )

        # ── R1 CONNECT: Working Memory ─────────────────────────────────────────
        _player_text = actions[0].action if actions else ""
        _player_name = actions[0].player_name if actions else "игрок"

        # action_type из классификатора (для ImportanceEngine)
        _act_type = shared_context.get("action_type", "unknown")

        # P0.1: действие игрока → Working Memory
        # Телеграф — технический маркер, не действие игрока
        if not _player_text.startswith("[TELEGRAPH"):
            self.memory_manager.record_event(campaign_id, {
                "type":        "player_action",
                "actor":       _player_name,
                "content":     _player_text,
                "action_type": _act_type,
                "location":    location,
            })
            print(f"[WM_WRITE] player_action: {_player_text[:50]}")

        # P0.2: ответы NPC → Working Memory
        for _reaction in npc_result.get("npc_reactions", []):
            if not isinstance(_reaction, str):
                continue
            if _reaction and ":" in _reaction:
                self.memory_manager.record_event(f"{campaign_id}:dialogue", {
                    "type":        "npc_speech",
                    "actor":       _reaction.split(":")[0].strip(),
                    "content":     _reaction.split(":", 1)[1].strip()[:120],
                    "action_type": "dialogue_key",
                })

        # P0.3: decay каждые 10 ходов
        _tick = shared_context.get("scene_state", {}).get("snapshot_tick", 0)
        # Decay → identity_weights → NPCIdentityL1 cache (РАЗРЫВ #2 закрыт)
        _identity_weights = self.memory_manager.run_decay_if_needed(campaign_id, _tick)
        # Resonance → identity_weights для каждого активного NPC
        if _identity_weights:
            _resonance = self.memory_manager.detect_resonance(campaign_id, actor_id="player")
            for _npc_id in shared_context.get("active_npc_ids", []):
                self.memory_manager.apply_identity_weights(campaign_id, _npc_id, _resonance)
        # ────────────────────────────────────────────────────────────────────────

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

    def _apply_npc_state_updates(self, updates: list, campaign_id: str = "", scene_state: dict | None = None) -> None:
        if not updates:
            return
        try:
            all_npcs = self._load_npcs_with_runtime(campaign_id) if campaign_id else self._load_npcs()
            changed  = False
            for upd in updates:
                npc_id       = upd.get("npc_id")
                trust_delta  = upd.get("trust_delta", 0.0)
                stress_delta = upd.get("stress_delta", 0)
                for npc in all_npcs:
                    if npc["id"] != npc_id:
                        continue
                    if trust_delta != 0.0:
                        ss = npc.setdefault("social_stats", {})
                        ss["trust"] = round(
                            max(0.0, min(1.0, ss.get("trust", 0.5) + trust_delta)), 4
                        )
                    if stress_delta != 0:
                        psyche = npc.setdefault("psyche", {})
                        psyche["stress"] = max(
                            0, min(100, psyche.get("stress", 0) + stress_delta)
                        )
                    changed = True
                    logger.info(
                        f"[NPC_STATE] {npc_id}: "
                        f"trust_delta={trust_delta:+.4f} stress_delta={stress_delta:+d}"
                    )
                    # P1: RelationshipStore
                    if trust_delta != 0.0 and campaign_id:
                        try:
                            self.memory_manager.update_relationship(
                                campaign_id = campaign_id,
                                source      = "player",
                                target      = npc_id,
                                delta       = {"trust": trust_delta},
                            )
                        except Exception as e:
                            print(f"[GAME_LOOP] Ошибка обновления отношений: {e}")
                    break
            if changed:
                # Пробой 7 закрыт: единственная точка сохранения — commit()
                self.scene_manager.commit(campaign_id, scene_state or {}, all_npcs)

        except Exception as e:
            logger.error(f"[GAME_LOOP] _apply_npc_state_updates failed: {e}")

    def _write_npc_memory(
        self,
        npc_reactions: list,
        player: str,
        action_text: str,
        turn_tick: int = 0,
        scene_state: dict | None = None,
    ) -> None:
        """Записывает ход в memory_trace каждого NPC который ответил."""
        if not npc_reactions:
            return
        try:
            all_npcs = self._load_npcs()
            changed  = False
            for reaction in npc_reactions:
                # reaction формат: "Люся: Я не знаю..."
                if ":" not in reaction:
                    continue
                npc_name_part = reaction.split(":")[0].strip()
                for npc in all_npcs:
                    if npc.get("name", "") != npc_name_part:
                        continue
                    trace = npc.setdefault("memory_trace", [])
                    trace.append({
                        "tick_added": turn_tick,
                        "event": f"{player}: {action_text[:80]}",
                        "my_response": reaction.split(":", 1)[1].strip()[:120],
                    })
                    # Храним последние 10 воспоминаний
                    if len(trace) > 10:
                        npc["memory_trace"] = trace[-10:]
                    changed = True
                    break
            if changed:
                # Пробой 7 закрыт: единственная точка сохранения — commit()
                self.scene_manager.commit("", scene_state or {}, all_npcs)
        except Exception as e:
            logger.warning(f"[GAME_LOOP] _write_npc_memory failed: {e}")

    async def _run_agent_safe(
        self, agent_name: str, agent, args: tuple, kwargs: dict
    ) -> dict:
        vram_monitor      = get_vram_monitor()
        error_interpreter = get_error_interpreter()
        start             = time.perf_counter()

        # Модель загружается лениво внутри agent.run() через новый llm/router.
        # Замер VRAM показывает потребление до и во время работы агента.
        vram_before = await vram_monitor.get_vram_mb()
        vram_after  = vram_before  # Будет обновлено после agent.run()

        jsonl_log({
            "level": "INFO", "agent": agent_name, "status": "model_switch",
            "vram_before_mb": vram_before, "vram_after_mb": vram_after,
        })

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(agent.run, *args, **kwargs),
                timeout=AGENT_TIMEOUT_SEC,
            )
            duration = round((time.perf_counter() - start) * 1000)
            jsonl_log({
                "level": "INFO", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_SUCCESS"],
                "duration_ms": duration, "status": "complete",
            })
            return result or {}

        except asyncio.TimeoutError:
            duration = round((time.perf_counter() - start) * 1000)
            msg = f"Агент '{agent_name}' превысил лимит {AGENT_TIMEOUT_SEC}с"
            # Прерываем зависшую генерацию на llama-server
            try:
                from app.services.llm.provider_manager import get_model_pool
                _pool = get_model_pool()
                if _pool._active_model:
                    _pool._active_model.provider.abort_generation()
                    print(f"[GAME_LOOP] abort sent to {_pool.active_model_key}")
            except Exception:
                pass
            jsonl_log({
                "level": "ERROR", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_TIMEOUT"],
                "duration_ms": duration, "status": "timeout",
                "human_msg": msg,
            })
            logger.error(f"[GAME_LOOP] {msg}")
            return {}

        except Exception as e:
            duration = round((time.perf_counter() - start) * 1000)
            human_msg, fix = error_interpreter.handle(
                e, {"agent": agent_name}, agent_name, agent_name
            )
            jsonl_log({
                "level": "ERROR", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_MODEL_FAIL"],
                "duration_ms": duration, "status": "failed",
                "human_msg": human_msg, "fix": fix,
            })
            logger.error(f"[GAME_LOOP] {agent_name} failed: {human_msg}")
            return {}

    async def _yield_model_info(self, state: _PipelineState):
        """Генерирует SSE-событие с метаинфо о выбранных моделях."""
        try:
            from app.services.llm.router import get_router as get_llm_router, Capability
            from app.services.llm.provider_manager import get_model_pool

            npc_contexts = state.shared_context.get("python_engines", {}).get("npc_contexts", [])
            has_major    = any(c.get("tier") == "major" for c in npc_contexts)
            router_llm   = get_llm_router()
            pool         = get_model_pool()
            dm_key       = router_llm.select_model(Capability.NARRATIVE)
            npc_cap      = Capability.DIALOGUE_GENERATION if has_major else Capability.DIALOGUE
            npc_key      = router_llm.select_model(npc_cap)
            dm_cfg       = pool.get_model_config(dm_key) if pool else None
            npc_cfg      = pool.get_model_config(npc_key) if pool else None
            yield {
                "type": "model",
                "data": {
                    "dm":  {
                        "key":      dm_key,
                        "name":     dm_cfg.name if dm_cfg else dm_key,
                        "provider": dm_cfg.provider_type.value if dm_cfg else "unknown",
                    },
                    "npc": {
                        "key":      npc_key,
                        "name":     npc_cfg.name if npc_cfg else npc_key,
                        "provider": npc_cfg.provider_type.value if npc_cfg else "unknown",
                    },
                },
            }
        except Exception as e:
            print(f"[GAME_LOOP] Ошибка получения location_id: {e}")

    def _write_memory(
        self,
        req: ChatTurnRequest,
        state: _PipelineState,
        dm_result: dict,
        python_engines_result: dict,
    ) -> None:
        memory_events = dm_result.get("memory_events", [])
        self.layered_memory.store_events(req.campaign_id, memory_events)
        self.layered_memory.write_campaign_memory(
            req.campaign_id,
            {
                "world_id": req.world_id,
                "location": req.location,
                "actions":  [a.model_dump() for a in req.actions],
                "rules":    state.rules_result,
                "dm":       dm_result.get("dm_response", ""),
                "npc":      dm_result.get("npc_reactions", []),
                "world":    dm_result.get("world_changes", []),
                "python_engines": python_engines_result,
            },
        )
        self.layered_memory.write_session_memory(
            req.campaign_id,
            {
                "world_id":     req.world_id,
                "location":     req.location,
                "last_actions": [a.model_dump() for a in req.actions],
                "dice_input_required": any(
                    a.dice_result is None for a in req.actions
                ),
            },
        )

    def _write_session_memory(
        self,
        campaign_id: str,
        world_id: str,
        location: str,
        player: str,
        action_text: str,
    ) -> None:
        self.memory_manager.record_event(
            campaign_id,
            {"type": "player_action", "player": player, "action": action_text, "location": location},
        )
        try:
            self.layered_memory.write_session_memory(
                campaign_id,
                {
                    "world_id":     world_id,
                    "location":     location,
                    "last_actions": [{"player_name": player, "action": action_text}],
                    "dice_input_required": False,
                },
            )
            self.layered_memory.write_campaign_memory(
                campaign_id,
                {
                    "world_id": world_id,
                    "location": location,
                    "actions":  [{"player_name": player, "action": action_text}],
                    "dm":       "",
                },
            )
        except Exception as e:
            logger.warning(f"[GAME_LOOP] Memory write error: {e}")

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
            self.layered_memory.write_world_canon(
                world_id,
                {"campaign_id": campaign_id, "source": filename, "payload": payload},
            )
        self.layered_memory.write_campaign_memory(
            campaign_id,
            {
                "event":        "campaign_loaded",
                "world_id":     world_id,
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
        history = self.layered_memory.read_campaign_memory(campaign_id, limit=100)
        for item in reversed(history):
            if item.get("event") == "campaign_loaded" and item.get("world_id"):
                self._campaign_world_index[campaign_id] = item["world_id"]
                return item["world_id"]
        return "manual"

# ────────────────────────────────────────────────────────────────────────────────
# Фиктивный Request для PythonEngines (ожидает объект с полями, не dict)
# ────────────────────────────────────────────────────────────────────────────────

class _FakeRequest:
    """Минимальный объект-заглушка для совместимости с PythonEngines.run()."""
    __slots__ = ("campaign_id", "world_id", "location", "actions")

    def __init__(self, campaign_id, world_id, location, actions):
        self.campaign_id = campaign_id
        self.world_id    = world_id
        self.location    = location
        self.actions     = actions

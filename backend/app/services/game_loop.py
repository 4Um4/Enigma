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
# False = legacy npc_agent → npc_result → DM (N LLM вызовов)
# ─────────────────────────────────────────────────────────────────────────────
R3_DIRECT_MODE: bool = True
from app.services.state.context_builder import build_context, patch_scene_state
from app.services.scene_state_manager import SceneStateManager
from app.services.memory import JsonMemoryStore, LayeredMemory
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

AGENT_TIMEOUT_SEC = 120
NPC_MEMORY_LIMIT  = 30

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
        dm_agent,
        npc_agent,
        rules_agent,
        load_npcs_func,
        adventure_loader: AdventureLoader,
        system_requirements: SystemRequirements,
    ):
        self.data_dir         = data_dir
        self.layered_memory   = layered_memory
        self.memory_manager   = memory_manager
        self.dm_orchestrator  = dm_orchestrator
        self.scene_manager    = scene_manager
        self.world_scheduler  = world_scheduler
        self.character_service = character_service
        # self.model_router удалён
        self.dm_agent         = dm_agent
        self.npc_agent        = npc_agent
        self.rules_agent      = rules_agent
        self._load_npcs           = load_npcs_func
        self.adventure_loader     = adventure_loader
        self.system_requirements  = system_requirements
        self._campaign_world_index: dict[str, str] = {}
        self._session_started_campaigns: set = set()
        # B.3/B.4: SceneContinuity — эпизодическая фиксация сцены
        self._scene_continuities: Dict[str, SceneContinuity] = {}

    # ────────────────────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ────────────────────────────────────────────────────────────────────────────

    def reset_session_flag(self, campaign_id: str) -> None:
        """Сбрасывает флаг начала сессии — следующий ход будет session_start.
        Вызывается при SESSION_REPLACED чтобы сбросить стресс NPC из прошлой сессии.
        """
        self._session_started_campaigns.discard(campaign_id)

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
        yield {"type": "done", "tokens": token_count, "ms": elapsed_ms, "tps": tps}

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
        shared_context = build_context(
            campaign_id         = campaign_id,
            world_id            = world_id,
            location            = location,
            player              = actions[0].player_name if actions else "",
            scene_state         = {},
            python_engines      = {},
            recent_memory       = [
                # Последние ответы DM — чтобы не повторять реакции NPC
                e["dm"] for e in self.layered_memory.read_campaign_memory(campaign_id, limit=3)
                if e.get("dm")
            ],
            reaction_order      = [],
        )

        # 4. SceneState
        try:
            scene_state = self.scene_manager.get_scene_state(campaign_id, location)
            if scene_state is None:
                time_of_day = "12:00"
                if campaign_state:
                    time_of_day = campaign_state.metadata.get("time_of_day", "12:00")
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
        except Exception as e:
            logger.warning(f"[GAME_LOOP] SceneState error: {e}")

        # 4.1. LifeEngine — тик расписания NPC (без LLM, чистая логика)
        # Двигает NPC по расписанию, меняет routine, скрывает/показывает по LOS.
        # Вызывается каждый ход — SceneChange применяются атомарно.
        try:
            _life_engine = get_life_engine()
            _life_changes = _life_engine.tick(campaign_id, scene_state)
            if _life_changes:
                self.scene_manager.apply_changes(campaign_id, _life_changes, scene_state)
                # TODO: Шаг 0.8 — save_npcs загрязнял major_npcs.json. 
                # LifeEngine runtime будет персистироваться через npc_runtime.json после рефакторинга LifeEngine.
                # _life_engine.save_npcs(campaign_id)
                print(f"[LIFE_ENGINE] {len(_life_changes)} изменений применено")
                # Сообщаем DM о прибывших NPC — чтобы он их анонсировал
                _arrivals = [
                    c.target for c in _life_changes
                    if c.type.value == "npc_position"
                    and c.field == "location"
                    and c.value == location
                ]
                if _arrivals:
                    shared_context["npc_arrivals"] = _arrivals
                    print(f"[LIFE_ENGINE] Прибыли в сцену: {_arrivals}")
        except Exception as _le:
            print(f"[LIFE_ENGINE] Ошибка тика: {_le}")

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
                else:
                    print(f"[TARGET] No target found in: {(raw_input or '')[:50]}...")
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
            
            dm_result = self.dm_orchestrator.process_player_action(
                raw_input=raw_input,
                player_data=shared_context.get("player", {}),
                player_markers=shared_context.get("player_markers", []),
                target_npc_id=shared_context.get("player_target_id"),
                spatial_data=_spatial_data,
                current_day=shared_context.get("current_day", 1),
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
                    "attack": EventType.PLAYER_ATTACKED,
                    "move": EventType.PLAYER_MOVED,
                    "stealth": EventType.PLAYER_MOVED,
                }
                _raw_type = shared_context.get("action_type", "dialogue")
                _game_evt = GameEvent(
                    event_type=_evt_map.get(_raw_type, EventType.PLAYER_SPOKE),
                    actor_id="player",
                    location=location,
                    campaign_id=campaign_id,
                    target_id=shared_context.get("player_target_id"),
                    parameters={"raw_input": raw_input, "action_type": _raw_type},
                )
                get_event_bus().publish(_game_evt)
                print(f"[EVENT_BUS] Published: {_game_evt.event_type.name}, target={_game_evt.target_id}")

            # Этап 4: Формируем NPC контексты для DecisionHub

            from app.services.npc.npc_loader import load_profile_from_legacy_json, load_l2_state_from_runtime_dict
            from app.services.verbalization.verbalization_context import VerbalizationContext, generate_emotional_nuance
            from app.services.npc.decision_hub import DecisionHub, EventContext as HubEventContext

            npc_contexts = []
            print(f"[DEBUG DM] is_valid={dm_result.is_valid}, scene_context={dm_result.scene_context}, error={dm_result.error}")
            if dm_result.is_valid and dm_result.scene_context:
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

                # Если CharacterFilter заблокировал действие — пропускаем NPC цикл
                if hub_event is None:
                    print(f"[CHAR_FILTER] Action blocked, skipping NPC decisions")

                _dirty_npcs: set = set()  # ID изменённых dict'ов для сохранения
                for npc in dm_result.scene_context.nearby_npcs:
                    if hub_event is None:
                        break  # CharacterFilter заблокировал — NPC не реагируют
                    # Salience Engine: собираем max_stress для фильтрации объектов
                    _max_npc_stress = 0.0
                    npc_id = npc.get("npc_id")
                    if npc_id and dm_result.scene_context.line_of_sight.get(npc_id, False):
                        
                        # 1. Загружаем полный профиль NPC по ID из major_npcs.json
                        _all_npcs_raw = self._load_npcs()
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

                        # Сброс динамического состояния при старте новой сессии
                        # R8: без этого stale emotion_tag даёт +0.35 к FLEE
                        if is_session_start:
                            state_l2.stress = 0.0
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

                        # 1.6. CognitiveDistortion: искажаем восприятие перед DecisionHub
                        # NPC видит мир через призму — меняет решение, не формулу
                        from app.services.npc.cognitive_distortion import CognitiveDistortionEngine
                        _distorted_state, _distortion_bias = CognitiveDistortionEngine().apply(
                            state_l2, actor_is_player=True
                        )


                        # 2. Этап 5: Запуск DecisionHub с L1 чертами (РАЗРЫВ #1+#2 полностью закрыт)
                        _identity_traits = self.memory_manager.get_identity_traits(
                            campaign_id=campaign_id,
                            npc_id=npc_id,
                        )
                        from app.models.npc_state import NPCIdentityL1
                        _identity = NPCIdentityL1(
                            npc_id=npc_id,
                            active_traits=_identity_traits,
                        )
                        decision = DecisionHub().compute(
                            state=_distorted_state,
                            personality=profile_l0,
                            event=hub_event,
                            identity=_identity,
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
                            # ЗАМЫКАНИЕ: Записываем новое состояние обратно в dict
                            from app.models.npc_state import NPCState
                            NPCState.write_to_legacy(state_to_use_for_llm, _npc_dict_for_write)
                            _dirty_npcs.add(id(_npc_dict_for_write))
                            # Salience: обновляем max_stress для фильтрации объектов
                            _max_npc_stress = max(_max_npc_stress, getattr(state_to_use_for_llm, "stress", 0.0))
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
                        )
                        
                        # Формируем единый контекст NPC
                        _stress_d = 0.0
                        _trust_d = 0.0
                        try:
                            _stress_d = decision.deltas.stress_delta_effective
                            _trust_d = decision.deltas.trust_delta
                        except Exception as e:
                            logger.warning(f"[DM_FACADE] Failed to parse deltas for {npc_id}: {e}")
                        
                        npc_contexts.append({
                            "npc_id": npc_id,
                            "tier": profile_l0.tier,
                            "verbalization_ctx": verb_ctx,   # КЛЮЧ: Переключает агента на путь R3!
                            "decision_result": decision,      # Для будущего StateApplicator
                            "distortion_bias": _distortion_bias,  # Для ProjectionLayer (речь)
                            "real_state": _npc_dict_for_write,   # Legacy dict для ProjectionLayer
                            "trust_delta": _trust_d,          # Для StateApplicator
                            "stress_delta": _stress_d,        # Для StateApplicator
                            "micro_events": _micro_events,    # ШАГ 0.5: физические реакции
                        })
                # Сохраняем через commit boundary (Пробой 7 закрыт)
                if _dirty_npcs:
                    self.scene_manager.commit(
                        campaign_id=campaign_id,
                        scene_state=shared_context["scene_state"],
                        npc_dicts=self._load_npcs(),
                    )
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
                # Если есть явный адресат — только он отвечает
                # (Позже: добавить свидетелей по LOS + distance)
                _explicit_target = shared_context.get("player_target_id")
                if _explicit_target:
                    _perceiving_ids = {_explicit_target}
                
                # ФИЛЬТРУЕМ — только воспринимающие NPC получают вербализацию
                _filtered_ctxs = [c for c in _all_npc_contexts if c.get("npc_id") in _perceiving_ids]
                shared_context["npc_contexts"] = _filtered_ctxs
                shared_context["perceiving_npcs"] = list(_perceiving_ids)
                _target_note = f" (target={_explicit_target})" if _explicit_target else ""
                print(f"[PERCEPTION_FILTER] {len(_perceiving_ids)}/{len(_all_npc_ids)} NPC{_target_note}: {list(_perceiving_ids)}")
            else:
                shared_context["npc_contexts"] = _all_npc_contexts
                print(f"[PERCEPTION_FILTER] skip: recent={len(_recent) if _recent else 0}, npcs={len(_all_npc_ids)}")
        except Exception as _pf_err:
            import traceback
            print(f"[PERCEPTION_FILTER] error: {_pf_err}")
            traceback.print_exc()
            shared_context["npc_contexts"] = _all_npc_contexts

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
            _visible = set(_scene_state.get("line_of_sight", {}).keys())
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

            # Строим SceneOutcome → DMFrame (с психологической проекцией)
            _scene = _builder.build(
                _decisions, _scene_ctx,
                state_snapshots=_state_snapshots,
                distortion_biases=_distortion_biases,
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
            _cont = self._scene_continuities.setdefault(campaign_id, SceneContinuity())
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
        else:
            # ── Legacy путь: npc_agent генерирует текст ──
            shared_context["working_memory"] = self.memory_manager.working_memory.get(campaign_id)
            npc_memory = self.layered_memory.read_npc_memory(campaign_id, limit=NPC_MEMORY_LIMIT)
            npc_result = await self._run_agent_safe(
                "npc", self.npc_agent,
                (location, actions, npc_memory, shared_context, {}),
                {},
            )

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
        self.memory_manager.record_event(campaign_id, {
            "type":        "player_action",
            "actor":       _player_name,
            "content":     _player_text,
            "action_type": _act_type,
            "location":    location,
        })

        # P0.2: ответы NPC → Working Memory
        for _reaction in npc_result.get("npc_reactions", []):
            if not isinstance(_reaction, str):
                continue
            if _reaction and ":" in _reaction:
                self.memory_manager.record_event(campaign_id, {
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
            all_npcs = self._load_npcs()
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
                        except Exception:
                            pass
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
        except Exception:
            pass

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

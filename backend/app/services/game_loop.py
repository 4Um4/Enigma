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
from app.services.action.processor import ActionProcessor, ProcessingResult
from app.services.action_classifier import classifier
from app.services.action.python_engines import PythonEngines
from app.services.action.player_target_extractor import PlayerTargetExtractor
from app.services.state.context_builder import build_context, patch_scene_state
from app.services.scene_state_manager import SceneStateManager
from app.services.memory import JsonMemoryStore, LayeredMemory
from app.services.model_router import ModelRouter
from app.services.world_scheduler import WorldScheduler
from app.services.character_service import CharacterService
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


# ─────────────────────────────────────────────────────────────────────────────
# Внутренний результат пайплайна (до DM-нарратива)
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# GameLoop
# ─────────────────────────────────────────────────────────────────────────────

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
        processor: ActionProcessor,
        python_engines: PythonEngines,
        scene_manager: SceneStateManager,
        world_scheduler: WorldScheduler,
        character_service: CharacterService,
        model_router: ModelRouter,
        dm_agent,
        npc_agent,
        rules_agent,
        load_npcs_func,
        save_npcs_func,
        adventure_loader: AdventureLoader,
        system_requirements: SystemRequirements,
    ):
        self.data_dir         = data_dir
        self.layered_memory   = layered_memory
        self.processor        = processor
        self.python_engines   = python_engines
        self.scene_manager    = scene_manager
        self.world_scheduler  = world_scheduler
        self.character_service = character_service
        self.model_router     = model_router
        self.dm_agent         = dm_agent
        self.npc_agent        = npc_agent
        self.rules_agent      = rules_agent
        self._load_npcs           = load_npcs_func
        self._save_npcs           = save_npcs_func
        self.adventure_loader     = adventure_loader
        self.system_requirements  = system_requirements
        self._campaign_world_index: dict[str, str] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # ПУБЛИЧНЫЙ API
    # ─────────────────────────────────────────────────────────────────────────

    async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
        """Блокирующий путь (REST). DM-нарратив собирается целиком."""
        self.assert_requirements()
        state = await self._run_pipeline(req.actions, req.campaign_id,
                                         req.world_id, req.location)

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

        # Немедленно отвечаем клиенту — ещё до pipeline
        yield {"type": "ping"}
        yield {"type": "status", "text": "Мастер думает..."}

        # Классификация — 0 мс, сразу отдаём тип действия
        from app.services.action_classifier import classifier
        act_type        = classifier.classify(action_text)
        action_type_str = act_type.value
        yield {"type": "action_type", "value": action_type_str}

        # Теперь запускаем тяжёлый pipeline
        state = await self._run_pipeline(
            actions, campaign_id, world_id, location,
            campaign_state=campaign_state,
        )

        # Модели — метаинфо
        async for event in self._yield_model_info(state):
            yield event

        # NPC реакции — ДО токенов DM
        npc_reactions = state.npc_result.get("npc_reactions", [])
        if npc_reactions:
            yield {
                "type":  "npc",
                "data":  npc_reactions,
                "model": state.npc_result.get("model"),
            }

        # DM — стриминг токенов
        yield {"type": "status", "text": "Мастер рассказывает..."}
        token_count  = 0
        world_result = {"world_events": []}

        try:
            async for token in self.dm_agent.stream_narrate(
                location=location,
                actions=actions,
                rules_result=state.rules_result,
                npc_result=state.npc_result,
                world_result=world_result,
                world_canon_exists=False,
                context=state.shared_context,
            ):
                token_count += 1
                yield {"type": "token", "text": token, "n": token_count}
        except Exception as e:
            yield {"type": "error", "text": str(e)}
            return

        elapsed_ms = int(time.time() * 1000 - state.start_ms)
        tps = round(token_count / (elapsed_ms / 1000), 1) if elapsed_ms > 0 else 0
        yield {"type": "done", "tokens": token_count, "ms": elapsed_ms, "tps": tps}

        self._write_session_memory(campaign_id, world_id, location, player, action_text)

    # ─────────────────────────────────────────────────────────────────────────
    # ОБЩИЙ ПАЙПЛАЙН (шаги 1–8 — одинаковы для REST и SSE)
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_pipeline(
        self,
        actions: list,
        campaign_id: str,
        world_id: str,
        location: str,
        campaign_state=None,
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

        # 2. ActionProcessor (classify + physics)
        player_names    = [a.player_name for a in actions]
        npc_importance  = {}  # заполняется позже при необходимости
        processing: ProcessingResult = self.processor.process(
            actions                 = actions,
            campaign_id             = campaign_id,
            location                = location,
            get_character_dict_func = self._get_character_dict,
            npc_importance          = npc_importance,
        )

        # 3. Базовый shared_context
        shared_context = build_context(
            campaign_id         = campaign_id,
            world_id            = world_id,
            location            = location,
            player              = player_names[0] if player_names else "",
            scene_state         = {},
            python_engines      = {},
            physics_validation  = processing.physics_validation,
            classification      = processing.classification,
            recent_memory       = [],
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
                logger.info(f"[GAME_LOOP] Новая сцена: {location}")
            patch_scene_state(shared_context, scene_state)
        except Exception as e:
            logger.warning(f"[GAME_LOOP] SceneState error: {e}")

        # 5. PythonEngines
        fake_req = _FakeRequest(campaign_id, world_id, location, actions)
        try:
            python_engines_result = await self.python_engines.run(
                fake_req, processing.classification, shared_context
            )
        except Exception as e:
            logger.error(f"[GAME_LOOP] PythonEngines error: {e}")
            python_engines_result = {}

        shared_context["python_engines"] = python_engines_result

        # 5.5: PerceptionFilter — кто из NPC воспринял последнее событие
        try:
            from app.services.npc.perception_filter import filter_perceiving_npcs
            from app.services.events.event_bus import get_event_bus

            npc_contexts = python_engines_result.get("npc_contexts", [])
            npc_ids = [ctx["npc_id"] for ctx in npc_contexts]
            recent = get_event_bus().get_recent_events(limit=1)

            if recent and npc_ids:
                perceiving = filter_perceiving_npcs(
                    npc_ids     = npc_ids,
                    event       = recent[0],
                    scene_state = shared_context.get("scene_state", {}),
                )
                shared_context["perceiving_npcs"] = perceiving
                logger.info(
                    f"[GAME_LOOP] PerceptionFilter: "
                    f"{len(perceiving)}/{len(npc_ids)} NPC воспринимают событие"
                )
            else:
                shared_context["perceiving_npcs"] = npc_ids
                logger.warning(
                    f"[GAME_LOOP] PerceptionFilter skip: "
                    f"recent={len(recent)} npc_ids={len(npc_ids)}"
                )
        except Exception as e:
            logger.error(f"[GAME_LOOP] PerceptionFilter error: {e}")
            shared_context["perceiving_npcs"] = []

        # 6. Rules агент
        rules_result = await self._run_agent_safe(
            "rules", self.rules_agent, (actions,), {}
        )

        # 7. NPC агент
        npc_memory = self.layered_memory.read_npc_memory(campaign_id, limit=NPC_MEMORY_LIMIT)
        npc_result = await self._run_agent_safe(
            "npc", self.npc_agent,
            (location, actions, npc_memory, shared_context, npc_importance),
            {},
        )

        # Применяем trust/stress дельты
        npc_state_updates = npc_result.get("npc_state_updates", [])
        if npc_state_updates:
            self._apply_npc_state_updates(npc_state_updates)
        # Записываем ход в память NPC
        self._write_npc_memory(
            npc_reactions = npc_result.get("npc_reactions", []),
            player        = actions[0].player_name if actions else "игрок",
            action_text   = actions[0].action if actions else "",
        )

        return _PipelineState(
            shared_context         = shared_context,
            classification_results = processing.classification,
            world_tick_meta        = world_tick_meta,
            rules_result           = rules_result,
            npc_result             = npc_result,
            python_engines_result  = python_engines_result,
            start_ms               = start_ms,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ─────────────────────────────────────────────────────────────────────────

    def _get_character_dict(self, campaign_id: str, player_name: str) -> dict:
        try:
            characters = self.character_service.list_characters(campaign_id)
            for char in characters:
                if char.name == player_name:
                    return char.model_dump()
        except Exception as e:
            logger.warning(f"[GAME_LOOP] Персонаж '{player_name}' не найден: {e}")
        return {}

    def _apply_npc_state_updates(self, updates: list) -> None:
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
                    break
            if changed:
                self._save_npcs(all_npcs)

        except Exception as e:
            logger.error(f"[GAME_LOOP] _apply_npc_state_updates failed: {e}")

    def _write_npc_memory(
        self,
        npc_reactions: list,
        player: str,
        action_text: str,
        turn_tick: int = 0,
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
                self._save_npcs(all_npcs)
        except Exception as e:
            logger.warning(f"[GAME_LOOP] _write_npc_memory failed: {e}")

    async def _run_agent_safe(
        self, agent_name: str, agent, args: tuple, kwargs: dict
    ) -> dict:
        vram_monitor      = get_vram_monitor()
        error_interpreter = get_error_interpreter()
        start             = time.perf_counter()

        vram_before = await vram_monitor.get_vram_mb()
        await self.model_router.switch_to_agent(agent_name)
        vram_after  = await vram_monitor.get_vram_mb()

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

# ─────────────────────────────────────────────────────────────────────────
    # УПРАВЛЕНИЕ КАМПАНИЕЙ + СИСТЕМНЫЕ ПРОВЕРКИ
    # ─────────────────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────────────────────
# Фиктивный Request для PythonEngines (ожидает объект с полями, не dict)
# ─────────────────────────────────────────────────────────────────────────────

class _FakeRequest:
    """Минимальный объект-заглушка для совместимости с PythonEngines.run()."""
    __slots__ = ("campaign_id", "world_id", "location", "actions")

    def __init__(self, campaign_id, world_id, location, actions):
        self.campaign_id = campaign_id
        self.world_id    = world_id
        self.location    = location
        self.actions     = actions
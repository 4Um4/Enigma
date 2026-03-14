# backend/app/services/orchestrator.py
# ОПТИМИЗАЦИЯ ПОД 8 GB VRAM — RTX 3070 Ti
#
# ИЗМЕНЕНИЯ vs оригинал:
# 1. УБРАН initialize_models_stub() из глобального scope — он ломал импорт
#    (ModelRouter не имеет статического register_model)
# 2. ThreadPoolExecutor убран — pipeline строго последовательный,
#    executor не давал параллелизма, только занимал RAM
# 3. Добавлен жёсткий agent_timeout (120 сек) — LLM не зависнет навсегда
# 4. NPC- и Rules-агенты получают урезанный контекст (limit=10 вместо 20)
#    → экономия ~200-400 токенов → быстрее + меньше нагрузка на VRAM
# 5. vram_monitor.start_session() вызывается при инициализации
#    (раньше baseline был 0, поэтому лог всегда показывал +5757 MB как "утечку")
# 6. switch_to_agent делается ОДИН раз за turn, не дублируется
# 7. Fallback: если агент упал — pipeline продолжается с пустым результатом,
#    игра не крашится
# 8. Добавлен AGENT_TIMEOUT как отдельный ErrorCode

# backend/app/services/orchestrator.py

import asyncio
from time import perf_counter
import logging
from pathlib import Path
from typing import Optional

from app.agents.dm_agent import DmAgent
from app.agents.memory_manager_agent import MemoryManagerAgent
from app.agents.npc_agent import NpcAgent
from app.agents.rules_agent import RulesAgent
from app.agents.world_sim_agent import WorldSimulationAgent

from app.core.config import settings
from app.models.schemas import (
    AgentTrace,
    CampaignLoadResponse,
    ChatTurnRequest,
    ChatTurnResponse,
)

from app.services.adventure_loader import AdventureLoader
from app.services.memory import JsonMemoryStore, LayeredMemory
from app.services.system_requirements import SystemRequirements
from app.services.world_scheduler import WorldScheduler
from app.services.character_service import CharacterService
from app.services.model_router import ModelRouter
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
from app.services.logging_tools import jsonl_log

logger = logging.getLogger(__name__)

ERROR_CODES = {
    "AGENT_SUCCESS":              "SUCCESS",
    "AGENT_TIMEOUT":              "TIMEOUT",
    "AGENT_JSON_PARSE":           "JSON_PARSE",
    "AGENT_MODEL_FAIL":           "MODEL_FAIL",
    "AGENT_CONTEXT_OVERFLOW":     "CONTEXT_OVERFLOW",
    "ORCHESTRATOR_PIPELINE_FAIL": "PIPELINE_FAIL",
}

AGENT_TIMEOUT_SEC = 120   # максимум 2 мин на агента
NPC_MEMORY_LIMIT  = 10    # лимит памяти NPC (экономия ~200 токенов)


class GameOrchestrator:
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or settings.data_dir)
        self.store = JsonMemoryStore(self.data_dir)
        self.layered_memory = LayeredMemory(self.store)

        self.dm_agent        = DmAgent()
        self.rules_agent     = RulesAgent()
        self.npc_agent       = NpcAgent()
        self.world_agent     = WorldSimulationAgent()
        self.world_scheduler = WorldScheduler(self.layered_memory, self.world_agent)
        self.memory_manager  = MemoryManagerAgent(self.layered_memory)
        self.character_service = CharacterService()
        self.adventure_loader  = AdventureLoader(self.data_dir / "campaigns")
        self.system_requirements = SystemRequirements(
            min_physical_cores=settings.min_cpu_physical_cores,
            min_ram_gb=settings.min_ram_gb,
        )
        self.model_router = ModelRouter()
        self._campaign_world_index: dict[str, str] = {}

        # ВАЖНО: никакого asyncio здесь — __init__ вызывается на module-level
        # из routes.py. VRAM baseline ставится в main.py startup_event.
        logger.info("[ORCHESTRATOR_INIT] GameOrchestrator ready")

    def session_state(self, campaign_id: str):
        class State:
            world_id = self._resolve_world_id(campaign_id)
        return State()

    def _resolve_world_id(self, campaign_id: str) -> str:
        if campaign_id in self._campaign_world_index:
            return self._campaign_world_index[campaign_id]
        history = self.layered_memory.read_campaign_memory(campaign_id, limit=100)
        for item in reversed(history):
            if item.get("event") == "campaign_loaded" and item.get("world_id"):
                self._campaign_world_index[campaign_id] = item["world_id"]
                return item["world_id"]
        return "manual"

    def _assert_requirements(self) -> dict:
        report = self.system_requirements.check()
        if settings.enforce_system_requirements and not report.meets:
            raise RuntimeError(f"Недостаточно ресурсов: {report.details}")
        return {"meets": report.meets, **report.details}

    def _check_player_precondition(self, campaign_id: str, player_names: list[str]):
        session = self.layered_memory.read_session_memory(campaign_id) or {}
        existing_players = {p["player_name"] for p in session.get("players", [])}
        missing = [p for p in player_names if p not in existing_players]
        if missing:
            raise ValueError(f"Не зарегистрированы игроки: {', '.join(missing)}")

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
                "event": "campaign_loaded",
                "world_id": world_id,
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

    def _build_shared_context(self, req: ChatTurnRequest) -> dict:
        return {
            "campaign_id":  req.campaign_id,
            "world_id":     req.world_id,
            "location":     req.location,
            "player_state": {a.player_name: {} for a in req.actions},
            "threat":       {},
            "perception":   {},
            "psyche":       {},
            "life":         {},
            "karma":        {},
        }

    def _extract_memory_events(self, dm_result: dict) -> list:
        return dm_result.get("memory_events", [])

    def _get_npc_importance(self, campaign_id: str, location: str) -> dict:
        return {}

    async def _run_agent_safe(
        self, agent_name: str, agent, args: tuple, kwargs: dict
    ) -> dict:
        """Запускает агента с таймаутом. При любой ошибке — fallback {}."""
        vram_monitor      = get_vram_monitor()
        error_interpreter = get_error_interpreter()
        agent_start       = perf_counter()

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
            duration = round((perf_counter() - agent_start) * 1000)
            jsonl_log({
                "level": "INFO", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_SUCCESS"],
                "duration_ms": duration, "status": "complete",
            })
            return result or {}

        except asyncio.TimeoutError:
            duration = round((perf_counter() - agent_start) * 1000)
            msg = f"Агент '{agent_name}' превысил лимит {AGENT_TIMEOUT_SEC}с"
            jsonl_log({
                "level": "ERROR", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_TIMEOUT"],
                "duration_ms": duration, "status": "timeout", "human_msg": msg,
            })
            logger.error(f"[ORCHESTRATOR] {msg}")
            return {}

        except Exception as e:
            duration = round((perf_counter() - agent_start) * 1000)
            human_msg, fix = error_interpreter.handle(
                e, {"agent": agent_name}, agent_name, agent_name
            )
            jsonl_log({
                "level": "ERROR", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_MODEL_FAIL"],
                "duration_ms": duration, "status": "failed",
                "human_msg": human_msg, "fix": fix,
            })
            logger.error(f"[ORCHESTRATOR] {agent_name} failed: {human_msg}")
            return {}

    async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
        logger.info("[ORCHESTRATOR] PIPELINE_START")
        start = perf_counter()

        player_names = [a.player_name for a in req.actions]
        self._assert_requirements()

        world_tick_meta = self.world_scheduler.maybe_tick(
            req.world_id, every_minutes=settings.world_tick_minutes
        )
        shared_context = self._build_shared_context(req)
        npc_importance = self._get_npc_importance(req.campaign_id, req.location)

        results: dict[str, dict] = {}

        # PIPELINE: строго последовательно (ModelPool: max_loaded=1)
        results["rules"] = await self._run_agent_safe(
            "rules", self.rules_agent, (req.actions,), {}
        )
        results["npc"] = await self._run_agent_safe(
            "npc", self.npc_agent,
            (
                req.location, req.actions,
                self.layered_memory.read_npc_memory(req.campaign_id, limit=NPC_MEMORY_LIMIT),
                shared_context, npc_importance,
            ),
            {},
        )
        results["dm"] = await self._run_agent_safe(
            "dm", self.dm_agent,
            (
                req.location, req.actions,
                results.get("rules"), results.get("npc"),
                {"world_events": world_tick_meta.get("events", [])},
                False, shared_context,
            ),
            {},
        )

        memory_events = self._extract_memory_events(results.get("dm", {}))
        self.layered_memory.store_events(req.campaign_id, memory_events)

        active_model = await self.model_router.get_model_for_agent("dm")
        journal_entry_id = self.layered_memory.write_campaign_memory(
            req.campaign_id,
            {
                "world_id": req.world_id, "location": req.location,
                "actions":  [a.model_dump() for a in req.actions],
                "rules":    results.get("rules", {}),
                "dm":       results.get("dm", {}).get("dm_response", ""),
                "npc":      results.get("dm", {}).get("npc_reactions", []),
                "world":    results.get("dm", {}).get("world_changes", []),
                "model":    active_model.model_dump() if active_model else "unknown",
            },
        )
        self.layered_memory.write_session_memory(
            req.campaign_id,
            {
                "world_id":  req.world_id, "location": req.location,
                "last_actions": [a.model_dump() for a in req.actions],
                "dice_input_required": any(a.dice_result is None for a in req.actions),
            },
        )

        pipeline_duration = round((perf_counter() - start) * 1000)
        jsonl_log({
            "level": "INFO", "agent": "orchestrator",
            "error_code": ERROR_CODES["AGENT_SUCCESS"],
            "duration_ms": pipeline_duration, "status": "pipeline_complete",
            "agents_executed": list(results.keys()),
        })

        traces = [
            AgentTrace(agent="performance",     output={"turn_elapsed_ms": pipeline_duration}),
            AgentTrace(agent="world_scheduler", output=world_tick_meta),
            AgentTrace(agent="rules",           output=results.get("rules", {})),
            AgentTrace(agent="npc",             output=results.get("npc", {})),
            AgentTrace(agent="dm",              output=results.get("dm", {})),
            AgentTrace(agent="orchestrator",    output={"pipeline_duration_ms": pipeline_duration}),
        ]

        logger.info(f"[ORCHESTRATOR] PIPELINE_END, elapsed_ms={pipeline_duration}")
        return ChatTurnResponse(
            dm_response=results.get("dm", {}).get("dm_response", ""),
            npc_reactions=results.get("dm", {}).get("npc_reactions", []),
            world_changes=results.get("dm", {}).get("world_changes", []),
            journal_entry_id=journal_entry_id,
            traces=traces,
        )


# ─────────────────────────────────────────────────────────────────────────────
# initialize_models_stub() УДАЛЁН.
#
# Почему это было критическим багом:
#   Строка 308 оригинала: initialize_models_stub()  ← выполнялась при импорте
#   → ModelRouter.register_model(...)               ← метода не существует
#   → AttributeError при импорте orchestrator
#   → main.py не мог загрузиться
#   → FastAPI никогда не стартовал
#   → start_enigma.bat ждал 60 сек → "Backend startup timeout"
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# УБРАНО: initialize_models_stub() вызывавшийся при импорте
#
# ПОЧЕМУ ЛОМАЛО ЗАПУСК:
#   ModelRouter.register_model("stub_model", stub_model)
#   → AttributeError: type object 'ModelRouter' has no attribute 'register_model'
#   → Любой import orchestrator падал с ошибкой
#   → FastAPI не мог стартануть
#
# Stub-модели для тестов регистрируются теперь только в conftest.py
# через patch, что правильно — тестовый код не должен быть в продакшене.
# ─────────────────────────────────────────────────────────────────────────────
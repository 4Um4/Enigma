from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

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
    SessionInterfaceState,
)
from app.services.adventure_loader import AdventureLoader
from app.services.llm_manager import LlmManager
from app.services.memory import JsonMemoryStore, LayeredMemory
from app.services.system_requirements import SystemRequirements
from app.services.world_scheduler import WorldScheduler


class GameOrchestrator:
    def __init__(self, data_dir: str = "data") -> None:
        self.store = JsonMemoryStore(data_dir)
        self.layered_memory = LayeredMemory(self.store)
        self.llm_manager = LlmManager()
        self.dm_agent = DmAgent()
        self.rules_agent = RulesAgent()
        self.npc_agent = NpcAgent()
        self.world_agent = WorldSimulationAgent()
        self.world_scheduler = WorldScheduler(self.layered_memory, self.world_agent)
        self.memory_manager = MemoryManagerAgent(self.layered_memory)
        self.adventure_loader = AdventureLoader(f"{data_dir}/campaigns")
        self.system_requirements = SystemRequirements(
            min_physical_cores=settings.min_cpu_physical_cores,
            min_ram_gb=settings.min_ram_gb,
        )
        self.pool = ThreadPoolExecutor(max_workers=max(2, settings.orchestrator_workers))
        self._campaign_world_index: dict[str, str] = {}

    def _assert_requirements(self) -> dict:
        report = self.system_requirements.check()
        if settings.enforce_system_requirements and not report.meets:
            raise RuntimeError(
                f"Недостаточно ресурсов для стабильной работы: {report.details}. "
                "Требуется CPU уровня i7-9700F (8+ физических ядер) и минимум 16 ГБ RAM."
            )
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
                "event": "campaign_loaded",
                "world_id": world_id,
                "loaded_files": list(loaded.get("files", {}).keys()),
                "status": loaded["status"],
            },
        )
        return CampaignLoadResponse(
            campaign_id=campaign_id,
            world_id=world_id,
            status=loaded["status"],
            loaded_files=list(loaded.get("files", {}).keys()),
        )

    def _resolve_world_id(self, campaign_id: str) -> str:
        if campaign_id in self._campaign_world_index:
            return self._campaign_world_index[campaign_id]

        history = self.layered_memory.read_campaign_memory(campaign_id, limit=100)
        for item in reversed(history):
            if item.get("event") == "campaign_loaded" and item.get("world_id"):
                world_id = item["world_id"]
                self._campaign_world_index[campaign_id] = world_id
                return world_id

        return "manual"

    def import_world_text(self, filename: str, content: str) -> str:
        return self.layered_memory.write_world_canon(
            "manual",
            {
                "filename": filename,
                "size": len(content),
                "preview": content[:1000],
            },
        )

    def trigger_world_tick(self, world_id: str) -> dict:
        return self.world_scheduler.maybe_tick(world_id, every_minutes=0)

    def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
        started = perf_counter()
        requirements = self._assert_requirements()
        active_model = self.llm_manager.switch_model(req.model)
        context = self.memory_manager.retrieve_context(req.world_id, req.campaign_id)

        world_tick_meta = self.world_scheduler.maybe_tick(req.world_id, every_minutes=settings.world_tick_minutes)

        rules_future = self.pool.submit(self.rules_agent.evaluate_actions, req.actions)
        npc_future = self.pool.submit(self.npc_agent.react, req.location, req.actions, context.get("npc_memory", []))
        world_future = self.pool.submit(self.world_agent.tick, req.world_id)

        rules_result = rules_future.result()
        npc_result = npc_future.result()
        world_result = world_future.result()

        dm_result = self.dm_agent.narrate(
            req.location,
            req.actions,
            rules_result,
            npc_result,
            world_result,
            world_canon_exists=bool(context["world_canon"]),
        )

        journal_entry_id = self.layered_memory.write_campaign_memory(
            req.campaign_id,
            {
                "world_id": req.world_id,
                "location": req.location,
                "actions": [a.model_dump() for a in req.actions],
                "rules": rules_result,
                "dm": dm_result["dm_response"],
                "npc": dm_result["npc_reactions"],
                "world": dm_result["world_changes"],
                "model": active_model.model_dump(),
            },
        )
        self.layered_memory.write_session_memory(
            req.campaign_id,
            {
                "world_id": req.world_id,
                "location": req.location,
                "last_actions": [a.model_dump() for a in req.actions],
                "dice_input_required": any(a.dice_result is None for a in req.actions),
            },
        )
        for note in npc_result.get("npc_memory_updates", []):
            self.layered_memory.write_npc_memory(req.campaign_id, {"note": note, "location": req.location})

        elapsed_ms = round((perf_counter() - started) * 1000, 2)

        traces = [
            AgentTrace(agent="system_requirements", output=requirements),
            AgentTrace(agent="performance", output={"turn_elapsed_ms": elapsed_ms}),
            AgentTrace(agent="world_scheduler", output=world_tick_meta),
            AgentTrace(agent="memory_manager", output=context),
            AgentTrace(agent="rules", output=rules_result),
            AgentTrace(agent="npc", output=npc_result),
            AgentTrace(agent="world_sim", output=world_result),
            AgentTrace(agent="dm", output=dm_result),
        ]

        return ChatTurnResponse(
            dm_response=dm_result["dm_response"],
            npc_reactions=dm_result["npc_reactions"],
            world_changes=dm_result["world_changes"],
            journal_entry_id=journal_entry_id,
            traces=traces,
        )

    def session_state(self, campaign_id: str, session_limit: int = 20) -> SessionInterfaceState:
        world_id = self._resolve_world_id(campaign_id)
        recent = self.layered_memory.build_dynamic_context(world_id=world_id, campaign_id=campaign_id, session_limit=session_limit)
        session_memory = recent["session_memory"]
        return SessionInterfaceState(
            campaign_id=campaign_id,
            world_id=world_id,
            players=[],
            session_log=[item.get("location", "unknown") for item in session_memory],
            dice_input_required=bool(session_memory and session_memory[-1].get("dice_input_required")),
            layers=recent,
        )

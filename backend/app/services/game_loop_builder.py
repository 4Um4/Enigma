# backend/app/services/game_loop_builder.py
"""
Чистая функция сборки GameLoop.
НЕ создаёт синглтон — вызывается из main.py при startup.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path

from app.core.config import settings
from app.services.game_loop import GameLoop
from app.services.adventure_loader import AdventureLoader
from app.services.system_requirements import SystemRequirements
from app.services.memory import JsonMemoryStore, LayeredMemory
from app.services.memory.memory_manager import MemoryManager
from app.services.world_scheduler import WorldScheduler
from app.services.character_service import CharacterService
from app.services.scene_state_manager import SceneStateManager
from app.services.state.json_persistence_adapter import JsonPersistenceAdapter
from app.services.action.dm_orchestrator import DMOrchestrator
from app.agents.dm_agent import DmAgent
from app.agents.npc_agent import NpcAgent
from app.agents.rules_agent import RulesAgent
from app.agents.world_sim_agent import WorldSimulationAgent

logger = logging.getLogger(__name__)


def build_game_loop(data_dir: Path) -> GameLoop:
    """Собирает GameLoop со всеми зависимостями. Вызывать ТОЛЬКО из startup."""
    store          = JsonMemoryStore(data_dir)
    layered_memory = LayeredMemory(store)
    memory_manager = MemoryManager(layered_memory, data_dir=str(data_dir))
    persistence    = JsonPersistenceAdapter(data_dir)
    scene_manager  = SceneStateManager(data_dir, persistence=persistence)
    char_service   = CharacterService()

    # NPC cache — замыкание, одно на весь lifecycle
    _cache: dict = {"npcs": None}

    def load_npcs() -> list:
        if _cache["npcs"] is not None:
            return _cache["npcs"]
        npc_path = data_dir / "npcs" / "major_npcs.json"
        if npc_path.exists():
            with open(npc_path, "r", encoding="utf-8") as f:
                _cache["npcs"] = json.load(f)
        else:
            _cache["npcs"] = []
        return _cache["npcs"]

    def save_npcs(npcs: list) -> None:
        npc_path = data_dir / "npcs" / "major_npcs.json"
        npc_path.parent.mkdir(parents=True, exist_ok=True)
        with open(npc_path, "w", encoding="utf-8") as f:
            json.dump(npcs, f, ensure_ascii=False, indent=2)
        _cache["npcs"] = npcs

    world_scheduler = WorldScheduler(
        layered_memory, WorldSimulationAgent()
    )

    dm_orchestrator = DMOrchestrator()

    loop = GameLoop(
        data_dir            = data_dir,
        layered_memory      = layered_memory,
        memory_manager      = memory_manager,
        dm_orchestrator     = dm_orchestrator,
        scene_manager       = scene_manager,
        world_scheduler     = world_scheduler,
        character_service   = char_service,
        dm_agent            = DmAgent(),
        npc_agent           = NpcAgent(),
        rules_agent         = RulesAgent(),
        load_npcs_func      = load_npcs,
        save_npcs_func      = save_npcs,
        adventure_loader    = AdventureLoader(data_dir / "campaigns"),
        system_requirements = SystemRequirements(
            min_physical_cores = settings.min_cpu_physical_cores,
            min_ram_gb         = settings.min_ram_gb,
        ),
    )

    logger.info("[BUILDER] GameLoop создан")
    return loop

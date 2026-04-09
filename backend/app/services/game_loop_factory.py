# backend/app/services/game_loop_factory.py
#
# Единственный экземпляр GameLoop для всего приложения.
# routes.py и routes_stream.py импортируют отсюда.
# Создаётся один раз при импорте модуля.

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
# Старый model_router удалён — загрузка моделей теперь управляется llm/router.py
from app.services.world_scheduler import WorldScheduler
from app.services.character_service import CharacterService
from app.services.scene_state_manager import SceneStateManager
from app.services.action.processor import ActionProcessor
from app.services.action.dm_orchestrator import DMOrchestrator
from app.services.action.player_target_extractor import PlayerTargetExtractor
from app.services.npc.life_engine import get_life_engine
from app.agents.dm_agent import DmAgent
from app.agents.npc_agent import NpcAgent
from app.agents.rules_agent import RulesAgent
from app.agents.world_sim_agent import WorldSimulationAgent

logger = logging.getLogger(__name__)


def _build_game_loop() -> GameLoop:
    data_dir       = Path(settings.data_dir)
    store          = JsonMemoryStore(data_dir)
    layered_memory = LayeredMemory(store)
    memory_manager = MemoryManager(layered_memory, data_dir=str(data_dir))
    scene_manager  = SceneStateManager(data_dir)
    life_engine    = get_life_engine()
    char_service   = CharacterService()
    # model_router удалён: загрузка моделей происходит лениво внутри агентов
    extractor      = PlayerTargetExtractor()

    # NPC cache — замыкание, одно на весь lifecycle приложения
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

    def get_npcs_in_location(location: str) -> list:
        return [n for n in load_npcs() if n.get("location") == location]

    def get_character_dict(campaign_id: str, player_name: str) -> dict:
        try:
            for char in char_service.list_characters(campaign_id):
                if char.name == player_name:
                    return char.model_dump()
        except Exception:
            pass
        return {}

    world_scheduler = WorldScheduler(
        layered_memory, WorldSimulationAgent()
    )

    dm_orchestrator = DMOrchestrator()

    loop = GameLoop(
        data_dir            = data_dir,
        layered_memory      = layered_memory,
        memory_manager      = memory_manager,
        processor           = ActionProcessor(),
        dm_orchestrator     = dm_orchestrator,
        scene_manager       = scene_manager,
        world_scheduler     = world_scheduler,
        character_service   = char_service,
        # model_router параметр удалён из GameLoop
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

    logger.info("[FACTORY] GameLoop singleton создан")
    return loop


# Единственный экземпляр — создаётся при импорте модуля
game_loop: GameLoop = _build_game_loop()

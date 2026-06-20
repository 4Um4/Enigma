# backend/app/services/game_loop_builder.py
"""
Чистая функция сборки GameLoop.
НЕ создаёт синглтон — вызывается из main.py при startup.
"""

from __future__ import annotations
import logging
from pathlib import Path

from app.core.config import settings
from app.services.game_loop import GameLoop
# AdventureLoader удалён (ADR-O-146)
from app.services.system_requirements import SystemRequirements
from app.services.memory import LayeredMemory
from app.services.memory.sqlite_store import SqliteMemoryStore
from app.services.memory.memory_manager import MemoryManager
from app.services.world_scheduler import WorldScheduler
from app.services.character_service import CharacterService
from app.services.player_avatar_service import PlayerAvatarService
from app.services.scene_state_manager import SceneStateManager
from app.services.state.sqlite_persistence_adapter import SqlitePersistenceAdapter
from app.services.action.dm_orchestrator import DMOrchestrator
from app.agents.dm_agent import DmAgent
from app.agents.rules_agent import RulesAgent
from app.agents.world_sim_agent import WorldSimulationAgent

logger = logging.getLogger(__name__)


def build_game_loop(data_dir: Path) -> GameLoop:
    """Собирает GameLoop со всеми зависимостями. Вызывать ТОЛЬКО из startup."""
    saves_dir      = Path(settings.saves_dir)
    # Закон 4.2.1: SQLite = runtime truth
    store          = SqliteMemoryStore(saves_dir / "enigma_memory.db")
    layered_memory = LayeredMemory(store)
    # ADR-O-146: RelationshipStore пишет в saves/ (runtime world), не data/ (static world)
    memory_manager = MemoryManager(layered_memory, data_dir=str(saves_dir))
    persistence    = SqlitePersistenceAdapter(saves_dir / "enigma_runtime.db")

    # ADR-128: Инжекция PersistencePort в LifeEngine для read-back
    # при cache miss. Без этого injuries теряются после TTL/LRU eviction.
    from app.services.npc.life_engine import get_life_engine
    get_life_engine().set_persistence(persistence)

    scene_manager  = SceneStateManager(data_dir, persistence=persistence, saves_dir=saves_dir)
    char_service   = CharacterService(root=str(saves_dir))
    avatar_service = PlayerAvatarService(root=str(saves_dir))

    # NPC cache — замыкание, одно на весь lifecycle
    _cache: dict = {"npcs": None, "runtime_path": None}

    def load_npcs(runtime_path=None) -> list:
        # Инвалидируем кэш если изменился runtime_path
        if _cache["runtime_path"] != runtime_path:
            _cache["npcs"] = None
            _cache["runtime_path"] = runtime_path
        
        if _cache["npcs"] is not None:
            return _cache["npcs"]
        
        from app.services.npc.npc_loader import load_npcs_merged
        _cache["npcs"] = load_npcs_merged(runtime_path)
        return _cache["npcs"]

    # NPC загружаются из config/npc/ через npc_loader.load_npcs_merged()
    # Runtime персистируется через PersistencePort

    world_scheduler = WorldScheduler(
        layered_memory, WorldSimulationAgent()
    )

    dm_orchestrator = DMOrchestrator()

    loop = GameLoop(
        saves_dir           = saves_dir,
        data_dir            = data_dir,
        memory_manager      = memory_manager,
        store               = store,
        dm_orchestrator     = dm_orchestrator,
        scene_manager       = scene_manager,
        world_scheduler     = world_scheduler,
        character_service   = char_service,
        avatar_service      = avatar_service,
        dm_agent            = DmAgent(),
        rules_agent         = RulesAgent(),
        load_npcs_func      = load_npcs,
        # AdventureLoader удалён (ADR-O-146) — vestigial, нет файлов world_lore/npc/locations
        system_requirements = SystemRequirements(
            min_physical_cores = settings.min_cpu_physical_cores,
            min_ram_gb         = settings.min_ram_gb,
        ),
    )

    logger.info("[BUILDER] GameLoop создан")
    return loop

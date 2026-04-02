# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\memory_manager_agent.py
from app.services.memory.memory_manager import MemoryManager


class MemoryManagerAgent:
    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory_manager = memory_manager

    def retrieve_context(self, world_id: str, campaign_id: str) -> dict:
        return self.memory_manager.build_context_for_turn(campaign_id, world_id)
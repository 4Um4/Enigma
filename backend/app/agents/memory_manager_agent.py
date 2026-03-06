from app.services.memory import LayeredMemory


class MemoryManagerAgent:
    def __init__(self, layered_memory: LayeredMemory) -> None:
        self.layered_memory = layered_memory

    def retrieve_context(self, world_id: str, campaign_id: str) -> dict:
        return self.layered_memory.build_context(world_id, campaign_id)

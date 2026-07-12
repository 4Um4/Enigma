from datetime import datetime, timedelta, timezone

from app.agents.world_sim_agent import WorldSimulationAgent
from app.services.memory import LayeredMemory


class WorldScheduler:
    """Generates hidden world events periodically even between explicit turns."""

    def __init__(
        self, memory: LayeredMemory, world_agent: WorldSimulationAgent
    ) -> None:
        self.memory = memory
        self.world_agent = world_agent

    def _last_tick_at(self, world_id: str) -> datetime | None:
        items = self.memory.store.recent(f"world_hidden_events_{world_id}", limit=1)
        if not items:
            return None
        raw = items[0].get("timestamp")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def maybe_tick(self, world_id: str, every_minutes: int) -> dict:
        now = datetime.now(timezone.utc)
        last_tick = self._last_tick_at(world_id)
        if last_tick and (now - last_tick) < timedelta(minutes=every_minutes):
            return {"triggered": False, "reason": "interval_not_elapsed", "events": []}

        # TODO: временная заглушка
        # будет удалено после: ФАЗА 6 — WorldTickEngine (Python-based, без LLM)
        # ПРИЧИНА: world_sim_agent использует LLM для генерации событий,
        # что нарушает главный контракт: "LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ"
        result = {"world_events": [], "simulation_log": "disabled_pending_phase6"}

        event_payload = {
            "visibility": "hidden",
            "events": result.get("world_events", []),
        }
        self.memory.store.append(f"world_hidden_events_{world_id}", event_payload)
        return {
            "triggered": True,
            "reason": "ok",
            "events": result.get("world_events", []),
        }

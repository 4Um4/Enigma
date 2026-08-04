import logging
from datetime import datetime, timedelta, timezone

from app.agents.world_sim_agent import WorldSimulationAgent
from app.services.memory import LayeredMemory

logger = logging.getLogger(__name__)


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
        except ValueError as e:
            logger.debug(f"World scheduler datetime parse error: {e}")
            return None

    def maybe_tick(self, world_id: str, every_minutes: int) -> dict:
        now = datetime.now(timezone.utc)
        last_tick = self._last_tick_at(world_id)
        if last_tick and (now - last_tick) < timedelta(minutes=every_minutes):
            return {"triggered": False, "reason": "interval_not_elapsed", "events": []}

        # MINIMAL OFFSCREEN TICK: мир живет, даже когда игрок думает.
        # Генерируем простые физические события без LLM.
        _events = []
        try:
            _npcs = self.memory.store.recent(f"npcs_runtime_{world_id}", limit=10)
            for _npc in _npcs:
                if _npc.get("life_status") == "ALIVE":
                    _events.append({
                        "type": "idle_tick",
                        "actor": _npc.get("id", "unknown"),
                        "tick": now.isoformat()
                    })
        except Exception as e:
            logger.error(f"[WORLD_SCHEDULER] Failed to generate idle_tick events for {world_id}: {e}", exc_info=True)

        result = {"world_events": _events, "simulation_log": "offscreen_tick_ok"}

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

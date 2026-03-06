from datetime import datetime, timezone


class WorldSimulationAgent:
    def tick(self, world_id: str) -> dict:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        event = f"[{now}] Во фракциях мира {world_id} происходят скрытые политические перестановки."
        return {"world_events": [event]}

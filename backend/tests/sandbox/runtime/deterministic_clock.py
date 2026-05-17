"""Детерминированные часы симуляции. Тикают только по команде."""
from dataclasses import dataclass

@dataclass
class DeterministicClock:
    current_tick: int = 0
    delta_seconds: int = 10
    game_time_seconds: int = 36000

    def tick(self) -> int:
        self.current_tick += 1
        self.game_time_seconds += self.delta_seconds
        return self.current_tick

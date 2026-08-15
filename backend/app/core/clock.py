# backend/app/core/clock.py
"""
Протокол Clock для изоляции реального времени (N-02 FIX).
LiveClock — для production (использует time.time / datetime.now).
FakeClock — для replay (использует game_time_seconds).
"""
import time
import datetime
from typing import Protocol, runtime_checkable

@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime.datetime: ...
    def timestamp(self) -> float: ...

class LiveClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now()
    def timestamp(self) -> float:
        return time.time()

class FakeClock:
    def __init__(self, game_time_seconds: float = 0.0):
        self._game_time = game_time_seconds

    def set_time(self, game_time_seconds: float) -> None:
        self._game_time = game_time_seconds

    def now(self) -> datetime.datetime:
        return datetime.datetime.utcfromtimestamp(self._game_time)

    def timestamp(self) -> float:
        return self._game_time

# Глобальный синглтон часов
_current_clock: Clock = LiveClock()

def get_clock() -> Clock:
    return _current_clock

def set_clock(clock: Clock) -> None:
    global _current_clock
    _current_clock = clock
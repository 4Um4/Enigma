# backend/app/services/replay/time_freezer.py
"""
path: backend/app/services/replay/time_freezer.py
Назначение: Контекст-менеджер для подмены wall-clock на game_time во время replay (Этап 2.4).
Зависимости: time, datetime, contextlib
"""
import time
import datetime
from contextlib import contextmanager

@contextmanager
def frozen_time(game_time_seconds: float):
    """Подменяет time.time() и datetime.datetime.now() на game_time_seconds."""
    original_time_time = time.time
    original_datetime_class = datetime.datetime
    
    # Подменяем класс datetime.datetime на подкласс с переопределённым now()
    class FrozenDateTime(original_datetime_class):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return original_datetime_class.fromtimestamp(game_time_seconds, tz)
            # Windows fallback: utcfromtimestamp не падает на малых таймстампах
            return original_datetime_class.utcfromtimestamp(game_time_seconds)
            
    time.time = lambda: game_time_seconds
    datetime.datetime = FrozenDateTime
    
    try:
        yield
    finally:
        time.time = original_time_time
        datetime.datetime = original_datetime_class
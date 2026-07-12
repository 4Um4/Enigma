# backend/app/services/game_loop_accessor.py
"""
Accessor для GameLoop через FastAPI app.state.
Устраняет глобальный синглтон — GameLoop живёт в runtime-контейнере.
"""

from app.services.game_loop import GameLoop
from fastapi import Request


def get_game_loop(request: Request) -> GameLoop:
    """Возвращает GameLoop из app.state. Используется через Depends()."""
    loop = request.app.state.game_loop
    if loop is None:
        raise RuntimeError("GameLoop не инициализирован — startup не завершён")
    return loop

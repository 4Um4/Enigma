"""
DEGOD Phase2-T1: пакетный вход. Контент переехал в game_loop.py (фасад GameLoop).

Назначение: тонкий публичный слой пакета game_loop (DEGOD Phase2-T1). Re-export живой поверхности; контент переехал в game_loop.py.
Зависимости: см. импорты
Основные сущности: GameLoop, _PipelineState"""

from app.services.game_loop.game_loop import GameLoop, _PipelineState

__all__ = ["GameLoop", "_PipelineState"]
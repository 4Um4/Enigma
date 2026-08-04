# backend/app/services/replay/replay_recorder.py
"""
path: backend/app/services/replay/replay_recorder.py
Назначение: Запись каузального следа сессии в ReplayStore (Этап 2.2).
Зависимости: app.services.replay.replay_store
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class ReplayRecorder:
    """Подписывается на хуки TickOrchestrator и пишет данные в SQLite."""

    def __init__(self, store: Any, session_id: str):
        self.store = store
        self.session_id = session_id

    def record_tick_state(self, tick_id: int, game_time: float, tick_state: Any) -> None:
        """Вызывается после Фазы 0 (сборка контекста)."""
        try:
            # tick_state может быть сложным объектом, сериализуем через default=str
            self.store.record_tick(
                session_id=self.session_id,
                tick_id=tick_id,
                game_time_seconds=game_time,
                tick_state=tick_state
            )
        except Exception as e:
            logger.error(f"[REPLAY_RECORDER] Failed to record tick_state: {e}")

    def record_tick_mutation(self, tick_id: int, mutation: Any) -> None:
        """Вызывается после Фазы 5 (NpcTickPipeline.run)."""
        try:
            self.store.record_tick(
                session_id=self.session_id,
                tick_id=tick_id,
                game_time_seconds=0.0,  # Обновляем существующую запись
                tick_state=None, # Не перезаписываем
                tick_mutation=mutation
            )
        except Exception as e:
            logger.error(f"[REPLAY_RECORDER] Failed to record tick_mutation: {e}")

    def record_world_snapshot(self, tick_id: int, snapshot: Any) -> None:
        """Вызывается после Фазы 9 (Integration)."""
        try:
            self.store.record_tick(
                session_id=self.session_id,
                tick_id=tick_id,
                game_time_seconds=0.0,
                tick_state=None,
                world_snapshot=snapshot
            )
        except Exception as e:
            logger.error(f"[REPLAY_RECORDER] Failed to record world_snapshot: {e}")

    def record_interventions(self, tick_id: int, interventions: list) -> None:
        """Вызывается до Фазы 10."""
        try:
            for interv in interventions:
                source = getattr(interv, "source", "unknown")
                payload = getattr(interv, "payload", {})
                self.store.record_intervention(
                    session_id=self.session_id,
                    tick_id=tick_id,
                    source=source,
                    payload=payload
                )
        except Exception as e:
            logger.error(f"[REPLAY_RECORDER] Failed to record interventions: {e}")
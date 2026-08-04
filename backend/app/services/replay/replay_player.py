# backend/app/services/replay/replay_player.py
"""
path: /project/backend/app/services/replay/replay_player.py
Назначение: Инструмент воспроизведения записанной сессии для A/B тестирования и поиска дрейфа.
Зависимости: app.services.replay.replay_store, app.services.replay.time_freezer
Основные сущности: ReplayPlayer, ReplayDriftError
"""
import logging
from typing import Any, Optional, List, Dict
from app.services.replay.replay_store import ReplayStore
from app.services.replay.time_freezer import frozen_time

logger = logging.getLogger(__name__)

class ReplayDriftError(Exception):
    """Выбрасывается при рассинхроне воспроизводимого тика и записанного."""
    pass

class ReplayPlayer:
    """Воспроизводит записанную сессию, сравнивая результаты тиков."""

    def __init__(self, store: ReplayStore, game_loop: Any, session_id: str, campaign_id: str, location_id: str):
        self.store = store
        self.game_loop = game_loop
        self.session_id = session_id
        self.campaign_id = campaign_id
        self.location_id = location_id

    def play(self, start_tick: int = 0, end_tick: Optional[int] = None, max_drift: int = 0) -> Dict[str, Any]:
        """
        Запускает воспроизведение.
        Возвращает отчёт о дрейфе.
        """
        from app.core.config import settings
        
        # Активируем LLM Cache (чтение)
        settings.replay_playback = True
        settings.replay_record = False
        
        total_drifts = 0
        replayed_ticks = 0

        try:
            tick_id = start_tick
            while end_tick is None or tick_id <= end_tick:
                recorded_tick = self._load_tick(tick_id)
                if not recorded_tick:
                    break # Сессия закончена

                game_time = recorded_tick["game_time_seconds"]
                recorded_snapshot = recorded_tick.get("world_snapshot")

                # 1. Подменяем wall-clock на game_time
                with frozen_time(game_time):
                    # 2. Вызываем idle_tick (воспроизведение interventions пока упрощено)
                    actual_result = self.game_loop.idle_tick(self.campaign_id)

                # 3. Сравниваем результаты (WorldSnapshot)
                drifts = self._compare_results(actual_result, recorded_snapshot)
                if drifts:
                    total_drifts += len(drifts)
                    logger.warning(f"[REPLAY_PLAYER] Drift detected on tick {tick_id}: {drifts}")
                    if total_drifts > max_drift:
                        raise ReplayDriftError(f"Превышен лимит дрейфа ({max_drift}) на тике {tick_id}. Drifts: {drifts}")

                replayed_ticks += 1
                tick_id += 1
        finally:
            # Восстанавливаем состояние
            settings.replay_playback = False

        return {
            "replayed_ticks": replayed_ticks,
            "total_drifts": total_drifts,
            "status": "SUCCESS" if total_drifts == 0 else "DRIFT_DETECTED"
        }

    def _load_tick(self, tick_id: int) -> Optional[Dict[str, Any]]:
        row = self.store.conn.execute(
            "SELECT game_time_seconds, tick_state_json, tick_mutation_json, world_snapshot_json FROM tick_snapshots WHERE session_id = ? AND tick_id = ?",
            (self.session_id, tick_id)
        ).fetchone()
        if not row:
            return None
        return {
            "game_time_seconds": row["game_time_seconds"],
            "tick_state": self.store._from_json_bytes(row["tick_state_json"]),
            "tick_mutation": self.store._from_json_bytes(row["tick_mutation_json"]),
            "world_snapshot": self.store._from_json_bytes(row["world_snapshot_json"])
        }

    def _compare_results(self, actual_result: Any, recorded_snapshot: Any) -> List[str]:
        """Сравнивает текущий результат с записанным. Возвращает список отличий."""
        drifts = []
        
        actual_snapshot_dict = actual_result.get("world_snapshot", {}) if isinstance(actual_result, dict) else {}
        
        if actual_snapshot_dict and recorded_snapshot:
            actual_pos = {k: v.get("local_position") for k, v in actual_snapshot_dict.get("npc_positions", {}).items()}
            recorded_pos = {k: v.get("local_position") for k, v in recorded_snapshot.get("npc_positions", {}).items()}
            if actual_pos != recorded_pos:
                drifts.append("WorldSnapshot positions mismatch")
                
        return drifts
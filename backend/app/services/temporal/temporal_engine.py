# backend/app/services/temporal/temporal_engine.py
"""
Единая точка времени и decay в системе.
Знает текущий тик, игровой день, расписание протухания.

Мигрировано из LifeEngine:
- _increment_tick → advance_tick
- _load_tick / _save_tick → гибридное сохранение RAM+JSON
- _tick_cache / _ticks_since_save → инкапсулированы

Файл: backend/app/services/temporal/temporal_engine.py
Назначение: Единая точка времени/decay в системе. Знает текущий тик, игровой день, расписание протухания.
Зависимости: app.models.temporal.TemporalContext, app.core.constants
Основные сущности: TemporalEngine

Принципы:
  - TemporalEngine управляет ходом времени в игре, инкрементируя тик и вычисляя TemporalContext для всех подсистем.
  - Он использует гибридное сохранение: RAM кэш для быстрого доступа и JSON файл для долговременного хранения, который обновляется раз в N тиков.
  - TemporalContext содержит текущий тик, игровой день, часы и информацию о том, нужно ли запускать decay для памяти NPC, что позволяет синхронизировать все подсистемы на одной временной информации.
  - TemporalEngine НЕ хранит TemporalContext внутри NPC или других сущностей. Это глобальный контекст, который вычисляется в начале каждого world_tick() и передаётся вниз по цепочке вызовов.
  - Это обеспечивает консистентность поведения NPC и правильный запуск событий, так как все части системы работают с одной и той же временной информацией.
  - В будущем TemporalEngine может быть расширен дополнительными функциями, такими как управление сезонами, праздниками или ночным временем, чтобы ещё больше обогатить контекст для принятия решений NPC.

  TODO:
  - Добавить "is_night_time" для влияния на поведение NPC (например, более агрессивные монстры ночью).
  - Ввести "is_festival_day" для создания особых событий и поведения NPC в праздничные дни.
  - Рассмотреть возможность добавления "season" для влияния на доступные ресурсы и поведение NPC (например, зима → меньше еды, более агрессивные животные).
  - Логирование TemporalContext в начале каждого world_tick() для анализа и отладки поведения NPC в зависимости от времени.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from app.core.constants import DECAY_EVERY, TICK_SAVE_INTERVAL, TICKS_PER_DAY
from app.models.temporal import TemporalContext

logger = logging.getLogger(__name__)


class TemporalEngine:
    """
    Управляет ходом времени: инкремент тика, гибридное сохранение,
    расчёт игровых дней и расписания decay.
    """
    def __init__(self, sessions_dir: Path) -> None:
        self._sessions_dir = sessions_dir
        self._tick_cache: Dict[str, int] = {}
        self._ticks_since_save: Dict[str, int] = {}
        # Тик последнего запуска memory decay
        self._last_decay_tick: Dict[str, int] = {}

    def get_temporal_context(self, campaign_id: str) -> TemporalContext:
        """Возвращает снимок временного состояния мира на текущий тик."""
        current_tick = self.get_current_tick(campaign_id)

        game_day = current_tick // TICKS_PER_DAY
        game_hour = current_tick % TICKS_PER_DAY

        last_decay = self._last_decay_tick.get(campaign_id, 0)
        ticks_since_last_decay = current_tick - last_decay
        should_run_memory_decay = ticks_since_last_decay >= DECAY_EVERY

        return TemporalContext(
            current_tick=current_tick,
            game_day=game_day,
            game_hour=game_hour,
            is_new_day=(game_hour == 0 and current_tick > 0),
            ticks_since_last_decay=ticks_since_last_decay,
            should_run_memory_decay=should_run_memory_decay,
        )

    def advance_tick(self, campaign_id: str) -> TemporalContext:
        """Инкрементирует тик, обновляет кэши и возвращает новый TemporalContext."""
        current = self._tick_cache.get(campaign_id)
        if current is None:
            current = self._load_tick(campaign_id)

        new_tick = current + 1
        self._tick_cache[campaign_id] = new_tick

        # Гибридное сохранение: JSON пишется раз в TICK_SAVE_INTERVAL тиков
        unsaved = self._ticks_since_save.get(campaign_id, 0) + 1
        if unsaved >= TICK_SAVE_INTERVAL:
            self._save_tick(campaign_id, new_tick)
            self._ticks_since_save[campaign_id] = 0
        else:
            self._ticks_since_save[campaign_id] = unsaved

        return self.get_temporal_context(campaign_id)

    def mark_decay_executed(self, campaign_id: str) -> None:
        """Фиксирует, что memory decay был запущен на текущем тике."""
        self._last_decay_tick[campaign_id] = self.get_current_tick(campaign_id)

    # ── Публичные методы (совместимость с LifeEngine) ─────────────────────

    def get_current_tick(self, campaign_id: str) -> int:
        """Возвращает текущий sim_tick (из RAM кэша или JSON)."""
        cached = self._tick_cache.get(campaign_id)
        if cached is not None:
            return cached
        return self._load_tick(campaign_id)

    def flush_ticks(self, campaign_id: Optional[str] = None) -> None:
        """Принудительная запись tick(s) в JSON (shutdown/save)."""
        if campaign_id:
            tick = self._tick_cache.get(campaign_id)
            if tick is not None:
                self._save_tick(campaign_id, tick)
                self._ticks_since_save[campaign_id] = 0
        else:
            for cid, tick in self._tick_cache.items():
                self._save_tick(cid, tick)
            self._ticks_since_save.clear()

    def invalidate_cache(self, campaign_id: str) -> None:
        """Сбрасывает RAM кэш тиков (при внешнем изменении JSON)."""
        self._tick_cache.pop(campaign_id, None)

    def cleanup_campaign(self, campaign_id: str) -> None:
        """Очищает RAM кэши тиков для кампании."""
        self._tick_cache.pop(campaign_id, None)
        self._ticks_since_save.pop(campaign_id, None)
        self._last_decay_tick.pop(campaign_id, None)

    def cleanup_all(self) -> None:
        """Очищает все RAM кэши тиков."""
        self._tick_cache.clear()
        self._ticks_since_save.clear()
        self._last_decay_tick.clear()

    # ADR-O-302 / DEBT-TIME-3: get_idle_seconds УДАЛЁН.
    # Метод вычислял idle time через datetime.now(), что нарушало §14 (Law of Singular Time)
    # и §15.1 (Law of Wall-Clock Isolation). TICK_CATCHUP мёртв с ADR-047.

    # ADR-O-302 / §14: get_world_ticks_elapsed УДАЛЁН.
    # Метод вычислял тики из datetime.now(), нарушая Закон Единичного Времени.
    # Тики симуляции — единственный авторитет, реальное время не может их предсказать.

    # ── Внутренние методы (перенесены из LifeEngine) ──────────────────────

    def _tick_file_path(self, campaign_id: str) -> Path:
        return self._sessions_dir / campaign_id / "world_tick.json"

    def _load_tick(self, campaign_id: str) -> int:
        path = self._tick_file_path(campaign_id)
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data.get("sim_tick", 0)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[TEMPORAL_ENGINE] Ошибка чтения tick: {e}")
            return 0

    def _save_tick(self, campaign_id: str, tick: int) -> None:
        path = self._tick_file_path(campaign_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        _existing = {}
        if path.exists():
            try:
                _existing = json.loads(path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, OSError):
                pass

        data = {
            "sim_tick": tick,
            "updated_at": datetime.now().isoformat(),  # §15.2: Persistence metadata
            # created_at пишется один раз при создании — не перезаписывается
            "created_at": _existing.get("created_at") or datetime.now().isoformat(),  # §15.2: Persistence metadata
        }
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"[TEMPORAL_ENGINE] Ошибка сохранения tick: {e}")
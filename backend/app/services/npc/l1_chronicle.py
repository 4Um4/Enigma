"""
path: backend/app/services/npc/l1_chronicle.py
Назначение: Хроника деформаций идентичности (L1). Интерпретатор причинности во времени.
Зависимости: backend/app/domain/identity_events.py, app.services.memory.sqlite_store
Основные сущности: L1Chronicle
ADR-L1-PERSIST: L1Chronicle персистируется в SQLite. На рестарте события восстанавливаются. In-memory dict — только кэш на текущую сессию.
"""

import logging
import math
from typing import Dict, List, Tuple

from app.domain.identity_events import TraitDriftEvent

_TAU_DECAY: float = 50.0
_logger = logging.getLogger(__name__)


class L1Chronicle:
    """
    Append-only causal trace of identity deformation.
    Truth Layer (Ontology): хранит всё, не интерпретирует ничего.

    Персистентность: SQLite (через sqlite_store). In-memory dict — кэш.
    """

    def __init__(self, store=None, campaign_id: str = ""):
        """
        Args:
            store: SQLiteStore instance. Если None — in-memory only (только для тестов).
            campaign_id: ID кампании для namespace.
        """
        self._store = store
        self._campaign_id = campaign_id
        # L1-T3 Fix: Per-NPC partitioning. Никакого global event soup.
        self._events: Dict[str, List[TraitDriftEvent]] = {}
        self._loaded: bool = False  # lazy load from SQLite

        # ADR-L1-PERSIST FIX: Гарантируем создание схемы при инициализации,
        # чтобы _ensure_loaded не падал на SELECT до CREATE TABLE.
        if self._store:
            try:
                self._store.execute("""
                    CREATE TABLE IF NOT EXISTS l1_chronicle_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        campaign_id TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        tick_id INTEGER NOT NULL,
                        source_id TEXT NOT NULL,
                        effect_value REAL NOT NULL,
                        observation_weight REAL NOT NULL,
                        event_type TEXT NOT NULL,
                        archived INTEGER DEFAULT 0
                    )
                """)
                self._store.execute("""
                    CREATE TABLE IF NOT EXISTS l1_chronicle_archive (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        campaign_id TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        tick_id INTEGER NOT NULL,
                        source_id TEXT NOT NULL,
                        effect_value REAL NOT NULL,
                        observation_weight REAL NOT NULL,
                        event_type TEXT NOT NULL
                    )
                """)
            except Exception as _init_err:
                _logger.error(f"[L1_CHRONICLE] Не удалось инициализировать схему БД: {_init_err}")

    def bind_campaign(self, campaign_id: str) -> None:
        """Привязка к campaign_id для ленивой загрузки из SQLite."""
        if self._campaign_id != campaign_id:
            self._campaign_id = campaign_id
            # Сбрасываем кэш, чтобы загрузить данные для новой кампании
            self._events = {}
            self._loaded = False

        # ADR-L1-PERSIST: Гарантируем загрузку из SQLite при привязке.
        # Без этого новый инстанс L1Chronicle остаётся пустым (in-memory).
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        """Lazy load из SQLite при первом обращении."""
        if self._loaded or self._store is None:
            return

        # FIX: Если campaign_id пустой — auto-detect из SQLite (последняя активная кампания).
        _campaign_to_load = self._campaign_id
        if not _campaign_to_load:
            try:
                _rows = self._store.query(
                    "SELECT campaign_id FROM l1_chronicle_events WHERE archived = 0 "
                    "GROUP BY campaign_id ORDER BY MAX(tick_id) DESC LIMIT 1"
                )
                if _rows:
                    _campaign_to_load = _rows[0]["campaign_id"]
                    _logger.info(
                        f"[L1_CHRONICLE] auto-bound to campaign='{_campaign_to_load}' "
                        f"(no explicit bind_campaign call)"
                    )
                    self._campaign_id = _campaign_to_load
            except Exception as e:
                logger.debug(f"SQLite load empty/failed: {e}")  # SQLite может быть пустой — это норма для нового game_loop

        if not _campaign_to_load:
            self._loaded = True
            return  # Нечего загружать

        try:
            # Создаём таблицу, если её нет
            self._store.execute("""
                CREATE TABLE IF NOT EXISTS l1_chronicle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    tick_id INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    effect_value REAL NOT NULL,
                    observation_weight REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    archived INTEGER DEFAULT 0
                )
            """)
            self._store.execute("""
                CREATE INDEX IF NOT EXISTS idx_l1_chronicle_npc
                ON l1_chronicle_events(campaign_id, target_id, tick_id)
            """)

            # S94-T2.3: L1Chronicle TTL — Архивация старых событий
            self._store.execute("""
                CREATE TABLE IF NOT EXISTS l1_chronicle_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    tick_id INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    effect_value REAL NOT NULL,
                    observation_weight REAL NOT NULL,
                    event_type TEXT NOT NULL
                )
            """)
            self._store.execute("""
                CREATE INDEX IF NOT EXISTS idx_l1_archive_npc
                ON l1_chronicle_archive(campaign_id, target_id, tick_id)
            """)

            rows = self._store.query(
                "SELECT target_id, tick_id, source_id, effect_value, observation_weight, event_type "
                "FROM l1_chronicle_events "
                "WHERE campaign_id = ? ORDER BY tick_id ASC",
                (self._campaign_id,),
            )
            for row in rows:
                event = TraitDriftEvent(
                    tick_id=row["tick_id"],
                    target_id=row["target_id"],
                    source_id=row["source_id"],
                    effect_value=row["effect_value"],
                    observation_weight=row["observation_weight"],
                    event_type=row["event_type"],
                )
                if event.target_id not in self._events:
                    self._events[event.target_id] = []
                self._events[event.target_id].append(event)
            self._loaded = True
            _logger.debug(
                f"[L1_CHRONICLE] loaded {sum(len(v) for v in self._events.values())} events "
                f"from SQLite for campaign={self._campaign_id}"
            )
        except Exception as e:
            # Fail-fast: если SQLite сломан — это критическая ошибка.
            _logger.error(
                f"[L1_CHRONICLE] CRITICAL: failed to load from SQLite: {e}. "
                f"L1Chronicle cannot start without persistence."
            )
            raise

    def append(self, event: TraitDriftEvent) -> None:
        """Единственная точка записи. Без проверки времени (L1-T2 Fix)."""
        self._ensure_loaded()
        if event.target_id not in self._events:
            self._events[event.target_id] = []

        # Idempotency Guard: предотвращаем дублирование событий
        # с одинаковым tick_id, target_id и event_type.
        _exists = any(
            e.tick_id == event.tick_id and e.event_type == event.event_type
            for e in self._events[event.target_id]
        )
        if _exists:
            return  # Событие уже зафиксировано

        self._events[event.target_id].append(event)

        # Персистентная запись
        if self._store is not None:
            try:
                self._store.execute(
                    "INSERT INTO l1_chronicle_events "
                    "(campaign_id, target_id, tick_id, source_id, effect_value, observation_weight, event_type) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        self._campaign_id,
                        event.target_id,
                        event.tick_id,
                        event.source_id,
                        event.effect_value,
                        event.observation_weight,
                        event.event_type,
                    ),
                )
            except Exception as e:
                _logger.error(
                    f"[L1_CHRONICLE] CRITICAL: failed to persist event {event}: {e}. "
                    f"In-memory state may diverge from SQLite."
                )
                raise

    def commit_tick_buffer(
        self, buffer: List[TraitDriftEvent], current_tick: int
    ) -> None:
        """Атомарная фиксация буфера от Оркестратора. Валидация времени — задача Оркестратора."""
        self._ensure_loaded()
        for event in buffer:
            # Idempotency Guard: предотвращаем дублирование событий в рамках одного тика
            # для одного и того же target_id и event_type.
            _exists = any(
                e.tick_id == event.tick_id
                and e.target_id == event.target_id
                and e.event_type == event.event_type
                for e in self._events.get(event.target_id, [])
            )
            if not _exists:
                self.append(event)

    def archive_old_events(
        self, current_tick: int, max_ticks_in_memory: int = 2000
    ) -> None:
        """S94-T2.3: Перенос старых событий в архив. Очищает RAM кэш и активную таблицу."""
        self._ensure_loaded()
        if self._store is None:
            return

        _threshold = current_tick - max_ticks_in_memory
        if _threshold <= 0:
            return

        try:
            # 1. Перенос в архивную таблицу
            self._store.execute(
                "INSERT INTO l1_chronicle_archive "
                "(campaign_id, target_id, tick_id, source_id, effect_value, observation_weight, event_type) "
                "SELECT campaign_id, target_id, tick_id, source_id, effect_value, observation_weight, event_type "
                "FROM l1_chronicle_events "
                "WHERE campaign_id = ? AND tick_id < ?",
                (self._campaign_id, _threshold),
            )
            # BUG-PERC-013 FIX: Мягкая архивация вместо удаления (Rule 28: Append-only)
            self._store.execute(
                "UPDATE l1_chronicle_events SET archived = 1 WHERE campaign_id = ? AND tick_id < ?",
                (self._campaign_id, _threshold),
            )
            # 3. Очистка RAM кэша
            for npc_id in list(self._events.keys()):
                self._events[npc_id] = [
                    e for e in self._events[npc_id] if e.tick_id >= _threshold
                ]
                if not self._events[npc_id]:
                    del self._events[npc_id]

            _logger.info(
                f"[L1_CHRONICLE] Archived events older than tick {_threshold} for campaign={self._campaign_id}"
            )
        except Exception as e:
            _logger.error(
                f"[L1_CHRONICLE] Failed to archive old events: {e}", exc_info=True
            )

    def query_raw(self, npc_id: str, t_from: int = 0) -> List[TraitDriftEvent]:
        """Чтение сырой правды. Читает из RAM (актуальные) + SQLite (архив) для PatternDetector."""
        self._ensure_loaded()

        # 1. Читаем актуальные из RAM (быстро)
        active_events = self._events.get(npc_id, [])
        if t_from > 0:
            active_events = [e for e in active_events if e.tick_id >= t_from]

        # 2. Если есть хранилище, читаем архив (события, которых уже нет в RAM)
        # PatternDetector должен видеть всю историю для кристаллизации убеждений.
        if self._store is not None:
            try:
                _rows = self._store.query(
                    "SELECT target_id, tick_id, source_id, effect_value, observation_weight, event_type "
                    "FROM l1_chronicle_archive "
                    "WHERE campaign_id = ? AND target_id = ? AND tick_id >= ? "
                    "ORDER BY tick_id ASC",
                    (self._campaign_id, npc_id, t_from),
                )
                archive_events = [
                    TraitDriftEvent(
                        tick_id=row["tick_id"],
                        target_id=row["target_id"],
                        source_id=row["source_id"],
                        effect_value=row["effect_value"],
                        observation_weight=row["observation_weight"],
                        event_type=row["event_type"],
                    )
                    for row in _rows
                ]
                return archive_events + active_events
            except Exception as e:
                _logger.warning(
                    f"[L1_CHRONICLE] Failed to query archive for {npc_id}: {e}"
                )

        return active_events

    def query_weighted(
        self, npc_id: str, current_tick: int, t_from: int = 0
    ) -> List[Tuple[TraitDriftEvent, float]]:
        """
        Чтение правды с весами для проекции.
        Возвращает ВСЕ события (порог убран), Резолвер решит, что важно.
        """
        self._ensure_loaded()
        if npc_id not in self._events:
            return []

        result = []
        for e in self._events[npc_id]:
            if e.tick_id < t_from:
                continue

            time_delta = current_tick - e.tick_id
            weight = math.exp(-time_delta / _TAU_DECAY) if time_delta > 0 else 1.0
            result.append((e, weight))

        return result

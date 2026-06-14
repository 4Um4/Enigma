# backend/app/services/state/sqlite_persistence_adapter.py
"""
SqlitePersistenceAdapter — SQLite реализация PersistencePort.

Устав 4.2.1: SQLite = runtime truth. Atomic commit. Всё или ничего.
JSON файлы = export для человека, не runtime truth.

Принцип: key-value хранилище JSON blob'ов в SQLite.
Ключи: scene:{campaign_id}, runtime:{session_id}, npcs:{campaign_id}

path: /backend/app/services/state/sqlite_persistence_adapter.py
Назначение: SQLite реализация PersistencePort с атомарным коммитом (Устав 4.2.1)
Зависимости: sqlite3 (stdlib), persistence_port, json, logging
Основные сущности: SqlitePersistenceAdapter
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.state.persistence_port import PersistencePort

logger = logging.getLogger(__name__)


class SqlitePersistenceAdapter(PersistencePort):
    """
    SQLite реализация порта сохранения.

    Каждая операция save_* — отдельный INSERT OR REPLACE.
    atomic_commit — атомарная транзакция (сцена + NPC runtime + events вместе).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Ленивое подключение — не держим соединение при импорте."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                isolation_level="IMMEDIATE",  # немедленная блокировка на запись
            )
            # WAL mode — читатели не блокируют писателей
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        """Создаёт таблицу если не существует."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS state_kv (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.commit()
        logger.debug(f"[SQLITE_PERSISTENCE] Инициализирован: {self._db_path}")

    def _upsert(self, key: str, value: dict) -> None:
        """INSERT OR REPLACE одной записью."""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO state_kv (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False, default=lambda o: list(o) if isinstance(o, set) else str(o)), datetime.now(timezone.utc).isoformat()),
        )

    def _select(self, key: str) -> Optional[dict]:
        """SELECT одной записи. None если не найдена."""
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM state_kv WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError as e:
            logger.error(f"[SQLITE_PERSISTENCE] Ошибка парсинга JSON для ключа {key}: {e}")
            return None

    def save_scene(self, campaign_id: str, scene_state: dict) -> None:
        """Сохраняет состояние сцены."""
        try:
            self._upsert(f"scene:{campaign_id}", scene_state)
            self._get_conn().commit()
            logger.debug(f"[SQLITE_PERSISTENCE] Scene saved: {campaign_id}")
        except sqlite3.Error as e:
            logger.error(f"[SQLITE_PERSISTENCE] Error saving scene: {e}")
            self._get_conn().rollback()

    def save_npcs(self, npc_dicts: list[dict]) -> None:
        """Сохраняет NPC статические данные (legacy)."""
        try:
            self._upsert("npcs:major", npc_dicts)
            self._get_conn().commit()
            logger.debug(f"[SQLITE_PERSISTENCE] NPCs saved: {len(npc_dicts)} records")
        except sqlite3.Error as e:
            logger.error(f"[SQLITE_PERSISTENCE] Error saving NPCs: {e}")
            self._get_conn().rollback()

    def save_npc_runtime(self, session_id: str, npc_dicts: list[dict]) -> None:
        """Сохраняет runtime-состояние NPC в сессию."""
        if not session_id:
            logger.warning("[SQLITE_PERSISTENCE] save_npc_runtime без session_id — пропуск")
            return
        try:
            self._upsert(f"runtime:{session_id}", npc_dicts)
            self._get_conn().commit()
            logger.debug(f"[SQLITE_PERSISTENCE] NPC runtime saved: {session_id} ({len(npc_dicts)} records)")
        except sqlite3.Error as e:
            logger.error(f"[SQLITE_PERSISTENCE] Error saving NPC runtime: {e}")

    def delete_campaign(self, campaign_id: str) -> None:
        """Удаляет все данные кампании (scene + runtime) из SQLite.
        New Game: полная очистка persistence-слоя."""
        try:
            conn = self._get_conn()
            conn.execute(
                "DELETE FROM state_kv WHERE key = ? OR key = ?",
                (f"scene:{campaign_id}", f"runtime:{campaign_id}")
            )
            conn.commit()
            logger.info(f"[SQLITE_PERSISTENCE] Campaign deleted: {campaign_id}")
        except sqlite3.Error as e:
            logger.error(f"[SQLITE_PERSISTENCE] Error deleting campaign {campaign_id}: {e}")
            self._get_conn().rollback()
            self._get_conn().rollback()

    def load_scene(self, campaign_id: str) -> dict | None:
        """Загружает состояние сцены из SQLite."""
        return self._select(f"scene:{campaign_id}")

    def load_npc_runtime(self, session_id: str) -> list[dict] | None:
        """Загружает runtime-состояние NPC из сессии."""
        if not session_id:
            return None
        data = self._select(f"runtime:{session_id}")
        if data is None:
            return None
        if isinstance(data, list):
            return data
        logger.warning(f"[SQLITE_PERSISTENCE] runtime:{session_id} не список, а {type(data)}")
        return None

    def atomic_commit(
        self,
        campaign_id: str,
        scene_state: dict,
        npc_states: list[dict] | None = None,
        events: list[dict] | None = None,
    ) -> bool:
        """Атомарный коммит: сцена + NPC runtime + events в одной транзакции.

        Устав 4.2.1: всё или ничего.
        Events сохраняются как JSON blob для аудита (ключ events_tick:{campaign_id}).
        """
        conn = self._get_conn()
        try:
            self._upsert(f"scene:{campaign_id}", scene_state)
            if npc_states is not None:
                self._upsert(f"runtime:{campaign_id}", npc_states)
            if events is not None:
                self._upsert(f"events_tick:{campaign_id}", events)
            conn.commit()
            logger.debug(f"[SQLITE_PERSISTENCE] Atomic commit OK: {campaign_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"[SQLITE_PERSISTENCE] Atomic commit FAILED ({campaign_id}): {e} — откат")
            conn.rollback()
            return False

    def close(self) -> None:
        """Закрывает соединение. Вызывать при shutdown."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
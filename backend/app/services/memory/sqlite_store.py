# backend/app/services/memory/sqlite_store.py
"""
Этап 11 — SqliteMemoryStore: SQLite backend для памяти.

Тот же интерфейс что JsonMemoryStore (append/recent) — drop-in замена.
Дополнительно: структурированная таблица event_memories для поиска по полям.

Закон 4.2.1: SQLite = runtime truth. Atomic commit.

path: backend/app/services/memory/sqlite_store.py
Назначение: SQLite backend для памяти — drop-in замена JsonMemoryStore с расширенным API для EventMemory
Зависимости: sqlite3, json, pathlib, typing
Основные сущности: SqliteMemoryStore
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger(__name__)


class _SafeEncoder(json.JSONEncoder):
    """Совместимость с JsonMemoryStore — сериализация dataclass/pydantic."""
    def default(self, o: Any) -> Any:
        import dataclasses
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "dict"):
            return o.dict()
        if isinstance(o, set):
            return list(o)
        return str(o)


class SqliteMemoryStore:
    """SQLite backend — замена JsonMemoryStore с расширенным API.

    Интерфейс совместимости:
        append(collection, payload) -> str
        recent(collection, limit) -> List[Dict]
    """

    def __init__(self, db_path: str | Path = "data/enigma_memory.db") -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        # uvicorn обслуживает запросы в разных потоках — соединение
        # создаётся при старте, используется из worker-потоков
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        # Generic entries — совместимость с JsonMemoryStore
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY,
                collection TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_collection
            ON entries(collection, timestamp DESC)
        """)
        # Структурированные EventMemory — для поиска по полям (Этап 11.2)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS event_memories (
                id TEXT PRIMARY KEY,
                npc_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                target_id TEXT DEFAULT '',
                emotion_tag TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                day INTEGER DEFAULT 0,
                importance REAL DEFAULT 0.0,
                accessibility REAL DEFAULT 1.0,
                clarity REAL DEFAULT 1.0,
                confidence REAL DEFAULT 1.0,
                decay_rate REAL DEFAULT 0.05,
                stage TEXT DEFAULT 'FRESH',
                sequence_id INTEGER DEFAULT 0,
                tags_json TEXT DEFAULT '[]',
                is_secret INTEGER DEFAULT 0,
                known_by_json TEXT DEFAULT '[]',
                hidden_from_json TEXT DEFAULT '[]',
                fulfilled INTEGER DEFAULT 0,
                contract_ref TEXT DEFAULT '',
                is_compressed INTEGER DEFAULT 0,
                compressed_from_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_memories_npc
            ON event_memories(campaign_id, npc_id, importance DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_memories_tags
            ON event_memories(campaign_id, npc_id, tags_json)
        """)
        self._conn.commit()

    # ── Совместимость с JsonMemoryStore ──────────────────────────────

    def append(self, collection: str, payload: Dict[str, Any]) -> str:
        entry_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False, cls=_SafeEncoder)
        try:
            self._conn.execute(
                "INSERT INTO entries (id, collection, timestamp, payload_json) VALUES (?, ?, ?, ?)",
                (entry_id, collection, timestamp, payload_json),
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"[SQLITE] append to {collection} failed: {e}")
            self._conn.rollback()
        return entry_id

    def recent(self, collection: str, limit: int = 25) -> List[Dict[str, Any]]:
        try:
            rows = self._conn.execute(
                "SELECT id, timestamp, payload_json FROM entries WHERE collection = ? ORDER BY timestamp DESC LIMIT ?",
                (collection, limit),
            ).fetchall()
            result = []
            for row in rows:
                entry = json.loads(row["payload_json"])
                entry["id"] = row["id"]
                entry["timestamp"] = row["timestamp"]
                result.append(entry)
            return result
        except Exception as e:
            logger.error(f"[SQLITE] recent from {collection} failed: {e}")
            return []

    # ── EventMemory — структурированное API ───────────────────────────

    def save_event_memory(
        self,
        mem_id: str,
        campaign_id: str,
        mem_data: Dict[str, Any],
    ) -> None:
        """Сохраняет EventMemory в структурированную таблицу."""
        import dataclasses
        from app.models.npc_state import EventMemory

        # Если передали dataclass — сериализуем
        if dataclasses.is_dataclass(mem_data) and not isinstance(mem_data, type):
            d = dataclasses.asdict(mem_data)
        else:
            d = mem_data

        tags = d.get("tags", ())
        known_by = d.get("known_by", ())
        hidden_from = d.get("hidden_from", ())
        compressed_from = d.get("compressed_from", ())

        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO event_memories (
                    id, npc_id, campaign_id, event_type, target_id, emotion_tag,
                    summary, day, importance, accessibility, clarity, confidence,
                    decay_rate, stage, sequence_id, tags_json, is_secret,
                    known_by_json, hidden_from_json, fulfilled, contract_ref,
                    is_compressed, compressed_from_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mem_id,
                    d.get("npc_id", ""),
                    campaign_id,
                    d.get("event_type", ""),
                    d.get("target_id", ""),
                    d.get("emotion_tag", ""),
                    d.get("summary", ""),
                    d.get("day", 0),
                    d.get("importance", 0.0),
                    d.get("accessibility", 1.0),
                    d.get("clarity", 1.0),
                    d.get("confidence", 1.0),
                    d.get("decay_rate", 0.05),
                    d.get("stage", "FRESH"),
                    d.get("sequence_id", 0),
                    json.dumps(list(tags)),
                    int(d.get("is_secret", False)),
                    json.dumps(list(known_by)),
                    json.dumps(list(hidden_from)),
                    int(d.get("fulfilled", False)),
                    d.get("contract_ref", ""),
                    int(d.get("is_compressed", False)),
                    json.dumps(list(compressed_from)),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"[SQLITE] save_event_memory failed: {e}")
            self._conn.rollback()

    def load_event_memories(
        self,
        campaign_id: str,
        npc_id: str,
    ) -> List[Dict[str, Any]]:
        """Загружает все EventMemory для NPC из SQLite."""
        try:
            rows = self._conn.execute(
                """SELECT * FROM event_memories
                   WHERE campaign_id = ? AND npc_id = ?
                   ORDER BY importance DESC""",
                (campaign_id, npc_id),
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["tags"] = tuple(json.loads(d.pop("tags_json")))
                d["known_by"] = tuple(json.loads(d.pop("known_by_json")))
                d["hidden_from"] = tuple(json.loads(d.pop("hidden_from_json")))
                d["compressed_from"] = tuple(json.loads(d.pop("compressed_from_json")))
                d["is_secret"] = bool(d["is_secret"])
                d["fulfilled"] = bool(d["fulfilled"])
                d["is_compressed"] = bool(d["is_compressed"])
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"[SQLITE] load_event_memories failed: {e}")
            return []

    def save_event_memories_batch(
        self,
        campaign_id: str,
        npc_id: str,
        memories: List[Dict[str, Any]],
    ) -> None:
        """Atomic commit: все записи NPC за тик — одна транзакция (Закон 4.2.1)."""
        try:
            for i, d in enumerate(memories):
                mem_id = f"{npc_id}_seq_{d.get('sequence_id', i)}"
                tags = d.get("tags", ())
                known_by = d.get("known_by", ())
                hidden_from = d.get("hidden_from", ())
                compressed_from = d.get("compressed_from", ())
                self._conn.execute(
                    """INSERT OR REPLACE INTO event_memories (
                        id, npc_id, campaign_id, event_type, target_id, emotion_tag,
                        summary, day, importance, accessibility, clarity, confidence,
                        decay_rate, stage, sequence_id, tags_json, is_secret,
                        known_by_json, hidden_from_json, fulfilled, contract_ref,
                        is_compressed, compressed_from_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        mem_id, npc_id, campaign_id,
                        d.get("event_type", ""), d.get("target_id", ""),
                        d.get("emotion_tag", ""), d.get("summary", ""),
                        d.get("day", 0), d.get("importance", 0.0),
                        d.get("accessibility", 1.0), d.get("clarity", 1.0),
                        d.get("confidence", 1.0), d.get("decay_rate", 0.05),
                        d.get("stage", "FRESH"), d.get("sequence_id", 0),
                        json.dumps(list(tags)), int(d.get("is_secret", False)),
                        json.dumps(list(known_by)), json.dumps(list(hidden_from)),
                        int(d.get("fulfilled", False)), d.get("contract_ref", ""),
                        int(d.get("is_compressed", False)),
                        json.dumps(list(compressed_from)),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            self._conn.commit()
        except Exception as e:
            logger.error(f"[SQLITE] batch save failed for {npc_id}: {e}")
            self._conn.rollback()

    def delete_campaign(self, campaign_id: str) -> int:
        """Удаляет все записи кампании из обеих таблиц.
        Вызывается из new_game() для полной очистки памяти."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM event_memories WHERE campaign_id = ?", (campaign_id,))
        deleted_events = cur.rowcount
        cur.execute("DELETE FROM entries WHERE collection LIKE ?", (f"%{campaign_id}%",))
        deleted_entries = cur.rowcount
        self._conn.commit()
        return deleted_events + deleted_entries

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
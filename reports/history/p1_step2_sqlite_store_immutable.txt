from __future__ import annotations

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


import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
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
        # S210 (P0 L1): connection общий между потоками (check_same_thread=False)
        # — доступ обязан сериализоваться. Без Lock: гонка in_transaction→commit
        # ("cannot commit - no transaction is active", TOCTOU).
        self._lock = threading.RLock()
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
        # KV-хранилище state-коллекций — контракт JsonMemoryStore.save_state/load_state.
        # Одна строка на коллекцию (identity_cache и другие state-кэши).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS state_collections (
                collection TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # EMRL E1.2: кристаллы смысла — LTM-знания NPC. PK = триплет +
        # origin_reference (два одинаковых триплета от разных источников —
        # ДВЕ записи, анти-каннибализация урока 9.6).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_crystals (
                campaign_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                origin_reference TEXT NOT NULL,
                object TEXT NOT NULL,
                source TEXT NOT NULL,
                related_episodes_json TEXT DEFAULT '[]',
                confidence REAL DEFAULT 0.5,
                retrieval_strength REAL DEFAULT 0.5,
                emotional_weight REAL DEFAULT 0.0,
                last_reinforced INTEGER DEFAULT 0,
                times_recalled INTEGER DEFAULT 0,
                PRIMARY KEY (campaign_id, owner_id, subject, predicate, origin_reference)
            )
        """)
        # EMRL E1.0: проекции интерпретации над EventMemory (не SSOT).
        # PK = (campaign, owner, content_reference, source_id): trace_id.
        # E1: заполняется только diagnostic-резолвером; production-дельты — E2.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS experience_traces (
                campaign_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                content_reference TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                meaning_json TEXT,
                valence REAL DEFAULT 0.0,
                arousal REAL DEFAULT 0.0,
                novelty REAL DEFAULT 0.0,
                personal_relevance REAL DEFAULT 0.0,
                social_relevance REAL DEFAULT 0.0,
                identity_relevance REAL DEFAULT 0.0,
                belief_relevance REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.5,
                retrieval_strength REAL DEFAULT 0.5,
                timestamp INTEGER DEFAULT 0,
                diagnostic INTEGER DEFAULT 0,
                applied_consumers_json TEXT DEFAULT '[]',
                PRIMARY KEY (campaign_id, owner_id, content_reference, source_id)
            )
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
            # S210 (P0 L1): execute+commit — атомарная пара под Lock;
            # rollback в except — тоже операция соединения, под Lock
            with self._lock:
                self._conn.execute(
                    "INSERT INTO entries (id, collection, timestamp, payload_json) VALUES (?, ?, ?, ?)",
                    (entry_id, collection, timestamp, payload_json),
                )
                self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[SQLITE] append to {collection} failed: {e}")
            with self._lock:
                self._conn.rollback()
        return entry_id

    def recent(self, collection: str, limit: int = 25) -> List[Dict[str, Any]]:
        try:
            # S210: чтение по общему соединению — под Lock
            with self._lock:
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
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"[SQLITE] recent from {collection} failed: {e}")
            return []

    def save_state(self, collection: str, payload: Dict[str, Any]) -> None:
        """Перезаписывает состояние коллекции (контракт JsonMemoryStore).

        KV-семантика: одна строка на коллекцию, INSERT OR REPLACE.
        Сбой логируется и не поднимается — паритет с JSON-стором:
        identity_cache не должен убивать тик (L4: громкость = лог).
        """
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, cls=_SafeEncoder)
        except TypeError as e:
            logger.error(f"[SQLITE] save_state serialize {collection} failed: {e}")
            return
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO state_collections
                       (collection, payload_json, updated_at) VALUES (?, ?, ?)""",
                    (collection, payload_json, datetime.now(timezone.utc).isoformat()),
                )
                self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[SQLITE] save_state to {collection} failed: {e}")
            with self._lock:
                self._conn.rollback()

    def load_state(self, collection: str) -> Dict[str, Any]:
        """Загружает состояние коллекции. {} если записи нет (контракт JsonMemoryStore)."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT payload_json FROM state_collections WHERE collection = ?",
                    (collection,),
                ).fetchone()
            if row is None:
                return {}
            return json.loads(row["payload_json"])
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"[SQLITE] load_state from {collection} failed: {e}")
            return {}

    def save_trace(self, campaign_id: str, trace: Any) -> None:
        """EMRL E1.0: upsert проекции трейса. PK стабилен (trace_id)."""
        import json as _json

        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO experience_traces
                       (campaign_id, owner_id, content_reference, source_id,
                        source_type, actor_id, meaning_json, valence, arousal,
                        novelty, personal_relevance, social_relevance,
                        identity_relevance, belief_relevance, confidence,
                        retrieval_strength, timestamp, diagnostic,
                        applied_consumers_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        campaign_id,
                        trace.owner_id,
                        trace.content_reference,
                        trace.source_id,
                        trace.source_type.value,
                        trace.actor_id,
                        _json.dumps(trace.meaning, ensure_ascii=False)
                        if trace.meaning is not None
                        else None,
                        max(-1.0, min(1.0, trace.valence)),
                        max(0.0, min(1.0, trace.arousal)),
                        max(0.0, min(1.0, trace.novelty)),
                        max(0.0, min(1.0, trace.personal_relevance)),
                        max(0.0, min(1.0, trace.social_relevance)),
                        max(0.0, min(1.0, trace.identity_relevance)),
                        max(0.0, min(1.0, trace.belief_relevance)),
                        max(0.0, min(1.0, trace.confidence)),
                        max(0.0, min(1.0, trace.retrieval_strength)),
                        int(trace.timestamp),
                        int(trace.diagnostic),
                        _json.dumps(list(trace.applied_consumers)),
                    ),
                )
                self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[SQLITE] save_trace failed: {e}")
            with self._lock:
                self._conn.rollback()

    def load_traces(self, campaign_id: str, owner_id: str) -> List[Dict[str, Any]]:
        """EMRL E1.0: все трейсы NPC кампании (проекции, не SSOT)."""
        import json as _json

        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM experience_traces WHERE campaign_id = ? AND owner_id = ?",
                    (campaign_id, owner_id),
                ).fetchall()
            result: List[Dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                d["meaning"] = _json.loads(d.pop("meaning_json")) if d.get("meaning_json") else None
                d["applied_consumers"] = tuple(_json.loads(d.pop("applied_consumers_json")))
                d["diagnostic"] = bool(d["diagnostic"])
                result.append(d)
            return result
        except (sqlite3.Error, _json.JSONDecodeError) as e:
            logger.error(f"[SQLITE] load_traces failed: {e}")
            return []

    def save_crystal(self, campaign_id: str, crystal: Any) -> None:
        """EMRL E1.2: upsert кристалла. PK стабилен (триплет+origin)."""
        import json as _json

        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO memory_crystals
                       (campaign_id, owner_id, subject, predicate,
                        origin_reference, object, source,
                        related_episodes_json, confidence,
                        retrieval_strength, emotional_weight,
                        last_reinforced, times_recalled)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        campaign_id,
                        crystal.owner_id,
                        crystal.subject,
                        crystal.predicate,
                        crystal.origin_reference,
                        crystal.object,
                        crystal.source,
                        _json.dumps(list(crystal.related_episodes)),
                        max(0.0, min(1.0, crystal.confidence)),
                        max(0.0, min(1.0, crystal.retrieval_strength)),
                        max(-1.0, min(1.0, crystal.emotional_weight)),
                        int(crystal.last_reinforced),
                        int(crystal.times_recalled),
                    ),
                )
                self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[SQLITE] save_crystal failed: {e}")
            with self._lock:
                self._conn.rollback()

    def load_crystals(self, campaign_id: str, owner_id: str) -> List[Dict[str, Any]]:
        """EMRL E1.2: все кристаллы NPC кампании."""
        import json as _json

        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT * FROM memory_crystals WHERE campaign_id = ? AND owner_id = ?",
                    (campaign_id, owner_id),
                ).fetchall()
            result: List[Dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                d["related_episodes"] = tuple(
                    _json.loads(d.pop("related_episodes_json"))
                )
                result.append(d)
            return result
        except (sqlite3.Error, _json.JSONDecodeError) as e:
            logger.error(f"[SQLITE] load_crystals failed: {e}")
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
            # S210: execute+commit — атомарная пара под Lock
            with self._lock:
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
        except (sqlite3.Error, json.JSONDecodeError, TypeError) as e:
            logger.error(f"[SQLITE] save_event_memory failed: {e}")
            with self._lock:
                self._conn.rollback()

    def load_event_memories(
        self,
        campaign_id: str,
        npc_id: str,
    ) -> List[Dict[str, Any]]:
        """Загружает все EventMemory для NPC из SQLite."""
        try:
            # S210: чтение по общему соединению — под Lock
            with self._lock:
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
        except (sqlite3.Error, json.JSONDecodeError) as e:
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
            # S210: весь батч — одна транзакция под Lock: чужой commit
            # посреди цикла разорвал бы атомарность (Закон 4.2.1)
            with self._lock:
                for i, d in enumerate(memories):
                    # Закон 4.2.1: Откат всей транзакции при невалидных данных (None вместо dict)
                    if not isinstance(d, dict):
                        raise TypeError(f"Invalid memory data: expected dict, got {type(d)}")
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
                            mem_id,
                            npc_id,
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
        except (sqlite3.Error, json.JSONDecodeError, TypeError) as e:
            logger.error(f"[SQLITE] batch save failed for {npc_id}: {e}")
            with self._lock:
                self._conn.rollback()

    def delete_campaign(self, campaign_id: str) -> int:
        """Удаляет все записи кампании из обеих таблиц.
        Вызывается из new_game() для полной очистки памяти."""
        # S210: каскад из двух DELETE + commit — под Lock (атомарность пары)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM event_memories WHERE campaign_id = ?", (campaign_id,))
            deleted_events = cur.rowcount
            cur.execute(
                "DELETE FROM entries WHERE collection LIKE ?", (f"%{campaign_id}%",)
            )
            deleted_entries = cur.rowcount
            self._conn.commit()
            return deleted_events + deleted_entries

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> int:
        """
        PUBLIC API: Выполняет произвольный SQL-запрос (INSERT/UPDATE/DELETE)
        и коммитит. Возвращает lastrowid или количество затронутых строк.
        Используется сервисами, владеющими своей схемой (например, L1Chronicle).
        """
        # FIX: Явный commit только если транзакция действительно активна.
        if self._conn is None:
            raise RuntimeError("SQLite connection is not initialized.")
        # S210 (P0 L1): проверка in_transaction и commit() — атомарная пара
        # под Lock; иначе другой поток закрывает транзакцию в окне между ними.
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            if self._conn.in_transaction:
                self._conn.commit()
            return cur.lastrowid or cur.rowcount

    def query(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """
        PUBLIC API: Выполняет SELECT запрос и возвращает список словарей.
        row_factory уже настроен на sqlite3.Row в _connect().
        """
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

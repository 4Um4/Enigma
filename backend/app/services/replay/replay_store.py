# backend/app/services/replay/replay_store.py
"""
path: backend/app/services/replay/replay_store.py
Назначение: SQLite хранилище для записи и воспроизведения сессий (Подсистема 2, Этап 2.1).
Зависимости: sqlite3, json, zlib
"""
import sqlite3
import json
import zlib
import uuid
import time
import logging
from pathlib import Path
from typing import Any, Optional, List, Dict

logger = logging.getLogger(__name__)

class ReplayStore:
    """Управляет записью сессии в SQLite (WAL mode)."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Создаёт схему БД, если её нет."""
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                commit_hash TEXT NOT NULL,
                started_at REAL NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS tick_snapshots (
                session_id TEXT NOT NULL,
                tick_id INTEGER NOT NULL,
                game_time_seconds REAL NOT NULL,
                tick_state_json BLOB NOT NULL,
                tick_mutation_json BLOB,
                world_snapshot_json BLOB,
                PRIMARY KEY (session_id, tick_id),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            
            CREATE TABLE IF NOT EXISTS interventions (
                intervention_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tick_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                payload_json BLOB,
                intent_compression_json BLOB,
                FOREIGN KEY (session_id, tick_id) REFERENCES tick_snapshots(session_id, tick_id)
            );
            
            CREATE TABLE IF NOT EXISTS llm_calls (
                call_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tick_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                prompt_json BLOB,
                response_json BLOB,
                model_name TEXT,
                latency_ms INTEGER,
                FOREIGN KEY (session_id, tick_id) REFERENCES tick_snapshots(session_id, tick_id)
            );
            
            CREATE TABLE IF NOT EXISTS causal_probes (
                probe_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tick_id INTEGER NOT NULL,
                probe_name TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json BLOB,
                FOREIGN KEY (session_id, tick_id) REFERENCES tick_snapshots(session_id, tick_id)
            );
            
            CREATE TABLE IF NOT EXISTS scene_changes (
                change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tick_id INTEGER NOT NULL,
                change_json BLOB,
                applied BOOLEAN,
                FOREIGN KEY (session_id, tick_id) REFERENCES tick_snapshots(session_id, tick_id)
            );
        """)
        self.conn.commit()

    def _to_json_bytes(self, obj: Any) -> bytes:
        """Сериализует объект в JSON и сжимает через zlib."""
        try:
            json_str = json.dumps(obj, default=str, ensure_ascii=False)
            return zlib.compress(json_str.encode('utf-8'))
        except Exception as e:
            logger.error(f"[REPLAY_STORE] JSON serialization failed: {e}")
            return zlib.compress(b'{"error": "serialization_failed"}')

    def _from_json_bytes(self, data: bytes) -> Any:
        if not data:
            return None
        try:
            return json.loads(zlib.decompress(data).decode('utf-8'))
        except Exception as e:
            logger.error(f"[REPLAY_STORE] JSON deserialization failed: {e}")
            return None

    def start_session(self, campaign_id: str, commit_hash: str) -> str:
        """Создаёт новую сессию записи и возвращает её ID."""
        session_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO sessions (session_id, campaign_id, commit_hash, started_at) VALUES (?, ?, ?, ?)",
            (session_id, campaign_id, commit_hash, time.time())
        )
        self.conn.commit()
        return session_id

    def record_tick(
        self,
        session_id: str,
        tick_id: int,
        game_time_seconds: float,
        tick_state: Any,
        tick_mutation: Any = None,
        world_snapshot: Any = None
    ) -> None:
        """Записывает срез тика (вход, выход, проекция)."""
        self.conn.execute(
            """INSERT OR REPLACE INTO tick_snapshots 
               (session_id, tick_id, game_time_seconds, tick_state_json, tick_mutation_json, world_snapshot_json) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id, tick_id, game_time_seconds,
                self._to_json_bytes(tick_state),
                self._to_json_bytes(tick_mutation),
                self._to_json_bytes(world_snapshot)
            )
        )
        self.conn.commit()

    def record_intervention(
        self,
        session_id: str,
        tick_id: int,
        source: str,
        payload: Any,
        intent_compression: Any = None
    ) -> None:
        """Записывает InterventionEvent."""
        self.conn.execute(
            """INSERT INTO interventions (session_id, tick_id, source, payload_json, intent_compression_json)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, tick_id, source, self._to_json_bytes(payload), self._to_json_bytes(intent_compression))
        )
        self.conn.commit()

    def record_llm_call(
        self,
        session_id: str,
        tick_id: int,
        agent_name: str,
        prompt: str,
        response: str,
        model_name: str,
        latency_ms: int
    ) -> None:
        """Записывает вызов LLM для кэширования при replay."""
        import hashlib
        prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        self.conn.execute(
            """INSERT INTO llm_calls (session_id, tick_id, agent_name, prompt_hash, prompt_json, response_json, model_name, latency_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, tick_id, agent_name, prompt_hash, self._to_json_bytes(prompt), self._to_json_bytes(response), model_name, latency_ms)
        )
        self.conn.commit()

    def record_causal_probe(
        self,
        session_id: str,
        tick_id: int,
        probe_name: str,
        status: str,
        details: Any = None
    ) -> None:
        """Записывает результат пробы Causal Probes."""
        self.conn.execute(
            """INSERT INTO causal_probes (session_id, tick_id, probe_name, status, details_json)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, tick_id, probe_name, status, self._to_json_bytes(details))
        )
        self.conn.commit()

    def record_scene_change(
        self,
        session_id: str,
        tick_id: int,
        change: Any,
        applied: bool
    ) -> None:
        """Записывает SceneChange."""
        self.conn.execute(
            """INSERT INTO scene_changes (session_id, tick_id, change_json, applied)
               VALUES (?, ?, ?, ?)""",
            (session_id, tick_id, self._to_json_bytes(change), applied)
        )
        self.conn.commit()

    def close(self) -> None:
        """Закрывает соединение с БД."""
        if self.conn:
            self.conn.close()
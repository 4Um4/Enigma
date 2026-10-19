# backend/app/services/replay/replay_store.py
"""
path: backend/app/services/replay/replay_store.py
Назначение: SQLite хранилище для записи и воспроизведения сессий (Подсистема 2, Этап 2.1).
Зависимости: sqlite3, json, zlib
"""
import json
import logging
import sqlite3
import threading
import time
import uuid
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class ReplayStore:
    """Управляет записью сессии в SQLite (WAL mode)."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
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

    def count_ticks(self, session_id: str) -> int:
        """R2 (Phantom fix): фактическое число записанных тиков сессии.

        session_id существует ≠ запись произведена (start_session пишет
        строку в sessions независимо от тиков). Единственный честный
        признак записи — счёт строк tick_snapshots.
        """
        _row = self.conn.execute(
            "SELECT COUNT(*) FROM tick_snapshots WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        return int(_row[0]) if _row else 0

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
        with self._lock:
            # 1. Гарантируем существование строки (заполняем NOT NULL поля дефолтами, если строки нет)
            self.conn.execute(
                """INSERT OR IGNORE INTO tick_snapshots
                   (session_id, tick_id, game_time_seconds, tick_state_json, tick_mutation_json, world_snapshot_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, tick_id, game_time_seconds, b'{}', b'{}', b'{}')
            )
            # 2. Точечно обновляем только переданные поля
            self.conn.execute(
                """UPDATE tick_snapshots SET
                       game_time_seconds = COALESCE(?, game_time_seconds),
                       tick_state_json = COALESCE(?, tick_state_json),
                       tick_mutation_json = COALESCE(?, tick_mutation_json),
                       world_snapshot_json = COALESCE(?, world_snapshot_json)
                   WHERE session_id = ? AND tick_id = ?""",
                (
                    game_time_seconds if game_time_seconds != 0.0 else None,  # noqa: ENIGMA001
                    self._to_json_bytes(tick_state) if tick_state is not None else None,  # noqa: ENIGMA001
                    self._to_json_bytes(tick_mutation) if tick_mutation is not None else None,  # noqa: ENIGMA001
                    self._to_json_bytes(world_snapshot) if world_snapshot is not None else None,  # noqa: ENIGMA001
                    session_id, tick_id
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
        latency_ms: int,
        system_prompt: Optional[str] = None,
        params: Any = None
    ) -> None:
        """Записывает вызов LLM для кэширования при replay."""
        from app.services.replay.llm_cache import compute_prompt_hash
        prompt_hash = compute_prompt_hash(prompt, system_prompt, params)
        with self._lock:
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

    def get_llm_call(self, session_id: str, agent_name: str, prompt_hash: str) -> Optional[Dict[str, Any]]:
        """Ищет закэшированный ответ LLM для воспроизведения (Этап 2.3)."""
        # prompt_hash теперь вычисляется с учётом system_prompt и params в router.py
        try:
            with self._lock:
                row = self.conn.execute(
                    "SELECT response_json, model_name FROM llm_calls WHERE session_id = ? AND agent_name = ? AND prompt_hash = ? ORDER BY call_id DESC LIMIT 1",
                    (session_id, agent_name, prompt_hash)
                ).fetchone()
            if row:
                return {
                    "response": self._from_json_bytes(row["response_json"]),
                    "model_name": row["model_name"]
                }
            return None
        except Exception as e:
            logger.error(f"[REPLAY_STORE] Failed to get LLM call: {e}")
            return None

    # ═══════════════════ D72: replay-бюджет (ADR-O-426 §1 II.Д) ═══════════════════
    # Консервативный контракт: методы существуют и тестируются (показывают,
    # что удаление возможно и правильно), но AUTO-prune по умолчанию OFF
    # (settings.replay_budget_keep_last=0). Активация — отдельный вердикт
    # Мастера. Pinned-сессии ADR-O-351 защищены ВСЕГДА (проверяется тестом).

    def list_sessions(
        self, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Возвращает сессии, отсортированные по started_at DESC.

        Поля: session_id, campaign_id, commit_hash, started_at, pinned.
        """
        with self._lock:
            rows = self.conn.execute(
                """SELECT session_id, campaign_id, commit_hash,
                          started_at, pinned
                   FROM sessions
                   ORDER BY started_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_sessions(self) -> int:
        """Полное число сессий (pinned + unpinned)."""
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
        return int(row[0]) if row else 0

    def pin_session(self, session_id: str) -> bool:
        """Защищает сессию от prune_old_sessions (ADR-O-351).

        Returns: True если row изменён (s стала pinned); False если уже
        была pinned или не существует. Idempotent.
        """
        with self._lock:
            cur = self.conn.execute(
                "UPDATE sessions SET pinned = 1 WHERE session_id = ? AND pinned = 0",
                (session_id,),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def unpin_session(self, session_id: str) -> bool:
        """Снимает pinned-защиту. Idempotent. Returns True если row изменён."""
        with self._lock:
            cur = self.conn.execute(
                "UPDATE sessions SET pinned = 0 WHERE session_id = ? AND pinned = 1",
                (session_id,),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def prune_old_sessions(
        self, keep_last: int, dry_run: bool = False
    ) -> list[str]:
        """D72: удаляет unpinned-сессии сверх keep_last (по started_at DESC).

        Pinned-сессии ADR-O-351 защищены ВСЕГДА — они не учитываются в
        keep_last и не удаляются ни при каких условиях.

        Семантика keep_last:
        - <0: невалидно, raise ValueError.
        - 0: удалить ВСЕ unpinned (валидный явный вызов "только pinned");
          в settings.replay_budget_keep_last=0 = OFF — GameLoop НЕ вызывает
          prune вовсе (см. game_loop.py wiring).
        - >0: оставить keep_last свежих unpinned + все pinned.

        Атомарность: одна транзакция (BEGIN IMMEDIATE ... COMMIT). При
        любом исключении — полный ROLLBACK, ни одна сессия не удалена.
        FK без CASCADE: ручное удаление 5 зависимых таблиц для каждой
        сессии (tick_snapshots, interventions, llm_calls, causal_probes,
        scene_changes). Возвращает список удалённых session_id.

        dry_run=True: возвращает список session_id для удаления БЕЗ
        фактического удаления (для observation и тестов).
        """
        if keep_last < 0:
            raise ValueError(
                f"keep_last must be >= 0, got {keep_last}"
            )
        with self._lock:
            # Кандидаты на удаление: unpinned, отсортированные от старых к
            # новым, начиная с позиции keep_last. LIMIT -1 = все строки
            # после OFFSET (SQLite-идиома).
            candidates = [
                str(r[0])
                for r in self.conn.execute(
                    """SELECT session_id FROM sessions
                       WHERE pinned = 0
                       ORDER BY started_at DESC
                       LIMIT -1 OFFSET ?""",
                    (keep_last,),
                ).fetchall()
            ]
            if dry_run or not candidates:
                return candidates
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            try:
                for sid in candidates:
                    # Ручной порядок удаления зависимостей (FK без CASCADE):
                    # 5 зависимых таблиц + sessions — последней.
                    self.conn.execute(
                        "DELETE FROM scene_changes WHERE session_id = ?",
                        (sid,),
                    )
                    self.conn.execute(
                        "DELETE FROM causal_probes WHERE session_id = ?",
                        (sid,),
                    )
                    self.conn.execute(
                        "DELETE FROM llm_calls WHERE session_id = ?",
                        (sid,),
                    )
                    self.conn.execute(
                        "DELETE FROM interventions WHERE session_id = ?",
                        (sid,),
                    )
                    self.conn.execute(
                        "DELETE FROM tick_snapshots WHERE session_id = ?",
                        (sid,),
                    )
                    self.conn.execute(
                        "DELETE FROM sessions WHERE session_id = ?",
                        (sid,),
                    )
                self.conn.commit()
                return candidates
            except Exception:
                self.conn.rollback()
                raise

    def close(self) -> None:
        """Закрывает соединение с БД."""
        if self.conn:
            self.conn.close()

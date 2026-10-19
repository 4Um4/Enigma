from __future__ import annotations

# backend/app/services/state/migration_runner.py
"""
path: backend/app/services/state/migration_runner.py
Назначение: MigrationRunner — версионирование схем SQLite-сторов поверх
PRAGMA user_version (ADR-O-426, COV-1/D58, гейт COV-GC-01). Единый
старт-контур миграций: per-file цепочки, bootstrap-классификация легаси
по маркерам, резервирование через online backup API с верификацией,
аудит-таблица _schema_migrations, fail-loud во всех неоднозначных
состояниях. В проде вызывается ТОЛЬКО конфиг-гейтом старта (Шаг 4/D70);
до него — библиотека (тесты + разовый стампинг Шага 1).
Зависимости: sqlite3, os, logging, dataclasses, pathlib, typing;
app.core.config.settings — лениво, только в резолверах prod-реестра
(тесты строят собственные регистрации с tmp-путями).
Основные сущности: MigrationError, MigrationSpec, StoreRegistration,
MigrationOutcome, build_default_registry, register_migrations,
validate_registry, run_startup_migrations.

Контракт (ADR-O-426, вердикт Мастера II.1–II.5):
- применение миграции = ОДНА транзакция: BEGIN IMMEDIATE → apply() →
  PRAGMA user_version → аудит-строка → COMMIT. apply() НЕ делает
  собственных COMMIT (проверяется машинно: conn.in_transaction).
- self-check реестра ДО любого касания БД (дыры/дуэли/разрывы).
- даунгрейд (user_version > HEAD) — блокирующий отказ, обходных флагов нет.
- bootstrap v0: классификация ТОЛЬКО по маркерам (множество таблиц ×
  колонки); неоднозначно → MigrationError, файл НЕ изменяется.
- бэкап перед первой записью раннера в файл: online backup API →
  верификация (integrity_check + множество таблиц + row-counts +
  user_version) → атомарная замена .pre-migration.bak. Единственная
  исправная копия не перезаписывается непроверенной (os.replace только
  после верификации новой копии).
- DDL v1-миграций — вербатим-копии схем сторов; паритет с
  _init_schema() сторов держится тестом T1 (сравнение МНОЖЕСТВ
  таблиц/индексов/колонок, не текстов sqlite_master: ALTER ADD COLUMN
  аппендит колонку в конец — позиция не семантична, прод-доступ только
  по именам колонок). При изменении _init_schema стора — зеркальная
  правка DDL здесь + новая миграция (две копии DDL заперты тестом T1).
- HEAD стора ВЫВОДИТСЯ из смерженной цепочки (builtin + external), а не
  хранится константой: сторонняя миграция (register_migrations, S1)
  поднимает HEAD без правки раннера (табу «правка раннера ради стора»).
"""

import logging
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Аудит-таблица (в каждой версионируемой БД) ──────────────────────
# Пишется в ТОЙ ЖЕ транзакции, что DDL и user_version (II.2).
_SCHEMA_MIGRATIONS_TABLE = "_schema_migrations"
_AUDIT_DDL = """
    CREATE TABLE IF NOT EXISTS _schema_migrations (
        store_id TEXT NOT NULL,
        from_version INTEGER NOT NULL,
        to_version INTEGER NOT NULL,
        owner TEXT NOT NULL,
        description TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        PRIMARY KEY (store_id, to_version)
    )
"""
# applied_at — §15.2 Устава: метаданные персистенции, симуляцией не читаются.


class MigrationError(RuntimeError):
    """Fail-loud ошибка контура миграций (ADR-O-426): неоднозначное
    легаси-состояние, даунгрейд, разрыв цепочки, отказ верификации
    бэкапа/итога. Файл БД при этом остаётся нетронутым — все проверки
    на запись идут до применения (II.1, условие 8 протокола стампинга)."""


# ════════════════════════════════ Типы ═══════════════════════════════


@dataclass(frozen=True)
class MigrationSpec:
    """Одна миграция: переводит БД стора с from_version на to_version.

    apply — чистая функция соединения: только conn.execute() с DDL/DML;
    собственные COMMIT/ROLLBACK внутри ЗАПРЕЩЕНЫ (транзакцию ведёт
    раннер; нарушение ловится машинно по conn.in_transaction).
    """

    store_id: str
    from_version: int
    to_version: int
    owner: str
    description: str
    apply: Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class StoreRegistration:
    """Регистрация стора в реестре: резолвер пути, классификатор
    легаси-состояний (user_version=0) и builtin-цепочка миграций.

    HEAD не хранится: выводится из смерженной цепочки (см. докстринг
    модуля) — сторонние миграции поднимают HEAD без правки раннера.
    """

    store_id: str
    path_resolver: Callable[[], Path | None]
    bootstrap_classifier: Callable[[sqlite3.Connection], int]
    migrations: tuple[MigrationSpec, ...]


@dataclass(frozen=True)
class MigrationOutcome:
    """Отчёт по одному стору (идёт в reports/cov1_stamp_report.json)."""

    store_id: str
    path: str
    status: str  # ok | ok-noop | skipped | dry-run
    detected_version: int
    head_version: int
    applied: tuple[tuple[int, int], ...] = ()
    baseline_stamped: bool = False
    backup_path: str | None = None
    reason: str = ""
    plan: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "store_id": self.store_id,
            "path": self.path,
            "status": self.status,
            "detected_version": self.detected_version,
            "head_version": self.head_version,
            "applied": [list(step) for step in self.applied],
            "baseline_stamped": self.baseline_stamped,
            "backup_path": self.backup_path,
            "reason": self.reason,
            "plan": list(self.plan),
        }


# ═══════════════ DDL v1-миграций (вербатим со схем сторов) ═══════════════
# Паритет с _init_schema() сторов заперт тестом T1 (множества, не тексты).


def _make_apply(
    statements: tuple[str, ...],
) -> Callable[[sqlite3.Connection], None]:
    def _apply(conn: sqlite3.Connection) -> None:
        for stmt in statements:
            conn.execute(stmt)

    return _apply


# enigma_memory v1: базовые 5 таблиц + 3 индекса; БЕЗ secret_id и его
# индекса (это v2, ex-ad-hoc ALTER-гвард sqlite_store.py:186-197).
_ENIGMA_MEMORY_V1_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS entries (
        id TEXT PRIMARY KEY,
        collection TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_entries_collection
    ON entries(collection, timestamp DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS state_collections (
        collection TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
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
    """,
    """
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
    """,
    """
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
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_event_memories_npc
    ON event_memories(campaign_id, npc_id, importance DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_event_memories_tags
    ON event_memories(campaign_id, npc_id, tags_json)
    """,
)

# enigma_memory v2: M1/P1 — расширение live-таблиц (CREATE IF NOT EXISTS
# не расширяет существующие). Бывший ad-hoc ALTER-гвард, последний
# снифинг-паттерн проекта, переведён в версионную миграцию (ADR-O-426).
_ENIGMA_MEMORY_V2_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE event_memories ADD COLUMN secret_id TEXT DEFAULT NULL",
    """
    CREATE INDEX IF NOT EXISTS idx_event_memories_secret
    ON event_memories(campaign_id, secret_id)
    """,
)

# enigma_runtime v1: единая KV-таблица (SqlitePersistenceAdapter).
_ENIGMA_RUNTIME_V1_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS state_kv (
        key         TEXT PRIMARY KEY,
        value       TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
)

# replay v1: 6 таблиц ReplayStore. ВАЖНО: отдельные execute(), НЕ
# executescript() — executescript неявно COMMITит до исполнения и
# ломит инвариант «одна транзакция» (II.2).
_REPLAY_V1_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        campaign_id TEXT NOT NULL,
        commit_hash TEXT NOT NULL,
        started_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tick_snapshots (
        session_id TEXT NOT NULL,
        tick_id INTEGER NOT NULL,
        game_time_seconds REAL NOT NULL,
        tick_state_json BLOB NOT NULL,
        tick_mutation_json BLOB,
        world_snapshot_json BLOB,
        PRIMARY KEY (session_id, tick_id),
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS interventions (
        intervention_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        tick_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        payload_json BLOB,
        intent_compression_json BLOB,
        FOREIGN KEY (session_id, tick_id) REFERENCES tick_snapshots(session_id, tick_id)
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS causal_probes (
        probe_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        tick_id INTEGER NOT NULL,
        probe_name TEXT NOT NULL,
        status TEXT NOT NULL,
        details_json BLOB,
        FOREIGN KEY (session_id, tick_id) REFERENCES tick_snapshots(session_id, tick_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scene_changes (
        change_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        tick_id INTEGER NOT NULL,
        change_json BLOB,
        applied BOOLEAN,
        FOREIGN KEY (session_id, tick_id) REFERENCES tick_snapshots(session_id, tick_id)
    )
    """,
)


# ═════════════════════ Bootstrap-классификаторы (II.1) ═════════════════════
# Возвращают эффективную версию НЕверсионированной БД (user_version=0):
# 0 = пустая, N = легаси-состояние N по маркерам. Неоднозначно → отказ.


def _user_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' AND name != ?",
        (_SCHEMA_MIGRATIONS_TABLE,),
    ).fetchall()
    return {str(r[0]) for r in rows}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    # Имя таблицы — внутренняя константа классификатора, не пользовательский ввод.
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        t: int(conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
        for t in sorted(_user_tables(conn))
    }


# База стора (обязательна; миграции COV-1 управляют только ею)…
_ENIGMA_MEMORY_TABLES = frozenset(
    {"entries", "state_collections", "memory_crystals", "experience_traces", "event_memories"}
)
# …и расширения семейства, живущие в том же файле: их создают лениво
# сами сторы (l1_chronicle.__init__/_ensure_loaded: l1_chronicle_events,
# l1_chronicle_archive — Rule 28 append-only; crystallized_belief_store:
# crystallized_beliefs), идемпотентным CREATE IF NOT EXISTS. Миграции их
# НЕ создают и НЕ трогают; присутствие опционально (установка без
# загрузки L1/L2.5), посторонних таблиц быть не может (поймано
# классификатором Шага D — dry-run на копии, живой файл не тронут).
_ENIGMA_MEMORY_EXTENSION_TABLES = frozenset(
    {"l1_chronicle_events", "l1_chronicle_archive", "crystallized_beliefs"}
)
_ENIGMA_RUNTIME_TABLES = frozenset({"state_kv"})
_REPLAY_TABLES = frozenset(
    {"sessions", "tick_snapshots", "interventions", "llm_calls", "causal_probes", "scene_changes"}
)


def _classify_enigma_memory(conn: sqlite3.Connection) -> int:
    tables = _user_tables(conn)
    if not tables:
        return 0
    base_missing = _ENIGMA_MEMORY_TABLES - tables
    unknown = tables - _ENIGMA_MEMORY_TABLES - _ENIGMA_MEMORY_EXTENSION_TABLES
    if base_missing or unknown:
        raise MigrationError(
            "enigma_memory: неоднозначное легаси-состояние — таблицы не совпадают "
            f"с семейством (база 5 обязательна + известные расширения L1/L2.5; "
            f"найдено: {sorted(tables)}). Файл НЕ изменён; "
            "решение за владельцем (ADR-O-426 §2: неизвестная схема не штампуется)."
        )
    if "secret_id" not in _table_columns(conn, "event_memories"):
        return 1
    # v2 определяется по колонке; индекс idx_event_memories_secret не входит в
    # маркеры — стор воссоздаёт его идемпотентно (CREATE IF NOT EXISTS).
    return 2


def _classify_enigma_runtime(conn: sqlite3.Connection) -> int:
    tables = _user_tables(conn)
    if not tables:
        return 0
    if tables != _ENIGMA_RUNTIME_TABLES:
        raise MigrationError(
            "enigma_runtime: неоднозначное легаси-состояние — ожидалась только "
            f"state_kv (найдено: {sorted(tables)}). Файл НЕ изменён."
        )
    return 1


def _classify_replay(conn: sqlite3.Connection) -> int:
    tables = _user_tables(conn)
    if not tables:
        return 0
    if tables != _REPLAY_TABLES:
        raise MigrationError(
            "replay: неоднозначное легаси-состояние — ожидаемые 6 таблиц "
            f"ReplayStore не совпадают (найдено: {sorted(tables)}). Файл НЕ изменён."
        )
    return 1


# ═══════════════════════════ Builtin-реестр ═══════════════════════════

_MEMORY_SPEC_V1 = MigrationSpec(
    store_id="enigma_memory",
    from_version=0,
    to_version=1,
    owner="COV-1/Б",
    description="enigma_memory v1: базовые 5 таблиц + 3 индекса (вербатим sqlite_store)",
    apply=_make_apply(_ENIGMA_MEMORY_V1_STATEMENTS),
)
_MEMORY_SPEC_V2 = MigrationSpec(
    store_id="enigma_memory",
    from_version=1,
    to_version=2,
    owner="COV-1/Б",
    description="event_memories.secret_id + idx_event_memories_secret (ex-ad-hoc ALTER, M1/P1)",
    apply=_make_apply(_ENIGMA_MEMORY_V2_STATEMENTS),
)
_RUNTIME_SPEC_V1 = MigrationSpec(
    store_id="enigma_runtime",
    from_version=0,
    to_version=1,
    owner="COV-1/Б",
    description="state_kv (SqlitePersistenceAdapter, Фаза 10 atomic_commit_all)",
    apply=_make_apply(_ENIGMA_RUNTIME_V1_STATEMENTS),
)
_REPLAY_SPEC_V1 = MigrationSpec(
    store_id="replay",
    from_version=0,
    to_version=1,
    owner="COV-1/Б",
    description="6 таблиц ReplayStore (WAL, ADR-O-351)",
    apply=_make_apply(_REPLAY_V1_STATEMENTS),
)

# replay v2: D72 (ADR-O-426 §1 II.Д) — replay-бюджет.
# sessions.pinned BOOLEAN NOT NULL DEFAULT 0 (защита живых A/B-сессий
# ADR-O-351 от авто-ротации); 2 индекса для O(log N) prune:
# idx_sessions_started_at (сортировка старых unpinned к удалению) +
# idx_sessions_pinned_started (фильтр pinned за один index seek).
# ADD COLUMN с DEFAULT — легален в одной транзакции (II.2).
_REPLAY_V2_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE sessions ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_pinned_started ON sessions(pinned, started_at)",
)
_REPLAY_SPEC_V2 = MigrationSpec(
    store_id="replay",
    from_version=1,
    to_version=2,
    owner="COV-1/Б",
    description="D72: sessions.pinned + 2 индекса (replay-бюджет)",
    apply=_make_apply(_REPLAY_V2_STATEMENTS),
)


def _resolve_memory_path() -> Path:
    from app.core.config import settings  # лениво: без import-сайд-эффектов

    return Path(settings.saves_dir) / "enigma_memory.db"


def _resolve_runtime_path() -> Path:
    from app.core.config import settings

    return Path(settings.saves_dir) / "enigma_runtime.db"


def _resolve_replay_path() -> Path:
    # У-3/Н-2 (закрыто археологией): replay.db живёт НЕ в saves/, а в
    # settings.replay_store_path (reports/replay_sessions/replay.db).
    # Отсутствие файла = replay не активен на этой установке → skip.
    from app.core.config import settings

    return Path(settings.replay_store_path)


_BUILTIN_REGISTRY: dict[str, StoreRegistration] = {
    reg.store_id: reg
    for reg in (
        StoreRegistration(
            store_id="enigma_memory",
            path_resolver=_resolve_memory_path,
            bootstrap_classifier=_classify_enigma_memory,
            migrations=(_MEMORY_SPEC_V1, _MEMORY_SPEC_V2),
        ),
        StoreRegistration(
            store_id="enigma_runtime",
            path_resolver=_resolve_runtime_path,
            bootstrap_classifier=_classify_enigma_runtime,
            migrations=(_RUNTIME_SPEC_V1,),
        ),
        StoreRegistration(
            store_id="replay",
            path_resolver=_resolve_replay_path,
            bootstrap_classifier=_classify_replay,
            migrations=(_REPLAY_SPEC_V1, _REPLAY_SPEC_V2),
        ),
    )
}

# Сторонние миграции (S1: ветвь А — event_memories NL-1/MEM-1 — через
# register_migrations, БЕЗ правки раннера; табу ADR-O-426).
_EXTERNAL_SPECS: list[MigrationSpec] = []


def build_default_registry() -> list[StoreRegistration]:
    """Prod-реестр: 3 стора (HEAD сегодня: 2 / 1 / 1 — выводится из цепочек)."""
    return list(_BUILTIN_REGISTRY.values())


# ═══════════════════ Self-check цепочки (II.4) ═══════════════════


def _merged_specs(store_id: str) -> list[MigrationSpec]:
    reg = _BUILTIN_REGISTRY.get(store_id)
    if reg is None:
        raise MigrationError(f"неизвестный store_id в реестре: {store_id!r}")
    specs = list(reg.migrations) + [s for s in _EXTERNAL_SPECS if s.store_id == store_id]
    return sorted(specs, key=lambda s: s.to_version)


def _check_chain(store_id: str, specs: list[MigrationSpec]) -> int:
    """Валидирует цепочку и возвращает её HEAD. Вызывается ДО любого
    касания БД: дыры/дуэли/разрывы блокируют старт (II.4)."""
    if not specs:
        raise MigrationError(f"{store_id}: пустая цепочка миграций")
    if specs[0].from_version != 0:
        raise MigrationError(
            f"{store_id}: цепочка обязана начинаться с создания (from_version=0), "
            f"начинается с {specs[0].from_version}"
        )
    seen_from: set[int] = set()
    seen_to: set[int] = set()
    prev_to = -1
    for spec in specs:
        if spec.from_version in seen_from:
            raise MigrationError(f"{store_id}: дуэль миграций с from_version={spec.from_version}")
        if spec.to_version in seen_to:
            raise MigrationError(f"{store_id}: дуэль миграций с to_version={spec.to_version}")
        if spec.to_version <= spec.from_version:
            raise MigrationError(f"{store_id}: to_version <= from_version в {spec.from_version}->{spec.to_version}")
        if spec.from_version != prev_to and prev_to != -1:
            raise MigrationError(
                f"{store_id}: разрыв цепочки — {spec.from_version}->{spec.to_version} "
                f"не стыкуется с предыдущей вершиной {prev_to}"
            )
        if spec.store_id != store_id:
            raise MigrationError(f"{store_id}: spec чужого стора ({spec.store_id}) в цепочке")
        seen_from.add(spec.from_version)
        seen_to.add(spec.to_version)
        prev_to = spec.to_version
    return prev_to


def validate_registry(
    registry: list[StoreRegistration] | None = None,
) -> list[tuple[str, int]]:
    """Self-check реестра без касания БД. Возвращает [(store_id, HEAD)]."""
    regs = registry if registry is not None else build_default_registry()
    result: list[tuple[str, int]] = []
    for reg in regs:
        head = _check_chain(reg.store_id, _merged_specs(reg.store_id))
        result.append((reg.store_id, head))
    return result


def register_migrations(*specs: MigrationSpec) -> None:
    """Единственный путь сторонних миграций (S1-контракт, Ф9).

    Ограничения (валидация fail-fast, включая полный self-check мержа):
    - только поверх сторов builtin-реестра (новый стор = вердикт Мастера
      + новая регистрация, не самовольная);
    - from_version >= 1 (создание 0->1 — за владельцем стора);
    - уникальность (store_id, from_version) среди внешних.
    """
    for spec in specs:
        if spec.store_id not in _BUILTIN_REGISTRY:
            raise MigrationError(
                f"register_migrations: store_id {spec.store_id!r} отсутствует в "
                "builtin-реестре — новый стор требует вердикта Мастера (ADR-O-426)"
            )
        if spec.from_version < 1:
            raise MigrationError(
                f"register_migrations: from_version >= 1 требуется ({spec.store_id} "
                f"{spec.from_version}->{spec.to_version}); создание 0->1 — за владельцем стора"
            )
        for existing in _EXTERNAL_SPECS:
            if existing.store_id == spec.store_id and existing.from_version == spec.from_version:
                raise MigrationError(
                    f"register_migrations: дубль from_version={spec.from_version} "
                    f"для {spec.store_id}"
                )
        _EXTERNAL_SPECS.append(spec)
    # Fail-fast: полный self-check мержа сразу (ловит дыру до старта).
    validate_registry()


# ═══════════════ Бэкап: online backup API + верификация (Ф3/II.В) ═══════════════


def _backup_database(db_path: Path) -> Path:
    """Проверенная резервная копия до первой записи раннера в файл.

    online backup API корректен при WAL; копия верифицируется ДО
    атомарной замены старого .bak (os.replace) — единственная исправная
    копия никогда не перезаписывается непроверенной.
    """
    tmp = db_path.parent / (db_path.name + ".pre-migration.bak.new")
    final = db_path.parent / (db_path.name + ".pre-migration.bak")
    if tmp.exists():
        tmp.unlink()
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    _verify_backup(db_path, tmp)
    os.replace(tmp, final)
    logger.info("[MIGRATION] Бэкап верифицирован и установлен: %s", final)
    return final


def _verify_backup(src_path: Path, bak_path: Path) -> None:
    src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
    bak = sqlite3.connect(str(bak_path))
    try:
        integrity = bak.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MigrationError(f"бэкап {bak_path.name}: integrity_check = {integrity!r}, копия отвергнута")
        src_tables, bak_tables = _user_tables(src), _user_tables(bak)
        if src_tables != bak_tables:
            raise MigrationError(
                f"бэкап {bak_path.name}: множество таблиц расходится с источником "
                f"({sorted(bak_tables)} vs {sorted(src_tables)})"
            )
        src_counts, bak_counts = _table_counts(src), _table_counts(bak)
        if src_counts != bak_counts:
            raise MigrationError(f"бэкап {bak_path.name}: row-counts расходятся с источником")
        src_v = int(src.execute("PRAGMA user_version").fetchone()[0])
        bak_v = int(bak.execute("PRAGMA user_version").fetchone()[0])
        if src_v != bak_v:
            raise MigrationError(f"бэкап {bak_path.name}: user_version {bak_v} != {src_v}")
    finally:
        bak.close()
        src.close()


# ═════════════════════════ Исполнение ═════════════════════════


def _now_iso() -> str:
    # §15.2 Устава: метаданные персистенции (не читается симуляцией).
    return datetime.now(timezone.utc).isoformat()


def _apply_spec(conn: sqlite3.Connection, spec: MigrationSpec) -> None:
    """Одна миграция = ОДНА транзакция: apply → user_version → аудит (II.2).
    Исключение → полный откат; частично применённой версии не остаётся."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        spec.apply(conn)
        if not conn.in_transaction:
            raise MigrationError(
                f"{spec.store_id} {spec.from_version}->{spec.to_version}: apply() "
                "закрыл транзакцию (собственный COMMIT) — нарушение табу ADR-O-426"
            )
        conn.execute(f"PRAGMA user_version = {spec.to_version}")
        conn.execute(_AUDIT_DDL)
        conn.execute(
            f"INSERT INTO {_SCHEMA_MIGRATIONS_TABLE} "
            "(store_id, from_version, to_version, owner, description, applied_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (spec.store_id, spec.from_version, spec.to_version, spec.owner, spec.description, _now_iso()),
        )
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    logger.info(
        "[MIGRATION] %s: применена %d->%d (%s)",
        spec.store_id, spec.from_version, spec.to_version, spec.owner,
    )


def _stamp_baseline(conn: sqlite3.Connection, store_id: str, version: int) -> None:
    """Базлайн-штамп легаси-БД, однозначно классифицированной как уже
    находящейся на версии `version`: только user_version + аудит-строка,
    без DDL (II.1: маркеры доказали соответствие)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(_AUDIT_DDL)
        conn.execute(f"PRAGMA user_version = {version}")
        conn.execute(
            f"INSERT INTO {_SCHEMA_MIGRATIONS_TABLE} "
            "(store_id, from_version, to_version, owner, description, applied_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                store_id,
                0,
                version,
                "COV-1/bootstrap",
                "базлайн-классификация легаси по маркерам (ADR-O-426 §2)",
                _now_iso(),
            ),
        )
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    logger.info("[MIGRATION] %s: базлайн-штамп v%d (без DDL)", store_id, version)


def _run_store(
    reg: StoreRegistration, *, dry_run: bool, make_backup: bool
) -> MigrationOutcome:
    # Self-check цепочки ДО любого касания БД (II.4).
    specs = _merged_specs(reg.store_id)
    head = _check_chain(reg.store_id, specs)

    resolved = reg.path_resolver()
    if resolved is None or not Path(resolved).exists():
        return MigrationOutcome(
            store_id=reg.store_id,
            path=str(resolved) if resolved else "",
            status="skipped",
            detected_version=-1,
            head_version=head,
            reason="файл БД не существует (стор не активен на установке — норма)",
        )
    db_path = Path(resolved)

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current > head:
            raise MigrationError(
                f"{reg.store_id}: ДАУНГРЕЙД — user_version={current} > HEAD={head} "
                f"({db_path}). Файл НЕ изменён. Восстановление: код новее данных — "
                "обнови код либо верни БД из проверенной резервной копии "
                "(ADR-O-426 §1; обходные флаги запрещены)."
            )
        baseline = current == 0
        detected = reg.bootstrap_classifier(conn) if baseline else current
        if detected > head:
            raise MigrationError(
                f"{reg.store_id}: классифицированное легаси-состояние v{detected} "
                f"новее HEAD={head} цепочки кода — аномалия, файл НЕ изменён"
            )
        counts_before = _table_counts(conn)

        plan = [s for s in specs if s.from_version >= detected]
        stamp_only = baseline and not plan
        writes_planned = bool(plan) or stamp_only

        if not writes_planned:
            # Идемпотентность (II.3): повторный запуск = no-op без записей.
            return MigrationOutcome(
                store_id=reg.store_id, path=str(db_path), status="ok-noop",
                detected_version=detected, head_version=head,
                reason=f"уже на HEAD={head}; записей нет",
            )

        plan_descr = tuple(
            f"{s.from_version}->{s.to_version} ({s.owner})" for s in plan
        ) or (f"базлайн-штамп v{detected} без DDL",)

        if dry_run:
            return MigrationOutcome(
                store_id=reg.store_id, path=str(db_path), status="dry-run",
                detected_version=detected, head_version=head, plan=plan_descr,
                reason=f"таблицы={len(counts_before)}, строк={sum(counts_before.values())}; "
                f"бэкап={'да' if make_backup else 'нет'}",
            )

        backup_path = _backup_database(db_path) if make_backup else None  # noqa: ENIGMA001

        if plan:
            for spec in plan:
                _apply_spec(conn, spec)
        else:
            _stamp_baseline(conn, reg.store_id, detected)

        # Послепроверка (условие 6 протокола стампинга): версия, целостность,
        # содержимое, открываемость.
        version_after = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version_after != head:
            raise MigrationError(
                f"{reg.store_id}: послепроверка — user_version={version_after} != HEAD={head}"
            )
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MigrationError(f"{reg.store_id}: послепроверка — integrity_check={integrity!r}")
        counts_after = _table_counts(conn)
        # Поведенческая нейтральность = сохранность ДАННЫХ существующих
        # таблиц (строки не тронуты) + ни одна таблица не исчезла.
        # Добавление таблиц/колонок — легальная эволюция схемы: v1-цепочка
        # сама создаёт таблицы на пустой БД, внешняя миграция (S1) тоже
        # может. Глобальное равенство множеств было неверной семантикой
        # (поймано T1/T10/T11 до живого стампинга; вердикт I.3-условие 6:
        # «проверены … схема, содержимое», а не «схема заморожена»).
        dropped = set(counts_before) - set(counts_after)
        if dropped:
            raise MigrationError(
                f"{reg.store_id}: послепроверка — таблицы исчезли "
                f"({sorted(dropped)}); миграции не имеют права удалять таблицы"
            )
        for table, count_before in counts_before.items():
            if counts_after.get(table) != count_before:
                raise MigrationError(
                    f"{reg.store_id}: послепроверка — row-count таблицы "
                    f"{table} изменился ({count_before} -> "
                    f"{counts_after.get(table)}); миграции обязаны быть "
                    "behavior-neutral по данным существующих таблиц"
                )

        return MigrationOutcome(
            store_id=reg.store_id, path=str(db_path), status="ok",
            detected_version=detected, head_version=head,
            applied=tuple((s.from_version, s.to_version) for s in plan),
            baseline_stamped=stamp_only,
            backup_path=str(backup_path) if backup_path else None,  # noqa: ENIGMA001
        )
    finally:
        conn.close()


def run_startup_migrations(
    registry: list[StoreRegistration] | None = None,
    *,
    dry_run: bool = False,
    make_backup: bool = True,
) -> list[MigrationOutcome]:
    """Единая точка применения миграций (Ф4: в проде — только из
    конфиг-гейта старта, Шаг 4). dry_run=True — отчёт без записей
    (условие 2 протокола стампинга). Любая неоднозначность = MigrationError,
    дальнейшие сторы не обрабатываются (условие 8)."""
    regs = registry if registry is not None else build_default_registry()
    outcomes: list[MigrationOutcome] = []
    for reg in regs:
        outcomes.append(_run_store(reg, dry_run=dry_run, make_backup=make_backup))
    return outcomes

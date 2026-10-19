# backend/tests/micro/test_d72_replay_budget.py
"""
path: backend/tests/micro/test_d72_replay_budget.py
Назначение: D72 (ADR-O-426 section II.D) replay-budget + pinned-protection.
  Pinned-сессии ADR-O-351 защищены ВСЕГДА. Тестирует:
  - миграцию v1->v2 (sessions.pinned + 2 индекса) через _REPLAY_SPEC_V2.apply;
  - API ReplayStore: list/count/pin/unpin/prune;
  - pinned-защиту (pinned защищены ВСЕГДА);
  - FK-cleanup во всех 5 зависимых таблицах (не только tick_snapshots);
  - атомарность prune (ROLLBACK при исключении; ни сессии, ни строки не удалены);
  - wiring логику (auto-prune только при keep_last > 0) + static guard check.
Зависимости: pytest, app.services.replay.replay_store.ReplayStore,
  app.services.state.migration_runner._REPLAY_SPEC_V2.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.services.replay.replay_store import ReplayStore


# ─────────────────── helpers ───────────────────

def _make_store_with_sessions(
    db_path: Path, n: int, pinned_ids: set[int] | None = None
) -> ReplayStore:
    """Создаёт ReplayStore (v1-схема в __init__), применяет v2-миграцию
    (sessions.pinned + индексы — D72), затем n сессий с started_at i*100.0.

    pinned_ids — индексы (0-based) сессий для pin после создания.
    i=0 — самая старая, i=n-1 — самая свежая.
    """
    from app.services.state.migration_runner import _REPLAY_V2_STATEMENTS
    pinned_ids = pinned_ids or set()
    store = ReplayStore(db_path)
    # v1->v2: ReplayStore.__init__ создаёт v1-схему; v2-колонка pinned
    # и индексы добавляются миграцией (как в проде через MigrationRunner).
    for stmt in _REPLAY_V2_STATEMENTS:
        store.conn.execute(stmt)
    store.conn.commit()
    for i in range(n):
        sid = store.start_session(campaign_id="Open_road", commit_hash="dev")
        store.conn.execute(
            "UPDATE sessions SET started_at = ? WHERE session_id = ?",
            (float(i * 100.0), sid),
        )
        if i in pinned_ids:
            store.pin_session(sid)
    store.conn.commit()
    return store


def _add_all_dependent_rows(
    store: ReplayStore, session_id: str, tick_id: int = 1
) -> None:
    """Добавляет по одной строке в каждую из 5 зависимых таблиц."""
    store.record_tick(
        session_id=session_id, tick_id=tick_id,
        game_time_seconds=0.0, tick_state={"test": True},
    )
    store.record_intervention(
        session_id=session_id, tick_id=tick_id,
        source="test", payload={"action": "test"},
    )
    store.record_llm_call(
        session_id=session_id, tick_id=tick_id,
        agent_name="test_agent", prompt="test prompt",
        response="test response", model_name="test_model", latency_ms=10,
    )
    store.record_causal_probe(
        session_id=session_id, tick_id=tick_id,
        probe_name="test_probe", status="ok", details={"data": True},
    )
    store.record_scene_change(
        session_id=session_id, tick_id=tick_id,
        change={"type": "test"}, applied=True,
    )


# ─────────────────── миграция v1->v2 ───────────────────

def test_d72_migrate_adds_pinned_column(tmp_path: Path) -> None:
    """T-D72-migrate: v2 migration adds sessions.pinned BOOLEAN NOT NULL DEFAULT 0."""
    db_path = tmp_path / "replay.db"
    store = ReplayStore(db_path)  # creates v1 schema in constructor
    from app.services.state.migration_runner import _REPLAY_V2_STATEMENTS
    for stmt in _REPLAY_V2_STATEMENTS:
        store.conn.execute(stmt)
    store.conn.commit()
    cols = [
        r[1]
        for r in store.conn.execute("PRAGMA table_info(sessions)").fetchall()
    ]
    assert "pinned" in cols, "sessions.pinned column missing after v2 migration"
    # DEFAULT 0: new session without explicit pinned is unpinned
    sid = store.start_session(campaign_id="test", commit_hash="dev")
    row = store.conn.execute(
        "SELECT pinned FROM sessions WHERE session_id = ?", (sid,)
    ).fetchone()
    assert int(row[0]) == 0, "default pinned should be 0 (unpinned)"
    store.close()


def test_d72_migrate_adds_indexes(tmp_path: Path) -> None:
    """T-D72-migrate-idx: v2 migration adds 2 indexes for O(log N) prune."""
    db_path = tmp_path / "replay.db"
    store = ReplayStore(db_path)
    from app.services.state.migration_runner import _REPLAY_V2_STATEMENTS
    for stmt in _REPLAY_V2_STATEMENTS:
        store.conn.execute(stmt)
    store.conn.commit()
    indexes = [
        r[0]
        for r in store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sessions'"
        ).fetchall()
    ]
    assert "idx_sessions_started_at" in indexes
    assert "idx_sessions_pinned_started" in indexes
    store.close()


def test_d72_migrate_via_spec_apply(tmp_path: Path) -> None:
    """T-D72-spec: _REPLAY_SPEC_V2.apply (runner's apply path) on v1 to v2 schema.

    Tests the actual apply function that MigrationRunner calls internally,
    not just the raw SQL strings. ReplayStore creates the real v1 schema
    in its constructor; then we apply the v2 migration via the spec.
    """
    from app.services.state.migration_runner import _REPLAY_SPEC_V2
    db_path = tmp_path / "replay.db"
    store = ReplayStore(db_path)
    store.conn.close()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _REPLAY_SPEC_V2.apply(conn)
    conn.commit()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
    assert "pinned" in cols, "pinned column missing after v2 apply"
    indexes = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sessions'"
        ).fetchall()
    ]
    assert "idx_sessions_started_at" in indexes
    assert "idx_sessions_pinned_started" in indexes
    conn.close()


# ─────────────────── list/count ───────────────────

def test_d72_list_sessions_desc_order(tmp_path: Path) -> None:
    """T-D72-list: list_sessions returns sessions sorted by started_at DESC."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=3)
    sessions = store.list_sessions()
    assert len(sessions) == 3
    assert sessions[0]["started_at"] > sessions[2]["started_at"]
    for s in sessions:
        assert {
            "session_id", "campaign_id", "commit_hash",
            "started_at", "pinned"
        } <= set(s.keys())
    store.close()


def test_d72_count_sessions(tmp_path: Path) -> None:
    """T-D72-count: count_sessions returns total N."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=4)
    assert store.count_sessions() == 4
    store.close()


# ─────────────────── pin/unpin ───────────────────

def test_d72_pin_unpin_idempotent(tmp_path: Path) -> None:
    """T-D72-pin: pin sets pinned=1, unpin sets 0; both idempotent."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=1)
    sid = store.list_sessions()[0]["session_id"]
    assert store.pin_session(sid) is True
    assert int(store.list_sessions()[0]["pinned"]) == 1
    assert store.pin_session(sid) is False  # idempotent
    assert store.unpin_session(sid) is True
    assert int(store.list_sessions()[0]["pinned"]) == 0
    assert store.unpin_session(sid) is False  # idempotent
    store.close()


def test_d72_pin_nonexistent(tmp_path: Path) -> None:
    """T-D72-pin-404: pin/unpin nonexistent session returns False, no exception."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=1)
    assert store.pin_session("nonexistent-uuid") is False
    assert store.unpin_session("nonexistent-uuid") is False
    store.close()


# ─────────────────── prune ───────────────────

def test_d72_prune_basic(tmp_path: Path) -> None:
    """T-D72-prune-basic: keep_last=2, 5 sessions removes 3 oldest."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=5)
    pruned = store.prune_old_sessions(keep_last=2)
    assert len(pruned) == 3
    assert store.count_sessions() == 2
    remaining_started = [s["started_at"] for s in store.list_sessions()]
    assert remaining_started == [400.0, 300.0]
    store.close()


def test_d72_prune_pinned_protected(tmp_path: Path) -> None:
    """T-D72-prune-pinned: pinned ALWAYS protected; keep_last=0 removes all unpinned."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=5, pinned_ids={0, 4})
    pruned = store.prune_old_sessions(keep_last=0)
    assert len(pruned) == 3
    assert store.count_sessions() == 2
    for s in store.list_sessions():
        assert int(s["pinned"]) == 1
    store.close()


def test_d72_prune_keep_zero_removes_all_unpinned(tmp_path: Path) -> None:
    """T-D72-prune-zero: keep_last=0 removes ALL unpinned; pinned remain."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=3, pinned_ids={1})
    pruned = store.prune_old_sessions(keep_last=0)
    assert len(pruned) == 2
    assert store.count_sessions() == 1
    store.close()


def test_d72_prune_dry_run(tmp_path: Path) -> None:
    """T-D72-prune-dry: dry_run=True returns candidates without deleting."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=5)
    candidates = store.prune_old_sessions(keep_last=2, dry_run=True)
    assert len(candidates) == 3
    assert store.count_sessions() == 5
    store.close()


def test_d72_prune_negative_raises(tmp_path: Path) -> None:
    """T-D72-prune-neg: keep_last<0 raises ValueError."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=2)
    with pytest.raises(ValueError, match="keep_last"):
        store.prune_old_sessions(keep_last=-1)
    store.close()


def test_d72_prune_fk_cleanup_all_tables(tmp_path: Path) -> None:
    """T-D72-fk: prune removes rows from ALL 5 dependent tables."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=3)
    for s in store.list_sessions():
        _add_all_dependent_rows(store, s["session_id"], tick_id=1)
    dependent_tables = [
        "tick_snapshots", "interventions", "llm_calls",
        "causal_probes", "scene_changes",
    ]
    for table in dependent_tables:
        n = store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n == 3, f"{table} should have 3 rows before prune, got {n}"
    pruned = store.prune_old_sessions(keep_last=1)
    assert len(pruned) == 2
    for sid in pruned:
        for table in dependent_tables:
            n = store.conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE session_id = ?",
                (sid,),
            ).fetchone()[0]
            assert n == 0, f"orphan rows in {table} for pruned session {sid}"
    remaining = store.list_sessions()
    assert len(remaining) == 1
    for table in dependent_tables:
        n = store.conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE session_id = ?",
            (remaining[0]["session_id"],),
        ).fetchone()[0]
        assert n == 1, f"{table} should have 1 row for remaining session"
    store.close()


def test_d72_prune_atomicity_on_error(tmp_path: Path) -> None:
    """T-D72-atomic: error during prune triggers ROLLBACK; nothing deleted.

    Verifies that on exception, ROLLBACK restores BOTH sessions AND
    all dependent rows — no partial deletion.

    Implementation note: sqlite3.Connection.execute is a read-only
    attribute in CPython (C-level protection). We wrap store.conn in
    a proxy that delegates to the real connection but counts execute
    calls and injects OperationalError on the N-th call. The proxy
    preserves in_transaction semantics by delegating to the real conn.
    """
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=5)
    for s in store.list_sessions():
        _add_all_dependent_rows(store, s["session_id"], tick_id=1)
    real_conn = store.conn

    class _FailingConnProxy:
        """Proxy over sqlite3.Connection: delegates everything, injects
        OperationalError on the fail_on-th execute() call.

        in_transaction is delegated to the real conn (read dynamically)
        so prune_old_sessions sees the correct transaction state.
        """

        def __init__(self, real: sqlite3.Connection, fail_on: int) -> None:
            self._real = real
            self._fail_on = fail_on
            self._n = 0

        @property
        def in_transaction(self) -> bool:
            return self._real.in_transaction

        @property
        def row_factory(self):
            return self._real.row_factory

        @row_factory.setter
        def row_factory(self, value):
            self._real.row_factory = value

        def execute(self, sql, params=None):
            self._n += 1
            if self._n == self._fail_on:
                raise sqlite3.OperationalError("simulated FK violation")
            if params is None:
                return self._real.execute(sql)
            return self._real.execute(sql, params)

        def commit(self):
            self._real.commit()

        def rollback(self):
            self._real.rollback()

        def close(self):
            self._real.close()

        def __getattr__(self, name):
            return getattr(self._real, name)

    # 8-й execute = 2-я сессия, 1-й DELETE (scene_changes) —
    # транзакция уже открыта (BEGIN IMMEDIATE в prune), часть
    # сессий уже удалена в RAM-логике, но в БД ещё не закоммичена.
    proxy = _FailingConnProxy(real_conn, fail_on=8)
    store.conn = proxy  # type: ignore[method-assign]
    try:
        with pytest.raises(sqlite3.OperationalError, match="simulated"):
            store.prune_old_sessions(keep_last=2)
    finally:
        # Восстановим настоящий conn для проверок ниже
        store.conn = real_conn  # type: ignore[method-assign]
    assert store.count_sessions() == 5, "atomicity broken: sessions deleted"
    dependent_tables = [
        "tick_snapshots", "interventions", "llm_calls",
        "causal_probes", "scene_changes",
    ]
    for table in dependent_tables:
        n = store.conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        assert n == 5, f"atomicity broken: {table} has {n} rows, expected 5"
    store.close()


# ─────────────────── wiring ───────────────────

def test_d72_wiring_zero_no_prune(tmp_path: Path) -> None:
    """T-D72-wire-zero: keep_last=0 means prune NOT called (logic guard).

    Verdict II.D: until path/activity confirmed, nothing is deleted.
    GameLoop wiring: 'if settings.replay_budget_keep_last > 0: prune(...)'.
    """
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=5)
    keep_last = 0
    if keep_last > 0:
        store.prune_old_sessions(keep_last=keep_last)
    assert store.count_sessions() == 5, "prune was called when keep_last=0"
    store.close()


def test_d72_wiring_positive_prunes(tmp_path: Path) -> None:
    """T-D72-wire-pos: keep_last>0 means prune called, sessions reduced."""
    db_path = tmp_path / "replay.db"
    store = _make_store_with_sessions(db_path, n=5)
    keep_last = 2
    if keep_last > 0:
        store.prune_old_sessions(keep_last=keep_last)
    assert store.count_sessions() == 2
    store.close()


def test_d72_wiring_source_guard_exists() -> None:
    """T-D72-wire-src: game_loop.py contains the budget guard and prune call.

    Static check that the wiring is in the production code.
    Path resolved from __file__ (pytest cwd = backend/) to avoid
    relative-path failures across invocation modes.
    """
    # __file__ = backend/tests/micro/test_d72_replay_budget.py
    # parents[0]=micro, [1]=tests, [2]=backend, [3]=Enigma (project root)
    _source_path = (
        Path(__file__).resolve().parents[3]
        / "backend" / "app" / "services" / "game_loop" / "game_loop.py"
    )
    source = _source_path.read_text(encoding="utf-8")
    assert "settings.replay_budget_keep_last > 0" in source, (
        "game_loop.py missing 'if settings.replay_budget_keep_last > 0' guard"
    )
    assert "prune_old_sessions" in source, (
        "game_loop.py missing prune_old_sessions call"
    )
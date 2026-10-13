from __future__ import annotations

# backend/tests/micro/test_migration_runner.py
"""
path: backend/tests/micro/test_migration_runner.py
Назначение: T1–T11 — приёмочные тесты MigrationRunner (ADR-O-426,
COV-1/D58, гейт COV-GC-01). Все сценарии на tmp-файлах (II.5:
живые saves/ в тестах не участвуют).
Зависимости: pytest, sqlite3, app.services.state.migration_runner;
app.services.memory.sqlite_store — только T1 (паритет схем).
Основные сущности: _reg/_build_v1/_build_v2/_snap, test_T1..test_T11.
"""

import sqlite3
from pathlib import Path

import pytest

from app.services.state import migration_runner as mr


@pytest.fixture(autouse=True)
def _clean_external():
    """Изоляция тестов от глобального _EXTERNAL_SPECS (register_migrations)."""
    mr._EXTERNAL_SPECS.clear()
    yield
    mr._EXTERNAL_SPECS.clear()


def _reg(db: Path) -> mr.StoreRegistration:
    return mr.StoreRegistration(
        store_id="enigma_memory",
        path_resolver=lambda: db,
        bootstrap_classifier=mr._classify_enigma_memory,
        migrations=(mr._MEMORY_SPEC_V1, mr._MEMORY_SPEC_V2),
    )


def _exec(db: Path, statements: tuple[str, ...], *, rows: int = 0, entries: int = 0) -> None:
    conn = sqlite3.connect(db)
    try:
        for stmt in statements:
            conn.execute(stmt)
        for i in range(rows):
            conn.execute(
                "INSERT INTO event_memories (id, npc_id, campaign_id, event_type, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (f"m{i}", f"npc{i}", "camp", "TALK", "2026-01-01T00:00:00"),
            )
        for i in range(entries):
            conn.execute(
                "INSERT INTO entries (id, collection, timestamp, payload_json)"
                " VALUES (?, ?, ?, ?)",
                (f"e{i}", "col", "t", "{}"),
            )
        conn.commit()
    finally:
        conn.close()


def _build_v1(db: Path, **kw) -> None:
    _exec(db, mr._ENIGMA_MEMORY_V1_STATEMENTS, **kw)


def _build_v2(db: Path, **kw) -> None:
    _exec(db, mr._ENIGMA_MEMORY_V1_STATEMENTS + mr._ENIGMA_MEMORY_V2_STATEMENTS, **kw)


def _snap(db: Path):
    """Множества таблиц/индексов/колонок + row-counts + user_version.
    sqlite_* и _schema_migrations (внутренняя таблица раннера) исключены."""
    conn = sqlite3.connect(db)
    try:
        objs = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','index')"
                " AND name NOT LIKE 'sqlite_%' AND name != '_schema_migrations'"
            )
        }
        cols: dict[str, set[str]] = {}
        counts: dict[str, int] = {}
        for name in objs:
            if name.startswith("idx_"):
                continue
            cols[name] = {c[1] for c in conn.execute(f"PRAGMA table_info({name})")}
            counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()
    return objs, cols, counts, version


def _version(db: Path) -> int:
    conn = sqlite3.connect(db)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def test_T1_fresh_chain_parity_with_store(tmp_path):
    """T1: пустая БД → полная цепочка; паритет МНОЖЕСТВ со свежей БД стора
    (замок двух копий DDL: ALTER аппендит колонку в конец — сравниваем
    множества, не тексты sqlite_master)."""
    from app.services.memory.sqlite_store import SqliteMemoryStore

    store_db = tmp_path / "store.db"
    store = SqliteMemoryStore(store_db)
    store.close()

    runner_db = tmp_path / "runner.db"
    _exec(runner_db, ())  # пустая (0 таблиц) БД — fresh-сценарий
    out = mr.run_startup_migrations([_reg(runner_db)])[0]
    assert out.status == "ok"
    assert out.applied == ((0, 1), (1, 2))

    s_objs, s_cols, _, s_ver = _snap(store_db)
    r_objs, r_cols, _, r_ver = _snap(runner_db)
    assert s_objs == r_objs
    assert s_cols == r_cols
    # стор свою БД не версифицирует — версифицирует раннер (Шаг D на живых)
    assert r_ver == 2 and s_ver == 0


def test_T2_v1_legacy_migrates_data_preserved(tmp_path):
    """T2: v1-легаси с данными → v1→v2; строки сохранены; бэкап хранит
    домиграционное состояние (GC-01 round-trip)."""
    db = tmp_path / "mem.db"
    _build_v1(db, rows=3, entries=2)
    objs_before, cols_before, counts_before, _ = _snap(db)
    assert "secret_id" not in cols_before["event_memories"]

    out = mr.run_startup_migrations([_reg(db)])[0]
    assert out.status == "ok"
    assert out.applied == ((1, 2),)
    assert not out.baseline_stamped

    objs_after, cols_after, counts_after, version = _snap(db)
    assert version == 2
    assert "secret_id" in cols_after["event_memories"]
    assert counts_after == counts_before
    assert objs_after - objs_before == {"idx_event_memories_secret"}

    bak = tmp_path / "mem.db.pre-migration.bak"
    assert out.backup_path == str(bak)
    _, _, bak_counts, bak_ver = _snap(bak)
    assert bak_counts == counts_before
    assert bak_ver == 0


def test_T3_v2_legacy_stamp_without_ddl(tmp_path):
    """T3: v2-легаси → базлайн-штамп без DDL; схема/данные нетронуты (II.3)."""
    db = tmp_path / "mem.db"
    _build_v2(db, rows=2)
    objs_before, cols_before, counts_before, _ = _snap(db)

    out = mr.run_startup_migrations([_reg(db)])[0]
    assert out.status == "ok"
    assert out.applied == ()
    assert out.baseline_stamped

    objs_after, cols_after, counts_after, version = _snap(db)
    assert version == 2
    assert objs_after == objs_before
    assert cols_after == cols_before
    assert counts_after == counts_before


def test_T4_ambiguous_state_refused_untouched(tmp_path):
    """T4: неоднозначное состояние (лишняя таблица) → отказ; файл НЕ изменён (II.1)."""
    db = tmp_path / "mem.db"
    _build_v1(db, rows=1)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE rogue_extra (id TEXT)")
    conn.commit()
    conn.close()
    objs_before, _, counts_before, ver_before = _snap(db)

    with pytest.raises(mr.MigrationError, match="неоднозначное"):
        mr.run_startup_migrations([_reg(db)])

    objs_after, _, counts_after, ver_after = _snap(db)
    assert ver_after == ver_before == 0
    assert objs_after == objs_before
    assert counts_after == counts_before
    assert not (tmp_path / "mem.db.pre-migration.bak").exists()


def test_T5_downgrade_blocked(tmp_path):
    """T5: user_version > HEAD → блокирующий отказ с диагностикой (Ф2)."""
    db = tmp_path / "mem.db"
    _build_v2(db)
    conn = sqlite3.connect(db, isolation_level=None)
    conn.execute("PRAGMA user_version = 999")
    conn.close()

    with pytest.raises(mr.MigrationError, match="ДАУНГРЕЙД"):
        mr.run_startup_migrations([_reg(db)])
    assert _version(db) == 999


def test_T6_idempotent_rerun_noop(tmp_path):
    """T6: повторный запуск = no-op: ни DDL, ни данных, ни аудита (II.3)."""
    db = tmp_path / "mem.db"
    _exec(db, ())  # пустая БД: первый прогон строит полную цепочку
    mr.run_startup_migrations([_reg(db)])
    objs1, cols1, counts1, ver1 = _snap(db)
    conn = sqlite3.connect(db)
    audit1 = conn.execute("SELECT COUNT(*) FROM _schema_migrations").fetchone()[0]
    conn.close()

    out2 = mr.run_startup_migrations([_reg(db)])[0]
    assert out2.status == "ok-noop"
    assert out2.applied == ()

    objs2, cols2, counts2, ver2 = _snap(db)
    assert (objs2, cols2, counts2, ver2) == (objs1, cols1, counts1, ver1)
    conn = sqlite3.connect(db)
    audit2 = conn.execute("SELECT COUNT(*) FROM _schema_migrations").fetchone()[0]
    conn.close()
    assert audit2 == audit1


def test_T7_apply_exception_full_rollback(tmp_path):
    """T7: исключение внутри apply → полный откат: версии/DDL/аудита нет (II.2)."""
    db = tmp_path / "x.db"
    conn = sqlite3.connect(db, isolation_level=None)
    try:
        conn.execute("CREATE TABLE pre (id TEXT)")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO pre VALUES ('a')")
        conn.execute("COMMIT")

        def _boom(c: sqlite3.Connection) -> None:
            c.execute("CREATE TABLE half_done (id TEXT)")
            raise RuntimeError("симуляция отказа посреди миграции")

        spec = mr.MigrationSpec("enigma_memory", 0, 1, "TEST", "fail", _boom)
        with pytest.raises(RuntimeError, match="симуляция"):
            mr._apply_spec(conn, spec)

        assert _version(db) == 0
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "half_done" not in tables
        assert "_schema_migrations" not in tables
        assert conn.execute("SELECT COUNT(*) FROM pre").fetchone()[0] == 1
    finally:
        conn.close()


def _spec(f: int, t: int) -> mr.MigrationSpec:
    return mr.MigrationSpec("enigma_memory", f, t, "TEST", "", lambda c: None)


def test_T8_chain_validation_blocks_before_touch(tmp_path):
    """T8: дыры/дуэли/разрывы цепочки → MigrationError ДО касания БД (II.4)."""
    with pytest.raises(mr.MigrationError, match="стыкуется"):
        mr._check_chain("enigma_memory", [_spec(0, 1), _spec(2, 3)])
    with pytest.raises(mr.MigrationError, match="дуэль"):
        mr._check_chain("enigma_memory", [_spec(0, 1), _spec(0, 2)])
    with pytest.raises(mr.MigrationError, match="to_version"):
        # 0->0: старт-чек проходит (from=0), ловится to_version<=from_version
        mr._check_chain("enigma_memory", [_spec(0, 0)])
    with pytest.raises(mr.MigrationError, match="чужого стора"):
        mr._check_chain("enigma_memory", [mr.MigrationSpec("other", 0, 1, "T", "", lambda c: None)])
    with pytest.raises(mr.MigrationError, match="начинаться"):
        mr._check_chain("enigma_memory", [_spec(1, 2)])
    assert mr._check_chain("enigma_memory", [_spec(0, 1), _spec(1, 2)]) == 2

    # отсутствующий файл → skip БЕЗ создания (кейс replay на неактивной установке)
    missing = tmp_path / "missing.db"
    out = mr.run_startup_migrations([_reg(missing)])[0]
    assert out.status == "skipped"
    assert not missing.exists()


def test_T9_backup_verified_and_protected(tmp_path, monkeypatch):
    """T9: бэкап верифицирован; непроверенная копия НЕ заменяет старый .bak
    (Ф3/II.В); no-op не плодит бэкапы."""
    db = tmp_path / "mem.db"
    _build_v2(db, rows=2)

    out = mr.run_startup_migrations([_reg(db)])[0]
    bak = tmp_path / "mem.db.pre-migration.bak"
    assert out.backup_path == str(bak)
    assert bak.exists()

    # старый .bak + симуляция провала верификации новой копии
    bak.write_text("OLD-SENTINEL", encoding="utf-8")

    def _fail(src: Path, bak_path: Path) -> None:
        raise mr.MigrationError("симуляция провала верификации")

    monkeypatch.setattr(mr, "_verify_backup", _fail)
    with pytest.raises(mr.MigrationError, match="верификации"):
        mr._backup_database(db)
    assert bak.read_text(encoding="utf-8") == "OLD-SENTINEL"
    assert (tmp_path / "mem.db.pre-migration.bak.new").exists()  # артефакт для разбора

    # no-op не трогает бэкап
    mtime = bak.stat().st_mtime_ns
    out2 = mr.run_startup_migrations([_reg(db)])[0]
    assert out2.status == "ok-noop"
    assert out2.backup_path is None
    assert bak.stat().st_mtime_ns == mtime


def _ext_spec() -> mr.MigrationSpec:
    return mr.MigrationSpec(
        store_id="enigma_memory",
        from_version=2,
        to_version=3,
        owner="TEST/A",
        description="внешняя миграция (S1-шаблон)",
        apply=lambda c: c.execute("CREATE TABLE ext_marker (id TEXT)"),
    )


def test_T10_register_migrations_contract(tmp_path):
    """T10: register_migrations — контракт S1: только поверх builtin,
    from_version>=1, без дублей; HEAD поднимается без правки раннера (Ф9)."""
    with pytest.raises(mr.MigrationError, match="builtin-реестре"):
        mr.register_migrations(mr.MigrationSpec("unknown_store", 1, 2, "T", "", lambda c: None))

    mr.register_migrations(_ext_spec())
    with pytest.raises(mr.MigrationError, match="from_version >= 1"):
        mr.register_migrations(mr.MigrationSpec("enigma_memory", 0, 1, "T", "", lambda c: None))
    with pytest.raises(mr.MigrationError, match="дубль"):
        mr.register_migrations(_ext_spec())

    assert dict(mr.validate_registry())["enigma_memory"] == 3

    db = tmp_path / "mem.db"
    _build_v2(db, rows=1)
    out = mr.run_startup_migrations([_reg(db)])[0]
    assert out.head_version == 3
    assert out.applied == ((2, 3),)
    assert _version(db) == 3
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ext_marker").fetchone()[0] == 0
        owners = [r[0] for r in conn.execute("SELECT owner FROM _schema_migrations")]
        assert owners == ["TEST/A"]
    finally:
        conn.close()


def test_T11_schema_plus_one_applied_once(tmp_path):
    """T11: «schema+1» (GC-01 дословно): применяется однократно,
    журналируется; повтор — no-op."""
    mr.register_migrations(_ext_spec())
    db = tmp_path / "mem.db"
    _exec(db, ())  # пустая БД — полная цепочка 0->1->2->3 одним прогоном

    out1 = mr.run_startup_migrations([_reg(db)])[0]
    assert out1.applied == ((0, 1), (1, 2), (2, 3))
    assert out1.to_dict()["applied"] == [[0, 1], [1, 2], [2, 3]]
    assert _version(db) == 3

    out2 = mr.run_startup_migrations([_reg(db)])[0]
    assert out2.status == "ok-noop"
    assert _version(db) == 3

    conn = sqlite3.connect(db)
    try:
        rows = [tuple(r) for r in conn.execute(
            "SELECT from_version, to_version, owner FROM _schema_migrations ORDER BY to_version"
        )]
        assert rows == [(0, 1, "COV-1/Б"), (1, 2, "COV-1/Б"), (2, 3, "TEST/A")]
    finally:
        conn.close()
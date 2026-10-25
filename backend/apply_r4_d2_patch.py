"""
R4/GATE-9A D2 — patch scene_state_manager.py
6 edits with verification. Each edit asserts exactly 1 replacement.
"""
import sys
import shutil
from pathlib import Path

SSM_PATH = Path("app/services/scene_state_manager.py")
BACKUP_PATH = Path("app/services/scene_state_manager.py.r4_backup")

if not SSM_PATH.exists():
    print(f"ERROR: {SSM_PATH} not found"); sys.exit(1)

# Backup once (don't overwrite existing backup)
if not BACKUP_PATH.exists():
    shutil.copy2(SSM_PATH, BACKUP_PATH)
    print(f"[OK] backup: {BACKUP_PATH}")
else:
    print(f"[skip] backup exists: {BACKUP_PATH}")

src = SSM_PATH.read_text(encoding="utf-8")
original_len = len(src)


def apply_edit(src: str, name: str, before: str, after: str) -> str:
    count = src.count(before)
    if count != 1:
        print(f"[FAIL] {name}: expected 1 occurrence, found {count}")
        sys.exit(2)
    new_src = src.replace(before, after, 1)
    print(f"[OK] {name}: 1 replacement applied")
    return new_src


# ─── Edit 1: __init__ — add _tick_aborted field ─────────────────────────
EDIT1_BEFORE = """        self._tick_scenes: dict[str, dict] = {}

    # ── Tick-Scoped Identity API (ADR-SCENE-LOCK) ──────────────────────"""
EDIT1_AFTER = """        self._tick_scenes: dict[str, dict] = {}
        # R4/GATE-9A D2: abort marker. See mark_tick_aborted / unlock_tick.
        # Reset at fresh acquire (lock_for_tick/lock_all_for_tick/adopt) and
        # at end of unlock_tick guard body (both branches, via finally).
        self._tick_aborted: bool = False

    # ── Tick-Scoped Identity API (ADR-SCENE-LOCK) ──────────────────────"""
src = apply_edit(src, "Edit 1: __init__ _tick_aborted", EDIT1_BEFORE, EDIT1_AFTER)


# ─── Edit 2: lock_for_tick fresh path — reset marker ────────────────────
EDIT2_BEFORE = """            self._tick_locked = True
            self._tick_campaign_id = campaign_id
            self._tick_scenes[location_id] = scene
            try:
                _recog = scene.get("player_recognition", {})"""
EDIT2_AFTER = """            self._tick_locked = True
            self._tick_campaign_id = campaign_id
            self._tick_scenes[location_id] = scene
            self._tick_aborted = False  # R4/GATE-9A D2: reset at fresh acquire
            try:
                _recog = scene.get("player_recognition", {})"""
src = apply_edit(src, "Edit 2: lock_for_tick reset", EDIT2_BEFORE, EDIT2_AFTER)


# ─── Edit 3: lock_all_for_tick — reset marker ──────────────────────────
EDIT3_BEFORE = """        self._tick_locked = True
        self._tick_campaign_id = campaign_id
        self._tick_scenes = {}
        for _loc_id in location_ids:"""
EDIT3_AFTER = """        self._tick_locked = True
        self._tick_campaign_id = campaign_id
        self._tick_scenes = {}
        self._tick_aborted = False  # R4/GATE-9A D2: reset at fresh acquire
        for _loc_id in location_ids:"""
src = apply_edit(src, "Edit 3: lock_all_for_tick reset", EDIT3_BEFORE, EDIT3_AFTER)


# ─── Edit 4: adopt_scene_for_tick — reset marker + insert mark_tick_aborted
EDIT4_BEFORE = """        self._tick_locked = True
        self._tick_campaign_id = campaign_id
        self._tick_scenes[location_id] = scene_state

    def is_tick_locked_for(self, campaign_id: str) -> bool:"""
EDIT4_AFTER = """        self._tick_locked = True
        self._tick_campaign_id = campaign_id
        self._tick_scenes[location_id] = scene_state
        self._tick_aborted = False  # R4/GATE-9A D2: reset at fresh acquire

    def mark_tick_aborted(self, campaign_id: str) -> None:
        \"\"\"R4/GATE-9A D2: помечает текущий тик как аварийный.

        Контракт:
        - Эффективен ТОЛЬКО при подтверждённом владении: lock удержан
          И _tick_campaign_id == campaign_id. Использует тот же guard,
          что и unlock_tick @238. Если вызывающий код не владеет тиком —
          silent no-op, чужое состояние НЕ затрагивается.
        - В последующем unlock_tick(campaign_id) пропускаются:
          atomic_commit_all, _sync_relationship_directed,
          _confirm_v2_migration. Persistence остаётся в pre-tick.
        - _tick_scenes НЕ очищается (мост SSE может читать); следующий
          fresh lock_for_tick загрузит pre-tick сцену из persistence
          (in-memory rollback через замену слота).

        Сброс маркера:
        - при fresh acquire (lock_for_tick/lock_all_for_tick/adopt)
        - в конце тела guard unlock_tick (обе ветки: persist и skip),
          через finally — гарантированно даже при исключении.
        \"\"\"
        if self._tick_locked and self._tick_campaign_id == campaign_id:
            self._tick_aborted = True
        # else: silent no-op — caller не владеет текущим тиком

    def is_tick_locked_for(self, campaign_id: str) -> bool:"""
src = apply_edit(src, "Edit 4: adopt reset + mark_tick_aborted method", EDIT4_BEFORE, EDIT4_AFTER)


# ─── Edit 5: unlock_tick — wrap persist in if not _tick_aborted, use finally
EDIT5_BEFORE = """    def unlock_tick(self, campaign_id: str) -> None:
        \"\"\"Разблокирует тик. Персистит кэш.
        ADR-SCENE-LOCK: НЕ очищаем _tick_scene сразу — bridge может читать его
        в SSE-потоке после unlock. Кэш живёт до следующего lock_for_tick().\"\"\"
        if self._tick_locked and self._tick_campaign_id == campaign_id:
            # СНИМАЕМ LOCK ДО save — иначе guard в save_scene_state() сделает return!
            self._tick_locked = False
            # S1-FIX (INV-COMMIT-CARDINALITY): 1 атомарный коммит для всех локаций.
            _valid_scenes = {k: v for k, v in self._tick_scenes.items() if v is not None}
            if self._persistence and _valid_scenes:
                # M1b.4.2: directed-поддерево обязано быть идентичным во всех
                # локациях кампании (отношения переживают смену локации) —
                # синхронизация ДО транзакции, консистентность — транзакцией.
                self._sync_relationship_directed(_valid_scenes)
                self._persistence.atomic_commit_all(
                    campaign_id=campaign_id,
                    all_scenes=_valid_scenes,
                )
                # M1b.4.2: маркер .migrated только ПОСЛЕ успешного коммита
                # (ратифицировано: истина cutover — сохранённый v2, не маркер)
                self._confirm_v2_migration(campaign_id)
            # Диагностика: round-trip проверка — пережил ли traversal save→load?
            if self._persistence and self._tick_scenes:
                # Проверяем первую попавшуюся сцену из кэша
                _verify = self._persistence.load_scene(campaign_id)
                _trav_after = (
                    list(_verify.get("active_traversals", {}).keys())
                    if _verify
                    else "LOAD_FAILED"
                )
                logger.debug(f"[UNLOCK_TRACE] AFTER LOAD: traversals={_trav_after}")
            # НЕ очищаем _tick_scenes! Bridge может читать их в SSE-потоке.
            # Кэш будет заменён при следующем lock_for_tick()."""

EDIT5_AFTER = """    def unlock_tick(self, campaign_id: str) -> None:
        \"\"\"Разблокирует тик. Персистит кэш (если тик НЕ помечен aborted).

        ADR-SCENE-LOCK: НЕ очищаем _tick_scene сразу — bridge может читать его
        в SSE-потоке после unlock. Кэш живёт до следующего lock_for_tick().

        R4/GATE-9A D2: если mark_tick_aborted(campaign_id) был вызван
        legitimate владельцем, atomic_commit_all / _sync_relationship_directed
        / _confirm_v2_migration пропускаются — persistence остаётся в pre-tick.
        Guard владения сохранён — только legitimate owner снимает блокировку;
        аварийная ветка меняет только решение о persist, не сам факт снятия.
        Маркер _tick_aborted сбрасывается через finally — гарантированно, даже
        при исключении в atomic_commit_all (блокер Мастера).
        \"\"\"
        if self._tick_locked and self._tick_campaign_id == campaign_id:
            # Guard владения сохранён — только legitimate owner снимает блокировку.
            # СНИМАЕМ LOCK ДО save — иначе guard в save_scene_state() сделает return!
            self._tick_locked = False
            try:
                if not self._tick_aborted:
                    # Нормальный путь — штатный persist.
                    # S1-FIX (INV-COMMIT-CARDINALITY): 1 атомарный коммит для всех локаций.
                    _valid_scenes = {k: v for k, v in self._tick_scenes.items() if v is not None}
                    if self._persistence and _valid_scenes:
                        # M1b.4.2: directed-поддерево обязано быть идентичным во всех
                        # локациях кампании (отношения переживают смену локации) —
                        # синхронизация ДО транзакции, консистентность — транзакцией.
                        self._sync_relationship_directed(_valid_scenes)
                        self._persistence.atomic_commit_all(
                            campaign_id=campaign_id,
                            all_scenes=_valid_scenes,
                        )
                        # M1b.4.2: маркер .migrated только ПОСЛЕ успешного коммита
                        # (ратифицировано: истина cutover — сохранённый v2, не маркер)
                        self._confirm_v2_migration(campaign_id)
                    # Диагностика: round-trip проверка — пережил ли traversal save→load?
                    if self._persistence and self._tick_scenes:
                        # Проверяем первую попавшуюся сцену из кэша
                        _verify = self._persistence.load_scene(campaign_id)
                        _trav_after = (
                            list(_verify.get("active_traversals", {}).keys())
                            if _verify
                            else "LOAD_FAILED"
                        )
                        logger.debug(f"[UNLOCK_TRACE] AFTER LOAD: traversals={_trav_after}")
                # else: тик помечен aborted — пропускаем persist и round-trip verify.
                # _tick_scenes остаётся в памяти (SSE bridge может читать); следующий
                # fresh lock_for_tick загрузит pre-tick сцену из persistence.
            finally:
                # R4/GATE-9A D2: всегда сбрасываем маркер аварии в конце
                # жизненного цикла (обе ветки: persist и skip), даже при
                # исключении в atomic_commit_all (блокер Мастера).
                self._tick_aborted = False
            # НЕ очищаем _tick_scenes! Bridge может читать их в SSE-потоке.
            # Кэш будет заменён при следующем lock_for_tick()."""
src = apply_edit(src, "Edit 5: unlock_tick with if not _tick_aborted + finally", EDIT5_BEFORE, EDIT5_AFTER)


# ─── Write result ───────────────────────────────────────────────────────
SSM_PATH.write_text(src, encoding="utf-8")
new_len = len(src)
print()
print(f"[DONE] {SSM_PATH} patched: {original_len} -> {new_len} bytes (+{new_len - original_len})")
print("[DONE] Backup at:", BACKUP_PATH)
print()
print("Next: re-run tests with: python -m pytest tests/test_r4_d2_ssm.py -v --tb=short")

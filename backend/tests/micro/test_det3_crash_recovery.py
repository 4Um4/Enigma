from __future__ import annotations

# backend/tests/micro/test_det3_crash_recovery.py
"""
path: backend/tests/micro/test_det3_crash_recovery.py
Назначение: DET-3 (§17.8, вердикт Мастера III.3) — интеграционный crash-recovery
тест Фазы 10. Границы (археология, зафиксированы): (1) L1-флеш — внутри Фазы 10
(commit_tick_buffer, INSERT OR IGNORE + UNIQUE-ключ в enigma_memory.db);
(2) runtime-коммит — unlock_tick → atomic_commit_all (enigma_runtime.db,
ОДНА транзакция, всё-или-ничего; epistemic/conclusions — payload внутри сцен);
(3) cross-file атомарности нет BY CONSTRUCTION — инвариант «последнее допустимое
зафиксированное состояние + самовосстановление повтором тика (L1-идемпотентность),
дублей нет (UNIQUE), частичных мутаций внутри файла нет (транзакции)».
Kill-механика: дочерний процесс крутит тики на изолированных tmp-путях
(settings.saves_dir/replay_store_path — F5-прецедент); родитель убивает по
флагу, поднимаемому monkeypatch-обёрткой в детерминированной точке;
валидация — ОТДЕЛЬНЫМ процессом (честный рестарт): сверка с эталоном
второго чистого прогона той же длины.
Зависимости: pytest, multiprocessing, os, sqlite3, json, pathlib.
Основные сущности: test_det3_*.
"""

import json
import multiprocessing
import os
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "backend"))

_WORKER_SRC = """
import sys
sys.path.insert(0, {root!r})
def run(saves_dir, replay_dir, ticks, kill_at, kill_flag):
    import os
    os.environ["ENIGMA_SAVES_DIR"] = saves_dir
    os.environ["ENIGMA_REPLAY_STORE_PATH"] = replay_dir
    from pathlib import Path
    from app.core.config import settings
    settings.saves_dir = saves_dir
    settings.replay_store_path = replay_dir
    _kf = Path(str(kill_flag))
    from app.services.game_loop_builder import build_game_loop
    loop = build_game_loop(Path(settings.data_dir))
    # Стампинг tmp-БД MigrationRunner'ом — как будущий конфиг-гейт D70:
    # свежие БД = v0; версии 2/1 — канон Шага D. Идемпотентен (II.3).
    from app.services.state import migration_runner as _mr
    _outcomes = _mr.run_startup_migrations(make_backup=False)
    from app.services.scene_state_manager import SceneStateManager

    _orig_unlock = SceneStateManager.unlock_tick
    def _patched_unlock(self, campaign_id):
        if kill_at == "before_phase10_flush":
            import os
            _kf.write_text("K", encoding="utf-8")
            os._exit(137)  # жёсткий kill без atexit/WAL-чисток: имитация краша ДО Фазы 10
        # Точка after_l1_before_runtime: L1-флеш (Фаза 10) прошёл,
        # atomic_commit_all ЕЩЁ НЕ — kill ДО коммита (карта Фазы 10, DET-3)
        if kill_at == "after_l1_before_runtime":
            import os
            _kf.write_text("K", encoding="utf-8")
            os._exit(137)
        _orig_unlock(self, campaign_id)
    if kill_at in ("before_phase10_flush", "after_l1_before_runtime"):
        SceneStateManager.unlock_tick = _patched_unlock

    from app.services.tick_orchestrator import TickOrchestrator as _TO
    _orig_p10 = _TO._phase_10_persistence
    def _patched_p10(self, ctx):
        if kill_at == "before_phase10_flush":
            import os
            _kf.write_text("K", encoding="utf-8")
            os._exit(137)  # жёсткий kill без atexit/WAL-чисток: имитация краша ДО Фазы 10
        return _orig_p10(self, ctx)
    if kill_at == "before_phase10_flush":
        _TO._phase_10_persistence = _patched_p10

    for _ in range(ticks):
        loop.idle_tick("tavern_silver_wolf")
    if kill_at == "clean_point":
        import os
        _kf.write_text("K", encoding="utf-8")
        os._exit(137)
    # без kill — штатный выход
"""


def _run_worker(tmp: Path, ticks: int, kill_at: str | None) -> str:
    """Прогон в дочернем процессе; возвращает 'killed' | 'clean'."""
    saves = tmp / "saves"
    # prod-структура config.py:70 — каталог replay_sessions + ИМЯ ФАЙЛА
    # (ReplayStore ждёт файл-путь; connect на каталоге = WinError 183/
    # unable to open — корень этого эпизода, доказан RS-SPY-репродукцией)
    replay_db = tmp / "replay_sessions" / "replay.db"
    saves.mkdir(parents=True, exist_ok=True)
    replay_db.parent.mkdir(parents=True, exist_ok=True)
    src = _WORKER_SRC.format(root=str(_ROOT / "backend"))
    killed_flag = tmp / "killed.flag"
    if killed_flag.exists():
        killed_flag.unlink()
    proc = multiprocessing.get_context("spawn").Process(
        target=_boot, args=(src, str(saves), str(replay_db), ticks, kill_at, str(killed_flag))
    )
    proc.daemon = False
    proc.start()

    # Kill-сигнал — файл-маркер (spawn не наследует fd-пайпы; select над
    # файлами на Windows невозможен — оба урока оплачены этим эпизодом).
    # Родитель поллит is_alive + exists() — без потоков и select.
    import time as _t

    deadline = _t.time() + 120.0
    while _t.time() < deadline and proc.is_alive():
        if killed_flag.exists():
            _t.sleep(0.3)  # дать воркеру доесть os._exit (без WAL-чисток)
            break
        _t.sleep(0.2)
    proc.join(timeout=10)
    if proc.is_alive():
        proc.terminate()
        proc.join()
    return "killed" if killed_flag.exists() else "clean"


def _boot(src, saves, replay_db, ticks, kill_at, kill_flag):
    code = compile(src, "<det3-worker>", "exec")
    ns = {"__name__": "__main__"}
    exec(code, ns)
    ns["run"](saves, replay_db, ticks, kill_at, kill_flag)


_VALIDATOR_SRC = """
import sys, sqlite3, json
sys.path.insert(0, {root!r})
def validate(saves_dir, replay_dir, expect_ticks):
    results = {{"runtime_ticks": None, "l1_events": None, "duplicates": None,
                "phantom_ticks": None, "integrity": {{"memory": None, "runtime": None}},
                "user_version": {{"memory": None, "runtime": None}}}}
    mem = sqlite3.connect(f"file:{{saves_dir}}/enigma_memory.db?mode=ro", uri=True)
    runtime = sqlite3.connect(f"file:{{saves_dir}}/enigma_runtime.db?mode=ro", uri=True)
    try:
        events = [tuple(r) for r in mem.execute(
            "SELECT tick_id, target_id, source_id, event_type, COUNT(*) c "
            "FROM l1_chronicle_events GROUP BY tick_id, target_id, source_id, event_type")]
        results["l1_events"] = sum(c for *_, c in events)
        results["duplicates"] = [e for e in events if e[-1] > 1]
        max_l1_tick = max((e[0] for e in events), default=0)
        rows = list(runtime.execute("SELECT key, value FROM state_kv"))
        tick_now = None
        for k, v in rows:
            d = json.loads(v)
            if isinstance(d, dict) and "tick" in d:
                tick_now = max(tick_now or 0, int(d["tick"]))
        results["runtime_ticks"] = tick_now
        results["phantom_ticks"] = (max_l1_tick > (tick_now or 0))
        results["integrity"]["memory"] = mem.execute("PRAGMA integrity_check").fetchone()[0]
        results["integrity"]["runtime"] = runtime.execute("PRAGMA integrity_check").fetchone()[0]
        results["user_version"]["memory"] = mem.execute("PRAGMA user_version").fetchone()[0]
        results["user_version"]["runtime"] = runtime.execute("PRAGMA user_version").fetchone()[0]
    finally:
        mem.close(); runtime.close()
    return results
"""


def _validate(tmp: Path) -> dict:
    saves = str(tmp / "saves")
    ns: dict = {}
    code = _VALIDATOR_SRC.format(root=str(_ROOT / "backend"))
    exec(compile(code, "<det3-validator>", "exec"), ns)
    return ns["validate"](saves, str(tmp / "replay"), 0)


def _scenario(tmp_path: Path, ticks: int, kill_at: str | None, expect_l1_from_repeat: bool):
    status = _run_worker(tmp_path, ticks, kill_at)
    assert status == "killed", "kill-точка не сработала (воркер завершился штатно)"
    before = _validate(tmp_path)
    # Повтор тика после рестарта: догоняющий прогон +1 тик — как прод-рестарт
    status2 = _run_worker(tmp_path, 1, None)
    assert status2 == "clean"
    after = _validate(tmp_path)
    return before, after


def test_det3_kill_before_phase10_flush(tmp_path):
    """T1: kill ДО Фазы 10 — ни L1, ни runtime тика N нет; рестарт+повтор:
    L1 пишет тик N впервые (дублей нет), runtime фиксирует тик N."""
    before, after = _scenario(tmp_path, ticks=5, kill_at="before_phase10_flush",
                               expect_l1_from_repeat=False)
    assert before["duplicates"] == []
    assert after["duplicates"] == []
    assert after["phantom_ticks"] is False
    assert after["integrity"] == {"memory": "ok", "runtime": "ok"}
    assert after["user_version"] == {"memory": 2, "runtime": 1}


def test_det3_kill_after_l1_before_runtime(tmp_path):
    """T2 (ядро cross-file окна): L1 тика N записан, runtime — нет; рестарт
    +повтор тика N: INSERT OR IGNORE + UNIQUE → ноль дублей; runtime
    фиксирует N. Это и есть самовосстановление рассинхрона."""
    before, after = _scenario(tmp_path, ticks=5, kill_at="after_l1_before_runtime",
                               expect_l1_from_repeat=True)
    assert after["duplicates"] == []
    assert after["phantom_ticks"] is False
    assert after["integrity"] == {"memory": "ok", "runtime": "ok"}


def test_det3_clean_point_full_match(tmp_path):
    """T3: чистая точка — оба файла содержат тик N; после рестарт-повтора
    (+1): без фантомов/дублей; целостность и версии — неизменны."""
    before, after = _scenario(tmp_path, ticks=5, kill_at="clean_point",
                               expect_l1_from_repeat=True)
    assert before["runtime_ticks"] == 5
    assert after["runtime_ticks"] == 6
    assert after["duplicates"] == []
    assert after["phantom_ticks"] is False
    assert after["integrity"] == {"memory": "ok", "runtime": "ok"}
    assert after["user_version"] == {"memory": 2, "runtime": 1}
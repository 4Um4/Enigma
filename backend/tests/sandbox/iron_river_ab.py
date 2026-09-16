"""
path: /project/backend/tests/sandbox/iron_river_ab.py
Назначение: IRON RIVER D-1/F1 — мини A/B канон-дифф (два подпроцесса,
    один ambient-паттерн, 150 тиков, канонический хеш сцены; real_ts
    исключён). Замена отсутствующему iron_river_run.py (Linux-сессия).
    D-3: копия data/ ЦЕЛИКОМ кроме replay.db/logs (наблюдательные
    артефакты) — память NPC (jsonl/SQLite) каузальна, обрезка входов
    в ранней версии давала кросс-прогонный хаос (4 уникальных хеша).
    atexit-очистка temp против утечки диска (WinError 112-урок).
Зависимости: subprocess, hashlib, json, tempfile
Основные сущности: _RUNNER (код подпроцесса), main
Запуск: cd backend; python tests/sandbox/iron_river_ab.py
"""
import os
import subprocess
import sys

_RUNNER = r"""
import sys, tempfile, types, os, hashlib, json, shutil, atexit
from pathlib import Path
sys.path.insert(0, ".")
from app.core.config import settings

# IRON RIVER D-3 (F4): ПОЛНОЕ temp-окружение с ПОЛНЫМИ входами.
# P0-4: life_engine.sessions_dir = data_dir/"sessions" (хардкод от
# data_dir) → копия data/ изолирует счётчик тиков. Production не тронут.
# Урок WinError 112 + хаос-урок: исключаем ТОЛЬКО replay.db и logs —
# наблюдательные артефакты; память NPC (jsonl/SQLite) — каузальный вход,
# обрезка недопустима (кросс-прогонный MISMATCH на пустых входах).
# ФИНАЛЬНЫЙ ФИКС ИЗОЛЯЦИИ: settings.data_dir на temp-копию —
# LifeEngine.sessions_dir (life_engine:245) строится ОТ settings.data_dir
# (НЕ от аргумента build_game_loop!) → без подмены TemporalEngine писал
# world_tick.json в ЖИВОЙ backend/data/sessions → RUN2 наследовал sim_tick
# RUN1 (+150) → систематический MISMATCH. Диагноз iron_river_trace.
_data_src = Path(settings.data_dir)
_data_tmp = Path(tempfile.mkdtemp(prefix="ab_f4_data_"))
_ignore = shutil.ignore_patterns("replay.db", "logs")
shutil.copytree(_data_src, _data_tmp, dirs_exist_ok=True, ignore=_ignore)
atexit.register(lambda: shutil.rmtree(_data_tmp, ignore_errors=True))
_wt = _data_tmp / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
# ЕДИНСТВЕННОЕ ДОБАВЛЕНИЕ к прежнему патчу:
settings.data_dir = str(_data_tmp)
settings.saves_dir = tempfile.mkdtemp(prefix="ab_f1_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
from app.services.game_loop_builder import build_game_loop
w = types.SimpleNamespace(game_loop=build_game_loop(_data_tmp))
# Phase B: router-stub (прецедент eat/work-тестов) — БЕЗ него executor
# ретраит мёртвую llama по wall-clock (1с/2с/300s) → успех диалога =
# функция реального времени → P2-5-интерливинг в тестовом окне.
_sched = getattr(w.game_loop, "_task_scheduler", None)
_exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
if _exec is not None and hasattr(_exec, "_router"):
    _exec._router = None
for _ in range(150):
    w.game_loop.idle_tick("Open_road")
scene = w.game_loop.scene_manager.get_scene_state("Open_road", "tavern") or {}
def canon(o):
    if isinstance(o, dict):
        return {k: ("<RT>" if k == "real_ts" else canon(v)) for k, v in sorted(o.items())}
    if isinstance(o, list):
        return [canon(x) for x in o]
    return o
print("HASH " + hashlib.sha256(json.dumps(canon(scene), sort_keys=True, default=str).encode()).hexdigest())
"""

def main() -> int:
    hashes = []
    for i in range(2):
        if i == 1:
            import time as _t

            _t.sleep(3.0)  # Phase B: охлаждение RUN2 (ОС-разогрев/интерливинг)
        _env = dict(os.environ)
        # Phase B/F5-зонд: фиксация PYTHONHASHSEED — разводит set-порядки
        # (P1-класс IRON RIVER) от async-остатков (P2-5)
        _env["PYTHONHASHSEED"] = "0"
        r = subprocess.run(
            [sys.executable, "-c", _RUNNER],
            capture_output=True, text=True, cwd=".", env=_env,
        )
        # WIN-урок (48 утечек): подпроцессный atexit+rmtree не справляется
        # с открытыми SQLite-хэндлами на Windows — родитель дочищает
        # префиксные каталоги после КАЖДОГО RUN (процесс вышел — хэндлы закрыты)
        import glob
        import shutil as _sh

        for _p in glob.glob(
            os.path.join(os.environ.get("TEMP", "."), "ab_f4_data_*")
        ):
            _sh.rmtree(_p, ignore_errors=True)
        line = next((l for l in r.stdout.splitlines() if l.startswith("HASH ")), "")
        if not line:
            print(f"RUN{i+1}: ERR")
            print("STDERR tail:", r.stderr.strip().splitlines()[-3:])
            hashes.append(None)
        else:
            hashes.append(line[5:])
            print(f"RUN{i+1}: {line[5:]}")
    if hashes[0] and hashes[0] == hashes[1]:
        print("VERDICT: MATCH")
        return 0
    print("VERDICT: MISMATCH")
    return 1

if __name__ == "__main__":
    sys.exit(main())
"""
path: backend/app/services/llm/server_lifecycle.py
Назначение: Управление жизненным циклом llama-server (start/stop/restart).
    COV-2/D61 (вердикт Мастера): единственный backend-владелец запуска и
    остановки; сериализация рестартов (asyncio.Lock); kill только
    ПРОВЕРЕННОГО llama-server (имя процесса по PID — произвольный процесс на
    занятом порту не завершается); готовность = HTTP /health 200 (модель
    загружена, не «процесс жив»); успех рестарта => сброс backoff пула.
    Классификация причин — перенос _LLM_REASONS-словаря game_launcher без
    изменения самого лаунчера.
Зависимости: app.core.config.settings; psutil (лениво, netstat-fallback).
Основные сущности: start_llama_server, restart_llama_server, kill_llama_server,
    acquire_llama_server_lock, _port_owner_pid, _stop_llama_server,
    _spawn_llama_server, _await_llama_ready, _llama_server_reasons.
"""
import asyncio
import atexit
import logging
import time
import urllib.request
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Глобальное состояние процесса (dict для передачи по ссылке)
_llama_state: dict[str, Any] = {
    "proc": None,
    "started_by_us": False,
    "restart_count": 0,
    "last_restart_time": 0.0,
}

# COV-2/D61: сериализация рестартов — одна попытка в момент времени.
# Модульный уровень: Python 3.10+ не привязывает Lock к loop при создании.
_restart_lock: asyncio.Lock | None = None


def _get_restart_lock() -> asyncio.Lock:
    global _restart_lock
    if _restart_lock is None:
        _restart_lock = asyncio.Lock()
    return _restart_lock


def _llama_server_reasons() -> dict:
    """Классификация причин для UI (ключи стабильны как API-контракт).

    Перенос словаря game_launcher._LLM_REASONS-стиля без изменения
    game_launcher (вердикт Мастера)."""
    return {
        "not_needed": "Сервер уже запущен и готов.",
        "exe_missing": "Не найден llama-server.exe — движок AI отсутствует.",
        "model_missing": "Файл модели не найден или повреждён.",
        "spawn_crashed": "llama-server упал сразу после запуска.",
        "load_timeout": "Модель не загрузилась за отведённое время.",
        "port_busy_unknown_owner": (
            "Порт занят процессом, не являющимся llama-server."
        ),
        "error": "Неожиданная ошибка перезапуска.",
    }


def _port_owner_pid(port: int) -> str:
    """PID владельца listening-порта (Windows): psutil → netstat → unknown.

    Перенос из scripts/llm_server_manager.py; 'unknown' — честный ответ, не
    выдуманный ноль. Прод-код app/: тихий pass запрещён (INV-SILENT-FAILURE)."""
    import subprocess as _sp

    try:
        import psutil

        for _c in psutil.net_connections(kind="tcp"):
            if (
                _c.laddr
                and _c.laddr.port == port
                and _c.status == psutil.CONN_LISTEN
                and _c.pid
            ):
                return str(_c.pid)
    except Exception as e:
        logger.debug(f"[LLM_PORT] psutil недоступен: {e}")
    try:
        _out = _sp.run(
            ["netstat", "-aon"], capture_output=True, text=True, timeout=5
        ).stdout
        for _line in _out.splitlines():
            if f":{port}" in _line and "LISTENING" in _line.upper():
                _parts = _line.split()
                if _parts:
                    return _parts[-1]
    except Exception as e:
        logger.warning(f"[LLM_PORT] netstat не удался: {e}")
    return "unknown"


def kill_llama_server() -> None:
    """atexit: останавливаем ТОЛЬКО сервер, поднятый нами (started_by_us).

    Сервер game_launcher не трогаем — владение сохраняется за спавнером."""
    if _llama_state.get("started_by_us") and _llama_state.get("proc") is not None:
        _stop_llama_server()


def _stop_llama_server() -> str:
    """Остановка llama-server по владельцу порта.

    Возврат: 'stopped' | 'not_found' | 'refused: <причина>' | 'error: <...>'.
    Вердикт Мастера: произвольный процесс на занятом порту НЕ завершается —
    сначала проверка имени процесса (llama-server.exe / main.exe)."""
    import psutil

    _pid = _port_owner_pid(settings.llama_cpp_port)
    if _pid == "unknown":
        return "not_found"
    try:
        _proc = psutil.Process(int(_pid))
        _name = (_proc.name() or "").lower()
        if _name not in ("llama-server.exe", "main.exe"):
            logger.warning(
                f"[LLM_STOP] порт {settings.llama_cpp_port} занят {_name} "
                f"(pid={_pid}) — не llama-server, не трогаем"
            )
            return f"refused: порт занят {_name} (pid={_pid})"
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except Exception:
            _proc.kill()
        logger.info(f"[LLM_STOP] llama-server (pid={_pid}) остановлен")
        return "stopped"
    except Exception as e:
        logger.warning(f"[LLM_STOP] не удалось остановить pid={_pid}: {e}")
        return f"error: {e}"


def _read_stderr_tail() -> str:
    """Хвост stderr-лога (последние 20 строк) для диагноза краша спавна."""
    _path = Path(__file__).resolve().parents[3] / "logs" / "llama_server_stderr.log"
    try:
        with open(_path, "r", encoding="utf-8") as f:
            return "".join(f.readlines()[-20:])
    except Exception as e:
        logger.debug(f"[LLM_STOP] stderr-хвост недоступен: {e}")
        return ""


def _spawn_llama_server() -> dict:
    """Канонический спавн (перенос блока main.py; host=127.0.0.1 —
    выравнивание с провайдерами/лаунчером: резолв localhost добавляет
    секунды к каждому health-запросу на части машин, наблюдено замерами)."""
    import os
    import subprocess as _sp

    if not os.path.exists(settings.llama_cpp_model_path):
        return {
            "started": False,
            "reason": "model_missing",
            "detail": settings.llama_cpp_model_path,
        }
    if not os.path.exists(settings.llama_cpp_server_executable):
        return {
            "started": False,
            "reason": "exe_missing",
            "detail": settings.llama_cpp_server_executable,
        }
    # Порт занят кем-то, не отвечающим health: спавн на занятый порт =
    # немедленный краш; безопасная обработка занятого порта (вердикт Мастера).
    _owner = _port_owner_pid(settings.llama_cpp_port)
    if _owner != "unknown":
        return {
            "started": False,
            "reason": "port_busy_unknown_owner",
            "detail": f"порт занят pid={_owner}",
        }
    _cmd = [
        settings.llama_cpp_server_executable,
        "-m", settings.llama_cpp_model_path,
        "--port", str(settings.llama_cpp_port),
        "--host", "127.0.0.1",
        "-ngl", str(settings.effective_gpu_layers),
        "-c", str(settings.ctx_size),
        "-t", str(settings.threads),
    ]
    _stderr_path = (
        Path(__file__).resolve().parents[3] / "logs" / "llama_server_stderr.log"
    )
    _stderr_path.parent.mkdir(parents=True, exist_ok=True)
    _stderr_file = open(_stderr_path, "a", encoding="utf-8")
    try:
        _proc = _sp.Popen(
            _cmd,
            stdout=_sp.DEVNULL,
            stderr=_stderr_file,
            creationflags=_sp.CREATE_NO_WINDOW
            if hasattr(_sp, "CREATE_NO_WINDOW")
            else 0,
        )
    finally:
        _stderr_file.close()
    _llama_state["proc"] = _proc
    _llama_state["started_by_us"] = True
    return {
        "started": True,
        "reason": "ok",
        "detail": f"pid={_proc.pid}",
        "proc": _proc,
    }


def _reset_backoff_if_pool() -> None:
    """Сброс доказанного отказа пула (если пул инициализирован)."""
    try:
        from app.services.llm.provider_manager import get_model_pool

        _pool = get_model_pool()
        if _pool is not None:
            _pool.pool_reset_backoff()
    except Exception as e:
        logger.warning(f"[LLM_RESTART] сброс backoff пула не удался: {e}")


async def _await_llama_ready(proc: Any) -> dict:
    """Живость после спавна (1с) + поллинг HTTP-готовности модели.

    Готовность = /health 200 (модель загружена), НЕ «процесс жив».
    Бюджет: settings.model_load_timeout_sec. Успех => сброс backoff."""
    await asyncio.sleep(1)
    if proc.poll() is not None:
        _tail = _read_stderr_tail()
        return {
            "started": False,
            "reason": "spawn_crashed",
            "detail": f"exit={proc.returncode}: {_tail[:300]}",
        }
    _deadline = time.monotonic() + settings.model_load_timeout_sec
    _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < _deadline:
        try:
            with _opener.open(
                f"{settings.llama_cpp_server_url}/health", timeout=2
            ) as _r:
                if _r.status == 200:
                    _reset_backoff_if_pool()
                    _llama_state["restart_count"] += 1
                    _llama_state["last_restart_time"] = time.time()
                    return {
                        "started": True,
                        "reason": "ok",
                        "detail": "модель загружена и готова",
                    }
        except Exception as e:
            logger.debug(f"[LLM_READY] ещё не готов: {e}")
        await asyncio.sleep(2)
    return {
        "started": False,
        "reason": "load_timeout",
        "detail": (
            f"готовность не достигнута за {settings.model_load_timeout_sec}с"
        ),
    }


async def start_llama_server() -> dict:
    """COV-2/D61: старт при поднятии бэкенда (замена spawn-блока main.py).

    reuse-лок: готов/грузится — не трогаем. Свободный порт — спавн +
    поллинг готовности. Единый контракт результата {started, reason, detail}."""
    _verdict, _why = acquire_llama_server_lock(
        settings.llama_cpp_port,
        f"{settings.llama_cpp_server_url}/health",
    )
    if _verdict == "reuse":
        return {"started": True, "reason": "not_needed", "detail": _why}
    _spawn = _spawn_llama_server()
    if not _spawn["started"]:
        return {
            "started": False,
            "reason": _spawn["reason"],
            "detail": _spawn["detail"],
        }
    return await _await_llama_ready(_spawn["proc"])


async def restart_llama_server() -> dict:
    """COV-2/D61 (вердикт Мастера): настоящий перезапуск.

    Сериализация (lock); kill только проверенного llama-server; спавн
    канонической командой; готовность = HTTP 200; успех => сброс backoff.
    Идемпотентность: при уже готовом сервере — немедленный успех not_needed
    (защита от повторных нажатий «Повторить»)."""
    async with _get_restart_lock():
        try:
            with urllib.request.urlopen(
                f"{settings.llama_cpp_server_url}/health", timeout=2
            ) as _r:
                if _r.status == 200:
                    _reset_backoff_if_pool()
                    return {
                        "restarted": True,
                        "reason": "not_needed",
                        "detail": "сервер уже готов",
                    }
        except Exception as e:
            logger.debug(f"[LLM_RESTART] сервер не отвечает: {e}")
        _stop = _stop_llama_server()
        if _stop.startswith("refused"):
            return {
                "restarted": False,
                "reason": "port_busy_unknown_owner",
                "detail": _stop,
            }
        _spawn = _spawn_llama_server()
        if not _spawn["started"]:
            return {
                "restarted": False,
                "reason": _spawn["reason"],
                "detail": _spawn["detail"],
            }
        _ready = await _await_llama_ready(_spawn["proc"])
        if _ready["started"]:
            return {
                "restarted": True,
                "reason": "ok",
                "detail": _ready["detail"],
            }
        return {
            "restarted": False,
            "reason": _ready["reason"],
            "detail": _ready["detail"],
        }


atexit.register(kill_llama_server)


def acquire_llama_server_lock(port: int, health_url: str) -> tuple:
    """ИНЦИДЕНТ 2026-08-30 (двойной llama-server → VRAM 96% → 503 на всех
    NARRATIVE): оба стартовых пути (game_launcher._ensure_llm_running,
    main._background_llm_startup) проверяли ТОЛЬКО /health — пока первый
    сервер грузит модель (30–60 сек), health молчит, и второй путь спавнит
    дубль на тот же порт.

    ЕДИНСТВЕННЫЙ процессный лок (обязателен для обоих спавнеров ДО Popen):
      ("reuse", reason) — НЕ спавнить: /health отвечает (сервер готов) ИЛИ
                          порт занят живым процессом (сервер грузится);
      ("spawn", reason) — порт свободен: спавнить можно.
    Bind-проба порта — вторая сигнальная линия, отличающая «грузится» от
    «никого нет». Возврат tuple, не bool: reason обязателен для наблюдаемости (L4).
    """
    import socket

    # Линия 1: /health отвечает → сервер готов → переиспользуем
    try:
        with urllib.request.urlopen(health_url, timeout=1.0) as resp:
            if resp.status == 200:
                return ("reuse", f"health ok: {health_url}")
    except Exception as e:
        # Не готов ИЛИ грузится — решает линия 2; отказ наблюдаем (L4,
        # INV-SILENT-FAILURE: наш собственный P0-код не имеет права на
        # тихие except — тот же класс, что чинили в downloader.py, S224)
        logger.debug(f"[LLM_LOCK] health silent ({health_url}): {e}")
    # Линия 2: порт занят кем-то → идёт загрузка/битый процесс → НЕ спавнить
    # (битый процесс — зона kill_llama_server/ручного вмешательства; спавн
    # третьего процесса поверх занятого порта никогда не был решением)
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _sock.settimeout(0.5)
        _sock.bind(("127.0.0.1", port))
    except OSError as e:
        # L4 (детектор «except: return without logging»): вердикт лока
        # каузально значим (порт занят → спавн запрещён) — обязан быть в
        # логах, а не только в возвращённом tuple, который могут игнорировать
        logger.debug(f"[LLM_LOCK] port {port} occupied — reuse (loading or alive): {e}")
        return ("reuse", f"port {port} occupied (loading or alive): {e}")
    finally:
        _sock.close()
    return ("spawn", f"port {port} free, health silent")

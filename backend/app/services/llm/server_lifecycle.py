"""
path: backend/app/services/llm/server_lifecycle.py
Назначение: Управление жизненным циклом llama-server (start/stop/restart).
Вынесено из app.main.py для разрыва циклической зависимости (routes -> main -> routes).
"""
import atexit
import logging
import urllib.request

from app.core.config import settings

logger = logging.getLogger(__name__)

# Глобальное состояние процесса (dict для передачи по ссылке)
_llama_state = {"proc": None, "started_by_us": False, "restart_count": 0, "last_restart_time": 0.0}


def kill_llama_server() -> None:
    """LLM управляется game_launcher.py. Эта функция оставлена как заглушка для atexit."""
    pass


def restart_llama_server() -> bool:
    """Пассивная проверка LLM. Управление процессом передано game_launcher.py."""
    try:
        urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=2)
        return True
    except Exception as e:
        logger.error(f"[LLM_CHECK] LLM сервер не отвечает. Управление передано game_launcher.py. Ошибка: {e}")
        return False

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
        return ("reuse", f"port {port} occupied (loading or alive): {e}")
    finally:
        _sock.close()
    return ("spawn", f"port {port} free, health silent")

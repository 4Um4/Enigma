"""
path: backend/app/services/llm/server_lifecycle.py
Назначение: Управление жизненным циклом llama-server (start/stop/restart).
Вынесено из app.main.py для разрыва циклической зависимости (routes -> main -> routes).
"""
import logging
import subprocess
import time
import urllib.request
import atexit

from app.core.config import settings, BASE_DIR

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

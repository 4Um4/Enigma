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
_llama_state = {"proc": None, "started_by_us": False}


def kill_llama_server() -> None:
    """Гарантированное убийство llama-server при любом выходе — только если МЫ его запустили."""
    if _llama_state["proc"] is not None and _llama_state["started_by_us"]:
        try:
            _llama_state["proc"].terminate()
            _llama_state["proc"].wait(timeout=3)
        except Exception:
            try:
                _llama_state["proc"].kill()
            except Exception as e:
                logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
        _llama_state["proc"] = None


def restart_llama_server() -> bool:
    """Restart llama-server если он упал во время игры. Возвращает True если сервер жив."""
    # Шаг 1: проверяем — может сервер уже жив (внешний или предыдущий инстанс)
    try:
        urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=2)
        return True  # Уже работает
    except Exception as e:
        logger.error(f"[LLM_RESTART] Health check failed: {e}", exc_info=True)

    # Шаг 2: убиваем старый процесс если он мёртв (poll != None) или завис
    if _llama_state["proc"] is not None:
        if _llama_state["proc"].poll() is not None:
            try:
                _llama_state["proc"].kill()
            except Exception as e:
                logger.error(f"[LLM_RESTART] Failed to kill dead process: {e}", exc_info=True)
            _llama_state["proc"] = None
        else:
            logger.warning("[LLM_RESTART] Процесс жив но /health не отвечает — убиваем")
            try:
                _llama_state["proc"].terminate()
                _llama_state["proc"].wait(timeout=5)
            except Exception:
                try:
                    _llama_state["proc"].kill()
                except Exception as e:
                    logger.error(f"[LLM_RESTART] Failed to kill unresponsive process: {e}", exc_info=True)
            _llama_state["proc"] = None

    # Шаг 3: запускаем новый
    logger.info("[LLM_RESTART] Перезапуск llama-server...")
    try:
        server_cmd = [
            settings.llama_cpp_server_executable,
            "-m", settings.llama_cpp_model_path,
            "--port", str(settings.llama_cpp_port),
            "--host", "localhost",
            "-ngl", str(settings.effective_gpu_layers),
            "-c", str(settings.ctx_size),
            "-t", str(settings.threads),
        ]
        _llama_stderr_path = str(BASE_DIR / "backend" / "logs" / "llama_server_stderr.log")
        _llama_stderr_file = open(_llama_stderr_path, "a", encoding="utf-8")
        try:
            _llama_state["proc"] = subprocess.Popen(
                server_cmd,
                stdout=subprocess.DEVNULL,
                stderr=_llama_stderr_file,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        finally:
            _llama_stderr_file.close()
        _llama_state["started_by_us"] = True
        
        for _attempt in range(int(settings.model_load_timeout_sec / 2)):
            try:
                _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                _opener.open(f"{settings.llama_cpp_server_url}/health", timeout=2)
                logger.info("[LLM_RESTART] llama-server перезапущен успешно")
                return True
            except Exception:
                time.sleep(2)
        logger.error(f"[LLM_RESTART] Перезапуск не удался за {settings.model_load_timeout_sec}с")
        return False
    except Exception as e:
        logger.error(f"[LLM_RESTART] Exception: {e}")
        _llama_state["proc"] = None
        return False

atexit.register(kill_llama_server)

"""
path: /scripts/llm_server_manager.py
Назначение: Управление жизненным циклом llama-server для тестов (IPT, DriftLab).
Зависимости: subprocess, urllib, time, logging, app.core.config
Основные сущности: start_llama_server, kill_llama_server
"""

import logging
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

# Добавляем backend в path для импорта settings
_BACKEND_DIR = Path(__file__).parent.parent / "backend"
import sys

sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings

logger = logging.getLogger(__name__)

_llama_proc: Optional[subprocess.Popen] = None

def start_llama_server() -> bool:
    """Запускает llama-server и ждёт его готовности (health check)."""
    global _llama_proc
    
    # Проверяем, не запущен ли уже
    try:
        _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        _opener.open(f"{settings.llama_cpp_server_url}/health", timeout=2)
        print("[LLM_MANAGER] llama-server уже запущен.")
        return True
    except Exception:
        pass

    print("[LLM_MANAGER] Запуск llama-server...")
    
    server_cmd = [
        settings.llama_cpp_server_executable,
        "-m",
        settings.llama_cpp_model_path,
        "--port",
        str(settings.llama_cpp_port),
        "--host",
        "localhost",
        "-ngl",
        str(settings.gpu_layers),
        "-c",
        str(settings.ctx_size),
        "-t",
        str(settings.threads),
    ]
    
    _stderr_path = _BACKEND_DIR / "logs" / "llama_server_stderr.log"
    _stderr_path.parent.mkdir(parents=True, exist_ok=True)
    _stderr_file = open(_stderr_path, "a", encoding="utf-8")
    
    try:
        _proc = subprocess.Popen(
            server_cmd,
            stdout=subprocess.DEVNULL,
            stderr=_stderr_file,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    finally:
        _stderr_file.close()
        
    # Ждём готовности (неблокирующе)
    _server_ready = False
    for _attempt in range(int(settings.model_load_timeout_sec / 2)):
        try:
            _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            _opener.open(f"{settings.llama_cpp_server_url}/health", timeout=2)
            _server_ready = True
            break
        except Exception:
            time.sleep(2)
            
    if _server_ready:
        print("[LLM_MANAGER] llama-server запущен успешно.")
        global _llama_proc
        _llama_proc = _proc
        return True
    else:
        print(f"[LLM_MANAGER] llama-server не ответил за {settings.model_load_timeout_sec}с.")
        if _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _proc.kill()
        return False

def kill_llama_server() -> None:
    """Останавливает llama-server, если он был запущен этим менеджером."""
    global _llama_proc
    if _llama_proc is not None and _llama_proc.poll() is None:
        print("[LLM_MANAGER] Остановка llama-server...")
        _llama_proc.terminate()
        try:
            _llama_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _llama_proc.kill()
        _llama_proc = None
        print("[LLM_MANAGER] llama-server остановлен.")
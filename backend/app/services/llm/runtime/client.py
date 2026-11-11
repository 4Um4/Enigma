"""
path: backend/app/services/llm/runtime/client.py
Назначение: LLM Host Client SDK — единый интерфейс для подключения
    игры, pytest, IPT и экспериментов к LLM Host broker (:8182).
    Клиенты не управляют процессами — получают URL через lease.
    ENIGMA_LLM_HOST=off → legacy llm_server_manager (осознанный переход).
Зависимости: os, threading, time, urllib, psutil, app.core.config,
    scripts.llm_server_manager (legacy fallback only)
"""
import atexit
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional, cast

from app.core.config import settings
from app.services.llm.runtime._proc import silent_subprocess_kwargs

_PROTOCOL_VERSION = "llm-host-v1"
_HOST_STARTUP_TIMEOUT = 30
_HEALTH_TIMEOUT = 2
_HEARTBEAT_INTERVAL = 15
_BACKEND_DIR = str(Path(__file__).resolve().parents[4])

_lease_id: Optional[str] = None
_lease_url: Optional[str] = None
_heartbeat_thread: Optional[threading.Thread] = None
_heartbeat_stop = threading.Event()
_legacy_mode = False


def _host_url() -> str:
    return f"http://127.0.0.1:{settings.llm_host_port}"


def _check_host_health() -> Optional[dict]:
    """GET /health → проверка protocol_version. None = Host чужой или отсутствует."""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"{_host_url()}/health", timeout=_HEALTH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if data.get("protocol_version") == _PROTOCOL_VERSION else None
    except Exception as e:
        print(f"[LLM_SDK] Host health check failed: {e}")
        return None


def _start_host() -> bool:
    """Запуск Host как detached process (переживает родителя)."""
    try:
        cmd = [
            sys.executable, "-m", "uvicorn",
            "app.services.llm.runtime.host:app",
            "--host", "127.0.0.1",
            "--port", str(settings.llm_host_port),
            "--log-level", "warning",
        ]
        if sys.platform == "win32":
            # Merge CREATE_NEW_PROCESS_GROUP (so we can Ctrl-Break the Host later)
            # with silent_subprocess_kwargs(): CREATE_NO_WINDOW | DETACHED_PROCESS
            # + STARTUPINFO(SW_HIDE) → no console window flash, no taskbar entry.
            _silent = silent_subprocess_kwargs()
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=_BACKEND_DIR,
                creationflags=_silent.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP,
                startupinfo=_silent.get("startupinfo"),
            )
        else:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=_BACKEND_DIR,
                start_new_session=True,
            )
        return True
    except Exception as e:
        print(f"[LLM_SDK] Failed to start Host: {e}")
        return False


def _wait_host_ready(timeout: int = _HOST_STARTUP_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _check_host_health() is not None:
            return True
        time.sleep(1)
    return False


def _discover_or_start_host() -> None:
    """Обнаружение Host или запуск нового. RuntimeError если невозможно."""
    if _check_host_health() is not None:
        return
    if not _start_host():
        raise RuntimeError(
            f"Cannot start LLM Host on port {settings.llm_host_port}. "
            f"Port may be occupied by a foreign service."
        )
    if not _wait_host_ready():
        raise RuntimeError(
            f"LLM Host not ready within {_HOST_STARTUP_TIMEOUT}s. "
            f"Port {settings.llm_host_port} may be occupied by foreign service "
            f"or Host process failed."
        )


def _get_create_time() -> float:
    try:
        import psutil
        return float(psutil.Process(os.getpid()).create_time())
    except Exception as e:
        print(f"[LLM_SDK] psutil create_time unavailable: {e}")
        return 0.0


def _post_json(url: str, data: dict) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Host returned {e.code}: {detail}") from e


def _heartbeat_loop() -> None:
    while not _heartbeat_stop.wait(_HEARTBEAT_INTERVAL):
        if _lease_id is None:
            return
        try:
            _post_json(f"{_host_url()}/heartbeat", {"lease_id": _lease_id})
        except Exception as e:
            print(f"[LLM_SDK] heartbeat failed (non-fatal, TTL will clean up): {e}")


def _start_heartbeat() -> None:
    global _heartbeat_thread
    _heartbeat_stop.clear()
    if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
        return
    _heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    _heartbeat_thread.start()


def _stop_heartbeat() -> None:
    _heartbeat_stop.set()


def ensure_llm(label: str = "", pinned: bool = False) -> str:
    """Ensure LLM Host lease and return llama-server URL.

    One SDK client — one active lease. Repeated calls reuse existing lease
    if still valid. ENIGMA_LLM_HOST=off → legacy. Host unavailable → RuntimeError.
    """
    global _lease_id, _lease_url, _legacy_mode

    # 1. Existing valid lease? → verify + return
    if _lease_id is not None and _lease_url is not None:
        try:
            _post_json(f"{_host_url()}/heartbeat", {"lease_id": _lease_id})
            return _lease_url
        except Exception:
            _lease_id = None
            _lease_url = None
            _stop_heartbeat()

    # 2. ENIGMA_LLM_HOST=off → legacy fallback (conscious)
    if os.environ.get("ENIGMA_LLM_HOST", "").strip().lower() == "off":
        if not _legacy_mode:
            from scripts.llm_server_manager import start_llama_server, kill_llama_server
            start_llama_server()
            atexit.register(kill_llama_server)
            _legacy_mode = True
        _lease_url = settings.llama_cpp_server_url
        return _lease_url

    # 3. Discover or start Host (RuntimeError if can't — NO fallback)
    _discover_or_start_host()

    # 4. Get lease
    resp = _post_json(f"{_host_url()}/ensure", {
        "pid": os.getpid(),
        "process_create_time": _get_create_time(),
        "label": label,
        "pinned": pinned,
    })
    _lease_id = resp["lease_id"]
    _lease_url = resp["url"]

    # 5. Start heartbeat (daemon thread, 15s)
    _start_heartbeat()
    print(f"[LLM_SDK] lease acquired: {_lease_id} (label={label}, url={_lease_url})")
    return _lease_url


def release_lease() -> None:
    """Release this SDK client's active lease. Idempotent.
    Does NOT stop Host or llama-server."""
    global _lease_id, _lease_url
    _stop_heartbeat()
    if _lease_id is not None:
        try:
            _post_json(f"{_host_url()}/release", {"lease_id": _lease_id})
            print(f"[LLM_SDK] lease released: {_lease_id}")
        except Exception as e:
            print(f"[LLM_SDK] release failed (non-fatal, TTL will clean up): {e}")
        finally:
            _lease_id = None
            _lease_url = None


atexit.register(release_lease)

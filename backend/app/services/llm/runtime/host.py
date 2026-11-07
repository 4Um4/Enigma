"""
path: backend/app/services/llm/runtime/host.py
Назначение: LLM Host broker — единственный распорядитель жизненным циклом
    llama-server. Control-plane only (data идёт напрямую client→llama-server:8181).
    Management port: settings.llm_host_port (8182).
    Этап 3 (LLM Runtime Unification MVP).

Контракт (вердикт Мастера):
    - Lease-based (UUID, не PID). Один SDK-клиент — один lease.
    - Health-check обязателен до выдачи lease (поправка B).
    - Adopted сервер (spawned_by_us=False) — NEVER killed.
    - Host shutdown — server NOT killed.
    - Kill by name/PID — ЗАПРЕЩЁН.
    - Fallback при аварии Host — ЗАПРЕЩЁН (только ENIGMA_LLM_HOST=off → legacy).
Зависимости: FastAPI, server_lifecycle (_spawn_llama_server, _await_llama_ready,
    acquire_llama_server_lock), app.core.config
"""
import asyncio
import time
import uuid
import urllib.request
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.llm.server_lifecycle import (
    _spawn_llama_server,
    _await_llama_ready,
    acquire_llama_server_lock,
)

PROTOCOL_VERSION = "llm-host-v1"
LEASE_TTL = 60
LEASE_TTL_PINNED = 300
STALE_CLEANUP_INTERVAL = 10
HEALTH_WAIT_TIMEOUT = 120
HEALTH_POLL_INTERVAL = 2

_broker_state: dict[str, Any] = {
    "llama_url": None,
    "llama_proc": None,
    "spawned_by_us": False,
    "llama_ready": False,
    "leases": {},
    "started_at": time.time(),
}


class EnsureRequest(BaseModel):
    pid: int
    process_create_time: float
    label: str = ""
    pinned: bool = False


class EnsureResponse(BaseModel):
    lease_id: str
    url: str
    status: str
    reason: str


class HeartbeatRequest(BaseModel):
    lease_id: str


class HeartbeatResponse(BaseModel):
    ok: bool
    expires_at: float


class ReleaseRequest(BaseModel):
    lease_id: str


class ReleaseResponse(BaseModel):
    released: bool


def _check_llama_health() -> bool:
    """HTTP /health → 200 = сервер готов."""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        opener.open(f"{settings.llama_cpp_server_url}/health", timeout=2)
        return True
    except Exception as e:
        print(f"[LLM_HOST] llama health check failed: {e}")
        return False


async def _wait_llama_health(timeout: int = HEALTH_WAIT_TIMEOUT) -> bool:
    """Поллинг /health до готовности или timeout (поправка B: port occupied ≠ ready)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _check_llama_health():
            return True
        await asyncio.sleep(HEALTH_POLL_INTERVAL)
    return False


async def _ensure_llama_server() -> tuple[bool, str]:
    """Гарантирует что llama-server запущен и отвечает /health.
    Возвращает (success, reason). URL выдаётся ТОЛЬКО после health-check 200."""
    if _broker_state["llama_ready"] and _check_llama_health():
        return True, "reused"

    verdict, reason = acquire_llama_server_lock(
        settings.llama_cpp_port,
        f"{settings.llama_cpp_server_url}/health",
    )

    if verdict == "reuse":
        if "health ok" in reason:
            _broker_state["llama_url"] = settings.llama_cpp_server_url
            _broker_state["spawned_by_us"] = False
            _broker_state["llama_ready"] = True
            return True, "adopted"
        # Port occupied, health silent → ждём загрузки
        if await _wait_llama_health():
            _broker_state["llama_url"] = settings.llama_cpp_server_url
            _broker_state["spawned_by_us"] = False
            _broker_state["llama_ready"] = True
            return True, "adopted"
        return False, "health timeout (port occupied, server not ready)"

    if verdict == "spawn":
        spawn_result = _spawn_llama_server()
        if not spawn_result["started"]:
            # Spawn отказал (возможна гонка) → re-check health (поправка B)
            if await _wait_llama_health(timeout=10):
                _broker_state["llama_url"] = settings.llama_cpp_server_url
                _broker_state["spawned_by_us"] = False
                _broker_state["llama_ready"] = True
                return True, "adopted (spawn race)"
            return False, f"spawn failed: {spawn_result['reason']}"
        ready_result = await _await_llama_ready(spawn_result["proc"])
        if ready_result["started"]:
            _broker_state["llama_url"] = settings.llama_cpp_server_url
            _broker_state["llama_proc"] = spawn_result["proc"]
            _broker_state["spawned_by_us"] = True
            _broker_state["llama_ready"] = True
            return True, "spawned"
        return False, f"spawn ok but not ready: {ready_result['reason']}"

    return False, f"unexpected lock verdict: {verdict}"


def _cleanup_stale_leases():
    """Удаление истёкших lease (background task). TTL — реальный механизм, atexit — дополнение."""
    now = time.time()
    expired = [lid for lid, l in _broker_state["leases"].items() if now > l["expires_at"]]
    for lid in expired:
        l = _broker_state["leases"].pop(lid)
        print(f"[LLM_HOST] lease expired: {lid} (label={l.get('label', '')})")


async def _cleanup_loop():
    while True:
        _cleanup_stale_leases()
        await asyncio.sleep(STALE_CLEANUP_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    # Shutdown: НЕ kill llama-server (вердикт Мастера — сервер переживает управляющий процесс)


app = FastAPI(title="ENIGMA LLM Host", version=PROTOCOL_VERSION, lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "protocol_version": PROTOCOL_VERSION,
        "uptime": time.time() - _broker_state["started_at"],
        "llama_status": "ready" if _broker_state["llama_ready"] else "not_ready",
    }


@app.post("/ensure", response_model=EnsureResponse)
async def ensure(req: EnsureRequest):
    success, reason = await _ensure_llama_server()
    if not success:
        raise HTTPException(status_code=503, detail=f"LLM server not available: {reason}")
    lease_id = str(uuid.uuid4())
    ttl = LEASE_TTL_PINNED if req.pinned else LEASE_TTL
    _broker_state["leases"][lease_id] = {
        "pid": req.pid,
        "process_create_time": req.process_create_time,
        "label": req.label,
        "pinned": req.pinned,
        "last_heartbeat": time.time(),
        "expires_at": time.time() + ttl,
    }
    print(f"[LLM_HOST] lease created: {lease_id} (pid={req.pid}, label={req.label}, reason={reason})")
    return EnsureResponse(lease_id=lease_id, url=_broker_state["llama_url"], status="ready", reason=reason)


@app.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(req: HeartbeatRequest):
    lease = _broker_state["leases"].get(req.lease_id)
    if lease is None:
        raise HTTPException(status_code=404, detail="lease not found")
    ttl = LEASE_TTL_PINNED if lease["pinned"] else LEASE_TTL
    lease["last_heartbeat"] = time.time()
    lease["expires_at"] = time.time() + ttl
    return HeartbeatResponse(ok=True, expires_at=lease["expires_at"])


@app.post("/release", response_model=ReleaseResponse)
async def release(req: ReleaseRequest):
    if req.lease_id in _broker_state["leases"]:
        l = _broker_state["leases"].pop(req.lease_id)
        print(f"[LLM_HOST] lease released: {req.lease_id} (label={l.get('label', '')})")
        return ReleaseResponse(released=True)
    return ReleaseResponse(released=False)


@app.get("/status")
async def status():
    return {
        "llama_url": _broker_state["llama_url"],
        "spawned_by_us": _broker_state["spawned_by_us"],
        "llama_ready": _broker_state["llama_ready"],
        "leases": [
            {"lease_id": lid, "pid": l["pid"], "label": l["label"],
             "pinned": l["pinned"], "expires_at": l["expires_at"]}
            for lid, l in _broker_state["leases"].items()
        ],
        "started_at": _broker_state["started_at"],
    }
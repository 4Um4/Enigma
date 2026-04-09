# backend/app/main.py
# ИСПРАВЛЕНИЯ vs оригинал:
# 1. StaticFiles с check_dir=False → не крашит если frontend/ui пустой
# 2. Все опасные операции в startup_event обёрнуты в try/except
# 3. LLM health check не блокирует старт (результат — только warning)
# 4. VRAM baseline устанавливается здесь (не в GameOrchestrator.__init__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import logging
import asyncio

from app.api.routes import router
from app.api import routes_debug
from app.api.routes_stream import router as stream_router
from app.core.config import settings
from app.core.runtime_config import get_api_url, get_frontend_url

from app.services.llm import initialize_router
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
from app.services.llm.provider_manager import get_model_pool
from app.services.llm.factory import ProviderFactory
from app.services.logging_tools import jsonl_log
from app.services.llm.llama_cpp_provider import LlamaCppProvider

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(routes_debug.router, prefix="/api")
app.include_router(stream_router, prefix="/api")

BASE_DIR     = Path(__file__).resolve().parents[2]   # Enigma root
FRONTEND_DIR = BASE_DIR / "frontend" / "ui"
DATA_DIR     = BASE_DIR / "backend" / "data"

# StaticFiles: монтируем только если директория существует
# (иначе uvicorn падает на старте с RuntimeError)
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
else:
    logger.warning(f"[STARTUP] frontend/ui не найден: {FRONTEND_DIR}")

if DATA_DIR.exists():
    app.mount("/backend/data", StaticFiles(directory=DATA_DIR), name="data")


@app.get("/")
def root():
    """Serve main UI или заглушку если frontend не готов."""
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({
        "status": "running",
        "message": "Enigma Backend работает. Frontend не найден.",
        "docs": "/docs",
        "health": "/api/health",
    })


@app.on_event("startup")
async def startup_event():
    print("\n=== STARTUP: Enigma Backend ===")

    # 1. LLM Router
    try:
        initialize_router()
        print("✓ LLM Router initialized")
    except Exception as e:
        logger.error(f"[STARTUP] LLM Router failed: {e}")
        print(f"✗ LLM Router error: {e}")

    # 2. ErrorInterpreter + VRAMMonitor
    try:
        get_error_interpreter()
        vram = get_vram_monitor()
        # Устанавливаем VRAM baseline ЗДЕСЬ — исправляет ложные утечки (+5757 MB)
        await vram.start_session()
        print("✓ ErrorInterpreter + VRAMMonitor initialized")
    except Exception as e:
        logger.error(f"[STARTUP] Monitor init failed: {e}")
        print(f"✗ Monitor error: {e}")

    # 3. JSONL startup log
    try:
        jsonl_log({
            "level": "INFO", "agent": "system",
            "event": "startup_complete",
            "log_dir": str(settings.log_dir),
        })
        print("✓ JSONL startup log written")
    except Exception as e:
        logger.warning(f"[STARTUP] JSONL log failed: {e}")

    # 4. ModelPool debug
    try:
        pool = get_model_pool()
        pool.debug = True
        logging.getLogger("app.services.llm.provider_manager").setLevel(logging.DEBUG)
        # Старый model_router удалён
        print("✓ ModelPool.debug = True")
    except Exception as e:
        logger.warning(f"[STARTUP] ModelPool debug failed: {e}")

    # 5. LLM server health check (НЕ блокирует старт при недоступности)
    print("\n=== Проверка LLM сервера ===")
    try:
        provider = LlamaCppProvider()
        is_available, message = await asyncio.wait_for(
            asyncio.to_thread(
                provider.check_server_with_retry,
                max_retries=settings.llm_health_check_retries,
                interval_sec=settings.llm_health_check_interval_sec,
            ),
            timeout=30,  # максимум 30 сек на проверку
        )
        icon = "✅" if is_available else "⚠️"
        print(f"  {icon} {message}")
        if not is_available:
            print("  Игра запущена в offline-режиме. LLM ответы будут недоступны.")
    except asyncio.TimeoutError:
        print("  ⚠️  LLM health check timeout (30s) — продолжаем без LLM")
    except Exception as e:
        print(f"  ⚠️  LLM check error: {e}")

    print("\n=== Application startup complete ===\n")
    _api      = get_api_url()
    _frontend = get_frontend_url()
    print(f"  Frontend:  {_frontend}")
    print(f"  Backend:   {_api}")
    print(f"  API Docs:  {_api}/docs")
    print(f"  VRAM:      {_api}/api/debug/vram\n")

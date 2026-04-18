# backend/app/main.py
# ИСПРАВЛЕНИЯ vs оригинал:
# 1. Все опасные операции в startup обёрнуты в try/except
# 3. LLM health check не блокирует старт (результат — только warning)
# 4. VRAM baseline устанавливается здесь (не в GameOrchestrator.__init__)
# 5. Migrated from @app.on_event to lifespan (FastAPI best practice)

from contextlib import asynccontextmanager
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
from app.core.runtime_config import get_api_url

from app.services.llm import initialize_router
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
from app.services.llm.provider_manager import get_model_pool
from app.services.logging_tools import jsonl_log
from app.services.llm.llama_cpp_provider import LlamaCppProvider
from app.services.game_loop_builder import build_game_loop

logger = logging.getLogger(__name__)

BASE_DIR     = Path(__file__).resolve().parents[2]   # Enigma root
DATA_DIR     = BASE_DIR / "backend" / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — замена устаревшего @app.on_event('startup'/'shutdown')."""
    print("\n=== STARTUP: Enigma Backend ===")

    # 1. LLM Router
    try:
        initialize_router()
        print("✓ LLM Router initialized")
    except Exception as e:
        logger.error(f"[STARTUP] LLM Router failed: {e}")
        print(f"✗ LLM Router error: {e}")

    # 1.5 ModelPool — регистрирует модели из settings.available_models
    try:
        from app.services.llm.provider_manager import initialize_model_pool
        results = initialize_model_pool()
        loaded = sum(1 for v in results.values() if v)
        print(f"✓ ModelPool initialized ({loaded}/{len(results)} models)")
    except Exception as e:
        logger.error(f"[STARTUP] ModelPool failed: {e}")
        print(f"✗ ModelPool error: {e}")

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

    # 5. GameLoop — единственный инстанс, живёт в app.state
    try:
        app.state.game_loop = build_game_loop(DATA_DIR)
        print("✓ GameLoop initialized (app.state)")
    except Exception as e:
        logger.error(f"[STARTUP] GameLoop failed: {e}")
        print(f"✗ GameLoop error: {e}")
        app.state.game_loop = None  # explicit — guard в accessor

    # 6. LLM server health check (НЕ блокирует старт при недоступности)
    print("\n=== Проверка LLM сервера ===")
    try:
        provider = LlamaCppProvider()
        is_available = await asyncio.wait_for(
            asyncio.to_thread(
                provider.is_available_with_retry,
                max_retries=settings.llm_health_check_retries,
                interval_sec=settings.llm_health_check_interval_sec,
            ),
            timeout=30,  # максимум 30 сек на проверку
        )
        mode = "сервер" if provider.use_server else "CLI"
        icon = "✅" if is_available else "⚠️"
        print(f"  {icon} LLM ({mode}): {'доступен' if is_available else 'недоступен'}")
        if not is_available:
            print("  Игра запущена в offline-режиме. LLM ответы будут недоступны.")
    except asyncio.TimeoutError:
        print("  ⚠️  LLM health check timeout (30s) — продолжаем без LLM")
    except Exception as e:
        print(f"  ⚠️  LLM check error: {e}")

    print("\n=== Application startup complete ===\n")
    _api      = get_api_url()
    _ui_mode = "pygame (встроенный)"
    print(f"  UI:        {_ui_mode}")
    print(f"  Backend:   {_api}")
    print(f"  API Docs:  {_api}/docs")
    print(f"  VRAM:      {_api}/api/debug/vram\n")

    yield  # приложение работает

    # ── SHUTDOWN ──
    # Завершение сессии VRAM мониторинга
    try:
        vram = get_vram_monitor()
        await vram.end_session()
        print("✓ VRAM session ended")
    except Exception:
        pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)

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

if DATA_DIR.exists():
    app.mount("/backend/data", StaticFiles(directory=DATA_DIR), name="data")


@app.get("/")
def root():
    """Статус backend — UI теперь в pygame."""
    return JSONResponse({
        "status": "running",
        "mode": "pygame",
        "docs": "/docs",
        "health": "/api/health",
    })
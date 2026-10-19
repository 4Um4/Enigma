# backend/app/main.py
# ИСПРАВЛЕНИЯ vs оригинал:
# 1. Все опасные операции в startup обёрнуты в try/except
# 3. LLM health check не блокирует старт (результат — только warning)
# 4. VRAM baseline устанавливается здесь (не в GameOrchestrator.__init__)
# 5. Migrated from @app.on_event to lifespan (FastAPI best practice)

import os

# Принудительно включаем UTF-8 для всего процесса бэкенда, чтобы не падать на символах типа ✓
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

# Локальный llama-server — никогда через прокси: backend сам ходит на
# localhost:8181 (health check, TaskScheduler). На машинах с системным
# прокси/WPAD urllib платит до ~4с на каждый запрос к localhost —
# наблюдено замерами; страховка дистрибутива, нулевой эффект на чистых машинах.
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"
# RE-D2 (Шаг 1 ТЗ Understanding Track): активация IntelligenceQueue
# (ADR-O-382, D8P) — LLM-экстракция диалога уходит с потока event loop
# на executor-пул TaskScheduler, sync/async пересечение в
# request_for_agent устраняется по построению (INV-LLM-LOOP-EXILE).
# Слой полностью проводён и принят d8p_intelligence_test; setdefault —
# явный env извне сохраняет право переопределения.
os.environ.setdefault("D8P_ENABLED", "1")

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from app.services.llm.server_lifecycle import _llama_state
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# CDS: Подключаем Uvicorn-подпроцесс к записи в общий лог-файл
_CDS_LOG_PATH = (
    Path(__file__).resolve().parents[2] / "backend" / "logs" / "cds_backend.log"
)
if _CDS_LOG_PATH.exists():
    _cds_handler = logging.FileHandler(str(_CDS_LOG_PATH), encoding="utf-8")
    _cds_handler.setLevel(logging.DEBUG)
    _cds_handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
    )
    logging.getLogger().addHandler(_cds_handler)
    logging.getLogger().setLevel(logging.INFO)

# ADR-DEBUG-001: Явное включение WARNING для каузально-критичных логгеров.
_CRITICAL_LOGGERS = [
    "app.services.scene.r3_direct_builder",  # R3_DIRECT warnings
    "app.services.world.world_tick_engine",  # DecisionHub.compute errors
    "app.services.npc.l1_chronicle",  # L1 persistence failures
    "app.services.npc.decision_hub",  # compute() signature errors
    "app.services.npc.life_engine",  # PIPELINE_FAULT L3_MISSING
    "app.services.verbalization",  # DM contract building
    "app.services.combat.injury_processor",  # injury creation failures
]
for _logger_name in _CRITICAL_LOGGERS:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)

from app.api import routes_debug
from app.api.routes import router
from app.api.routes_board import board_router
from app.api.routes_chronicle import chronicle_router
from app.api.routes_stream import router as stream_router
from app.api.world_routes import world_router
from app.core.config import settings
from app.core.runtime_config import get_api_url
from app.services.error_interpreter import get_error_interpreter
from app.services.game_loop_builder import build_game_loop
from app.services.llm import initialize_router
from app.services.llm.llama_cpp_provider import LlamaCppProvider
from app.services.llm.provider_manager import get_model_pool
from app.services.logging_tools import jsonl_log
from app.services.vram_monitor import get_vram_monitor

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]  # Enigma root
DATA_DIR = BASE_DIR / "backend" / "data"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan — замена устаревшего @app.on_event('startup'/'shutdown')."""
    # CDS FileHandler: пишет каузальные факты в файл для пост-мортем анализа LLM
    # Не трогает stdout, не ломает SSE. Уровень DEBUG ловит [DECISION_HUB] и [STATE_APPLIED].
    _logs_dir = Path(__file__).resolve().parents[2] / "backend" / "logs"
    _logs_dir.mkdir(exist_ok=True)
    _cds_log_path = (
        _logs_dir / f"cds_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    _cds_handler = logging.FileHandler(str(_cds_log_path), encoding="utf-8")
    _cds_handler.setLevel(logging.DEBUG)
    _cds_handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
    )
    logging.getLogger().addHandler(_cds_handler)
    logger.info(f"[CDS] FileHandler initialized: {_cds_log_path}")

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
        print("~ ErrorInterpreter initialized; VRAMMonitor — ЗАГЛУШКА (S142), телеметрия нулевая")
    except Exception as e:
        logger.error(f"[STARTUP] Monitor init failed: {e}")
        print(f"✗ Monitor error: {e}")

    # 3. JSONL startup log
    try:
        jsonl_log(
            {
                "level": "INFO",
                "agent": "system",
                "event": "startup_complete",
                "log_dir": str(settings.log_dir),
            }
        )
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

    # 5. GameLoop (обязательное ядро) — единая блокирующая сборка
    #    с гейтом ADR-O-426 D70: build_game_loop → startup_gate.
    #    Любой провал → cleanup + raise до yield → uvicorn exit non-zero.
    #    Необязательные интеграции (LLM/ModelPool/VRAM) остаются выше —
    #    их отказ не блокирует ядро, а только деградирует readiness.
    from app.core.startup_gate import (
        StartupValidationError,
        get_known_config_fields,
        run_startup_gate,
    )

    _game_loop = None
    try:
        _game_loop = build_game_loop(DATA_DIR)
        print("✓ GameLoop initialized")

        # Startup Gate (ADR-O-426 Шаг 4 / D70): config → migrations → schema.
        # Миграции (Шаг 1 wiring, вердикт В3) — единый путь в рантайме;
        # стампинг живых БД — отдельный протокол первичной классификации,
        # обычный запуск его не обходит.
        _gate_result = run_startup_gate(
            known_config_fields=get_known_config_fields(),
            game_loop=_game_loop,
        )
        app.state.startup_gate = _gate_result
        print(
            f"✓ Startup gate passed (migrations: {len(_gate_result.migrations)}, "
            f"config warnings: {len(_gate_result.config_warnings)})"
        )

        app.state.game_loop = _game_loop
        _game_loop = None  # ownership передан app.state
    except StartupValidationError as e:
        # Блокирующий провал ядра — cleanup уже созданных ресурсов,
        # uvicorn не принимает соединения (raise до yield).
        logger.error(f"[STARTUP] Startup gate FAILED: step={e.step}")
        for err in e.errors:
            logger.error(f"[STARTUP]   - {err}")
        print(f"✗ Startup gate failed (step={e.step}): {e.detail}")
        if _game_loop is not None:
            try:
                _game_loop.dispose()
            except Exception as dispose_err:
                logger.warning(f"[STARTUP] dispose on fail crashed: {dispose_err}")
        app.state.game_loop = None
        app.state.startup_gate = None
        raise  # uvicorn увидит RuntimeError → non-zero exit
    except Exception as e:
        # Любой другой провал build_game_loop / gate wiring — тоже fail-loud:
        # ранее глотали и оставляли game_loop=None, что позволяло uvicorn
        # обслуживать запросы с мёртвым ядром (COV-D70).
        logger.error(f"[STARTUP] GameLoop/gate crashed: {e}", exc_info=True)
        print(f"✗ GameLoop/gate error: {e}")
        if _game_loop is not None:
            try:
                _game_loop.dispose()
            except Exception as dispose_err:
                logger.warning(f"[STARTUP] dispose on fail crashed: {dispose_err}")
        app.state.game_loop = None
        app.state.startup_gate = None
        raise

    # === БЫСТРЫЙ СТАРТ ЗАВЕРШЁН — сервер готов принимать соединения ===
    # Медленные операции (llama-server, health check) запускаются в фоне.
    # Фронтенд может подключаться немедленно и опрашивать /health для статуса.
    app.state.startup_status = {"llm_server": "pending", "llm_health": "pending"}

    async def _background_llm_startup() -> None:
        """Неблокирующий старт llama-server + LLM health check.
        Обновляет app.state.startup_status для /health endpoint."""

        # 5.5 Авто-старт llama-server (если URL настроен)
        if settings.llama_cpp_server_url:
            app.state.startup_status["llm_server"] = "starting"
            try:
                # ПРОЦЕССНЫЙ ЛОК (инцидент 2026-08-30: два llama-server на 8181
                # → VRAM 96% → 503 на NARRATIVE → DRI 2%). Health-проверка одна
                # не отличает «сервер грузится» от «сервера нет»: пока первый
                # грузит модель (30–60с), health молчит — второй путь спавнил
                # дубль. Лок: reuse = health жив ИЛИ порт занят; spawn = порт
                # свободен. Канонический примитив — server_lifecycle (обе точки).
                from app.services.llm.server_lifecycle import (
                    acquire_llama_server_lock,
                )

                _verdict, _why = acquire_llama_server_lock(
                    settings.llama_cpp_port,
                    f"{settings.llama_cpp_server_url}/health",
                )
                if _verdict == "reuse":
                    print(f"✓ llama-server уже запущен/грузится ({_why})")
                    app.state.startup_status["llm_server"] = "ready"
                else:
                    # Порт свободен — имитируем health-промах оригинала:
                    # исполнение уходит в except-ветку со спавн-блоком ниже
                    raise ConnectionError(_why)
            except ConnectionError:
                # COV-2/D61: единственный владелец спавна — server_lifecycle
                # (de-dup: тот же код обслуживает и рестарт из модалки).
                # startup_status остаётся собственностью main; контракт
                # результата: {started, reason, detail}. Очистка сироты при
                # load_timeout — ответственность server_lifecycle.
                from app.services.llm.server_lifecycle import start_llama_server

                _start = await start_llama_server()
                if _start["started"]:
                    print(
                        f"✓ llama-server запущен ({settings.llama_cpp_server_url}): {_start['detail']}"
                    )
                    app.state.startup_status["llm_server"] = "ready"
                else:
                    print(f"✗ llama-server не запущен: {_start['reason']}: {_start['detail']}")
                    logger.warning(
                        f"[STARTUP] llama-server: {_start['reason']}: {_start['detail']}"
                    )
                    app.state.startup_status["llm_server"] = "failed"
                    app.state.startup_status["llm_error"] = _start["reason"]
        else:
            app.state.startup_status["llm_server"] = "skipped"

        # 6. LLM server health check
        app.state.startup_status["llm_health"] = "checking"
        print("\n=== Проверка LLM сервера ===")
        try:
            provider = LlamaCppProvider()
            is_available = await asyncio.wait_for(
                asyncio.to_thread(
                    provider.is_available_with_retry,
                    max_retries=settings.llm_health_check_retries,
                    interval_sec=settings.llm_health_check_interval_sec,
                ),
                timeout=30,
            )
            mode = "сервер" if provider.use_server else "CLI"
            icon = "✅" if is_available else "⚠️"
            print(
                f"  {icon} LLM ({mode}): {'доступен' if is_available else 'недоступен'}"
            )
            logger.info(
                f"[STARTUP] LLM ({mode}): {'доступен' if is_available else 'недоступен'}"
            )
            app.state.startup_status["llm_health"] = (
                "ready" if is_available else "unavailable"
            )
            if not is_available:
                print("  Игра запущена в offline-режиме. LLM ответы будут недоступны.")
        except asyncio.TimeoutError:
            print("  ⚠️  LLM health check timeout (30s) — продолжаем без LLM")
            app.state.startup_status["llm_health"] = "timeout"
        except Exception as e:
            print(f"  ⚠️  LLM check error: {e}")
            app.state.startup_status["llm_health"] = "error"

        print("\n=== Application startup complete ===\n")
        print(f"  VRAM:      {get_api_url()}/api/debug/vram\n")

    _bg_task = asyncio.create_task(_background_llm_startup())

    _api = get_api_url()
    print("\n=== Fast startup complete ===")
    print(f"  Backend:   {_api}")
    print(f"  API Docs:  {_api}/docs")
    print("  LLM:       загружается в фоне (проверяйте /health)...\n")

    yield  # ← Сервер ПРИНЯМАЕТ СОЕДИНЕНИЯ немедленно

    # ── SHUTDOWN ──
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError as e:
        logger.debug(f"Background task cancelled: {e}")

    # Синхронизируем состояние с глобалами для atexit-хендлера
    if _llama_state["proc"] is not None and _llama_state["started_by_us"]:
        try:
            _llama_state["proc"].terminate()
            _llama_state["proc"].wait(timeout=5)
            print("✓ llama-server stopped")
        except Exception:
            _llama_state["proc"].kill()
            print("✓ llama-server killed")

    # Завершение сессии VRAM мониторинга
    try:
        vram = get_vram_monitor()
        await vram.end_session()
        print("✓ VRAM session ended")
    except Exception as e:
        logger.warning(f"[B5-FIX] silent failure suppressed: {e}")


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
app.include_router(world_router, prefix="/api")
app.include_router(board_router, prefix="/api")
# CCH-2 / ADR-O-420: Character Chronicle API (вне тик-контура; layer 4)
app.include_router(chronicle_router, prefix="/api")

if DATA_DIR.exists():
    app.mount("/backend/data", StaticFiles(directory=DATA_DIR), name="data")


@app.get("/")
def root() -> JSONResponse:
    """Статус backend — UI теперь в pygame."""
    return JSONResponse(
        {
            "status": "running",
            "mode": "pygame",
            "docs": "/docs",
            "health": "/api/health",
        }
    )

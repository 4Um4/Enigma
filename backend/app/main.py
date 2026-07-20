# backend/app/main.py
# ИСПРАВЛЕНИЯ vs оригинал:
# 1. Все опасные операции в startup обёрнуты в try/except
# 3. LLM health check не блокирует старт (результат — только warning)
# 4. VRAM baseline устанавливается здесь (не в GameOrchestrator.__init__)
# 5. Migrated from @app.on_event to lifespan (FastAPI best practice)

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Глобальная ссылка на процесс llama-server — для atexit
_llama_server_proc = None
_llama_started_by_us = False

import atexit
import subprocess
import time


def _kill_llama_server() -> None:
    """Гарантированное убийство llama-server при любом выходе — только если МЫ его запустили."""
    global _llama_server_proc, _llama_started_by_us
    if _llama_server_proc is not None and _llama_started_by_us:
        try:
            _llama_server_proc.terminate()
            _llama_server_proc.wait(timeout=3)
        except Exception:
            try:
                _llama_server_proc.kill()
            except Exception as e:
                logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
        _llama_server_proc = None


def _restart_llama_server() -> bool:
    """Restart llama-server если он упал во время игры. Возвращает True если сервер жив."""
    global _llama_server_proc, _llama_started_by_us
    import urllib.request

    # Шаг 1: проверяем — может сервер уже жив (внешний или предыдущий инстанс)
    try:
        urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=2)
        return True  # Уже работает
    except Exception as e:
        logger.error(f"[LLM_RESTART] Health check failed: {e}", exc_info=True)
    # Шаг 2: убиваем старый процесс если он мёртв (poll != None) или завис
    if _llama_server_proc is not None:
        if _llama_server_proc.poll() is not None:
            # Процесс мёртв — можно перезапускать
            try:
                _llama_server_proc.kill()
            except Exception as e:
                logger.error(f"[LLM_RESTART] Failed to kill dead process: {e}", exc_info=True)
            _llama_server_proc = None
        else:
            # Процесс жив но не отвечает — убиваем
            logger.warning("[LLM_RESTART] Процесс жив но /health не отвечает — убиваем")
            try:
                _llama_server_proc.terminate()
                _llama_server_proc.wait(timeout=5)
            except Exception:
                try:
                    _llama_server_proc.kill()
                except Exception as e:
                    logger.error(f"[LLM_RESTART] Failed to kill unresponsive process: {e}", exc_info=True)
            _llama_server_proc = None
    # Шаг 3: запускаем новый
    logger.info("[LLM_RESTART] Перезапуск llama-server...")
    try:
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
        _llama_stderr_path = str(
            BASE_DIR / "backend" / "logs" / "llama_server_stderr.log"
        )
        _llama_stderr_file = open(_llama_stderr_path, "a", encoding="utf-8")
        try:
            _llama_server_proc = subprocess.Popen(
                server_cmd,
                stdout=subprocess.DEVNULL,
                stderr=_llama_stderr_file,
                creationflags=subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0,
            )
        finally:
            _llama_stderr_file.close()
        _llama_started_by_us = True
        # Ждём HTTP readiness
        for _attempt in range(int(settings.model_load_timeout_sec / 2)):
            try:
                urllib.request.urlopen(
                    f"{settings.llama_cpp_server_url}/health", timeout=2
                )
                logger.info("[LLM_RESTART] llama-server перезапущен успешно")
                print("✓ llama-server перезапущен")
                return True
            except Exception:
                time.sleep(2)
        logger.error(
            f"[LLM_RESTART] Перезапуск не удался за {settings.model_load_timeout_sec}с"
        )
        print("⚠️ Перезапуск llama-server не удался")
        return False
    except Exception as e:
        logger.error(f"[LLM_RESTART] Exception: {e}")
        print(f"⚠️ Перезапуск llama-server failed: {e}")
        _llama_server_proc = None
        return False


atexit.register(_kill_llama_server)
import asyncio
import logging
from datetime import datetime

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
async def lifespan(app: FastAPI):
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
        print("✓ ErrorInterpreter + VRAMMonitor initialized")
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

    # 5. GameLoop — единственный инстанс, живёт в app.state
    try:
        app.state.game_loop = build_game_loop(DATA_DIR)
        print("✓ GameLoop initialized (app.state)")
    except Exception as e:
        logger.error(f"[STARTUP] GameLoop failed: {e}")
        print(f"✗ GameLoop error: {e}")
        app.state.game_loop = None  # explicit — guard в accessor

    # === БЫСТРЫЙ СТАРТ ЗАВЕРШЁН — сервер готов принимать соединения ===
    # Медленные операции (llama-server, health check) запускаются в фоне.
    # Фронтенд может подключаться немедленно и опрашивать /health для статуса.
    app.state.startup_status = {"llm_server": "pending", "llm_health": "pending"}
    _llama_state = {"proc": None, "started_by_us": False}

    async def _background_llm_startup() -> None:
        """Неблокирующий старт llama-server + LLM health check.
        Обновляет app.state.startup_status для /health endpoint."""
        global _llama_server_proc, _llama_started_by_us

        # 5.5 Авто-старт llama-server (если URL настроен)
        if settings.llama_cpp_server_url:
            app.state.startup_status["llm_server"] = "starting"
            try:
                import urllib.request

                urllib.request.urlopen(
                    f"{settings.llama_cpp_server_url}/health", timeout=2
                )
                print(f"✓ llama-server уже запущен ({settings.llama_cpp_server_url})")
                app.state.startup_status["llm_server"] = "ready"
            except Exception:
                # Не запущен — стартуем
                try:
                    server_cmd = [
                        settings.llama_cpp_server_executable,
                        "-m",
                        settings.llama_cpp_model_path,  # ADR-087: Без флага модели сервер крашит!
                        "--port",
                        str(settings.llama_cpp_port),  # C2 FIX: Порт из settings
                        "--host",
                        "localhost",
                        "-ngl",
                        str(
                            settings.gpu_layers
                        ),  # GPU offload — без этого 5.4ГБ грузится на CPU → таймаут
                        "-c",
                        str(settings.ctx_size),  # размер контекста
                        "-t",
                        str(settings.threads),  # потоки
                    ]
                    _llama_stderr_path = str(
                        BASE_DIR / "backend" / "logs" / "llama_server_stderr.log"
                    )
                    _llama_stderr_file = open(_llama_stderr_path, "a", encoding="utf-8")
                    try:
                        _proc = subprocess.Popen(
                            server_cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=_llama_stderr_file,
                            creationflags=subprocess.CREATE_NO_WINDOW
                            if hasattr(subprocess, "CREATE_NO_WINDOW")
                            else 0,
                        )
                    finally:
                        _llama_stderr_file.close()
                    # Проверка: процесс жив после spawn?
                    await asyncio.sleep(1)
                    if _proc.poll() is not None:
                        _exit_code = _proc.returncode
                        _llama_stderr_file.close()
                        _err_lines = ""
                        try:
                            with open(_llama_stderr_path, "r", encoding="utf-8") as f:
                                _err_lines = "".join(f.readlines()[-20:])
                        except Exception as e:
                            logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
                        print(f"✗ llama-server упал при старте (exit={_exit_code})")
                        print(f"  stderr: {_err_lines[:500]}")
                        logger.error(
                            f"[STARTUP] llama-server exited immediately (code={_exit_code}): {_err_lines[:500]}"
                        )
                        app.state.startup_status["llm_server"] = "failed"
                    else:
                        # Процесс жив — ждём HTTP readiness (неблокирующе)
                        import urllib.request

                        _server_ready = False
                        for _attempt in range(int(settings.model_load_timeout_sec / 2)):
                            try:
                                urllib.request.urlopen(
                                    f"{settings.llama_cpp_server_url}/health",
                                    timeout=2,
                                )
                                _server_ready = True
                                break
                            except Exception:
                                await asyncio.sleep(2)
                        if _server_ready:
                            print(
                                f"✓ llama-server запущен ({settings.llama_cpp_server_url}, GPU={settings.gpu_layers}, ctx={settings.ctx_size})"
                            )
                            logger.info(
                                f"[STARTUP] llama-server запущен ({settings.llama_cpp_server_url})"
                            )
                            _llama_state["proc"] = _proc
                            _llama_state["started_by_us"] = True
                            _llama_server_proc = _proc
                            _llama_started_by_us = True
                            app.state.startup_status["llm_server"] = "ready"
                        else:
                            print(
                                f"⚠️ llama-server не ответил за {settings.model_load_timeout_sec}с — убиваем сироту"
                            )
                            logger.warning(
                                "[STARTUP] llama-server timeout — killing orphan process"
                            )
                            try:
                                _proc.terminate()
                                _proc.wait(timeout=5)
                            except Exception:
                                try:
                                    _proc.kill()
                                except Exception as e:
                                    logger.warning(
                                        f"[B5-FIX] silent failure suppressed: {e}"
                                    )
                            _llama_stderr_file.close()
                            app.state.startup_status["llm_server"] = "failed"
                except Exception as e:
                    logger.warning(f"[STARTUP] llama-server start failed: {e}")
                    print(f"⚠️ llama-server не запущен: {e}")
                    if _llama_state["proc"] is not None:
                        try:
                            _llama_state["proc"].kill()
                        except Exception:
                            pass
                    app.state.startup_status["llm_server"] = "failed"
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
    except asyncio.CancelledError:
        pass

    # Синхронизируем состояние с глобалами для atexit-хендлера
    _llama_server_proc = _llama_state["proc"]
    _llama_started_by_us = _llama_state["started_by_us"]
    if _llama_server_proc is not None and _llama_started_by_us:
        try:
            _llama_server_proc.terminate()
            _llama_server_proc.wait(timeout=5)
            print("✓ llama-server stopped")
        except Exception:
            _llama_server_proc.kill()
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

if DATA_DIR.exists():
    app.mount("/backend/data", StaticFiles(directory=DATA_DIR), name="data")


@app.get("/")
def root():
    """Статус backend — UI теперь в pygame."""
    return JSONResponse(
        {
            "status": "running",
            "mode": "pygame",
            "docs": "/docs",
            "health": "/api/health",
        }
    )

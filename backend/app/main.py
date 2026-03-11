from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# API
# -----------------------------
app.include_router(router, prefix="/api")

# -----------------------------
# FRONTEND
# -----------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend" / "ui"

app.mount("/ui", StaticFiles(directory=FRONTEND_DIR), name="ui")


@app.get("/")
def root():
    """Serve main UI"""
    return FileResponse(FRONTEND_DIR / "index.html")


# -----------------------------
# STARTUP
# -----------------------------
@app.on_event("startup")
async def startup_event():
    """Initialize LLM providers on application startup."""
    from app.services.llm import initialize_router
    from app.services.llm.factory import ProviderFactory
    from app.core.config import settings

    print("Initializing LLM Model Router...")
    initialize_router()
    
    # Проверка доступности LLM серверов
    print("\n=== Проверка LLM серверов ===")
    health_status = ProviderFactory.check_health_all()
    
    for agent, is_available in health_status.items():
        server_config = settings.get_llm_server_config(agent)
        status_icon = "✅" if is_available else "❌"
        print(f"  {status_icon} {agent.upper()}: http://{server_config['host']}:{server_config['port']} - {'Доступен' if is_available else 'Недоступен'}")
    
    # Общая проверка с retry
    print("\n=== Детальная проверка основного сервера ===")
    from app.services.llm.llama_cpp_provider import LlamaCppProvider
    provider = LlamaCppProvider()
    is_available, message = provider.check_server_with_retry(
        max_retries=settings.llm_health_check_retries,
        interval_sec=settings.llm_health_check_interval_sec
    )
    print(f"  {message}")
    
    if not is_available:
        print("\n⚠️  ВНИМАНИЕ: LLM сервер недоступен! Агенты будут использовать fallback режим.")
        print("   Убедитесь что llama-server запущен: backend\\start_enigma.bat")
    else:
        print("\n✅ LLM сервер готов к работе!")
    
    print("\nApplication startup complete. Model Router ready.")

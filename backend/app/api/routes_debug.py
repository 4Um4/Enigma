"""
Debug API Routes (F1-T03)
Agent Health Dashboard + VRAM/logs for frontend debug.html
"""
import time
from fastapi import APIRouter

from app.services.llm.provider_manager import get_model_pool
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
from app.core.config import settings

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/health/agents")
async def agent_health_dashboard():
    """Per-agent status for dashboard (model/VRAM/last_error)."""
    pool = get_model_pool()
    status = await pool.get_status()
    errors = get_error_interpreter().analyze_recent_errors()
    
    # Agent-specific (mock for now, extend from orchestrator/agents)
    agents_status = {
        "dm": {"model": status.get("active_model", "none"), "ready": status.get("has_active_model", False)},
        "rules": {"model": "saiga", "ready": True},  # From agent_model_map
        "npc": {"model": "npc_major", "ready": True},
        "world": {"model": "qwen_9b", "ready": True},
        "memory": {"model": "saiga", "ready": True},
    }
    
    return {
        "timestamp": time.time(),
        "vram": status.get("current_vram_mb", 0),
        "agents": agents_status,
        "recent_errors": errors,
        "logs_tail": get_error_interpreter().get_recent_logs(20),
    }


@router.get("/vram")
async def vram_status():
    """Real-time VRAM (F1-T02)."""
    monitor = get_vram_monitor()
    return await monitor.get_dashboard()


@router.get("/logs-tail")
async def logs_tail(lines: int = 50):
    """Tail of JSONL logs."""
    interpreter = get_error_interpreter()
    return {"logs": interpreter.get_recent_logs(lines)}


@router.get("/reset-errors/{model_key}")
async def reset_model_errors(model_key: str):
    """Reset error_count for model (dev tool)."""
    pool = get_model_pool()
    if pool.active_model_key == model_key and pool.active_model:
        pool.active_model.reset_errors()
        return {"status": "ok", "model": model_key}
    return {"status": "error", "model": model_key}


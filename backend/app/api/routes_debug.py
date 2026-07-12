"""
Debug API Routes (F1-T03)
Agent Health Dashboard + VRAM/logs
"""

import time

from app.services.error_interpreter import get_error_interpreter
from app.services.llm.provider_manager import get_model_pool
from app.services.vram_monitor import get_vram_monitor
from fastapi import APIRouter, Request

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/health/agents")
async def agent_health_dashboard():
    """Per-agent status for dashboard (model/VRAM/last_error)."""
    pool = get_model_pool()
    status = await pool.get_status()
    errors = get_error_interpreter().analyze_recent_errors()

    # Agent-specific (mock for now, extend from orchestrator/agents)
    active_model = status.get("active_model", "none")
    has_model = status.get("has_active_model", False)
    agents_status = {
        "dm": {"model": active_model, "ready": has_model},
        "rules": {"model": active_model, "ready": has_model},
        "npc": {"model": active_model, "ready": has_model},
        "world": {"model": active_model, "ready": has_model},
        "memory": {"model": active_model, "ready": has_model},
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


@router.get("/npc/{npc_id}/causal_ledger")
async def get_npc_causal_ledger(npc_id: str, campaign_id: str, request: Request):
    """
    God Mode: просмотр CausalLedger NPC.
    Показывает полную цепочку причинно-следственных связей —
    почему NPC имеет текущее состояние, роль, уровень стресса.
    """
    from app.services.game_loop_accessor import get_game_loop

    loop = get_game_loop(request)
    all_npcs = loop._load_npcs_with_runtime(campaign_id)

    for npc_dict in all_npcs:
        if npc_dict.get("id") == npc_id:
            ledger_raw = npc_dict.get("causal_ledger", [])
            drives_raw = npc_dict.get("temporary_drives", [])
            return {
                "npc_id": npc_id,
                "current_role": npc_dict.get("current_role", "unknown"),
                "stress": npc_dict.get("psyche", {}).get("stress", 0),
                "will_state": npc_dict.get("psyche", {}).get("state", "free"),
                "temporary_drives": drives_raw,
                "ledger": ledger_raw,
                "ledger_size": len(ledger_raw),
            }

    return {"error": f"NPC '{npc_id}' not found in campaign '{campaign_id}'"}


@router.post("/reset-relationships/{campaign_id}")
async def reset_campaign_relationships(campaign_id: str):
    """Миграция: сброс relationships после бага #7 (дублирование дельт)."""
    from app.core.game_loop import get_game_loop

    loop = get_game_loop()
    if not loop or not loop.memory_manager:
        return {"status": "error", "message": "GameLoop not initialized"}
    count = loop.memory_manager._relationships.reset_campaign(campaign_id)
    return {"status": "ok", "campaign_id": campaign_id, "reset_count": count}

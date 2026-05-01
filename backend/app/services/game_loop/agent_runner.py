# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop\agent_runner.py
"""
Безопасный запуск агентов с timeout и мониторингом.

Вынесено из game_loop — утилита, не зависит от GameLoop state.

Назначение: Безопасный запуск агентов с timeout, VRAM-мониторингом, логированием
Зависимости: asyncio, time, logging, app.services.vram_monitor, app.services.error_interpreter, app.services.logging_tools
Основные сущности: AGENT_TIMEOUT_SEC, ERROR_CODES, run_agent_safe
"""

import asyncio
import logging
import time

from app.services.vram_monitor import get_vram_monitor
from app.services.error_interpreter import get_error_interpreter
from app.services.logging_tools import jsonl_log

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SEC = 35

ERROR_CODES = {
    "AGENT_SUCCESS":              "SUCCESS",
    "AGENT_TIMEOUT":              "TIMEOUT",
    "AGENT_MODEL_FAIL":           "MODEL_FAIL",
    "ORCHESTRATOR_PIPELINE_FAIL": "PIPELINE_FAIL",
}


async def run_agent_safe(agent_name: str, agent, args: tuple, kwargs: dict) -> dict:
    """Запуск агента с timeout, VRAM-мониторингом и структурированным логированием."""
    vram_monitor      = get_vram_monitor()
    error_interpreter = get_error_interpreter()
    start             = time.perf_counter()

    # Модель загружается лениво внутри agent.run() через новый llm/router.
    # Замер VRAM показывает потребление до и во время работы агента.
    vram_before = await vram_monitor.get_vram_mb()
    vram_after  = vram_before  # Будет обновлено после agent.run()

    jsonl_log({
        "level": "INFO", "agent": agent_name, "status": "model_switch",
        "vram_before_mb": vram_before, "vram_after_mb": vram_after,
    })

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(agent.run, *args, **kwargs),
            timeout=AGENT_TIMEOUT_SEC,
        )
        duration = round((time.perf_counter() - start) * 1000)
        jsonl_log({
            "level": "INFO", "agent": agent_name,
            "error_code": ERROR_CODES["AGENT_SUCCESS"],
            "duration_ms": duration, "status": "complete",
        })
        return result or {}

    except asyncio.TimeoutError:
        duration = round((time.perf_counter() - start) * 1000)
        msg = f"Агент '{agent_name}' превысил лимит {AGENT_TIMEOUT_SEC}с"
        # Прерываем зависшую генерацию на llama-server
        try:
            from app.services.llm.provider_manager import get_model_pool
            _pool = get_model_pool()
            if _pool._active_model:
                _pool._active_model.provider.abort_generation()
                logger.warning(f"[GAME_LOOP] abort sent to {_pool.active_model_key}")
        except Exception:
            pass


async def yield_model_info(state):
    """Генерирует SSE-событие с метаинфо о выбранных моделях."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        from app.services.llm.router import get_router as get_llm_router, Capability
        from app.services.llm.provider_manager import get_model_pool

        _pe = state.shared_context.python_engines
        npc_contexts = _pe.get("npc_contexts", []) if isinstance(_pe, dict) else []
        has_major    = any(c.get("tier") == "major" for c in npc_contexts)
        router_llm   = get_llm_router()
        pool         = get_model_pool()
        dm_key       = router_llm.select_model(Capability.NARRATIVE)
        npc_cap      = Capability.DIALOGUE_GENERATION if has_major else Capability.DIALOGUE
        npc_key      = router_llm.select_model(npc_cap)
        dm_cfg       = pool.get_model_config(dm_key) if pool else None
        npc_cfg      = pool.get_model_config(npc_key) if pool else None
        yield {
            "type": "model",
            "data": {
                "dm":  {
                    "key":      dm_key,
                    "name":     dm_cfg.name if dm_cfg else dm_key,
                    "provider": dm_cfg.provider_type.value if dm_cfg else "unknown",
                },
                "npc": {
                    "key":      npc_key,
                    "name":     npc_cfg.name if npc_cfg else npc_key,
                    "provider": npc_cfg.provider_type.value if npc_cfg else "unknown",
                },
            },
        }
    except Exception as e:
        logger.warning(f"[GAME_LOOP] Ошибка получения model info: {e}")
        jsonl_log({
            "level": "ERROR", "agent": agent_name,
            "error_code": ERROR_CODES["AGENT_TIMEOUT"],
            "duration_ms": duration, "status": "timeout",
            "human_msg": msg,
        })
        logger.error(f"[GAME_LOOP] {msg}")
        return

    except Exception as e:
        duration = round((time.perf_counter() - start) * 1000)
        human_msg, fix = error_interpreter.handle(
            e, {"agent": agent_name}, agent_name, agent_name
        )
        jsonl_log({
            "level": "ERROR", "agent": agent_name,
            "error_code": ERROR_CODES["AGENT_MODEL_FAIL"],
            "duration_ms": duration, "status": "failed",
            "human_msg": human_msg, "fix": fix,
        })
        logger.error(f"[GAME_LOOP] {agent_name} failed: {human_msg}")
        return
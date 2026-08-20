# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop\phase_2_world_tick.py
"""
Stage 0 Task 0.10: Параллельный WorldTick-путь упразднён.

Все writes должны идти через StateApplicator.apply_deltas_and_commit.
WorldTickEngine в будущем будет публиковать List[EventDTO] в EventBus (Устав §2.1.2).
"""

import logging
from typing import Any

from app.services.game_loop.tick_context import TickBuffer

logger = logging.getLogger(__name__)


def tick_world_proactive(
    world_tick_engine: Any,
    reputation_engine: Any,
    memory_relationship_store: Any,
    economic_profiles_getter: Any,
    campaign_id: str,
    location: str,
    shared_context: Any,
    tick_ctx: TickBuffer,
    tick_orchestrator: Any = None,
    economy_tracker: Any = None,
) -> None:
    """Stub: Параллельный WorldTick-путь закрыт (Stage 0 Task 0.10)."""
    logger.debug(
        f"[STAGE_0] tick_world_proactive disabled for {campaign_id} "
        f"(phase_2_world_tick.py bypassed)"
    )
    return

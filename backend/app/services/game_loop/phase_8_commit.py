"""ФАЗА 8: Persistence — единственная точка мутации мира за тик.

Устав 4.2.1: SQLite = runtime truth. Atomic commit. Всё или ничего.
Устав 4.2.3: Нет транзакции = нет сохранения.

Закон: если где-то в коде остался прямой commit() или save_scene_state()
внутри _run_pipeline — рефакторинг провален.

path: C:/DDD/Codex/VSC_Enigma/Enigma/backend/app/services/game_loop/phase_8_commit.py
Назначение: Единственная точка коммита за тик (Устав 4.2.1)
Зависимости: logging, app.services.game_loop.tick_context
Основные сущности: commit_tick
"""

import logging
from typing import Any

from app.services.game_loop.tick_context import TickBuffer

logger = logging.getLogger(__name__)


def commit_tick(
    scene_manager: Any,
    campaign_id: str,
    scene_state: dict,
    tick_ctx: TickBuffer,
) -> list[str]:
    """Единственный коммит за тик — NPC state + scene state атомарно.

    Возвращает список источников изменений для логирования.
    Если ничего не грязно — не коммитит.
    """
    if not (tick_ctx.dirty_npcs or tick_ctx.wt_dirty or tick_ctx.prop_dirty):
        return []

    scene_manager.commit(
        campaign_id=campaign_id,
        scene_state=scene_state,
        npc_dicts=tick_ctx.all_npcs_raw,
    )

    _sources: list[str] = []
    if tick_ctx.dirty_npcs:
        _sources.append(f"npc={len(tick_ctx.dirty_npcs)}")
    if tick_ctx.wt_dirty:
        _sources.append("world_tick")
    if tick_ctx.prop_dirty:
        _sources.append("social")

    logger.warning(f"[COMMIT] single commit: {', '.join(_sources)}")
    return _sources
# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop\phase_5_perception.py
"""
ФАЗА 5: PerceptionFilter — фильтрация NPC контекстов.

NPC получают вербализацию только если воспринимают событие.
Адресат (target) всегда воспринимает.

Назначение: ФАЗА 5 — PerceptionFilter, фильтрация NPC контекстов по воспринимающим
Зависимости: logging
Основные сущности: apply_perception_filter
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_perception_filter(
    all_npc_contexts: list[dict],
    shared_context: Any,
    campaign_id: str,
    event_bus: Any,
) -> None:
    """Фильтрует npc_contexts по воспринимающим NPC.

    Мутирует shared_context.npc_contexts и shared_context.perceiving_npcs.
    """
    _all_npc_ids = [ctx["npc_id"] for ctx in all_npc_contexts]
    _recent = event_bus.get_recent_events(limit=1, campaign_id=campaign_id)

    if _recent and _all_npc_ids:
        from app.services.npc.perception_filter import filter_perceiving_npcs

        _perceiving_ids = set(filter_perceiving_npcs(
            npc_ids=_all_npc_ids,
            event=_recent[0],
            scene_state=shared_context.scene_state or {},
        ))
        # Адресат всегда воспринимает + свидетели по perception
        _explicit_target = shared_context.player_target_id
        if _explicit_target:
            _perceiving_ids.add(_explicit_target)

        # ФИЛЬТРУЕМ — только воспринимающие NPC получают вербализацию
        _filtered_ctxs = [c for c in all_npc_contexts if c.get("npc_id") in _perceiving_ids]
        shared_context.npc_contexts = _filtered_ctxs
        shared_context.perceiving_npcs = list(_perceiving_ids)
        _target_note = f" (target={_explicit_target})" if _explicit_target else ""
        logger.warning(f"[PERCEPTION_FILTER] {len(_perceiving_ids)}/{len(_all_npc_ids)} NPC{_target_note}: {list(_perceiving_ids)}")
    else:
        shared_context.npc_contexts = all_npc_contexts
        logger.warning(f"[PERCEPTION_FILTER] skip: recent={len(_recent) if _recent else 0}, npcs={len(_all_npc_ids)}")
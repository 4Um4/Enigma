# path: backend/app/services/game_loop/finalize_phase.py
"""
ФАЗА 7-8: Финализация тика — R3 frame, NPC state, memory, decay.

Вызывается после NPC оркестрации и perception/social фаз.
НЕ содержит EventBus publish — это фаза интеграции, не ввода.

БАГ-ФИКС: удалён publish_player_speech (дублировал publish_classified_player_event из dm_phase).

Необходимо для:
- R3 Direct Mode: build_r3_dm_frame → DMFrame вместо NPC реакций.
- Применения NPC state updates (trust/stress) к состоянию NPC.
- Записи в память NPC (ход игрока и реакции NPC).
- Обновления рабочей памяти (STM + L2) реакциями NPC.
- Запуска decay и resonance каждые 10 ходов.

Зависимости:
- game_loop (для доступа к memory_manager и другим сервисам)
- npc_state_helpers (для применения NPC state updates и записи в память)
- memory_manager (для обновления рабочей памяти и запуска decay)
- r3_direct_builder (для сборки DMFrame в R3 Direct Mode)
- ctx (для доступа к состоянию сцены и NPC)

Формулы и алгоритмы:
- NPC state updates: применяются к NPC state (trust/stress) по формуле new_value = old_value + delta, с ограничениями на min/max.
- Запись в память NPC: сохраняются player_name, action_text и npc_reactions в память NPC с привязкой к npc_id.
- Обновление рабочей памяти: реакции NPC преобразуются в STM и L2 записи с  привязкой к npc_id и campaign_id.
- Decay: каждые 10 ходов запускается decay для всех NPC, уменьшая trust и stress на фиксированную величину, а также запускается resonance для усиления или ослабления определённых воспоминаний в зависимости от текущего состояния NPC.
"""

import logging
from typing import Any, Dict

from app.services.game_loop.npc_state_helpers import apply_npc_state_updates, write_npc_memory
from app.services.memory.working_memory_tick import write_npc_reactions_to_memory, run_decay_and_resonance
from app.services.scene.r3_direct_builder import build_r3_dm_frame

logger = logging.getLogger(__name__)

# Единственная точка включения R3 Direct Mode
from app.services.game_loop import R3_DIRECT_MODE


def run_finalize_phase(
    game_loop: Any,
    actions: list,
    shared_context: Any,
    ctx: Any,
    campaign_id: str,
    rules_result: Dict[str, Any],
) -> Dict[str, Any]:
    """R3 frame → NPC state updates → memory → working memory → decay.

    Возвращает npc_result dict.
    Мутирует: game_loop (через helpers), shared_context.
    """
    # R3 Direct Mode: DecisionResult → SceneOutcome → DMFrame
    if R3_DIRECT_MODE:
        npc_result = build_r3_dm_frame(shared_context, actions, rules_result)
    else:
        npc_result = {}

    # Применяем trust/stress дельты к NPC state
    npc_state_updates = npc_result.get("npc_state_updates", [])
    if npc_state_updates:
        apply_npc_state_updates(
            game_loop, npc_state_updates,
            npc_dicts=ctx.all_npcs_raw, campaign_id=campaign_id,
        )

    # Записываем ход в память NPC
    write_npc_memory(
        loop=game_loop,
        npc_reactions=npc_result.get("npc_reactions", []),
        player=actions[0].player_name if actions else "игрок",
        action_text=actions[0].action if actions else "",
        npc_dicts=ctx.all_npcs_raw,
    )

    # Working Memory: ответы NPC → STM + L2
    write_npc_reactions_to_memory(
        game_loop.memory_manager,
        npc_result.get("npc_reactions", []),
        ctx.all_npcs_raw,
        campaign_id,
    )

    # Decay каждые 10 ходов
    _tick = (shared_context.scene_state or {}).get("snapshot_tick", 0)
    run_decay_and_resonance(
        game_loop.memory_manager, campaign_id, _tick,
        shared_context.active_npc_ids,
    )

    return npc_result
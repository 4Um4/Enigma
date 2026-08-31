"""Фаза 3: Memory Phase.

Обновляет NPCState через MemoryManager ДО принятия решения (Устав §3.1).
Вынесено из TickOrchestrator в рамках декомпозиции God-object (S99→S100).

Три блока:
1. compress_narrative_cache — каждые 10 тиков (YELLOW, idle-safe)
2. check_identity_promotion — каждые 50 тиков, только при causal input (GREEN GATE, ADR-S86.7)
3. mm.apply() — для каждого NPC, затронутого phase_2_events, с write-back в legacy dict
"""

import logging
from dataclasses import replace

from app.models.npc_state import NPCState
from app.services.dto import _TickContext
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from app.services.tick_utils import resolve_affected_npcs

logger = logging.getLogger(__name__)


def execute_memory_phase(ctx: _TickContext, memory_manager) -> int:
    """Выполнить Фазу 3: обновление памяти NPC.

    Args:
        ctx: Тиковый контекст с npc_states, phase_2_events, campaign_id.
        memory_manager: Экземпляр MemoryManager (инжектируется из TickOrchestrator).

    Returns:
        Количество обработанных memory updates (для логирования).
    """
    processed = 0

    # ── Блок 1: compress_narrative_cache (каждые 10 тиков, idle-safe) ──
    if ctx.tick_number % 10 == 0:
        for npc_dict in ctx.npc_states:
            npc_id = npc_dict.get("id")
            if not npc_id:
                continue
            try:
                npc_state = load_l2_state_from_runtime_dict(npc_dict)
                _compressed = memory_manager.compress_narrative_cache(
                    npc_state.narrative_cache
                )
                if _compressed != npc_state.narrative_cache:
                    npc_state.narrative_cache = _compressed
                    # ADR-117: to_persistence_dict — staticmethod, вызов через класс
                    NPCState.to_persistence_dict(npc_state, npc_dict)
            except Exception as e:
                logger.error(
                    f"[PHASE_3_MEMORY] compress_narrative_cache failed for {npc_id}: {e}. Пробрасываем исключение.",
                    exc_info=True,
                )
                raise

    # ── GREEN GATE: Memory cannot generate identity without causal input ──
    # Запрет кристаллизации L2.5 в idle-тиках (ADR-S86.7, предотвращение фантомного дрейфа)
    if not ctx.phase_2_events:
        return processed

    # ── Блок 2: check_identity_promotion (каждые 50 тиков, только при events) ──
    if ctx.tick_number % 50 == 0:
        for npc_dict in ctx.npc_states:
            npc_id = npc_dict.get("id")
            if not npc_id:
                continue
            try:
                _new_traits = memory_manager.check_identity_promotion(
                    campaign_id=ctx.campaign_id, npc_id=npc_id
                )
                if _new_traits:
                    logger.info(
                        f"[PHASE_3_MEMORY] new identity traits for {npc_id}: {_new_traits}"
                    )
            except Exception as e:
                logger.error(
                    f"[PHASE_3_MEMORY] check_identity_promotion failed for {npc_id}: {e}. Пробрасываем исключение.",
                    exc_info=True,
                )
                raise

    # ── Блок 3: Применение событий памяти к затронутым NPC ──
    for event in ctx.phase_2_events:
        for npc_id in resolve_affected_npcs(event):
            npc_dict = next(
                (n for n in ctx.npc_states if n.get("id") == npc_id),
                None,
            )
            if not npc_dict:
                continue

            npc_state = load_l2_state_from_runtime_dict(npc_dict)
            # apply() ищет npc_id в payload — инжектим
            new_payload = {**event.payload, "npc_id": npc_id}
            new_event = replace(event, payload=new_payload)

            _sq = (
                getattr(ctx.npc_services, "spatial_query", None)  # noqa: ENIGMA001, ENIGMA002
                if ctx.npc_services
                else None
            )
            memory_manager.apply(
                new_event, npc_state, campaign_id=ctx.campaign_id, spatial_query=_sq
            )
            # Мост обратно: apply() обновил narrative_cache на NPCState,
            # но Фаза 5 пересоздаёт NPCState из npc_dict (Устав §3.1)
            NPCState.to_persistence_dict(npc_state, npc_dict)
            processed += 1

    # ── Блок 4: V8-MEM-1 FIX — Decay & Resonance (L3 Identity cascade) ──
    # Раньше run_decay_and_resonance никогда не вызывалась в production.
    # run_decay_if_needed сам проверяет раз в N тиков, можно вызывать каждый тик.
    _active_npc_ids = [n.get("id") for n in ctx.npc_states if n.get("id")]
    if _active_npc_ids:
        try:
            _identity_weights = memory_manager.run_decay_if_needed(
                ctx.campaign_id, ctx.tick_number
            )
            if _identity_weights:
                # V8-MEM-13: резонанс per-NPC из буфера campaign:npc —
                # один общий резонанс = контаминация всех NPC чужими паттернами
                for npc_id in _active_npc_ids:
                    _resonance = memory_manager.detect_resonance(ctx.campaign_id, npc_id, actor_id="player")
                    if not _resonance:
                        continue
                    memory_manager.apply_identity_weights(ctx.campaign_id, npc_id, _resonance)
        except Exception as e:
            logger.error(f"[PHASE_3_MEMORY] run_decay_and_resonance failed: {e}. Пробрасываем исключение.", exc_info=True)
            raise

    logger.debug(f"[TICK_ORCH] Фаза 3: {processed} memory updates")
    return processed

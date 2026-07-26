"""
Вспомогательные функции для обновления состояния NPC и записи памяти.

Назначение:
- apply_npc_state_updates: применяет изменения доверия и стресса к NPC на основе входящих обновлений от LifeEngine или других систем. Также обновляет отношения в RelationshipStore.
- write_npc_memory: записывает ход игрока и реакцию NPC в memory_trace каждого NPC, который ответил. Это позволяет NPC "помнить" взаимодействия с игроком и использовать эту информацию в будущем.
- Эти функции работают с буфером NPC, который может быть передан из SceneManager для оптимизации доступа к данным NPC без повторной загрузки из базы данных.
- Они также логируют изменения для отладки и мониторинга состояния NPC.

Зависимости:
- loop.memory_manager для обновления отношений в RelationshipStore.
- loop._load_npcs() для загрузки текущего списка NPC, если не передан буфер npc_dicts.
- Логирование для отслеживания изменений состояния NPC и отладки.

Основные сущности:
- npc_dicts: список словарей NPC, который может быть передан для оптимизации доступа к данным NPC. Если не передан, функции загрузят NPC из базы данных.
- updates: список словарей с изменениями для NPC, содержащих npc_id, trust_delta и stress_delta.
- npc_reactions: список строк с реакциями NPC в формате "NPC_NAME: REACTION_TEXT".
- player: имя игрока, используемое при записи в memory_trace.
- action_text: текст действия игрока, используемый при записи в memory_trace.
- turn_tick: текущий тик игры, используемый для отметки времени в memory_trace.

Формулы:
- Новое доверие: new_trust = max(0.0, min(1.0, old_trust + trust_delta))
- Новый стресс: new_stress = max(0, min(100, old_stress + stress_delta))
- Ограничение memory_trace до последних 10 записей.

- Добавить обработку edge cases, таких как отсутствие NPC с данным npc_id или неправильный формат реакций.
- Оптимизировать поиск NPC по npc_id и имени, возможно, используя словарь для быстрого доступа.

Путь к файлу: backend/app/services/game_loop/npc_state_helpers.py
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_npc_state_updates(
    memory_manager: Any,
    updates: list,
    npc_dicts: list | None = None,
    campaign_id: str = "",
) -> None:
    if not updates:
        return
    try:
        if not npc_dicts:
            logger.warning(
                "[NPC_STATE] apply_npc_state_updates: npc_dicts пуст, пропускаем"
            )
            return
        all_npcs = npc_dicts
        changed = False
        for upd in updates:
            npc_id = upd.get("npc_id")
            trust_delta = upd.get("trust_delta", 0.0)
            stress_delta = upd.get("stress_delta", 0)
            for npc in all_npcs:
                if npc["id"] != npc_id:
                    continue
                if trust_delta != 0.0:
                    ss = npc.setdefault("social_stats", {})
                    ss["trust"] = round(
                        max(0.0, min(1.0, ss.get("trust", 0.5) + trust_delta)), 4
                    )
                if stress_delta != 0:
                    psyche = npc.setdefault("psyche", {})
                    psyche["stress"] = max(
                        0, min(100, psyche.get("stress", 0) + stress_delta)
                    )
                changed = True
                logger.info(
                    f"[NPC_STATE] {npc_id}: "
                    f"trust_delta={trust_delta:+.4f} stress_delta={stress_delta:+d}"
                )
                # P1: RelationshipStore
                if trust_delta != 0.0 and campaign_id:
                    try:
                        memory_manager.update_relationship(
                            campaign_id=campaign_id,
                            source="player",
                            target=npc_id,
                            delta={"trust": trust_delta},
                        )
                    except Exception as e:
                        logger.warning(f"[GAME_LOOP] Ошибка обновления отношений: {e}")
                break
        if changed:
            logger.warning(
                f"[NPC_STATE] {sum(1 for u in updates if u.get('npc_id'))} trust/stress deltas applied to buffer"
            )

    except Exception as e:
        logger.error(f"[NPC_STATE] apply_npc_state_updates failed: {e}")


def write_npc_memory(
    memory_manager: Any,
    npc_reactions: list,
    player: str,
    action_text: str,
    turn_tick: int = 0,
    npc_dicts: list | None = None,
    loop: Any = None,
) -> None:
    """Записывает ход в memory_trace каждого NPC который ответил."""
    if not npc_reactions:
        return
    try:
        if loop is None:
            logger.warning("[NPC_MEM] write_npc_memory: loop is None, cannot load npcs.")
            return
        all_npcs = npc_dicts if npc_dicts is not None else loop._load_npcs()
        changed = False
        for reaction in npc_reactions:
            # reaction формат: "Люся: Я не знаю..."
            if ":" not in reaction:
                continue
            npc_name_part = reaction.split(":")[0].strip()
            for npc in all_npcs:
                if npc.get("name", "") != npc_name_part:
                    continue
                trace = npc.setdefault("memory_trace", [])
                trace.append(
                    {
                        "tick_added": turn_tick,
                        "event": f"{player}: {action_text[:80]}",
                        "my_response": reaction.split(":", 1)[1].strip()[:120],
                    }
                )
                # Храним последние 10 воспоминаний
                if len(trace) > 10:
                    npc["memory_trace"] = trace[-10:]
                changed = True
                break
        if changed:
            logger.warning(
                f"[NPC_MEM] memory_trace updated for {len(npc_reactions)} reactions in buffer"
            )
    except Exception as e:
        logger.warning(f"[NPC_MEM] write_npc_memory failed: {e}")

# -*- coding: utf-8 -*-
"""
path: backend/app/models/idle_tick.py
Назначение: Контракты для time-driven idle-обработчиков (Фаза 0.5).
Зависимости: typing, app.models.state_delta.StateDeltas
Основные сущности: NPCStateSnapshot, IdleTickHandler

Фаза 0.5 = time-driven decay (social drift, reputation drift).
Фаза 8 = event-driven processing (perception, social propagation).
Не смешивать.

TODO:
- в будущем можно добавить отдельные контракты для разных типов idle-обработчиков (например, для репутационного дрейфа, для социальных связей и т.д.), чтобы обеспечить более строгую типизацию и ясность в коде. Но на начальном этапе достаточно общего протокола IdleTickHandler, который может обрабатывать любые аспекты NPC state, не мутируя исходные данные и возвращая дельты для применения. Это позволит нам гибко добавлять новые механики в фазу 0.5 без необходимости менять контракт каждого обработчика.
- важно, что эти обработчики не мутируют all_npcs_raw, а возвращают List[StateDeltas], который оркестратор применяет через StateApplicator.apply_batch(). Это обеспечивает чистоту данных и предсказуемость изменений в NPC state, а также позволяет легко отслеживать и логировать изменения, вызванные каждым обработчиком.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, TypedDict

from app.models.state_delta import StateDeltas


class NPCStateSnapshot(TypedDict):
    """READ-ONLY проекция NPC для idle-обработчиков.
    
    Handlers не видят внутренних деталей scene_state.
    Оркестратор строит снапшоты из all_npcs_raw.
    """
    npc_id: str
    stress: float
    relationship_cache: Dict[str, Any]    # {target: {trust, fear, base_trust, ...}}
    base_values: Dict[str, Any]          # {target: base_trust, ...} для drift-расчёта
    faction_affiliations: List[str]      # [faction_id, ...]


class IdleTickHandler(Protocol):
    """Протокол для time-driven обработчиков Фазы 0.5.
    
    Контракт:
    - Чистая функция: не мутирует all_npcs_raw.
    - Возвращает List[StateDeltas] для применения через StateApplicator.apply_batch().
    - Вызывается КАЖДЫЙ тик (время не останавливается).
    """
    name: str
    def handle(
        self,
        npcs: List[NPCStateSnapshot],
        campaign_id: str,
        current_tick: int,
    ) -> List[StateDeltas]: ...
# -*- coding: utf-8 -*-
"""
path: backend/app/models/idle_tick.py
Назначение: Контракты для time-driven idle-обработчиков (Фаза 0.5).
Зависимости: typing, app.models.state_delta.StateDeltas
Основные сущности: NPCStateSnapshot, IdleTickHandler

Фаза 0.5 = time-driven decay (social drift, reputation drift).
Фаза 8 = event-driven processing (perception, social propagation).
Не смешивать.

- в будущем можно добавить отдельные контракты для разных типов idle-обработчиков (например, для репутационного дрейфа, для социальных связей и т.д.), чтобы обеспечить более строгую типизацию и ясность в коде. Но на начальном этапе достаточно общего протокола IdleTickHandler, который может обрабатывать любые аспекты NPC state, не мутируя исходные данные и возвращая дельты для применения. Это позволит нам гибко добавлять новые механики в фазу 0.5 без необходимости менять контракт каждого обработчика.
- важно, что эти обработчики не мутируют all_npcs_raw, а возвращают List[StateDeltas], который оркестратор применяет через StateApplicator.apply_batch(). Это обеспечивает чистоту данных и предсказуемость изменений в NPC state, а также позволяет легко отслеживать и логировать изменения, вызванные каждым обработчиком.
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol, Tuple, TypedDict

from app.models.state_delta import StateDeltas


class NPCStateSnapshot(TypedDict):
    """READ-ONLY проекция NPC для idle-обработчиков.

    Handlers не видят внутренних деталей scene_state.
    Оркестратор строит снапшоты из all_npcs_raw.
    """

    npc_id: str
    stress: float
    relationship_cache: Dict[str, Any]  # {target: {trust, fear, base_trust, ...}}
    base_values: Dict[str, Any]  # {target: base_trust, ...} для drift-расчёта
    faction_affiliations: List[str]  # [faction_id, ...]

    # Physiology Domain: Body LOD Macro (Мастер Тай: Damage & Stress Propagation)
    hp: float  # Текущее здоровье (производная абстракция, макро-LOD)
    max_hp: float  # Максимум здоровья из body_profile
    pain: float  # Текущий уровень боли (0-100)
    fatigue: float  # Текущий уровень усталости (0-100)
    blood_loss: float  # Кровопотеря (0-1.0)
    consciousness: float  # Сознание (0-1.0, 0=кома/обморок, 1=ясность)
    shock_impulse: float  # Физический шок / болевой удар (0-1.0) — затухает как pain
    life_status: str  # ADR-124: "ALIVE" или "DEAD" — DEATH LOCK для decay handlers
    injuries_by_zone: Dict[
        str, List[Dict[str, Any]]
    ]  # Травмы, сгруппированные по target_zone
    base_abilities: Dict[str, float]  # Базовые характеристики (из body_profile)
    modifiers: Dict[str, float]  # Модификаторы (травмы/баффы/экипировка, из body_state)
    statuses: List[str]  # Активные статусы (stagger, unconscious, bleeding и т.д.)

    # S2B.5 / ADR-O-373: плоская READ-ONLY проекция для BodyEngine (Phase 0.5).
    # Заполняется билдером снапшотов; mutable-ссылки на body_state ЗАПРЕЩЕНЫ
    # (projection, не alias). combat-билдеры заполняют для единообразия контракта.
    velocity: Tuple[float, float]  # Скорость — детекция WALK/RUN в BodyEngine
    activity: str  # Активность (activity || routine.current — резолвит билдер)
    coupling_mode: str  # FULL_WAKE/DROWSY/SLEEP/DEEP_SLEEP/REM (из coupling_profile; S2B6-A: фантомные AWAKE/SLEEPING удалены)
    body_mass: float  # Масса тела (placeholder 1.0 до S2B.7)

    # Affective Domain: Psyche LOD Macro (S74: Temporal Mind)
    affective_load: float  # Аффективный интеграл (0-1.0) — затухает в idle
    emotion: str  # Текущий эмоциональный тег (neutral/fearful/panic) — коллапсирует при decay


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

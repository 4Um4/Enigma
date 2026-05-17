# -*- coding: utf-8 -*-
"""
path: backend/app/services/combat/combat_subscriber.py
Назначение: Phase8Handler — мост между боевыми событиями (EventDTO) и 
    физическим интегратором (ImpactEngine).
Зависимости: EventBus, Phase8Context, Phase8Result, ImpactEngine, ImpactIntentDTO
Основные сущности: CombatSubscriber

Мастер Тай: CombatSubscriber НЕ создаёт Physiology напрямую.
Он только транслирует EventDTO → ImpactIntentDTO → ImpactEngine.
Тело — инерционная система, дельты — инъекции энергии.

Порядок в Фазе 8: perception → reaction → social → combat
(насилие применяется после социальных реакций на угрозу).

TODO:
- В будущем можно расширить ImpactIntentDTO, добавив поля для более сложных взаимодействий (например, area_of_effect для взрывов, или conditional_effects для эффектов, зависящих от состояния цели).
- ContactResult может быть расширен для включения более детальной информации о результатах воздействия,например, какие конкретные травмы были нанесены, или какие статусы были применены к цели. Это позволит нам более точно моделировать последствия физических воздействий и их влияние на NPC state.
- Важно, что эти контракты должны быть достаточно абстрактными, чтобы позволить гибкую реализацию механики насилия в будущем, включая возможность добавления новых типов воздействий, новых зон попадания, и более сложных взаимодействий между атакующими и защищающимися NPC. Это обеспечит нам широкие возможности для развития механики насилия в рамках нашей игры, не требуя постоянного изменения контрактов при добавлении новых фич.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set

from app.domain.constants import ACTION_INTENSITY
from app.models.impact import ImpactIntentDTO
from app.models.phase8 import Phase8Context, Phase8Result
from app.services.combat.impact_engine import resolve_physical_impact
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)

# События, порождающие физические воздействия
_COMBAT_EVENT_TYPES: list[EventType] = [
    EventType.PLAYER_ATTACKS,
    EventType.PLAYER_ATTACKED,
    EventType.COMBAT,
]

# Дефолтные параметры воздействия (если payload неполный)
_DEFAULT_DAMAGE_TYPE = "blunt"
_DEFAULT_WEAPON_REACH = 1.0
_DEFAULT_FORCE_SCALE = 30.0  # Базовая сила для action без указанного оружия


class CombatSubscriber:
    """Phase8Handler: транслятор боевых событий → физические воздействия.

    Поток:
      1. EventBus доставляет событие → _on_event() накапливает
      2. Оркестратор → drain_events() снимок + очистка (Фаза 8)
      3. Оркестратор → handle(events, ctx) → Phase8Result (Фаза 8)

    Deltas маршрутизируются через delta_buffer → apply_batch (ADR-002).
    PHYSICS_COMPOSITE: дельты НЕ суммируются в _aggregate_deltas,
    а передаются как инъекции энергии в StateApplicator.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._pending_events: list = []
        self._subscribe()

    def _subscribe(self) -> None:
        """Подписывается на типы событий, порождающие физические воздействия."""
        for et in _COMBAT_EVENT_TYPES:
            self._event_bus.subscribe(et, self._on_event)

    def _on_event(self, event) -> Optional[dict]:
        """EventHandler: накапливает событие для обработки на Фазе 8."""
        self._pending_events.append(event)
        return None

    @property
    def name(self) -> str:
        return "combat"

    def drain_events(self) -> List:
        """Снимок накопленных событий + очистка буфера."""
        snapshot = self._pending_events[:]
        self._pending_events.clear()
        return snapshot

    def handle(
        self,
        events: List,
        ctx: Phase8Context,
    ) -> Phase8Result:
        """ФАЗА 8: транслирует боевые события в физические воздействия.

        events — из drain_events(), может быть пустым.
        ctx — READ-ONLY.
        Возвращает Phase8Result(deltas) — оркестратор маршрутизирует
        через delta_buffer → apply_batch.

        PHYSICS_COMPOSITE: дельты обходят _aggregate_deltas merge,
        так как тело — инерционная система, а не бухгалтерия.
        """
        if not events:
            return Phase8Result()

        # Строим dict npc_id → npc_dict для быстрого доступа
        npc_by_id: dict[str, dict] = {}
        for npc in ctx.all_npcs_raw:
            npc_id = npc.get("id") or npc.get("npc_id")
            if npc_id:
                npc_by_id[npc_id] = npc

        deltas = []
        events_processed = 0

        for event in events:
            intent = self._extract_impact_intent(event, npc_by_id)
            if intent is None:
                continue

            # Получаем снапшоты атакующего и защищающегося
            attacker_snapshot = self._build_snapshot(intent.actor_id, npc_by_id)
            defender_snapshot = self._build_snapshot(intent.target_id, npc_by_id)

            if defender_snapshot is None:
                # Нет цели — нет воздействия (но атакующий устаёт)
                logger.debug(
                    f"[COMBAT_SUB] target {intent.target_id} not found, skip"
                )
                continue

            # Если атакующий не найден (игрок), используем идеальный снапшот
            if attacker_snapshot is None:
                attacker_snapshot = self._make_player_snapshot()

            # Вызов физического интегратора (Pure Function)
            impact_deltas = resolve_physical_impact(
                attacker=attacker_snapshot,
                defender=defender_snapshot,
                intent=intent,
                rng_seed=hash((event.id if hasattr(event, 'id') else 0, intent.actor_id, intent.target_id)) & 0xFFFFFFFF,
            )

            deltas.extend(impact_deltas)
            events_processed += 1

        if deltas:
            logger.debug(
                f"[COMBAT_SUB] {len(events)} events, "
                f"{events_processed} impacts resolved, "
                f"{len(deltas)} physiology deltas"
            )

        return Phase8Result(
            deltas=deltas,
            events_processed=events_processed,
        )

    def _extract_impact_intent(
        self, event, npc_by_id: dict[str, dict]
    ) -> Optional[ImpactIntentDTO]:
        """Извлекает ImpactIntentDTO из EventDTO.payload.

        Маппинг:
            payload.actor_id → actor_id (fallback на event.source)
            payload.target_id → target_id (обязателен)
            payload.force → force (вычисляется из intensity * scale)
            payload.damage_type → damage_type (fallback "blunt")
            payload.target_zone → target_zone (None = случайная)
            payload.weapon_reach → weapon_reach (fallback 1.0)
        """
        payload = event.payload if hasattr(event, 'payload') else {}
        if not isinstance(payload, dict):
            payload = {}

        # Определяем участников
        actor_id = payload.get("actor_id") or getattr(event, 'source', 'player')
        target_id = payload.get("target_id")
        
        # ADR-035 FIX: Если Слой 2 не дал ID, пробуем найти по target_reference (имени)
        if not target_id:
            target_ref = payload.get("target_reference")
            if target_ref:
                for npc_id, npc_dict in npc_by_id.items():
                    npc_name = npc_dict.get("name", "").lower()
                    if target_ref in npc_name or npc_name.startswith(target_ref):
                        target_id = npc_id
                        logger.debug(f"[COMBAT_SUB] Resolved target_reference '{target_ref}' to npc_id '{target_id}'")
                        break

        if not target_id:
            logger.warning(
                f"[COMBAT_SUB] event {getattr(event, 'type', '?')} "
                f"has no target_id and target_reference '{payload.get('target_reference')}' not found. Pipeline DEAD."
            )
            return None

        # Вычисляем силу воздействия
        intensity = payload.get("intensity", 0.5)
        force = payload.get("force", intensity * _DEFAULT_FORCE_SCALE)

        # Если intensity не указана, берём из ACTION_INTENSITY
        if "force" not in payload and "intensity" not in payload:
            event_type_str = getattr(event, 'type', '').lower()
            intensity = ACTION_INTENSITY.get(event_type_str, 0.2)
            force = intensity * _DEFAULT_FORCE_SCALE

        return ImpactIntentDTO(
            actor_id=actor_id,
            target_id=target_id,
            damage_type=payload.get("damage_type", _DEFAULT_DAMAGE_TYPE),
            target_zone=payload.get("target_zone"),
            force=force,
            weapon_reach=payload.get("weapon_reach", _DEFAULT_WEAPON_REACH),
        )

    @staticmethod
    def _build_snapshot(npc_id: str, npc_by_id: dict[str, dict]) -> Optional[dict]:
        """Строит NPCStateSnapshot из npc_dict.

        Использует ту же логику проекции, что и _build_npc_snapshots
        в TickOrchestrator, но для одного NPC.
        """
        npc = npc_by_id.get(npc_id)
        if npc is None:
            return None

        from app.models.idle_tick import NPCStateSnapshot

        psyche = npc.get("psyche", {})
        ss = npc.get("social_stats", {})
        body_profile = npc.get("body_profile", {})
        body_state = npc.get("body_state", {})

        _max_hp = float(body_profile.get("max_hp", 100.0))
        _current_hp = float(body_state.get("current_hp", _max_hp))
        _base_abilities = body_profile.get("abilities", {})
        _modifiers = body_state.get("modifiers", {})
        _statuses = body_state.get("statuses", [])

        # Injuries grouped by zone
        _raw_injuries = body_state.get("injuries", [])
        injuries_by_zone: dict[str, list] = {}
        for inj in _raw_injuries:
            zone = inj.get("target_zone", "unknown")
            if zone not in injuries_by_zone:
                injuries_by_zone[zone] = []
            injuries_by_zone[zone].append(inj)

        return NPCStateSnapshot(
            npc_id=npc_id,
            stress=float(psyche.get("stress", 0.0)),
            relationship_cache=npc.get("relationship_cache", {}),
            base_values=npc.get("base_values", {}),
            faction_affiliations=list(
                npc.get("status_profile", {}).get("faction_rank", {}).keys()
            ),
            hp=_current_hp,
            max_hp=_max_hp,
            pain=float(body_state.get("pain", 0.0)),
            fatigue=float(body_state.get("fatigue", 0.0)),
            blood_loss=float(body_state.get("blood_loss", 0.0)),
            consciousness=float(body_state.get("consciousness", 1.0)),
            injuries_by_zone=injuries_by_zone,
            base_abilities=_base_abilities,
            modifiers=_modifiers,
            statuses=_statuses,
        )

    @staticmethod
    def _make_player_snapshot() -> dict:
        """Идеальный снапшот игрока (не NPC, нет в all_npcs_raw).

        Мастер Тай: игрок — это источник давления, а не его жертва.
        Его тело не моделируется, но его способности влияют на Contact Resolution.
        """
        from app.models.idle_tick import NPCStateSnapshot

        return NPCStateSnapshot(
            npc_id="player",
            stress=0.0,
            relationship_cache={},
            base_values={},
            faction_affiliations=[],
            hp=100.0,
            max_hp=100.0,
            pain=0.0,
            fatigue=0.0,
            blood_loss=0.0,
            consciousness=1.0,
            injuries_by_zone={},
            base_abilities={"strength": 15.0, "dexterity": 12.0},
            modifiers={},
            statuses=[],
        )
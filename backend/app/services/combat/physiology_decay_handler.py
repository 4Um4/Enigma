# -*- coding: utf-8 -*-
"""
path: backend/app/services/combat/physiology_decay_handler.py
Назначение: Phase 0.5 idle-handler — экспоненциальное затухание физиологических
    параметров (leaky integrator).
Зависимости: math, app.models.idle_tick, app.models.state_delta
Основные сущности: PhysiologyDecayHandler

Мастер Тай: тело — инерционная система с памятью.
S_t = S_{t-1} * e^(-lambda * dt) + new_impacts

На idle-тике (Фаза 0.5) новых импульсов нет — только затухание.
Боль, шок, усталость экспоненциально убывают.
Кровопотеря имеет отдельную скорость (медленнее).
Сознание восстанавливается от затухания шока.

Closing drift (как в SocialDecayHandler): если остаток < EPSILON →
обнуляем напрямую, избегая микро-осцилляций.

TODO: в будущем можно добавить разные lambda для разных типов повреждений
(например, кровопотеря может затухать медленнее из-за свертывания крови).
"""

from __future__ import annotations

import logging
import math
from typing import List

from app.models.delta_payloads import PhysiologyPayload
from app.models.idle_tick import NPCStateSnapshot
from app.models.state_delta import DeltaDomain, StateDeltas

logger = logging.getLogger(__name__)

# --- Константы затухания (leaky integrator) ---
# Мастер Тай: разные физические процессы имеют разные постоянные времени

PAIN_DECAY_LAMBDA: float = 0.05       # Боль затухает ~5% за тик
FATIGUE_DECAY_LAMBDA: float = 0.03    # Усталость медленнее (восстановление)
BLOOD_LOSS_DECAY_LAMBDA: float = 0.01 # Кровопотеря ещё медленнее (свертывание)
CONSCIOUSNESS_RECOVERY: float = 0.02  # Восстановление сознания

PHYSIOLOGY_DECAY_EPSILON: float = 0.001  # Порог closing drift (кровопотеря даёт дельты ~0.005 при blood_loss=0.5)

# Пороги фазовых переходов (emergent states)
# Мастер Тай: не if pain > X, а устойчивость траектории
STAGGER_PAIN_THRESHOLD: float = 50.0   # Боль выше этого → нестабильность движения
COLLAPSE_CONSCIOUSNESS: float = 0.1    # Сознание ниже → коллапс системы


class PhysiologyDecayHandler:
    """Phase 0.5: экспоненциальное затухание физиологических параметров.

    Leaky integrator: S_t = S_{t-1} * exp(-lambda * dt)
    На idle-тике dt=1, новых импульсов нет.

    Возвращает StateDeltas(PHYSIOLOGY) с дельтами затухания.
    StateApplicator применяет их атомарно.
    """

    name: str = "physiology_decay"

    def handle(
        self,
        npcs: List[NPCStateSnapshot],
        campaign_id: str,
        current_tick: int,
    ) -> List[StateDeltas]:
        """Чистая функция: экспоненциальное затухание боли/усталости/кровопотери."""
        results: List[StateDeltas] = []

        for npc in npcs:
            npc_id = npc.get("npc_id", "")
            if not npc_id:
                continue

            # Текущие значения из снапшота
            current_pain = npc.get("pain", 0.0)
            current_fatigue = npc.get("fatigue", 0.0)
            current_blood_loss = npc.get("blood_loss", 0.0)
            current_consciousness = npc.get("consciousness", 1.0)

            # Пропускаем NPC без физиологических изменений
            if (current_pain <= PHYSIOLOGY_DECAY_EPSILON
                    and current_fatigue <= PHYSIOLOGY_DECAY_EPSILON
                    and current_blood_loss <= PHYSIOLOGY_DECAY_EPSILON
                    and current_consciousness >= 1.0 - PHYSIOLOGY_DECAY_EPSILON):
                continue

            # --- Leaky Integrator: экспоненциальное затухание ---
            # S_t = S_{t-1} * exp(-lambda * dt), dt = 1 tick

            # Боль затухает
            pain_after_decay = current_pain * math.exp(-PAIN_DECAY_LAMBDA)
            pain_delta = _closing_drift(pain_after_decay, 0.0) - current_pain

            # Усталость восстанавливается
            fatigue_after_decay = current_fatigue * math.exp(-FATIGUE_DECAY_LAMBDA)
            fatigue_delta = _closing_drift(fatigue_after_decay, 0.0) - current_fatigue

            # Кровопотеря медленно снижается (свертывание крови)
            blood_after_decay = current_blood_loss * math.exp(-BLOOD_LOSS_DECAY_LAMBDA)
            blood_loss_delta = _closing_drift(blood_after_decay, 0.0) - current_blood_loss

            # Сознание восстанавливается (обратно пропорционально боли)
            if current_consciousness < 1.0:
                # Чем меньше боли — тем быстрее восстановление
                recovery_rate = CONSCIOUSNESS_RECOVERY * (1.0 - current_pain / 100.0)
                consciousness_delta = min(
                    recovery_rate,
                    1.0 - current_consciousness  # Не больше максимума
                )
                # Closing drift
                if 1.0 - (current_consciousness + consciousness_delta) < PHYSIOLOGY_DECAY_EPSILON:
                    consciousness_delta = 1.0 - current_consciousness
            else:
                consciousness_delta = 0.0

            # Пропускаем если всё затухло
            if (abs(pain_delta) < PHYSIOLOGY_DECAY_EPSILON
                    and abs(fatigue_delta) < PHYSIOLOGY_DECAY_EPSILON
                    and abs(blood_loss_delta) < PHYSIOLOGY_DECAY_EPSILON
                    and abs(consciousness_delta) < PHYSIOLOGY_DECAY_EPSILON):
                continue

            # --- Фазовые переходы (emergent states) ---
            # Мастер Тай: стабильность траектории, не пороги
            add_statuses: tuple = ()
            remove_statuses: tuple = ()

            # STAGGER: высокая боль → нестабильность движения
            future_pain = current_pain + pain_delta
            if future_pain > STAGGER_PAIN_THRESHOLD:
                add_statuses = ("stagger",)
            else:
                # Боль упала ниже порога — убираем stagger
                if "stagger" in _get_statuses(npc):
                    remove_statuses = ("stagger",)

            # COLLAPSE: сознание ниже порога → обморок
            future_consciousness = current_consciousness + consciousness_delta
            if future_consciousness < COLLAPSE_CONSCIOUSNESS:
                add_statuses = add_statuses + ("unconscious",)
            else:
                # Сознание восстановилось — убираем unconscious
                if "unconscious" in _get_statuses(npc):
                    remove_statuses = remove_statuses + ("unconscious",)

            results.append(StateDeltas(
                npc_id=npc_id,
                domain=DeltaDomain.PHYSIOLOGY,
                payload=PhysiologyPayload(
                    pain_delta=round(pain_delta, 4),
                    fatigue_delta=round(fatigue_delta, 4),
                    blood_loss_delta=round(blood_loss_delta, 4),
                    add_statuses=add_statuses,
                    remove_statuses=remove_statuses,
                ),
                source="physiology_decay",
            ))

        if results:
            logger.debug(
                f"[PHYSIOLOGY_DECAY] {len(results)} NPCs with decay"
            )

        return results


def _closing_drift(current: float, target: float) -> float:
    """Closing drift: если остаток < EPSILON → обнуляем напрямую.

    Как в SocialDecayHandler: гарантирует достижение равновесия
    без микро-осцилляций.
    """
    if abs(current - target) < PHYSIOLOGY_DECAY_EPSILON:
        return target
    return current


def _get_statuses(npc: NPCStateSnapshot) -> list:
    """Извлекает текущие статусы из снапшота."""
    return npc.get("statuses", [])
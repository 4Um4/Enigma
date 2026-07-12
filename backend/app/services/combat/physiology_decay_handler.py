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

PAIN_DECAY_LAMBDA: float = 0.05  # Боль затухает ~5% за тик
FATIGUE_DECAY_LAMBDA: float = 0.03  # Усталость медленнее (восстановление)
BLOOD_LOSS_DECAY_LAMBDA: float = 0.01  # Кровопотеря ещё медленнее (свертывание)
CONSCIOUSNESS_RECOVERY: float = 0.02  # Восстановление сознания
SHOCK_DECAY_LAMBDA: float = 0.08  # Шок затухает быстрее боли (~8% за тик)

PHYSIOLOGY_DECAY_EPSILON: float = (
    0.001  # Порог closing drift (кровопотеря даёт дельты ~0.005 при blood_loss=0.5)
)

# Пороги фазовых переходов (emergent states)
# Мастер Тай: не if pain > X, а устойчивость траектории
STAGGER_PAIN_THRESHOLD: float = 50.0  # Боль выше этого → нестабильность движения
COLLAPSE_CONSCIOUSNESS: float = 0.1  # Сознание ниже → коллапс системы


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

        # P3 ARCH: Perceptual causes decay (threat/uncertainty/anomaly).
        # Активные причины сами затухают со временем, если нет новых стимулов.
        PERCEPTUAL_DECAY_LAMBDA = 0.05  # ~5% за тик

        for npc in npcs:
            npc_id = npc.get("npc_id", "")
            if not npc_id:
                continue

            # ADR-124 DEATH LOCK: Physics layer НЕ мутирует мёртвых.
            # Инвариант: DEAD does NOT affect physics layer.
            # Decay, healing, injury processing — все пропускают DEAD NPC.
            # Единственный путь DEAD → ALIVE: RevivalSystem (пока не реализован).
            if npc.get("life_status", "ALIVE") == "DEAD":
                continue

            # ADR-100/124: Физиология хранится ТОЛЬКО внутри body_state.
            _body = npc.get("body_state", {})
            if not isinstance(_body, dict):
                _body = {}

            # Текущие значения из снапшота
            current_pain = _body.get("pain", 0.0)
            current_fatigue = _body.get("fatigue", 0.0)
            current_blood_loss = _body.get("blood_loss", 0.0)
            current_consciousness = _body.get("consciousness", 1.0)
            current_shock = _body.get("shock_impulse", 0.0)

            # Диагностика: почему injuries теряются между тиками?
            _inj = _body.get("injuries_by_zone", {})
            if _inj:
                logger.debug(
                    f"[DECAY_INJURY] npc={npc.get('npc_id', '?')} has_injuries=True zones={list(_inj.keys())} blood_loss={current_blood_loss:.3f}"
                )
            elif current_blood_loss > 0.01:
                logger.debug(
                    f"[DECAY_INJURY_LOST] npc={npc.get('npc_id', '?')} has_injuries=False BUT blood_loss={current_blood_loss:.3f} — INJURIES LOST!"
                )

            # Perceptual Kernel — чтение текущих активных причин
            pk = npc.get("perceptual_kernel", {})
            current_threat = float(pk.get("threat_gradient", 0.0))
            current_uncertainty = float(pk.get("uncertainty", 0.0))
            current_anomaly = float(pk.get("anomaly_score", 0.0))

            # Пропускаем NPC без физиологических и перцептивных изменений
            if (
                current_pain <= PHYSIOLOGY_DECAY_EPSILON
                and current_fatigue <= PHYSIOLOGY_DECAY_EPSILON
                and current_blood_loss <= PHYSIOLOGY_DECAY_EPSILON
                and current_consciousness >= 1.0 - PHYSIOLOGY_DECAY_EPSILON
                and current_shock <= PHYSIOLOGY_DECAY_EPSILON
                and current_threat <= PHYSIOLOGY_DECAY_EPSILON
                and current_uncertainty <= PHYSIOLOGY_DECAY_EPSILON
                and current_anomaly <= PHYSIOLOGY_DECAY_EPSILON
            ):
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
            blood_loss_delta = (
                _closing_drift(blood_after_decay, 0.0) - current_blood_loss
            )

            # Шок затухает быстрее боли — это острый сигнал, не хроническое состояние
            shock_after_decay = current_shock * math.exp(-SHOCK_DECAY_LAMBDA)
            shock_delta = _closing_drift(shock_after_decay, 0.0) - current_shock

            # Сознание восстанавливается (обратно пропорционально боли)
            if current_consciousness < 1.0:
                # Чем меньше боли — тем быстрее восстановление
                recovery_rate = CONSCIOUSNESS_RECOVERY * (1.0 - current_pain / 100.0)
                consciousness_delta = min(
                    recovery_rate,
                    1.0 - current_consciousness,  # Не больше максимума
                )
                # Closing drift
                if (
                    1.0 - (current_consciousness + consciousness_delta)
                    < PHYSIOLOGY_DECAY_EPSILON
                ):
                    consciousness_delta = 1.0 - current_consciousness
            else:
                consciousness_delta = 0.0

            # P3 ARCH: Decay Perceptual Causes (активные причины затухают)
            threat_after_decay = current_threat * math.exp(-PERCEPTUAL_DECAY_LAMBDA)
            uncertainty_after_decay = current_uncertainty * math.exp(
                -PERCEPTUAL_DECAY_LAMBDA
            )
            anomaly_after_decay = current_anomaly * math.exp(-PERCEPTUAL_DECAY_LAMBDA)

            threat_delta = _closing_drift(threat_after_decay, 0.0) - current_threat
            uncertainty_delta = (
                _closing_drift(uncertainty_after_decay, 0.0) - current_uncertainty
            )
            anomaly_delta = _closing_drift(anomaly_after_decay, 0.0) - current_anomaly

            # Пропускаем если всё затухло
            if (
                abs(pain_delta) < PHYSIOLOGY_DECAY_EPSILON
                and abs(fatigue_delta) < PHYSIOLOGY_DECAY_EPSILON
                and abs(blood_loss_delta) < PHYSIOLOGY_DECAY_EPSILON
                and abs(consciousness_delta) < PHYSIOLOGY_DECAY_EPSILON
                and abs(shock_delta) < PHYSIOLOGY_DECAY_EPSILON
                and abs(threat_delta) < PHYSIOLOGY_DECAY_EPSILON
                and abs(uncertainty_delta) < PHYSIOLOGY_DECAY_EPSILON
                and abs(anomaly_delta) < PHYSIOLOGY_DECAY_EPSILON
            ):
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

            # Физиология (боль, шок и тд)
            if (
                abs(pain_delta) >= PHYSIOLOGY_DECAY_EPSILON
                or abs(fatigue_delta) >= PHYSIOLOGY_DECAY_EPSILON
                or abs(blood_loss_delta) >= PHYSIOLOGY_DECAY_EPSILON
                or abs(consciousness_delta) >= PHYSIOLOGY_DECAY_EPSILON
                or abs(shock_delta) >= PHYSIOLOGY_DECAY_EPSILON
            ):
                results.append(
                    StateDeltas(
                        npc_id=npc_id,
                        domain=DeltaDomain.PHYSIOLOGY,
                        payload=PhysiologyPayload(
                            pain_delta=round(pain_delta, 4),
                            fatigue_delta=round(fatigue_delta, 4),
                            blood_loss_delta=round(blood_loss_delta, 4),
                            shock_impulse=round(shock_delta, 4),
                            add_statuses=add_statuses,
                            remove_statuses=remove_statuses,
                        ),
                        source="physiology_decay",
                    )
                )

            # Восприятие (угроза, неопределённость, аномалия) — причины затухают
            # АРХИТЕКТУРНЫЙ ДОЛГ: Это emergency bandage. Правильная архитектура —
            # recompute PerceptualKernel из observable world state на каждом тике.
            # Пока perceive_world() не реализован, decay — единственный способ
            # избежать "вечного страха" после одной атаки.
            if (
                abs(threat_delta) >= PHYSIOLOGY_DECAY_EPSILON
                or abs(uncertainty_delta) >= PHYSIOLOGY_DECAY_EPSILON
                or abs(anomaly_delta) >= PHYSIOLOGY_DECAY_EPSILON
            ):
                from app.models.delta_payloads import PerceptionPayload

                results.append(
                    StateDeltas(
                        npc_id=npc_id,
                        domain=DeltaDomain.PERCEPTION,
                        payload=PerceptionPayload(
                            threat_gradient_delta=round(threat_delta, 4),
                            uncertainty_delta=round(uncertainty_delta, 4),
                            anomaly_score_delta=round(anomaly_delta, 4),
                        ),
                        source="perception_decay",
                    )
                )

        if results:
            logger.debug(f"[PHYSIOLOGY_DECAY] {len(results)} NPCs with decay")

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

"""
path: backend/app/services/npc/belief_crystallization_engine.py
Назначение: Мост между статистикой (L1.5) и психологией (L2.5).
Зависимости: backend/app/domain/identity_events.py, backend/app/models/npc_state.py
Основные сущности: BeliefCrystallizationEngine, CrystallizedBelief
"""

import logging
import math
from typing import Dict, List

from app.domain.identity_events import CrystallizedBelief, EvidenceOfPersistence

logger = logging.getLogger(__name__)

# ADR-O-307: Множитель асимметричной травмы. Опровержение в 6 раз сильнее подтверждения.
TRAUMA_MULTIPLIER: float = 6.0
MAX_WEIGHT: float = 1.0

# Энтропия убеждений: Половина веса теряется за ~70 тиков без подкрепления.
BELIEF_DECAY_TAU: float = 100.0
# Порог забывания: если вес упал ниже этого значения, убеждение стирается.
BELIEF_FORGET_THRESHOLD: float = 0.05


class BeliefCrystallizationEngine:
    """
    L2.5: Проецирует агрегированную статистику (EvidenceOfPersistence)
    в психологическое убеждение (CrystallizedBelief), модулированное drives_base (L0).

    ADR-O-305: Не читает L1Chronicle. Работает только с готовой статистикой.
    ADR-O-307: Реализует асимметричную травму.
    """

    def crystallize(
        self,
        evidence_list: List[EvidenceOfPersistence],
        drives_base: Dict[str, float],
        existing_beliefs: List[CrystallizedBelief],
        current_tick: int,
    ) -> List[CrystallizedBelief]:
        """
        Формирует или обновляет убеждения на основе свежей статистики.

        Args:
            evidence_list: Статистика от PatternDetector (L1.5).
            drives_base: Базовые драйвы личности NPC (L0).
            existing_beliefs: Текущие убеждения NPC (для асимметричной травмы).
            current_tick: Текущий тик симуляции.

        Returns:
            Обновлённый список CrystallizedBelief.
        """
        updated_beliefs: Dict[str, CrystallizedBelief] = {}

        # 1. Фаза Энтропии: Затухание старых убеждений
        for belief in existing_beliefs:
            time_delta = max(0, current_tick - belief.last_updated_tick)
            decay_factor = math.exp(-time_delta / BELIEF_DECAY_TAU)
            decayed_weight = belief.weight * decay_factor

            # Если вес выше порога забывания — сохраняем убеждение
            if decayed_weight > BELIEF_FORGET_THRESHOLD:
                updated_beliefs[belief.source_id] = CrystallizedBelief(
                    source_id=belief.source_id,
                    trait=belief.trait,
                    weight=decayed_weight,
                    last_updated_tick=belief.last_updated_tick,  # Сохраняем оригинальный тик
                )

        for evidence in evidence_list:
            # Определение направления эффекта (угроза или помощь)
            # Отрицательный эффект = угроза -> fear
            # Положительный эффект = помощь -> trust
            if evidence.cumulative_effect < 0.0:
                target_trait = "fear"
                # Модуляция личностью: высокий fear_drive делает NPC более чувствительным к угрозам
                sensitivity = drives_base.get("fear", 0.25)
                # ADR-O-307: Асимметричная травма. Опровержение в 6 раз сильнее.
                effect_magnitude = abs(evidence.cumulative_effect) * TRAUMA_MULTIPLIER
            else:
                target_trait = "trust"
                # Модуляция личностью: высокий significance или desire делает NPC ценящим помощь
                sensitivity = drives_base.get("significance", 0.25) + drives_base.get(
                    "desire", 0.25
                )
                # Позитивный эффект не имеет множителя
                effect_magnitude = evidence.cumulative_effect

            # Базовый вес формируемого убеждения (нормализованный к 1.0)
            # Учитываем magnitude эффекта и чувствительность личности
            # Делим на 10.0 как масштабный коэффициент (предполагаем, что cumulative_effect в диапазоне ~-10..10)
            base_weight = min(abs(evidence.cumulative_effect) / 10.0, 1.0) * sensitivity

            # Поиск существующего убеждения к этому источнику
            existing = updated_beliefs.get(evidence.source_id)

            if existing:
                # ADR-O-307: Асимметричная травма
                if existing.trait == target_trait:
                    # Подтверждение: линейный рост
                    new_weight = min(existing.weight + base_weight, MAX_WEIGHT)
                else:
                    # Опровержение: вес старого убеждения падает в 6 раз быстрее
                    # И если он падает до нуля, может сформироваться новое убеждение
                    decayed_weight = existing.weight - (base_weight * TRAUMA_MULTIPLIER)

                    if decayed_weight <= 0.0:
                        # Старое убеждение разрушено, формируем новое
                        # Остаточный вес переносится (опровергнуто, но не полностью)
                        new_weight = min(abs(decayed_weight), MAX_WEIGHT)
                        target_trait = target_trait  # Трейт меняется на новый
                    else:
                        # Убеждение ещё держится, но ослабло
                        new_weight = decayed_weight
                        target_trait = (
                            existing.trait
                        )  # Трейт остаётся старым, пока вес > 0

                updated_beliefs[evidence.source_id] = CrystallizedBelief(
                    source_id=evidence.source_id,
                    trait=target_trait,
                    weight=new_weight,
                    last_updated_tick=current_tick,
                )
                logger.info(f"[L2.5] Crystallized: npc={evidence.source_id} trait={target_trait} weight={new_weight:.2f}")
            else:
                # Формирование нового убеждения
                if base_weight > 0.05:  # Порог кристаллизации
                    updated_beliefs[evidence.source_id] = CrystallizedBelief(
                        source_id=evidence.source_id,
                        trait=target_trait,
                        weight=base_weight,
                        last_updated_tick=current_tick,
                    )
                    logger.info(f"[L2.5] Crystallized: npc={evidence.source_id} trait={target_trait} weight={base_weight:.2f}")

        return list(updated_beliefs.values())

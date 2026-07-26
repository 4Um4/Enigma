# -*- coding: utf-8 -*-
"""
path: backend/app/domain/vital_state.py
Назначение: Переходный слой оценки жизненного состояния. Заменяет hp<=0.
Зависимости: typing (только)
Основные сущности: LifeStatus, evaluate_vital_state, is_conscious, is_capable

═══════════════════════════════════════════════════════════════
ПЕРЕХОДНЫЙ СЛОЙ — НЕ ФИНАЛЬНАЯ ОНТОЛОГИЯ
═══════════════════════════════════════════════════════════════

Этот модуль существует для одной цели:
заменить `if hp <= 0: dead = True` на причинно-корректную оценку.

Он НЕ является финальной системой смерти.
Финальная система появится после Injury:

    Impact → Injury → Physiology → VitalState → DecisionHub

Пока Injury нет, смерть возможна ТОЛЬКО через кровопотерю —
единственный существующий процесс, способный накапливаться
до фатального уровня.

═══════════════════════════════════════════════════════════════
ТРИ ОСИ — НЕ ОДНА
═══════════════════════════════════════════════════════════════

Жизнь, сознание и дееспособность — независимые оси.

NPC может быть:
    ALIVE + UNCONSCIOUS + INCAPACITATED  (нокаут)
    ALIVE + CONSCIOUS + INCAPACITATED    (сломаны ноги)
    ALIVE + CONSCIOUS + OPERATIONAL      (здоров)

Смешивание осей в один enum — архитектурная ошибка,
потому что создаёт невозможные комбинации
и теряет информацию о том, ЧТО именно нарушено.

═══════════════════════════════════════════════════════════════
ЧТО ЗАПРЕЩЕНО
═══════════════════════════════════════════════════════════════

❌ hp <= 0 как источник смерти
❌ shock_impulse как источник смерти (шок — сигнал, не процесс)
❌ Новые поля body_state без причинного источника
❌ Прогнозы («неизбежно умрёт») — система не умеет прогнозировать
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict

logger = logging.getLogger(__name__)


# ── Ось 1: Жизнь ────────────────────────────────────────────────────────


class LifeStatus(str, Enum):
    """Жизнь или смерть. Переходный вариант — только две точки.

    После Injury система расширится:
    появятся процессы (кровотечение, удушье, отравление),
    и LifeStatus будет учитывать их.

    Сейчас единственный процесс, способный убить — кровопотеря.
    """

    ALIVE = "ALIVE"
    DEAD = "DEAD"


# ── Пороги кровопотери ──────────────────────────────────────────────────
# Единственный существующий механизм смерти.
# Порог = наблюдение: при потере 90% крови организм не может функционировать.
# Это НЕ прогноз. Это наблюдение текущего состояния.
# Кровопотеря накапливается тик за тиком через bleeding injuries,
# поэтому между ранением и смертью есть окно для спасения.

_BLOOD_LOSS_FATAL: float = 0.9

# ADR-124: Structural collapse threshold.
# Когда суммарное структурное повреждение всех ран превышает этот порог,
# организм не может поддерживать функцию органов — multiple organ failure.
# Это НЕ "shock kills" (Rule 39). Это физическое разрушение тканей.
# ~3 тяжёлых удара (structural_damage ~0.5 каждый) = 1.5 → DEAD
# ~5 умеренных ударов (structural_damage ~0.3 каждый) = 1.5 → DEAD
# Кулачный бой: 3-5 точных попаданий → смерть (реалистично)
# Нож: 1-2 попадания + кровопотеря → смерть (через кровь или структуру)
_STRUCTURAL_COLLAPSE: float = 1.5


def evaluate_vital_state(body_state: Dict[str, Any]) -> LifeStatus:
    """Pure function: BodyState → LifeStatus.

    ЕДИНСТВЕННЫЙ владелец решения о жизни/смерти.
    Никто другой не имеет права объявлять смерть.

    Два пути смерти (ADR-124):
    1. Hemorrhagic: кровопотеря ≥ 90% → необратимый коллапс circulation
    2. Structural: кумулятивное разрушение тканей ≥ 1.5 → organ failure

    Запрещено (Rule 39): shock_impulse как прямой источник смерти.
    Шок — сигнал, не процесс. Но структурное разрушение — процесс.
    """
    if not body_state:
        return LifeStatus.ALIVE

    # ADR-124 DEATH LOCK: Временный инвариант против баговой реинкарнации.
    # Любой переход DEAD → ALIVE запрещён обычной физиологией (decay, healing, evaluation).
    # Такой переход может выполняться ТОЛЬКО через RevivalSystem (пока не реализован).
    # Причина: decay снижает blood_loss/pain/shock для мёртвых NPC → evaluator
    # пересчитывает смерть с нуля → воскрешает. Это каузальный разрыв.
    # ПЕРВАЯ проверка: если уже мёртв — не пересчитываем.
    if body_state.get("life_status") == LifeStatus.DEAD.value:
        return LifeStatus.DEAD

    # Pathway 1: Hemorrhagic death
    blood_loss = float(body_state.get("blood_loss", 0.0))
    if blood_loss >= _BLOOD_LOSS_FATAL:
        # TODO (Backlog): death_cause = "HEMORRHAGIC", reversibility = 0.3
        # Подготовка слота для DeathState (каузальная классификация смерти)
        return LifeStatus.DEAD

    # Pathway 2: Structural collapse (ADR-124)
    # Кумулятивное разрушение → multiple organ failure.
    # Реалистично: тело с >60% тяжёлых повреждений не может функционировать.
    _injuries = body_state.get("injuries", [])
    if _injuries:
        _total_structural = sum(
            float(inj.get("structural_damage", 0.0)) for inj in _injuries
        )
        logger.warning(
            f"[VITAL_EVAL] injuries={len(_injuries)} total_structural={_total_structural:.3f} threshold={_STRUCTURAL_COLLAPSE} blood_loss={blood_loss:.3f}"
        )
        if _total_structural >= _STRUCTURAL_COLLAPSE:
            logger.warning(
                f"[STRUCTURAL_DEATH] total={_total_structural:.3f} >= {_STRUCTURAL_COLLAPSE} injuries={len(_injuries)}"
            )
            # TODO (Backlog): death_cause = "STRUCTURAL", reversibility = 0.05
            # Подготовка слота для DeathState (каузальная классификация смерти)
            return LifeStatus.DEAD

    return LifeStatus.ALIVE


# ── Ось 2: Сознание ────────────────────────────────────────────────────

# Порог потери сознания. Совпадает с COLLAPSE_CONSCIOUSNESS
# из physiology_decay_handler.py.
_CONSCIOUSNESS_THRESHOLD: float = 0.1


def is_conscious(body_state: Dict[str, Any]) -> bool:
    """Pure function: BodyState → сознание есть/нет.

    Если сознания нет — DecisionHub блокируется.
    Тело продолжает жить (кровопотеря может продолжаться).
    """
    if not body_state:
        return True

    consciousness = float(body_state.get("consciousness", 1.0))
    return consciousness > _CONSCIOUSNESS_THRESHOLD


# ── Ось 3: Дееспособность ──────────────────────────────────────────────

# Пороги моторной блокировки. Боль или шок могут сделать
# невозможным действие, даже если сознание есть.
_PAIN_INCAPACITATED: float = 70.0
_SHOCK_INCAPACITATED: float = 0.7


def is_capable(body_state: Dict[str, Any]) -> bool:
    """Pure function: BodyState → может действовать/нет.

    В сознании, но боль или шок блокируют моторику.
    DecisionHub может работать с ограничениями (Somatic Veto).
    """
    if not body_state:
        return True

    pain = float(body_state.get("pain", 0.0))
    shock_impulse = float(body_state.get("shock_impulse", 0.0))

    return pain < _PAIN_INCAPACITATED and shock_impulse < _SHOCK_INCAPACITATED

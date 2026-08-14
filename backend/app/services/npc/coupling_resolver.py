"""
path: /project/backend/app/services/npc/coupling_resolver.py
Назначение: Вычисление непрерывного профиля связанности тела (CouplingProfile) на основе BodyState.
Зависимости: app.domain.body, typing
Основные сущности: CouplingResolver
Запреты:
- НЕ мутирует BodyState (чистая функция вычисления).
- НЕ использует случайность (недетерминированность).
- НЕ хранит состояние между тиками (Stateless).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.domain.body import CouplingProfile, CouplingMode

logger = logging.getLogger(__name__)


class CouplingResolver:
    """
    Вычисляет CouplingProfile из BodyState.
    Заменяет хардкод-переключатели if is_sleeping на непрерывные оси.
    """

    def resolve(self, body_state: Dict[str, Any]) -> CouplingProfile:
        """
        Вычисляет профиль связанности на основе sleep_pressure и arousal.
        
        Архитектурный сдвиг "Сон как Телесный Режим":
        - external_vision_mult: падает при низком arousal.
        - external_hearing_mult: падает, но медленнее (слух — последний бастиан).
        - motor_output_mult: резко падает при high sleep_pressure.
        - memory_activation_mult: возрастает при high sleep_pressure.
        - imagination_mult: возрастает при high sleep_pressure + low arousal.
        """
        if not body_state:
            return CouplingProfile()  # Дефолтный профиль бодрствования

        sleep_pressure = float(body_state.get("sleep_pressure", 0.0))
        arousal = float(body_state.get("arousal", 0.0))

        # Нормализация (на случай выхода за границы из-за багов мутации)
        sleep_pressure = max(0.0, min(1.0, sleep_pressure))
        arousal = max(0.0, min(1.0, arousal))

        # Wakefulness: инверсия sleep_pressure, но модулированная arousal (внезапный шум будит)
        wakefulness = max(0.0, arousal - sleep_pressure * 0.5)

        # Внешние связи затухают по мере ухода в сон
        external_vision_mult = max(0.05, wakefulness)  # Минимум 5% (сны могут иметь визуал)
        external_hearing_mult = max(0.2, wakefulness * 0.8 + arousal * 0.2)  # Слух последним отключается
        
        # Моторика блокируется сном
        motor_output_mult = max(0.0, 1.0 - sleep_pressure * 1.2)

        # Внутренняя симуляция усиливается во сне
        memory_activation_mult = 0.5 + sleep_pressure * 0.5
        imagination_mult = 0.1 + sleep_pressure * 0.9

        # Вычисление диагностической метки CouplingMode
        coupling_mode = self._resolve_mode(sleep_pressure, arousal)

        return CouplingProfile(
            external_vision_mult=external_vision_mult,
            external_hearing_mult=external_hearing_mult,
            motor_output_mult=motor_output_mult,
            memory_activation_mult=memory_activation_mult,
            imagination_mult=imagination_mult,
            coupling_mode=coupling_mode
        )

    def _resolve_mode(self, sleep_pressure: float, arousal: float) -> CouplingMode:
        """Определяет диагностическую метку режима для UI/логов."""
        if sleep_pressure < 0.3:
            return CouplingMode.FULL_WAKE
        elif sleep_pressure < 0.7:
            return CouplingMode.DROWSY
        elif arousal > 0.6:  # REM-фаза (быстрый сон)
            return CouplingMode.REM
        elif sleep_pressure > 0.9 and arousal < 0.1:
            return CouplingMode.DEEP_SLEEP
        else:
            return CouplingMode.SLEEP
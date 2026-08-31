# -*- coding: utf-8 -*-
"""
path: /project/backend/app/services/npc/sleep_onset_resolver.py
Назначение: S2B6-B (вердикты В1/В2): чистая оценка УСЛОВИЯ физиологического
    засыпания (SleepOnsetEligibility), не факт. Компоненты: sleep intent
    (поведенческий сигнал расписания) + BED-контекст (мир говорит «здесь
    можно спать») + settled (нет активного traversal) + alive + не
    заблокирован (GAP9-пороги страха/стресса, когнитивный паралич).
Зависимости: app.domain.body, app.services.npc.sleep_states
Основные сущности: SleepOnsetResolver
Запреты:
- НЕ пишет body_state (условие; факт пишет SleepLifecycleService Phase 0.6).
- НЕ решает поведение при отказе (no-BED ≠ resting — вердикт §9).
- НЕ вводит новые калибровки (пороги — существующие GAP9/паралич; закон №13).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.domain.body import SleepOnsetEligibility
from app.services.npc.sleep_states import is_sleeping

logger = logging.getLogger(__name__)

# Существующие пороги (значения канонизированы, НЕ изменены):
# GAP9 (life_engine: спящий под угрозой/стрессом не засыпает) и
# когнитивный паралич (_check_wake_up: init_sup > 0.7).
_THREAT_BLOCK = 0.3
_STRESS_BLOCK = 50.0
_PARALYSIS_BLOCK = 0.7


class SleepOnsetResolver:
    """S2B6-B: eligibility — чистая функция (condition ≠ fact)."""

    name: str = "sleep_onset_resolver"

    @staticmethod
    def resolve(
        npc: Dict[str, Any],
        tick: int,
        bed_ok: bool,
        settled: bool,
    ) -> SleepOnsetEligibility:
        """Разрешён ли физиологический переход в сон на тике tick.

        Порядок проверок детерминирован; первая блокирующая причина
        попадает в reason (диагностика/лог, не ветвление поведения).
        bed_ok/settled поставляет вызывающий контур (оркестратор
        Phase 0.6): валидация BED-позиции и отсутствие traversal —
        не знания этого резолвера.
        """
        _body = npc.get("body_state") or {}
        if (_body.get("life_status") or "ALIVE") == "DEAD":
            return SleepOnsetEligibility(eligible=False, tick=tick, reason="dead")

        _current = (npc.get("routine") or {}).get("current", "")
        if not is_sleeping(_current):
            return SleepOnsetEligibility(eligible=False, tick=tick, reason="no_intent")

        if not bed_ok:
            return SleepOnsetEligibility(eligible=False, tick=tick, reason="no_bed")

        if not settled:
            return SleepOnsetEligibility(eligible=False, tick=tick, reason="travelling")

        _kernel = npc.get("perceptual_kernel")
        if isinstance(_kernel, dict):
            _threat = float(_kernel.get("threat_gradient", 0.0))
            _init_sup = float(_kernel.get("initiative_suppression", 0.0))
        elif _kernel:
            _threat = float(getattr(_kernel, "threat_gradient", 0.0))
            _init_sup = float(getattr(_kernel, "initiative_suppression", 0.0))
        else:
            _threat = 0.0
            _init_sup = 0.0
        _stress = float((npc.get("psyche") or {}).get("stress", 0.0))

        if _threat > _THREAT_BLOCK:
            return SleepOnsetEligibility(eligible=False, tick=tick, reason="blocked_threat")
        if _stress > _STRESS_BLOCK:
            return SleepOnsetEligibility(eligible=False, tick=tick, reason="blocked_stress")
        if _init_sup > _PARALYSIS_BLOCK:
            return SleepOnsetEligibility(eligible=False, tick=tick, reason="blocked_paralysis")

        return SleepOnsetEligibility(eligible=True, tick=tick)

"""
path: /project/backend/app/services/npc/dream_generation_service.py
Назначение: Генерация DreamSignal из стимулов PerceptualKernel во время сна (Phase E).
Зависимости: app.domain.body
Основные сущности: DreamGenerationService
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.body import DreamSignal

logger = logging.getLogger(__name__)


class DreamGenerationService:
    """
    Pure function: конвертирует стимулы PerceptualKernel в DreamSignal.
    Исказает восприятие через призму спящего тела (imagination_mult).
    """

    @staticmethod
    def generate(npc: Dict[str, Any], tick: int) -> Optional[DreamSignal]:
        """Создаёт DreamSignal, если стимулы достаточно сильны."""
        _body = npc.get("body_state", {})
        _cp_dict = _body.get("coupling_profile", {})
        if not _cp_dict:
            return None

        _kernel = npc.get("perceptual_kernel")
        if not _kernel:
            return None

        _threat = 0.0
        _uncertainty = 0.0
        _anomaly = 0.0

        if isinstance(_kernel, dict):
            _threat = float(_kernel.get("threat_gradient", 0.0))
            _uncertainty = float(_kernel.get("uncertainty", 0.0))
            _anomaly = float(_kernel.get("anomaly_score", 0.0))
        else:
            _threat = float(getattr(_kernel, "threat_gradient", 0.0))
            _uncertainty = float(getattr(_kernel, "uncertainty", 0.0))
            _anomaly = float(getattr(_kernel, "anomaly_score", 0.0))

        # Исказаем стимулы через imagination_mult (внутренняя симуляция во сне).
        _imagination_mult = float(_cp_dict.get("imagination_mult", 0.1))
        _dream_pressure = max(_threat, _uncertainty * 0.5, _anomaly * 0.5) * _imagination_mult

        if _dream_pressure < 0.15:
            return None

        # Маппинг стимулов в искажённые образы (субъективный опыт).
        _raw_stimulus = "noise"
        _distorted_perception = "shadow"

        if _threat > 0.5:
            _raw_stimulus = "threat"
            _distorted_perception = "monster" if _imagination_mult > 0.5 else "shadow"
        elif _anomaly > 0.5:
            _raw_stimulus = "anomaly"
            _distorted_perception = "falling" if _imagination_mult > 0.5 else "strange_sound"
        elif _uncertainty > 0.5:
            _raw_stimulus = "uncertainty"
            _distorted_perception = "maze" if _imagination_mult > 0.5 else "whisper"

        npc_id = npc.get("id", "unknown")

        return DreamSignal(
            target_id=npc_id,
            tick=tick,
            raw_stimulus=_raw_stimulus,
            distorted_perception=_distorted_perception,
            salience=min(1.0, _dream_pressure)
        )
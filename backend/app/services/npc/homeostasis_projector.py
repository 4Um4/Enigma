"""
path: backend/app/services/npc/homeostasis_projector.py
Назначение: Field Layer гомеостаза (Фаза 0.5).
             Непрерывный дрейф social_satiation под давлением (setpoint - EMA).
             Не обрабатывает события напрямую — только непрерывную математику.
Зависимости: models.state_delta, models.delta_payloads
Основные сущности: HomeostasisProjector (статический метод compute_isolation_decay)
"""

import logging
import math
from typing import List

from app.models.delta_payloads import SocialPayload
from app.models.state_delta import DeltaDomain, StateDeltas

logger = logging.getLogger(__name__)

import math

# --- Коэффициенты Field Layer (Фаза 0.5) ---
# Полураспад EMA: 50 тиков (5 минут game-time). ln(2) / 50 ≈ 0.0138
_SOCIAL_EMA_DECAY_RATE = math.log(2) / 50.0 
# Множитель дрейфа насыщения от давления (setpoint - actual). 
_SOCIAL_DRIFT_SCALE = 2.0                   


class HomeostasisProjector:
    """Field Layer: непрерывный дрейф гомеостаза (Фаза 0.5).
    
    Не подписывается на события. Вызывается оркестратором статически.
    """

    @staticmethod
    def compute_isolation_decay(
        all_npcs_raw: List[dict],
    ) -> List[StateDeltas]:
        """Field-driven drift: social_satiation дрейфует под давлением гомеостаза.
        
        Pressure = Setpoint (gregariousness) - Actual (EMA).
        Если Pressure > 0 (скучно) → satiation падает.
        Если Pressure < 0 (перегруз) → satiation растёт.
        Также EMA затухает к 0 (память о социальном входе растворяется).
        Вызывается из Phase 0.5. Clamp выполняется в StateApplicator.
        """
        deltas: List[StateDeltas] = []

        for npc_dict in all_npcs_raw:
            _npc_id = npc_dict.get("npc_id", "")
            if not _npc_id or _npc_id == "player":
                continue

            _psyche = npc_dict.get("psyche", {})
            # Setpoint: вычисляется на лету из gregariousness. 0.2 (интроверт) ... 0.8 (экстраверт)
            _setpoint = 0.2 + (0.6 * float(_psyche.get("gregariousness", 0.5)))
            _actual = float(npc_dict.get("social_input_ema", 0.0))

            # Давление: разница между желаемым и реальным.
            _pressure = _setpoint - _actual
            
            # Дрейф насыщения: изоляция (pressure > 0) опускает, перегруз (pressure < 0) поднимает.
            _satiation_delta = -_pressure * _SOCIAL_DRIFT_SCALE
            
            # Затухание EMA (полураспад)
            _ema_decay_delta = -_actual * _SOCIAL_EMA_DECAY_RATE

            if abs(_satiation_delta) > 1e-4 or abs(_ema_decay_delta) > 1e-4:
                deltas.append(StateDeltas(
                    npc_id=_npc_id,
                    domain=DeltaDomain.SOCIAL,
                    payload=SocialPayload(
                        social_satiation_delta=_satiation_delta,
                        social_input_ema_delta=_ema_decay_delta,
                    ),
                    source="homeostasis_isolation",
                ))

        return deltas
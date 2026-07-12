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
from typing import Dict, Any, List

from app.models.delta_payloads import SocialPayload
from app.models.state_delta import DeltaDomain, StateDeltas

logger = logging.getLogger(__name__)


# --- Коэффициенты Field Layer (Фаза 0.5) ---
# Полураспад EMA: 50 тиков (5 минут game-time). ln(2) / 50 ≈ 0.0138
_SOCIAL_EMA_DECAY_RATE = math.log(2) / 50.0
# Множитель внешнего давления (setpoint - EMA) на состояние.
_SOCIAL_PRESSURE_SCALE = 1.5
# Множитель внутренней релаксации к базовому уровню (50.0).
_SOCIAL_RELAXATION_RATE = 0.05


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
            _actual = float(npc_dict.get("social_input_ema", 0.0))

            # Field Channel: единственная persisted-динамика — затухание EMA (полураспад)
            _ema_decay_delta = -_actual * _SOCIAL_EMA_DECAY_RATE

            if abs(_ema_decay_delta) > 1e-4:
                # Setpoint вычисляется на лету в behavior_modifiers. Здесь мы только гасим память поля.
                deltas.append(
                    StateDeltas(
                        npc_id=_npc_id,
                        domain=DeltaDomain.SOCIAL,
                        payload=SocialPayload(
                            social_input_ema_delta=_ema_decay_delta,
                        ),
                        source="homeostasis_ema_decay",
                    )
                )

        return deltas

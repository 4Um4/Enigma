"""
Назначение: Если мы переведем дальние локации в облегченный режим (LOD), нам нужно будет пропускать тяжелые фазы (память, решения, события) и оставлять только физиологию (LifeEngine) и время.
"""

import time
import logging
from collections import deque
from typing import List, Optional

logger = logging.getLogger(__name__)

class AdaptiveTickLoader:
    """Дополнение Б (п. Б.11): Автоматический LOD (Level of Detail) для тика."""
    
    SLOW_TICK_THRESHOLD_MS = 500
    LOD_ACTIVATION_SAMPLES = 5
    LOD_DEACTIVATION_SAMPLES = 50

    def __init__(self):
        self._tick_history: deque = deque(maxlen=100)
        self._consecutive_slow = 0
        self._consecutive_fast = 0
        self._lod_active = False

    def record_tick(self, duration_ms: float, npc_count: int) -> None:
        self._tick_history.append({'duration': duration_ms, 'npc_count': npc_count})
        
        if duration_ms > self.SLOW_TICK_THRESHOLD_MS:
            self._consecutive_slow += 1
            self._consecutive_fast = 0
            if self._consecutive_slow >= self.LOD_ACTIVATION_SAMPLES and not self._lod_active:
                self._activate_lod()
        else:
            self._consecutive_fast += 1
            self._consecutive_slow = 0
            if self._consecutive_fast >= self.LOD_DEACTIVATION_SAMPLES and self._lod_active:
                self._deactivate_lod()

    def _activate_lod(self) -> None:
        self._lod_active = True
        logger.info("[AdaptiveTickLoader] LOD activated. Distant locations will tick physiology-only.")

    def _deactivate_lod(self) -> None:
        self._lod_active = False
        logger.info("[AdaptiveTickLoader] LOD deactivated. All locations tick fully.")

    def is_lod_active(self) -> bool:
        return self._lod_active

    def should_tick_fully(self, location_id: str, active_location_id: str, connected_locations: Optional[List[str]] = None) -> bool:
        """True если локация должна тикать полностью. False если только физиология."""
        if not self._lod_active:
            return True
        if location_id == active_location_id:
            return True
        if connected_locations and location_id in connected_locations:
            return True
        return False
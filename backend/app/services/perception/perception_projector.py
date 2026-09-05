"""
path: backend/app/services/perception/perception_projector.py
Назначение: UI projection layer. Reads state_t+1, builds perception.
OUTSIDE kernel. Kernel does NOT know perception.
Зависимости: app.services.perception.behavior_manifestation_service,
app.services.perception.phenomenology_projection_service
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PerceptionProjector:
    """Reads state_t+1, builds perception. OUTSIDE kernel.

    Kernel produces state. UI reads state → builds perception.
    This class is called by game_screen / frontend, NOT by tick_orchestrator.
    """

    def __init__(self) -> None:
        from app.services.perception.behavior_manifestation_service import (
            BehaviorManifestationService,
        )
        from app.services.perception.phenomenology_projection_service import (
            PhenomenologyProjectionService,
        )

        self._manifest_svc = BehaviorManifestationService()
        self._project_svc = PhenomenologyProjectionService()

    def project(
        self,
        scene_state: Dict[str, Any],
        all_npcs_raw: List[Any],
        tick: int,
    ) -> Any:
        """Build perception from state_t+1.

        Called AFTER execute() returns. Kernel already committed state.
        """
        try:
            if not scene_state or not all_npcs_raw:
                return None

            # Rule X: Моторные следы строятся строго из физиологии и PerceptualKernel
            _traces = self._manifest_svc.produce_traces(
                scene_state, all_npcs_raw=all_npcs_raw
            )
            _player_perception = self._project_svc.project(
                _traces, scene_state, tick=tick
            )

            return _player_perception
        except Exception as e:
            logger.exception(f"[PERCEPTION_PROJECTOR] CRASHED: {e}")
            return None

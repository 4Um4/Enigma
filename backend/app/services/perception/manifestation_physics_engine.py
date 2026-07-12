from typing import Any, Dict

# backend/app/services/perception/manifestation_physics_engine.py
"""
Файл: backend/app/services/perception/manifestation_physics_engine.py
Назначение: Вычисляет ManifestationState из NPCState (Reality). Детерминированный маппер психика→физика. Необратимое сжатие.
Зависимости: backend.app.domain.manifestation
"""

import logging

from app.domain.manifestation import (
    BodyManifestation,
    BreathingManifestation,
    GazeManifestation,
    HandsManifestation,
    ManifestationState,
    MicroExpressionManifestation,
    MovementManifestation,
    VoiceManifestation,
)

logger = logging.getLogger(__name__)


class ManifestationPhysicsEngine:
    """
    Маппер: Reality (NPCState, BodyState) → ManifestationState (Immutable).
    ЗАПРЕТ: Не читает observer_id, observer_position, environment.
    ЗАПРЕТ: Не читает true_cause. Только детерминированная физика проявлений.
    """

    def manifest(
        self, npc_state: Dict[str, Any], body_state: Dict[str, Any], traversal: Dict[str, Any] = None
    ) -> ManifestationState:
        if not npc_state or not isinstance(npc_state, dict):
            return ManifestationState()

        # 1. Извлекаем физиологию (Reality)
        pain = float(body_state.get("pain", 0.0)) if body_state else 0.0
        fatigue = float(body_state.get("fatigue", 0.0)) if body_state else 0.0
        shock_impulse = (
            float(body_state.get("shock_impulse", 0.0)) if body_state else 0.0
        )
        blood_loss = float(body_state.get("blood_loss", 0.0)) if body_state else 0.0

        # 2. Извлекаем психику (Reality)
        psyche = npc_state.get("psyche", {})
        stress = float(psyche.get("stress", 0.0))

        social_stats = npc_state.get("social_stats", {})
        fear_of_player = float(social_stats.get("fear_of_player", 0.0))

        drives = npc_state.get("drives_base", {})
        fear_drive = float(drives.get("fear", 0.0))

        # Воля и восприятие (Reality)
        personality = npc_state.get("personality", {})
        willpower = float(personality.get("willpower", 50.0)) / 100.0

        pk = npc_state.get("perceptual_kernel", {})
        threat_gradient = (
            float(pk.get("threat_gradient", 0.0)) if isinstance(pk, dict) else 0.0
        )
        aggression_inhibition = (
            float(pk.get("aggression_inhibition", 0.0)) if isinstance(pk, dict) else 0.0
        )

        # 3. Вычисляем ManifestationState (необратимое сжатие)
        return ManifestationState(
            body=self._compute_body(
                pain, shock_impulse, fatigue, stress, threat_gradient, willpower
            ),
            gaze=self._compute_gaze(
                fear_of_player, threat_gradient, aggression_inhibition, traversal
            ),
            voice=self._compute_voice(stress, fear_drive, shock_impulse, pain),
            breathing=self._compute_breathing(stress, pain, fear_drive, traversal),
            movement=self._compute_movement(traversal, fatigue, pain, shock_impulse),
            hands=self._compute_hands(threat_gradient, fear_drive, pain),
            micro_expression=self._compute_micro_expression(
                fear_drive, stress, pain, aggression_inhibition
            ),
        )

    def _compute_body(
        self,
        pain: float,
        shock: float,
        fatigue: float,
        stress: float,
        threat: float,
        will: float,
    ) -> BodyManifestation:
        # muscle_tension: страх, агрессия, решимость
        muscle_tension = min(
            1.0, (threat * 0.5) + (stress / 100.0 * 0.4) + (pain / 100.0 * 0.3)
        )
        muscle_tension *= 1.0 - will * 0.2  # Воля подавляет внешние проявления

        # collapse: усталость, кровопотеря
        collapse = min(1.0, (fatigue / 100.0 * 0.6) + (pain / 100.0 * 0.4))

        # standing_balance: шок и боль снижают
        balance = max(0.0, 1.0 - (shock * 0.8) - (pain / 100.0 * 0.4))

        return BodyManifestation(
            muscle_tension=muscle_tension,
            collapse=collapse,
            standing_balance=balance,
            openness=-threat * 0.5,  # Закрытие от угрозы
            weight_shift=0.0,  # Пока не вычисляем
        )

    def _compute_gaze(
        self, fear: float, threat: float, inhib: float, traversal: Dict[str, Any]
    ) -> GazeManifestation:
        # Избегание зрительного контакта: страх, стыд, подчинение
        avoidance = min(1.0, (fear * 0.5) + (inhib * 0.4))

        # Если двигается, взгляд направлен по движению
        gaze_dir = 0.0
        if traversal and traversal.get("status") == "MOVING":
            gaze_dir = float(traversal.get("target_angle", 0.0))

        return GazeManifestation(
            gaze_direction=gaze_dir,
            head_orientation=gaze_dir,
            fixation_duration=0.0 if avoidance > 0.5 else 1.0,
        )

    def _compute_voice(
        self, stress: float, fear: float, shock: float, pain: float
    ) -> VoiceManifestation:
        tremor = min(1.0, (stress / 100.0 * 0.4) + (fear * 0.3) + (pain / 100.0 * 0.2))
        pitch = 130.0 + (stress / 100.0 * 20.0) + (fear * 30.0)

        return VoiceManifestation(
            tremor=tremor,
            pitch=pitch,
            tempo=120.0 + (stress / 100.0 * 40.0),  # Тахифемия от стресса
            articulation=max(0.2, 1.0 - (shock * 0.5)),
        )

    def _compute_breathing(
        self, stress: float, pain: float, fear: float, traversal: Dict[str, Any]
    ) -> BreathingManifestation:
        rate = 14.0 + (stress / 100.0 * 8.0) + (fear * 6.0)
        if traversal and traversal.get("status") == "MOVING":
            rate += 10.0  # Физическая нагрузка

        irregularity = min(1.0, (pain / 100.0 * 0.5) + (stress / 100.0 * 0.3))

        return BreathingManifestation(
            rate=rate, depth=min(1.0, 0.5 + (rate / 40.0)), irregularity=irregularity
        )

    def _compute_movement(
        self, traversal: Dict[str, Any], fatigue: float, pain: float, shock: float
    ) -> MovementManifestation:
        if not traversal or traversal.get("status") != "MOVING":
            return MovementManifestation()

        speed = float(traversal.get("speed", 0.0))
        coordination = max(
            0.0, 1.0 - (fatigue / 100.0 * 0.4) - (pain / 100.0 * 0.3) - (shock * 0.3)
        )
        tremor = min(1.0, (fatigue / 100.0 * 0.3) + (pain / 100.0 * 0.4))

        return MovementManifestation(
            speed=speed,
            coordination=coordination,
            tremor=tremor,
            precision=coordination,
        )

    def _compute_hands(
        self, threat: float, fear: float, pain: float
    ) -> HandsManifestation:
        grip = min(1.0, (threat * 0.6) + (fear * 0.4))
        fidget = min(1.0, (fear * 0.5) + (pain / 100.0 * 0.2))

        return HandsManifestation(
            grip_strength=grip, fidget_intensity=fidget, gesture_active=False
        )

    def _compute_micro_expression(
        self, fear: float, stress: float, pain: float, inhib: float
    ) -> MicroExpressionManifestation:
        # Микровыражения будут видны только при высоком resolution (PerceptionPhysics)
        return MicroExpressionManifestation(
            jaw_clench=min(1.0, (stress / 100.0 * 0.4) + (inhib * 0.3)),
            pupil_dilation=min(1.0, (fear * 0.6) + (stress / 100.0 * 0.3)),
            brow_position=-min(1.0, (fear * 0.7) + (pain / 100.0 * 0.3)),  # Нахмурен
        )

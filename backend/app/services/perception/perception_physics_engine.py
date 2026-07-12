# backend/app/services/perception/perception_physics_engine.py
"""
Файл: backend/app/services/perception/perception_physics_engine.py
Назначение: Вычисляет ObservationRelation и фильтрует ManifestationState в PerceivedSignal.
Зависимости: backend.app.domain.perception_physics, backend.app.domain.manifestation
"""

import logging
import math
import uuid
from typing import List, Dict, Optional, Any
from app.domain.perception_physics import ObservationRelation, PerceivedSignal
from app.domain.manifestation import ManifestationState

logger = logging.getLogger(__name__)

class PerceptionPhysicsEngine:
    """
    ФАЗА 9.1: Perception Physics Engine.
    Вычисляет ObservationRelation (геометрия, свет, шум) и фильтрует ManifestationState в PerceivedSignal.
    ЗАПРЕТ: Не читает psyche, true_cause, Memory, Inference.
    """
    
    # Пороги видимости (могут быть вынесены в YAML)
    MAX_VISIBILITY_DISTANCE = 20.0  # Метров
    MAX_AUDIBILITY_DISTANCE = 15.0  # Метров
    MIN_RESOLUTION_FOR_MICRO = 0.7  # Для микровыражений
    
    def compute_relation(
        self,
        observer_id: str,
        target_id: str,
        spatial_query: Any,
        scene_state: dict
    ) -> Optional[ObservationRelation]:
        """Вычисляет ObservationRelation для пары observer-target."""
        
        dist = spatial_query.distance(observer_id, target_id)
        if dist >= 999.0:
            return None  # Нет данных о позиции
            
        los = spatial_query.visibility(observer_id, target_id)
        
        env = scene_state.get("environment", {})
        light = float(env.get("light", 0.5))
        noise = float(env.get("noise", 0.2))
        
        # Угол (пока заглушка, можно вычислить из local_position)
        angle = 0.0
        
        return ObservationRelation(
            distance=dist,
            angle=angle,
            light_level=light,
            noise_level=noise,
            is_line_of_sight_clear=los,
            observer_type="humanoid"  # Пока хардкод, будет браться из observer_state
        )
    
    def filter_manifestation(
        self,
        manifest: ManifestationState,
        relation: ObservationRelation,
        target_id: str,
        current_tick: float
    ) -> List[PerceivedSignal]:
        """Фильтрует ManifestationState по ObservationRelation. Возвращает PerceivedSignals."""
        
        signals = []
        
        # Вычисляем базовые параметры видимости
        visibility = self._compute_visibility(relation)
        audibility = self._compute_audibility(relation)
        resolution = self._compute_resolution(relation)
        
        # 1. Body Manifestation (визуальный канал)
        if visibility > 0.1:
            signals.extend(self._filter_body(manifest.body, relation, target_id, current_tick, visibility, resolution))
            signals.extend(self._filter_gaze(manifest.gaze, relation, target_id, current_tick, visibility, resolution))
            signals.extend(self._filter_hands(manifest.hands, relation, target_id, current_tick, visibility, resolution))
            
            # Микровыражения только при высоком resolution
            if resolution >= self.MIN_RESOLUTION_FOR_MICRO:
                signals.extend(self._filter_micro_expression(manifest.micro_expression, relation, target_id, current_tick, visibility, resolution))
        
        # 2. Voice Manifestation (аудио канал)
        if audibility > 0.1:
            signals.extend(self._filter_voice(manifest.voice, relation, target_id, current_tick, audibility))
            signals.extend(self._filter_breathing(manifest.breathing, relation, target_id, current_tick, audibility))
        
        # 3. Movement (визуальный + аудио)
        if visibility > 0.1 or audibility > 0.1:
            signals.extend(self._filter_movement(manifest.movement, relation, target_id, current_tick, visibility, audibility))
        
        return signals
    
    def _compute_visibility(self, relation: ObservationRelation) -> float:
        """Вычисляет коэффициент видимости (0-1) на основе дистанции, света и LOS."""
        if not relation.is_line_of_sight_clear:
            return 0.0
        
        dist_factor = max(0.0, 1.0 - (relation.distance / self.MAX_VISIBILITY_DISTANCE))
        light_factor = 0.1 + (relation.light_level * 0.9)
        
        return dist_factor * light_factor
    
    def _compute_audibility(self, relation: ObservationRelation) -> float:
        """Вычисляет коэффициент слышимости (0-1) на основе дистанции и шума."""
        dist_factor = max(0.0, 1.0 - (relation.distance / self.MAX_AUDIBILITY_DISTANCE))
        noise_factor = 1.0 - (relation.noise_level * 0.8)
        
        return dist_factor * noise_factor
    
    def _compute_resolution(self, relation: ObservationRelation) -> float:
        """Вычисляет разрешение (детализацию) на основе дистанции и света."""
        dist_factor = max(0.1, 1.0 - (relation.distance / 10.0))
        light_factor = 0.2 + (relation.light_level * 0.8)
        
        return dist_factor * light_factor
    
    def _compute_confidence(
        self, base_resolution: float, observer_attention: float, signal_salience: float
    ) -> float:
        """Вычисляет confidence (0-1). Никогда не 1.0."""
        raw = base_resolution * observer_attention * (1.0 - 0.0) * (0.5 + 0.5 * signal_salience)
        return min(0.95, raw)
    
    def _make_signal(
        self, target_id: str, channel: str, field: str, value: Any, confidence: float,
        tick: float, relation: ObservationRelation, via: str
    ) -> PerceivedSignal:
        return PerceivedSignal(
            signal_id=str(uuid.uuid4()),
            target_id=target_id,
            channel=channel,
            field=field,
            perceived_value=value,
            confidence=confidence,
            perceived_at=tick,
            perceived_via=(via,),
            distance=relation.distance,
            lighting=relation.light_level,
            distortions={}
        )

    # --- Фильтрация каналов ---
    
    def _filter_body(
        self, body: Any, relation: ObservationRelation, target_id: str, tick: float,
        visibility: float, resolution: float
    ) -> List[PerceivedSignal]:
        signals = []
        if body.muscle_tension > 0.1:
            conf = self._compute_confidence(visibility, 0.8, body.muscle_tension)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "body_manifestation", "muscle_tension", body.muscle_tension, conf, tick, relation, "visual"))
        
        if body.collapse > 0.1 and resolution > 0.4:
            conf = self._compute_confidence(visibility, resolution, body.collapse)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "body_manifestation", "collapse", body.collapse, conf, tick, relation, "visual"))
        
        if body.standing_balance < 0.9 and resolution > 0.5:
            conf = self._compute_confidence(visibility, resolution, 1.0 - body.standing_balance)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "body_manifestation", "standing_balance", body.standing_balance, conf, tick, relation, "visual"))
        
        return signals
    
    def _filter_gaze(
        self, gaze: Any, relation: ObservationRelation, target_id: str, tick: float,
        visibility: float, resolution: float
    ) -> List[PerceivedSignal]:
        signals = []
        if resolution > 0.3:
            conf = self._compute_confidence(visibility, resolution, 0.7)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "gaze", "gaze_direction", gaze.gaze_direction, conf, tick, relation, "visual"))
                signals.append(self._make_signal(target_id, "gaze", "head_orientation", gaze.head_orientation, conf, tick, relation, "visual"))
        return signals
    
    def _filter_hands(
        self, hands: Any, relation: ObservationRelation, target_id: str, tick: float,
        visibility: float, resolution: float
    ) -> List[PerceivedSignal]:
        signals = []
        if resolution > 0.4:
            conf = self._compute_confidence(visibility, resolution, 0.9)
            if conf > 0.2:
                if hands.held_object_left:
                    signals.append(self._make_signal(target_id, "hands", "held_object_left", hands.held_object_left, conf, tick, relation, "visual"))
                if hands.held_object_right:
                    signals.append(self._make_signal(target_id, "hands", "held_object_right", hands.held_object_right, conf, tick, relation, "visual"))
        
        if hands.grip_strength > 0.1 and resolution > 0.5:
            conf = self._compute_confidence(visibility, resolution, hands.grip_strength)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "hands", "grip_strength", hands.grip_strength, conf, tick, relation, "visual"))
        return signals
    
    def _filter_micro_expression(
        self, micro: Any, relation: ObservationRelation, target_id: str, tick: float,
        visibility: float, resolution: float
    ) -> List[PerceivedSignal]:
        signals = []
        if micro.jaw_clench > 0.1:
            conf = self._compute_confidence(visibility, resolution, micro.jaw_clench)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "micro_expression", "jaw_clench", micro.jaw_clench, conf, tick, relation, "visual"))
        
        if micro.pupil_dilation > 0.1:
            conf = self._compute_confidence(visibility, resolution, micro.pupil_dilation)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "micro_expression", "pupil_dilation", micro.pupil_dilation, conf, tick, relation, "visual"))
        
        if abs(micro.brow_position) > 0.1:
            conf = self._compute_confidence(visibility, resolution, abs(micro.brow_position))
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "micro_expression", "brow_position", micro.brow_position, conf, tick, relation, "visual"))
        return signals
    
    def _filter_voice(
        self, voice: Any, relation: ObservationRelation, target_id: str, tick: float,
        audibility: float
    ) -> List[PerceivedSignal]:
        signals = []
        if voice.tremor > 0.1:
            conf = self._compute_confidence(audibility, 1.0, voice.tremor)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "voice_manifestation", "tremor", voice.tremor, conf, tick, relation, "auditory"))
        
        conf_pitch = self._compute_confidence(audibility, 1.0, 0.5)
        if conf_pitch > 0.2:
            signals.append(self._make_signal(target_id, "voice_manifestation", "pitch", voice.pitch, conf_pitch, tick, relation, "auditory"))
            signals.append(self._make_signal(target_id, "voice_manifestation", "tempo", voice.tempo, conf_pitch, tick, relation, "auditory"))
            signals.append(self._make_signal(target_id, "voice_manifestation", "loudness", voice.loudness, conf_pitch, tick, relation, "auditory"))
        return signals
    
    def _filter_breathing(
        self, breathing: Any, relation: ObservationRelation, target_id: str, tick: float,
        audibility: float
    ) -> List[PerceivedSignal]:
        signals = []
        if breathing.rate > 16.0:
            conf = self._compute_confidence(audibility, 1.0, (breathing.rate - 16.0) / 10.0)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "breathing", "rate", breathing.rate, conf, tick, relation, "auditory"))
        
        if breathing.irregularity > 0.1:
            conf = self._compute_confidence(audibility, 1.0, breathing.irregularity)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "breathing", "irregularity", breathing.irregularity, conf, tick, relation, "auditory"))
        return signals
    
    def _filter_movement(
        self, movement: Any, relation: ObservationRelation, target_id: str, tick: float,
        visibility: float, audibility: float
    ) -> List[PerceivedSignal]:
        signals = []
        if movement.speed > 0.1:
            # Шаги можно услышать
            if audibility > 0.1:
                conf = self._compute_confidence(audibility, 1.0, movement.speed / 2.0)
                if conf > 0.2:
                    signals.append(self._make_signal(target_id, "movement", "speed", movement.speed, conf, tick, relation, "auditory"))
            # Движение можно увидеть
            if visibility > 0.1:
                conf = self._compute_confidence(visibility, 0.8, movement.speed / 2.0)
                if conf > 0.2:
                    signals.append(self._make_signal(target_id, "movement", "speed", movement.speed, conf, tick, relation, "visual"))
        
        if movement.tremor > 0.1 and visibility > 0.1:
            conf = self._compute_confidence(visibility, 0.8, movement.tremor)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "movement", "tremor", movement.tremor, conf, tick, relation, "visual"))
        
        if movement.coordination < 0.9 and visibility > 0.1:
            conf = self._compute_confidence(visibility, 0.8, 1.0 - movement.coordination)
            if conf > 0.2:
                signals.append(self._make_signal(target_id, "movement", "coordination", movement.coordination, conf, tick, relation, "visual"))
        return signals
"""
Файл: frontend/perceptual_momentum.py
Назначение: Инерция, S-кривая сборки реальности и контролируемый стохастический дрейф.
Зависимости: presentation_firewall

TODO: 
- В будущем может потребоваться более сложная модель, учитывающая индивидуальные особенности NPC, контекст ситуации и динамические изменения в восприятии игрока. Но для MVP достаточно базовой инерции с S-кривой и контролируемой вариацией.
"""

import math
import random
from dataclasses import dataclass
from typing import Tuple
from presentation_firewall import SanitizedPerceptualVectors

def _clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(max_val, val))

@dataclass
class ManifestationProfile:
    """Строго математические векторы оптической деформации для рендера."""
    visual_instability: float = 0.0       # Тремор, хроматическая аберрация
    auditory_distortion: float = 0.0      # Глушение, звон (для будущей аудиосистемы)
    motor_disruption: float = 0.0         # Искажение отклика мыши/клавиш
    contrast_instability: float = 0.0     # Пульсация контраста (мир "дышит")
    attention_tunneling: float = 0.0      # Виньетка, сужение фокуса
    motion_bias: Tuple[float, float] = (0.0, 0.0) # Вектор визуального сноса
    temporal_distortion: float = 0.0      # Лаг рендера, "размазывание" кадров
    temporal_assembly_delay: float = 0.0  # Задержка подтверждения реальности (PerceptualLatency)
    blood_visibility: float = 0.0         # Инерция кровавой виньетки


class PerceptualMomentum:
    """Темпоральная инерция восприятия. 
    Предотвращает мгновенное вкл/выкл эффектов, реализует S-curve и гистерезис.
    """
    def __init__(self):
        self.current = ManifestationProfile()

    def _apply_controlled_stochasticity(self, base_value: float, noise_level: float) -> float:
        """Ограниченная перцептивная вариация. Не случайность, а дрейф."""
        if noise_level <= 0:
            return base_value
        variance = (random.random() - 0.5) * noise_level * 0.2
        return _clamp(base_value + variance)

    def _map_vectors_to_target(self, vectors: SanitizedPerceptualVectors) -> ManifestationProfile:
        """Маппинг санитизированных векторов в профиль деформации (Shader Law)."""
        noise = vectors.sensory_noise
        
        return ManifestationProfile(
            visual_instability=self._apply_controlled_stochasticity(vectors.visual_instability, noise),
            motor_disruption=self._apply_controlled_stochasticity(vectors.motor_disruption, noise * 0.5),
            contrast_instability=self._apply_controlled_stochasticity(vectors.sensory_noise, noise),
            attention_tunneling=vectors.attention_tunneling,
            motion_bias=vectors.directional_pressure,
            temporal_distortion=vectors.temporal_distortion,
            temporal_assembly_delay=vectors.perceptual_latency,
            blood_visibility=vectors.blood_visibility # Кровь появляется быстро, сходит медленно
        )

    def _smoothstep(self, t: float) -> float:
        """S-curve (Sigmoid-like) для плавных переходов."""
        t = _clamp(t, 0.0, 1.0)
        return t * t * (3 - 2 * t)

    def _lerp_with_momentum(
        self, 
        current: float, 
        target: float, 
        dt: float, 
        reconciliation_rate: float,
        degrade_speed: float = 4.0,
        recover_base_speed: float = 1.0
    ) -> float:
        """Асимметричная интерполяция с S-кривой.
        Деградация быстрая, восстановление медленное (определяется reconciliation_rate).
        """
        if target > current:
            # Срыв в деградацию: резкий, лавинообразный
            speed = degrade_speed
        else:
            # Восстановление: медленное, зависит от воли/усталости
            speed = recover_base_speed * max(0.05, reconciliation_rate)

        # Вычисляем шаг интерполяции
        t = min(1.0, speed * dt)
        # Применяем S-кривую к шагу для устранения линейности
        t = self._smoothstep(t)

        return current + (target - current) * t

    def update(self, delta_seconds: float, vectors: SanitizedPerceptualVectors) -> None:
        """Обновляет текущий профиль деформации с учётом инерции и S-кривой."""
        target = self._map_vectors_to_target(vectors)
        recon_rate = vectors.reality_reconciliation_rate

        self.current.visual_instability = self._lerp_with_momentum(
            self.current.visual_instability, target.visual_instability, delta_seconds, recon_rate)
        
        self.current.attention_tunneling = self._lerp_with_momentum(
            self.current.attention_tunneling, target.attention_tunneling, delta_seconds, recon_rate)
            
        self.current.temporal_distortion = self._lerp_with_momentum(
            self.current.temporal_distortion, target.temporal_distortion, delta_seconds, recon_rate)
            
        self.current.temporal_assembly_delay = self._lerp_with_momentum(
            self.current.temporal_assembly_delay, target.temporal_assembly_delay, delta_seconds, recon_rate)

        self.current.motor_disruption = self._lerp_with_momentum(
            self.current.motor_disruption, target.motor_disruption, delta_seconds, recon_rate)

        self.current.contrast_instability = self._lerp_with_momentum(
            self.current.contrast_instability, target.contrast_instability, delta_seconds, recon_rate)

        # Кровь появляется быстро (degrade_speed=8.0), но медленно исчезает (через reconciliation_rate)
        self.current.blood_visibility = self._lerp_with_momentum(
            self.current.blood_visibility, target.blood_visibility, delta_seconds, recon_rate, degrade_speed=8.0, recover_base_speed=0.3)
            
        # Моторный и визуальный снос интерполируем напрямую (векторы)
        self.current.motion_bias = (
            self._lerp_with_momentum(self.current.motion_bias[0], target.motion_bias[0], delta_seconds, recon_rate),
            self._lerp_with_momentum(self.current.motion_bias[1], target.motion_bias[1], delta_seconds, recon_rate)
        )
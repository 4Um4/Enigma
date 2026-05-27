"""
Файл: frontend/presentation_firewall.py
Назначение: Повреждённая сетчатка. Очищает входящие DTO от семантики, категорий и спайков. Преобразует в строго ограниченные скаляры.
Зависимости: Нет (чистая функция)

TODO:
- В будущем может включать в себя более сложные алгоритмы фильтрации, например, машинное обучение для выявления аномалий в данных от бэкенда, если потребуется.
"""

from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass
class SanitizedPerceptualVectors:
    """Строго математические векторы оптической деформации. Никаких строк и енумов."""
    blood_visibility: float = 0.0
    visual_instability: float = 0.0       # Тремор, хроматическая аберрация
    attention_tunneling: float = 0.0      # Виньетка, сужение фокуса
    temporal_distortion: float = 0.0      # Лаг рендера, "размазывание" кадров
    perceptual_latency: float = 0.0       # Задержка сборки реальности
    reality_reconciliation_rate: float = 1.0 # Скорость возврата в норму
    sensory_noise: float = 0.0            # ADR-084: Визуальный шум от конфликта воли (дрожь, артефакты)
    motor_disruption: float = 0.0          # ADR-084: Моторный тремор (камера, курсор) от Воли или Шока
    
    # Средовые векторы (заглушка до интеграции AmbientPhenomenologyDTO)
    emotional_temperature: float = 0.0    # -1.0 (лед) до 1.0 (жар)
    proximity_compression: float = 0.0    # 0.0-1.0, давление пространства
    directional_pressure: Tuple[float, float] = (0.0, 0.0) # Вектор сноса внимания

def _clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(max_val, val))

def sanitize_perceptual_input(
    avatar_state: Optional[dict], 
    ambient_state: Optional[dict] = None
) -> SanitizedPerceptualVectors:
    """
    Presentation Firewall.
    Транслирует сырые DTO в непрерывные векторы деформации.
    Блокирует протечку категорий (mental_state, physical_state) в оптический слой.
    """
    if not avatar_state:
        return SanitizedPerceptualVectors()

    # Извлечение феноменологических скаляров
    stability = float(avatar_state.get("perceptual_stability", 1.0))
    coherence = float(avatar_state.get("cognitive_coherence", 1.0))
    noise = float(avatar_state.get("sensory_noise", 0.0))
    latency = float(avatar_state.get("perceptual_latency", 0.0))
    recon_rate = float(avatar_state.get("reality_reconciliation_rate", 1.0))
    blood = float(avatar_state.get("blood_visibility", 0.0))
    motor = float(avatar_state.get("motor_disruption", 0.0)) # ADR-084: Тремор от Воли

    # Firewall: Жёсткое ограничение диапазонов
    vectors = SanitizedPerceptualVectors(
        blood_visibility=_clamp(blood),
        visual_instability=_clamp(1.0 - stability),
        attention_tunneling=_clamp(1.0 - coherence),
        temporal_distortion=_clamp(1.0 - coherence + latency),
        perceptual_latency=_clamp(latency),
        reality_reconciliation_rate=_clamp(recon_rate),
        sensory_noise=_clamp(noise), # ADR-084: Проброс шума конфликта воли
        motor_disruption=_clamp(motor), # ADR-084: Проброс моторного тремора
    )

    # Средовая обработка (AmbientPhenomenologyDTO)
    if ambient_state:
        vectors.emotional_temperature = _clamp(float(ambient_state.get("emotional_temperature", 0.0)), -1.0, 1.0)
        vectors.proximity_compression = _clamp(float(ambient_state.get("proximity_compression", 0.0)))
        dpb = ambient_state.get("directional_pressure_bias", (0.0, 0.0))
        if isinstance(dpb, (list, tuple)) and len(dpb) == 2:
            vectors.directional_pressure = (_clamp(float(dpb[0]), -1.0, 1.0), _clamp(float(dpb[1]), -1.0, 1.0))

    return vectors
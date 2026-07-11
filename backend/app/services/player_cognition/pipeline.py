"""
app/services/player_cognition/pipeline.py
Orchestrator — собирает PerceivedScene прогоном через весь pipeline.

Порядок (строгий):
    SceneState
        → Spatial Layer
        → Perception Layer
        → Attention Layer
        → Recognition Layer
        → Interpretation Layer
        → Cognitive Distortion
        → Memory Layer
        → Uncertainty Layer
        → PerceivedScene

path: /backend/app/services/player_cognition/pipeline.py
Назначение: Главная точка входа — прогоняет SceneState через все слои в утверждённом порядке, возвращает PerceivedScene
Зависимости: все слои, types
Основные сущности: PerceptionConfig, build_perceived_scene()
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app.services.player_cognition.types import (
    PerceivedEnvironment,
    PerceivedScene,
)
from app.services.player_cognition.spatial_layer import extract_spatial_data
from app.services.player_cognition.perception_layer import apply_perception
from app.services.player_cognition.attention_layer import PlayerFocus, apply_attention
from app.services.player_cognition.recognition_layer import EncounterHistory, apply_recognition
from app.services.player_cognition.interpretation_layer import apply_interpretation
from app.services.player_cognition.cognitive_distortion import (
    PlayerDistortionInputs,
    apply_cognitive_distortion,
)
from app.services.player_cognition.memory_layer import PlayerMemory, apply_memory
from app.services.player_cognition.uncertainty_layer import apply_uncertainty


@dataclass
class PerceptionConfig:
    """Конфигурация одного вызова pipeline — абстрагирует источники данных"""
    player_focus: PlayerFocus = field(default_factory=PlayerFocus)
    player_stress: float = 0.0
    player_hp: int = 100
    player_max_hp: int = 100
    player_fatigue: float = 0.0
    encounter_history: Optional[EncounterHistory] = None
    player_memory: Optional[PlayerMemory] = None


def _build_perceived_environment(scene_state: dict, distortion_inputs: PlayerDistortionInputs) -> PerceivedEnvironment:
    """
    Заполняет воспринимаемое окружение на основе objective environment + искажения.
    Стресс делает мир темнее и шумнее.
    """
    env = scene_state.get("environment", {})
    modifiers = scene_state.get("environment_modifiers", {})

    light_raw = env.get("light_level", "normal")
    noise_raw = env.get("noise_level", "moderate")
    weather = env.get("weather_inside", "")

    # Искажение от стресса
    stress = distortion_inputs.stress
    if stress > 60.0:
        # Высокий стресс — мир кажется темнее
        if light_raw == "bright":
            light_perceived = "приглушённо"
        else:
            light_perceived = "темно"
        # Шум кажется громче
        noise_perceived = "оглушительно"
    elif stress > 30.0:
        light_perceived = "приглушённо" if light_raw == "bright" else light_raw
        noise_perceived = "шумно"
    else:
        light_perceived = light_raw
        noise_perceived = noise_raw

    # Температура и запах — из weather
    temp = ""
    smell = ""
    if "warm" in weather:
        temp = "жарко"
    elif "cold" in weather:
        temp = "холодно"
    if "busy" in weather and stress < 50.0:
        smell = "запах еды и напитков"

    return PerceivedEnvironment(
        light_perceived=light_perceived,
        noise_perceived=noise_perceived,
        temperature_perceived=temp,
        smell_perceived=smell,
    )


def _build_body_state(distortion_inputs: PlayerDistortionInputs) -> List[str]:
    """
    Генерирует телесные ощущения на основе состояния игрока.
    "ты тяжело дышишь", "рука болит" — мягкие подсказки вместо HP барa.
    """
    states: List[str] = []

    stress = distortion_inputs.stress
    hp_ratio = distortion_inputs.effective_hp / max(1, distortion_inputs.effective_max_hp)
    fatigue = distortion_inputs.fatigue

    # HP → телесные ощущения
    if hp_ratio < 0.2:
        states.append("ты еле стоишь на ногах")
    elif hp_ratio < 0.4:
        states.append("боль мешает двигаться")
    elif hp_ratio < 0.6:
        states.append("ты прихрамываешь")

    # Stress → физиология
    if stress > 70.0:
        states.append("сердце колотится")
    elif stress > 50.0:
        states.append("ты тяжело дышишь")
    elif stress > 30.0:
        states.append("потоет ладони")

    # Fatigue → общее состояние
    if fatigue > 70.0:
        states.append("глаза слипаются")
    elif fatigue > 50.0:
        states.append("веет усталостью")

    return states


def build_perceived_scene(
    scene_state: dict,
    config: Optional[PerceptionConfig] = None,
) -> PerceivedScene:
    """
    Главная точка входа pipeline.
    Принимает объективный SceneState, возвращает PerceivedScene для UI.

    Args:
        scene_state: полный словарь из SceneStateManager.get_scene_state()
        config: параметры игрока (фокус, стресс, HP). Если None — дефолтные.

    Returns:
        PerceivedScene — только то, что персонаж воспринимает.
    """
    if config is None:
        config = PerceptionConfig()

    if config.encounter_history is None:
        config.encounter_history = EncounterHistory()
    if config.player_memory is None:
        config.player_memory = PlayerMemory()

    location_id = scene_state.get("location_id", "unknown")

    # === 1. Spatial Layer ===
    entities = extract_spatial_data(scene_state)

    # === 2. Perception Layer ===
    audio_events = apply_perception(entities, scene_state)

    # === 3. Attention Layer ===
    entities = apply_attention(entities, config.player_focus, config.player_stress)

    # === 4. Recognition Layer ===
    apply_recognition(entities, config.encounter_history)

    # === 5. Interpretation Layer ===
    apply_interpretation(entities)

    # === 6. Cognitive Distortion ===
    distortion_inputs = PlayerDistortionInputs(
        stress=config.player_stress,
        hp=config.player_hp,
        max_hp=config.player_max_hp,
        fatigue=config.player_fatigue,
    )
    apply_cognitive_distortion(entities, distortion_inputs)

    # === 7. Memory Layer ===
    apply_memory(entities, config.player_memory)

    # === 8. Uncertainty Layer ===
    apply_uncertainty(entities)

    # === 9. Сборка PerceivedScene ===
    environment = _build_perceived_environment(scene_state, distortion_inputs)
    body_state = _build_body_state(distortion_inputs)

    # Обновляем память из текущего восприятия (после всех слоёв)
    config.player_memory.update_from_perception(entities)

    return PerceivedScene(
        location_id=location_id,
        entities=entities,
        audio_events=audio_events,
        environment=environment,
        attention_focus_id=config.player_focus.focus_entity_id,
        player_body_state=body_state,
    )
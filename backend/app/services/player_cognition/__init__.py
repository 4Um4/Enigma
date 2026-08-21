"""
app/services/player_cognition/
Система восприятия игрока — проекция сознания персонажа на UI.

path: backend/app/services/player_cognition/__init__.py
Назначение: Пакет системы восприятия игрока — проекция сознания персонажа на UI
Зависимости: typing, dataclasses (только стандартная библиотека)
Основные сущности: Inference, PerceivedEntity, AudioEvent, PerceivedEnvironment, PerceivedScene

Pipeline:
    SceneState (объективный мир)
    Spatial Layer: LOS, distance, sound physics
    Perception Layer: видит/слышит/не видит
    Attention Layer: на что СМОТРИТ / что игнорирует
    Recognition Layer: кто это?
    Interpretation Layer: что это ЗНАЧИТ?
    Cognitive Distortion: искажение
    Memory Layer: сохранение + деградация
    Uncertainty Layer: уверенность/сомнение
    PerceivedScene: UI
"""

from app.services.player_cognition.attention_layer import PlayerFocus, apply_attention
from app.services.player_cognition.cognitive_distortion import (
    PlayerDistortionInputs,
    apply_cognitive_distortion,
)
from app.services.player_cognition.interpretation_layer import apply_interpretation
from app.services.player_cognition.memory_layer import PlayerMemory, apply_memory
from app.services.player_cognition.perception_layer import apply_perception
from app.services.player_cognition.pipeline import (
    PerceptionConfig,
    build_perceived_scene,
)
from app.services.player_cognition.recognition_layer import (
    EncounterHistory,
    apply_recognition,
)
from app.services.player_cognition.spatial_layer import extract_spatial_data
from app.services.player_cognition.types import (
    AudioEvent,
    Inference,
    PerceivedEntity,
    PerceivedEnvironment,
    PerceivedScene,
)
from app.services.player_cognition.action_semantic_resolver import ActionSemanticResolver
from app.services.player_cognition.uncertainty_layer import apply_uncertainty

__all__ = [
    "ActionSemanticResolver",
    "Inference",
    "PerceivedEntity",
    "AudioEvent",
    "PerceivedEnvironment",
    "PerceivedScene",
    "extract_spatial_data",
    "apply_perception",
    "PlayerFocus",
    "apply_attention",
    "EncounterHistory",
    "apply_recognition",
    "apply_interpretation",
    "PlayerDistortionInputs",
    "apply_cognitive_distortion",
    "PlayerMemory",
    "apply_memory",
    "apply_uncertainty",
    "PerceptionConfig",
    "build_perceived_scene",
]

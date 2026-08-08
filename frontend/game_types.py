"""
path: /frontend/game_types.py
Назначение: Frontend-локальные DTO для рендера восприятия. Копия backend-типов без импорта app.services — удовлетворяет Закон 1.1
Зависимости: dataclasses, enum, typing (только stdlib)
Основные сущности: InferenceTier, Inference, PerceivedEntity, AudioEvent, PerceivedEnvironment, PerceivedScene

TODO: В будущем можно расширить PerceivedEntity для поддержки разных типов (NPC, объекты, события) и добавить сырые данные для отладки. Сейчас упрощённая версия для базового рендера.
TODO: Внедрить в рендеринг HUD и мира, заменить сырые данные из SceneState на эти структуры для изоляции слоя.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Literal, Optional


class InferenceTier(Enum):
    """Уровень интерпретации — чем выше, тем сложнее вывод"""

    PHYSICAL = auto()  # Tier 1: "рука движется быстро" → "возможен удар"
    BEHAVIORAL = auto()  # Tier 2: "intent=attack + distance<1.5" → "агрессия"


@dataclass
class Inference:
    """Один вывод интерпретационного слоя"""

    inference_type: str
    tier: InferenceTier
    confidence: float
    source_observations: List[str] = field(default_factory=list)


@dataclass
class PerceivedEntity:
    """
    Одна воспринятая сущность — фронтенд-копия backend-типа.
    Структура идентична backend/app/services/player_cognition/types.py:PerceivedEntity
    для совместимости через duck typing при рендере.
    """

    entity_id: str

    # --- что это ---
    entity_type: Literal["npc", "object", "event"] = "object"

    # --- Spatial Layer ---
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0  # S133: Высота прыжка (проекция от backend Execution Kernel)
    body_heading: float = 1.5708  # NEW-ORIENT-003 FIX: Ориентация тела (рад)
    head_yaw: float = 0.0  # NEW-ORIENT-003 FIX: Ориентация головы (offset от body_heading, [-pi, pi])
    distance: float = 999.0
    los: bool = False
    los_blocked_by: Optional[str] = None
    body_heading: float = 1.5708  # ADR-O-315: Угол ориентации тела (рад). Pi/2 = Юг.

    # --- Perception Layer ---
    visible: bool = False
    audible: bool = False
    clarity: float = 0.0
    audio_only: bool = False

    # --- Attention Layer ---
    in_attention: bool = False
    attention_score: float = 0.0

    # --- Recognition Layer ---
    display_name: str = ""
    recognition_confidence: float = 0.0
    activity: str = "idle"  # S163: Для отрисовки Action Markers

    # --- Manifestation Layer (S168: VisualDTO) ---
    pose_tense: float = 0.0
    pose_tremor: float = 0.0
    gaze_avoidance: float = 0.0
    blur_intensity: float = 0.0
    # S176: Тип доставки реплики (NORMAL, SHOUT, WHISPER) для Visual Casting
    delivery_type: str = "NORMAL"
    current_expression: str = "neutral"  # S172: Visual Casting System (tense, shouting, etc.)

    # --- Traversal Layer (Спринт 30: Dual-Time Ontology) ---
    # Бэкенд компрессирует время, фронтенд разархивирует его непрерывным движением
    traversal_status: str = "IDLE"  # PENDING, MOVING, ARRIVED, CANCELLED
    path_waypoints: list = field(default_factory=list)  # Визуальные x,y точки
    current_waypoint_idx: int = 0
    traversal_progress: float = 0.0  # 0.0 - 1.0 прогресс между текущими waypoint
    traversal_speed: float = 1.5  # Скорость визуальной интерполяции (м/с)
    # S90.4: ETKE-IK VelocityRenderer fields
    velocity: tuple = (0.0, 0.0)
    exertion_level: float = 0.0

    # --- Embodied Trace Layer (The Fool v2: Моторные следы) ---
    is_frozen: bool = False
    is_shaking: bool = False
    instability: float = 0.0
    perception_cues: list = field(default_factory=list)  # Словари {cue_key: str}

    # --- Cognitive Layer (Спринт 30: Визуализация Cognitive Freeze) ---
    initiative_suppression: float = 0.0  # 0.0-1.0, паралич воли

    # --- Interpretation Layer ---
    observations: List[str] = field(default_factory=list)
    inferences: List[Inference] = field(default_factory=list)

    # --- Cognitive Distortion ---
    threat_bias: float = 0.0
    trust_bias: float = 0.0
    salience_bias: float = 0.0

    # --- Memory Layer ---
    memory_tag: Literal["new", "known", "familiar", "forgotten"] = "new"
    memory_decay: float = 1.0

    # --- Uncertainty Layer ---
    final_confidence: float = 0.0

    # --- сырые данные из SceneState (для отладки, не для UI) ---
    _raw_data: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class AudioEvent:
    """Звуковое событие без визуального источника"""

    description: str
    direction: Optional[str] = None
    approximate_distance: float = 999.0
    confidence: float = 0.5


@dataclass
class PerceivedEnvironment:
    """Воспринимаемое окружение — то, что чувствует персонаж"""

    light_perceived: str = "normal"
    noise_perceived: str = "normal"
    temperature_perceived: str = ""
    smell_perceived: str = ""
    crowding_perceived: str = ""


@dataclass
class PerceivedScene:
    """
    Финальный результат pipeline — то, что получает UI.
    Фронтенд-копия backend-типа для изоляции слоя (Закон 1.1).
    """

    location_id: str
    entities: List[PerceivedEntity] = field(default_factory=list)
    audio_events: List[AudioEvent] = field(default_factory=list)
    environment: PerceivedEnvironment = field(default_factory=PerceivedEnvironment)
    attention_focus_id: Optional[str] = None
    player_body_state: List[str] = field(default_factory=list)


# ============================================================================
# State-типы для pipeline — фронтенд создаёт, бэкенд обрабатывает через duck typing
# ============================================================================


class MemoryTier(Enum):
    """Уровень памяти о сущности"""

    SHORT = auto()  # текущий ход — нет decay
    MEDIUM = auto()  # последние 5-10 ходов — медленный decay
    LONG = auto()  # прошлые сессии — быстрый decay


@dataclass
class MemoryEntry:
    """Одна запись в памяти о сущности"""

    entity_id: str
    entity_type: str
    display_name: str
    last_seen_time: float
    encounter_count: int = 0
    last_clarity: float = 0.0
    key_observations: List[str] = field(default_factory=list)


@dataclass
class PlayerFocus:
    """Текущий фокус внимания игрока — управляется гибридно"""

    focus_entity_id: Optional[str] = None
    focus_direction: tuple = (0.0, -1.0)
    focus_zone_radius: float = 1.5


@dataclass
class PerceptionConfig:
    """Конфигурация одного вызова pipeline — абстрагирует источники данных"""

    player_focus: PlayerFocus = field(default_factory=PlayerFocus)
    player_stress: float = 0.0
    player_hp: int = 100
    player_max_hp: int = 100
    player_fatigue: float = 0.0

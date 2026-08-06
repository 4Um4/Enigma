"""
path: /project/backend/app/domain/presentation.py
Назначение: Контракты для трёхканальной презентации (Visual, Audible).
Зависимости: dataclasses, typing
Основные сущности: NPCVisualState, VisualDTO, AudibleDTO
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class NeedSeverity(Enum):
    """Уровень критичности потребности для UI (без локализации)."""
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"
    EXTREME = "extreme"


@dataclass(frozen=True)
class NeedStatusDTO:
    """S151: DTO состояния потребности (только данные, без текста и цвета)."""
    id: str
    severity: NeedSeverity


@dataclass(frozen=True)
class EmbodiedStatusDTO:
    """S151: Воплощённое состояние аватара для UI."""
    gold: float
    food_count: float
    current_weight: float
    max_weight: float
    active_needs: List[NeedStatusDTO]

@dataclass(frozen=True)
class PoseOverlay:
    """Визуальная поза NPC."""
    tense_contour: float = 0.0
    frozen_overlay: float = 0.0
    tremor_animation: float = 0.0
    collapse_posture: float = 0.0

@dataclass(frozen=True)
class GazeArrow:
    """Направление взгляда NPC."""
    target_id: Optional[str] = None
    avoidance: float = 0.0

@dataclass(frozen=True)
class NPCVisualState:
    """Визуальное состояние одного NPC для рендера."""
    npc_id: str
    display_name: str = "Незнакомец"
    name_certainty: float = 0.0
    pose_overlay: PoseOverlay = field(default_factory=PoseOverlay)
    gaze_arrow: Optional[GazeArrow] = None
    activity_badge: Optional[str] = None
    blur_intensity: float = 0.0
    noise_intensity: float = 0.0

@dataclass(frozen=True)
class VisualDTO:
    """Канал визуальной презентации."""
    npcs: Tuple[NPCVisualState, ...] = ()

@dataclass(frozen=True)
class VoiceAudio:
    """Аудио параметры голоса NPC."""
    npc_id: str
    tempo: float = 120.0
    pitch: float = 130.0
    loudness: float = 55.0
    tremor: float = 0.0

@dataclass(frozen=True)
class BreathingAudio:
    """Аудио параметры дыхания NPC."""
    npc_id: str
    rate: float = 14.0
    depth: float = 0.5
    irregularity: float = 0.0

@dataclass(frozen=True)
class AudibleDTO:
    """Канал аудио презентации."""
    voices: Tuple[VoiceAudio, ...] = ()
    breathing_sounds: Tuple[BreathingAudio, ...] = ()


@dataclass(frozen=True)
class PerceivedManifestationDTO:
    """Наблюдаемое проявление NPC (без эмоций)."""
    channel: str          # "voice", "body", "gaze"
    description: str      # "голос дрожит", "избегает взгляда"
    intensity: float      # 0.0 - 1.0 (сила проявления)
    confidence: float     # 0.0 - 1.0 (уверенность игрока в том, что он это увидел)


@dataclass(frozen=True)
class PerceivedNarrativeDTO:
    """Атом восприятия. Событие, прошедшее через фильтр игрока."""
    event_id: str         # UUID для связи с блокнотом/гипотезами
    speaker_id: Optional[str] = None
    visible_text: str = ""     # Текст, который игрок реально услышал
    perception_source: str = "PLAYER_HEARD" # PLAYER_HEARD, PLAYER_SAW, NPC_REPORT, INTERNAL_ACCESS, INFERRED
    perception_certainty: float = 1.0  # 0.0 - 1.0 (уверенность в факте события)
    auditory_clarity: float = 1.0      # 0.0 - 1.0 (насколько чётко услышан текст)
    recognition: str = "KNOWN_NAME"    # KNOWN_NAME, STRANGE_FACE, UNKNOWN_MALE
    delivery_type: str = "NORMAL"      # NORMAL, WHISPER, SHOUT
    manifestations: Tuple[PerceivedManifestationDTO, ...] = ()
    attention_weight: float = 0.5      # Насколько это должно всплыть в UI (хлебные крошки)
    lifetime: str = "TRANSIENT"        # TRANSIENT, PINNED, SLAM


@dataclass(frozen=True)
class AvatarPerceptionProfile:
    """S159: Профиль восприятия аватара. Изолирует Projector от всей психики."""
    perceptual_stability: float = 1.0  # 0.0-1.0


@dataclass(frozen=True)
class PerceptionContext:
    """S159: Изолированный контекст восприятия. Projector не читает scene_state напрямую."""
    player_position: Tuple[float, float]
    speaker_positions: Dict[str, Tuple[float, float]]
    avatar_profile: AvatarPerceptionProfile = field(default_factory=AvatarPerceptionProfile)
    lighting: float = 1.0  # Заглушка для будущего (0.0 - темнота, 1.0 - день)
    occlusion: float = 0.0 # Заглушка для будущего (0.0 - нет стен, 1.0 - глухая стена)
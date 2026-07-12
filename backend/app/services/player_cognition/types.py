"""
app/services/player_cognition/types.py
Типы-контракты системы восприятия игрока.

path: /backend/app/services/player_cognition/types.py
Назначение: Типы-контракты pipeline — каждый слой обогащает эти структуры
Зависимости: typing, dataclasses, enum (только стандартная библиотека)
Основные сущности: InferenceTier, Inference, PerceivedEntity, AudioEvent, PerceivedEnvironment, PerceivedScene

Каждый слой pipeline получает частично заполненную структуру
и обогащает свою часть. Ни один слой не создаёт с нуля и не переписывает чужое.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Literal, Optional


class InferenceTier(Enum):
    """Уровень интерпретации — чем выше, тем сложнее вывод"""

    PHYSICAL = auto()  # Tier 1: "рука движется быстро" → "возможен удар"
    BEHAVIORAL = auto()  # Tier 2: "intent=attack + distance<1.5" → "агрессия"
    # Tier 3 (NARRATIVE) — живёт только в DM-промпте, не в этой структуре


@dataclass
class Inference:
    """Один вывод интерпретационного слоя"""

    inference_type: str  # "possible_attack", "friendly_gesture"
    tier: InferenceTier  # какой уровень сделал вывод
    confidence: float  # 0.0 – 1.0
    source_observations: List[str] = field(default_factory=list)  # что вызвало вывод


@dataclass
class PerceivedEntity:
    """
    Одна воспринятая сущность — проходит через весь pipeline.
    Каждый слой заполняет свою часть, остальные остаются None/пустыми.
    """

    entity_id: str

    # --- что это ---
    entity_type: Literal["npc", "object", "event"] = "object"

    # --- Spatial Layer ---
    x: float = 0.0  # мировая координата (метры)
    y: float = 0.0  # мировая координата (метры)
    distance: float = 999.0  # метры, 999 = не определено
    los: bool = False  # line of sight чистый
    los_blocked_by: Optional[str] = None  # "wall", "obstacle", None

    # --- Perception Layer ---
    visible: bool = False  # в зоне видимости (distance + light)
    audible: bool = False  # в зоне слышимости
    clarity: float = 0.0  # 0-1, чёткость восприятия
    audio_only: bool = False  # слышно, но не видно

    # --- Attention Layer ---
    in_attention: bool = False  # попал в фокус внимания
    attention_score: float = 0.0  # 0-1, почему попал (или нет)

    # --- Recognition Layer ---
    display_name: str = ""  # "Торнин" / "кажется, Торнин" / "мужчина"
    recognition_confidence: float = 0.0  # 0-1

    # --- Interpretation Layer ---
    observations: List[str] = field(default_factory=list)  # сырые: "arm_moving_fast"
    inferences: List[Inference] = field(default_factory=list)

    # --- Cognitive Distortion ---
    threat_bias: float = 0.0  # -1 .. +1, усиление/ослабление угрозы
    trust_bias: float = 0.0  # -1 .. 0, снижение доверия
    salience_bias: float = 0.0  # 0 .. +1, фиксация на угрозах

    # --- Memory Layer ---
    memory_tag: Literal["new", "known", "familiar", "forgotten"] = "new"
    memory_decay: float = 1.0  # 1.0 = свежее, 0.0 = стёрлось

    # --- Uncertainty Layer (финальный) ---
    final_confidence: float = 0.0  # итоговая уверенность 0-1

    # --- сырые данные из SceneState (для отладки, не для UI) ---
    _raw_data: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class AudioEvent:
    """
    Звуковое событие без визуального источника.
    "глухой звук удара" — источник НЕ раскрывается, если не виден.
    """

    description: str  # "глухой звук", "крик"
    direction: Optional[str] = None  # "слева", "сзади", "за стеной", None = неизвестно
    approximate_distance: float = 999.0
    confidence: float = 0.5  # насколько игрок уверен в описании


@dataclass
class PerceivedEnvironment:
    """Воспринимаемое окружение — не объективное, а то, что чувствует персонаж"""

    light_perceived: str = "normal"  # "ярко" / "приглушённо" / "темно"
    noise_perceived: str = "normal"  # "тихо" / "шумно" / "оглушительно"
    temperature_perceived: str = ""  # "жарко", "холодно", ""
    smell_perceived: str = ""  # "запах алкоголя", ""
    crowding_perceived: str = ""  # "тесно", "пусто", ""


@dataclass
class PerceivedScene:
    """
    Финальный результат pipeline — то, что получает UI.
    Содержит ТОЛЬКО то, что персонаж воспринимает.
    """

    location_id: str
    entities: List[PerceivedEntity] = field(default_factory=list)
    audio_events: List[AudioEvent] = field(default_factory=list)
    environment: PerceivedEnvironment = field(default_factory=PerceivedEnvironment)
    attention_focus_id: Optional[str] = None  # entity_id в фокусе
    player_body_state: List[str] = field(
        default_factory=list
    )  # ["тяжело дышишь", "рука болит"]

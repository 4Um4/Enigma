"""
Назначение: DTO для передачи данных о моторных и физических паттернах NPC, а также их восприятии Игроком.
Зависимости: dataclasses, typing

- В будущем можно расширить EmbodiedTraceDTO дополнительными параметрами (например, дыхание, пульс), если появится необходимость в более тонкой детализации моторных паттернов.
- PlayerPerceptionDTO может быть расширен для включения более сложных интерпретаций, таких как эмоциональные оценки или социальные сигналы, если это будет разрешено в рамках запретов.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class EmbodiedTraceDTO:
    """
    Наблюдаемые моторные и физические паттерны NPC.
    Не содержит эмоций. Только следы тела в пространстве.
    """

    npc_id: str

    # Моторные искажения (0.0 - 1.0)
    locomotion_instability: float = 0.0  # Дрожь, пошатывание (от pain/shock)
    posture_rigidity: float = 0.0  # Замер, окамененость (от initiative_suppression)
    gait_asymmetry: float = 0.0  # P5.1: Асимметрия походки (от травмы ноги)
    arm_restriction: float = 0.0  # P5.2: Ограничение руки/защитная поза (от травмы руки)
    gaze_break_rate: float = 0.0  # Отведение взгляда (от низкой compliance/lodge)
    action_interruption: float = 0.0  # Прерванное действие (от shock/path_abort)
    micro_pause_density: float = 0.0  # Частые микро-остановки (от blood_loss/fatigue)

    # Производные (вычисляются на фронте для "тупого" рендера)
    is_frozen: bool = False  # posture_rigidity > 0.7
    is_shaking: bool = False  # locomotion_instability > 0.5

    # Uncertainty Model (ADR-O-318)
    confidence: float = 0.8  # Базовая уверенность для физических проявлений (0.0-1.0)
    possible_causes: tuple[str, ...] = ()  # Возможные физические причины (напр., "cold", "fear", "pain")


@dataclass
class PlayerPerceptionDTO:
    """Доменный формат для BehaviorManifestation → WorldSnapshotBuilder._convert_perception.
    НЕ каноничный API-формат. Конвертер переводит его в snapshot.PlayerPerceptionDTO."""

    active_perceptions: list[dict[str, Any]] = field(
        default_factory=list
    )  # Список dicts {"npc_id", "cue_key"}
    atmosphere_key: Optional[str] = None
    atmosphere_intensity: float = 0.0
    embodied_traces: list[dict[str, Any]] = field(
        default_factory=list
    )  # Список dicts моторных следов
    manifestations: dict[str, list[str]] = field(
        default_factory=dict
    )  # {npc_id: [manifest_key, ...]} — наблюдаемые проявления
    observed_facts: list[str] = field(default_factory=list)  # ADR-O-318: Список фактов для DM

"""
path: backend/app/domain/snapshot.py
Назначение: Снимок мира для frontend. Единственное, что видит клиент.
Зависимости: dataclasses, typing, uuid.UUID
Основные сущности: WorldSnapshotDTO, NPCPositionDTO, VisibleEventDTO
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID


class PhysicalPresentationState(str, Enum):
    """Визуальное физическое состояние аватара для рендера."""

    HEALTHY = "healthy"
    WOUNDED = "wounded"
    BLEEDING = "bleeding"
    CRIPPLED = "crippled"
    DYING = "dying"
    DEAD = "dead"  # ADR-127: Необратимая смерть


class MentalPresentationState(str, Enum):
    """Визуальное ментальное состояние аватара для рендера."""

    CALM = "calm"
    STRESSED = "stressed"
    PANICKED = "panicked"
    DISSOCIATING = "dissociating"
    BROKEN = "broken"


@dataclass(frozen=True)
class AvatarStateDTO:
    """Феноменологическая проекция состояния аватара (ADR-035, ADR-037).
    Фронтенд не знает о HP, pain или identity_integrity.
    Он знает только как ИСКРИВЛЯТЬ восприятие игрока."""

    physical_state: PhysicalPresentationState = PhysicalPresentationState.HEALTHY
    mental_state: MentalPresentationState = MentalPresentationState.CALM

    # Феноменологические скаляры (Бэкенд вычисляет давление, Фронтенд генерирует кино)
    perceptual_stability: float = 1.0  # 0.0-1.0 (1.0 = кристально чистое восприятие)
    cognitive_coherence: float = (
        1.0  # 0.0-1.0 (0.0 = диссоциация, потеря связи "я-здесь")
    )
    sensory_noise: float = 0.0  # 0.0-1.0 (звон, пятна, глушение)
    motor_disruption: float = 0.0  # 0.0-1.0 (тремор, замедление моторики аватара)
    perceptual_latency: float = (
        0.0  # 0.0-1.0, задержка сборки реальности (шок, диссоциация)
    )
    reality_reconciliation_rate: float = (
        1.0  # 0.0-1.0, скорость восстановления когерентности
    )

    # Аудио и моторные маркеры для рендера
    blood_visibility: float = 0.0  # 0.0-1.0, кровь на экране/персонаже
    breathing_profile: str = "calm"  # calm, heavy, gasping, hyperventilating
    posture_state: str = "upright"  # upright, hunched, collapsed
    life_status: str = (
        "ALIVE"  # ADR-127: "ALIVE" или "DEAD" — feedback смерти для фронтенда
    )
    # ADR-039: Embodied Will Friction
    will_resistance: float = 0.0  # Сила сопротивления (0.0 - 1.0)
    embodied_vector: Optional[str] = None  # Моторный импульс (AVOIDANCE, FREEZE)


@dataclass(frozen=True)
class NPCPositionDTO:
    """Позиция одного NPC в мире. Readonly для frontend.
    A2-FIX: Структура приведена в соответствие с контрактом frontend (вложенный local_position, activity, name).
    Это устраняет необходимость в адаптере snapshot_npc_positions_to_dict.
    """

    npc_id: str
    local_position: Dict[str, float]  # Вложенный словарь {"x": float, "y": float}
    location_id: str
    facing: str = "south"  # 'north', 'south', 'east', 'west' (DEPRECATED: legacy 4-dir)
    body_heading: float = (
        1.5708  # ADR-O-315: Непрерывный угол ориентации тела (рад). Pi/2 = Юг.
    )
    activity: str = (
        "idle"  # 'idle', 'walking', 'talking', 'working' (переименовано с action)
    )
    name: str = ""  # Истинное имя (для DM и логики)
    display_name: str = "Незнакомец"  # ADR-O-319: Имя для UI (зависит от RecognitionMemory)
    recognition_confidence: float = 0.0  # ADR-O-319: Уверенность распознавания (0.0-1.0)
    initiative_suppression: float = (
        0.0  # Спринт 30: Cognitive Freeze (0.0-1.0), паралич воли
    )
    velocity: Tuple[float, float] = (
        0.0,
        0.0,
    )  # ETKE-IK: Вектор скорости для непрерывного рендера
    exertion_level: float = 0.0  # ETKE-IK: Уровень усталости (0.0-1.0)


@dataclass(frozen=True)
class RecentDialogueDTO:
    """Реплика NPC для отображения в виде облачка (Speech Bubble)."""

    speaker_id: str
    text: str
    exposure: str = "normal"  # normal, whisper, shout
    timestamp: float = 0.0


@dataclass(frozen=True)
class VisibleEventDTO:
    """Событие видимое frontend. Отфильтровано по visibility и радиусу."""

    event_id: str
    timestamp: float
    text: str
    actor_id: str
    visibility: str  # 'public', 'private', 'whisper'


@dataclass(frozen=True)
class AvatarDesyncDTO:
    """Визуальное искажение без поломки управления (Слой 0: Подсознание).
    ADR-039/ТЗ EMBODIED UI: Запрет на лаг ввода. Только инерция камеры и шлейфы."""

    camera_inertia: float = 0.0  # Смещение/запаздывание камеры
    motion_trail: float = 0.0  # Шлейф при движении
    auditory_muffle: float = 0.0  # Глушение звуков


@dataclass(frozen=True)
class ActivePerception:
    """Активное восприятие игрока с инерцией затухания (Слои 2-3: Атмосфера и Центральное внимание)."""

    text: str
    intensity: float  # Текущая яркость (1.0 = только что замечено)
    decay_rate: float  # Скорость затухания (например, -0.05 за тик)
    created_tick: int


@dataclass(frozen=True)
class PeripheralCueDTO:
    """Периферическое наблюдение за NPC (Слой 1: Наблюдение, не диагноз).
    ЗАПРЕТ: Текст строго внешний ("Замер"), без телепатии ("Боится").

    A3-FIX: поле переименовано cue_type → cue_key для согласования с frontend.
    Раньше frontend читал cue_key, backend отдавал cue_type → пустые симптомы.
    """

    npc_id: str
    cue_key: str  # "FREEZE", "HURRY", "AVOID_GAZE" (renamed from cue_type)
    hover_text: str  # "Замер на месте", "Отвел взгляд"

    # Uncertainty Model (ADR-O-318)
    confidence: float = 0.5  # Уверенность наблюдателя (0.0-1.0)
    possible_causes: tuple[str, ...] = ()  # Возможные причины без указания истинной


@dataclass(frozen=True)
class ReconstructionEventDTO:
    """Каузальная Реконструкция (Слой 5: Постфактум)."""

    text: str
    tick: int


@dataclass(frozen=True)
class ManifestationDTO:
    """Наблюдаемое физическое проявление NPC (НЕ эмоция!).
    Моторный паттерн, который аватар видит телесно: застыл, дрожит, суетится.
    Multi-manifest: NPC может быть одновременно напряжён И неуверен."""

    npc_id: str
    tags: List[str] = field(
        default_factory=list
    )  # ["MANIFEST_TENSE", "MANIFEST_ALERT"]


@dataclass(frozen=True)
class PlayerPerceptionDTO:
    """Линза восприятия игрока. Тупой рендер.
    ТЗ EMBODIED UI: Фронтенд получает этот объект и ничего не вычисляет."""

    # Слой 0: Подсознание (вычисляется из AvatarStateDTO)
    avatar_desync: Optional[AvatarDesyncDTO] = None

    # Слой 1-3: Активные восприятия (отсортированы по приоритету)
    active_perceptions: List[ActivePerception] = field(default_factory=list)

    # Слой 1: Периферия (кто сейчас выделяется в толпе)
    peripheral_cues: List[PeripheralCueDTO] = field(default_factory=list)

    # Слой 1.5: Наблюдаемые физические проявления (моторные, НЕ эмоции)
    manifestations: List[ManifestationDTO] = field(default_factory=list)

    # Слой 4: Эхо
    echo_count: int = 0

    # Слой 5: Реконструкция
    reconstruction_events: List[ReconstructionEventDTO] = field(default_factory=list)

    # The Fool: Моторные следы для физического рендера (дрожь, замер)
    embodied_traces: List[Dict[str, Any]] = field(default_factory=list)

    # ADR-O-318: Наблюдаемые факты для DM (чтобы не дублировать визуал)
    observed_facts: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorldSnapshotDTO:
    """Снимок мира на конец тика.

    Единственное, что пересекает границу backend → frontend.
    Не содержит NPCState, trust, fear, secret_events — только визуальное.
    """

    tick: int
    version: int  # инкремент SceneStateManager, защита от stale
    last_event_id: Optional[UUID]  # последнее обработанное событие
    player_position: Tuple[float, float]
    # A2-FIX: Dict[str, NPCPositionDTO] — canonical.
    # Раньше List[NPCPositionDTO] + runtime adapter snapshot_npc_positions_to_dict.
    # Adapter маскировал архитектурный разрыв между backend (List) и frontend (Dict).
    # Теперь: Dict напрямую, frontend читает .items() без конвертации.
    npc_positions: Dict[str, NPCPositionDTO]
    available_actions: List[str]
    location_id: str
    weather: str
    time_of_day: str
    visible_events: List[VisibleEventDTO] = field(default_factory=list)
    # ADR-JOURNAL: Очередь последних 100 реплик. SSOT формируется на бэкенде.
    dialog_journal: List[Dict[str, str]] = field(default_factory=list)
    game_time_seconds: int = 0
    active_traversals: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )  # ADR-019, CEI-2: Dict[npc_id, data] — синхронно с scene_state
    avatar_state: Optional[AvatarStateDTO] = (
        None  # ADR-035: Феноменологическая проекция
    )
    ambient_phenomenology: Optional[Dict[str, float]] = (
        None  # ADR-037: Средовое давление (температура, плотность)
    )
    player_perception: Optional[PlayerPerceptionDTO] = (
        None  # ТЗ EMBODIED UI: Симметричная онтология восприятия
    )
    recent_dialogues: List["RecentDialogueDTO"] = field(
        default_factory=list
    )  # ADR-O-313: Труба диалогов для Speech Bubbles

    # ТЗ Presentation v2.0: Физика Восприятия и Инвентарь
    player_body_topology: Optional[Dict[str, Any]] = (
        None  # BodyTopology аватара игрока для UI (сериализованная)
    )
    visual_dto: Optional[Dict[str, Any]] = (
        None  # Канал визуальной презентации (NPC проявления, экипировка)
    )
    audible_dto: Optional[Dict[str, Any]] = (
        None  # Канал аудио презентации (голос, дыхание, шаги)
    )


# A2-FIX: snapshot_npc_positions_to_dict УДАЛЕН.
# Раньше конвертировал List[NPCPositionDTO] → dict для frontend.
# Теперь WorldSnapshotDTO.npc_positions = Dict[str, NPCPositionDTO] напрямую.
# Frontend читает .items() без конвертации.
#
# Если где-то ещё нужен dict-формат (для JSON serialization), использовать asdict():
# from dataclasses import asdict
# positions_dict = {nid: asdict(pos) for nid, pos in ws.npc_positions.items()}

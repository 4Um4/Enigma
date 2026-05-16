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
from typing import Any, Dict, List, Literal, Optional, Set


class InferenceTier(Enum):
    """Уровень интерпретации — чем выше, тем сложнее вывод"""
    PHYSICAL = auto()    # Tier 1: "рука движется быстро" → "возможен удар"
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
    distance: float = 999.0
    los: bool = False
    los_blocked_by: Optional[str] = None

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

    # --- Traversal Layer (Спринт 30: Dual-Time Ontology) ---
    # Бэкенд компрессирует время, фронтенд разархивирует его непрерывным движением
    traversal_status: str = "IDLE"               # PENDING, MOVING, ARRIVED, CANCELLED
    path_waypoints: list = field(default_factory=list) # Визуальные x,y точки
    current_waypoint_idx: int = 0
    traversal_progress: float = 0.0              # 0.0 - 1.0 прогресс между текущими waypoint
    traversal_speed: float = 1.5                 # Скорость визуальной интерполяции (м/с)

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
    SHORT = auto()    # текущий ход — нет decay
    MEDIUM = auto()   # последние 5-10 ходов — медленный decay
    LONG = auto()     # прошлые сессии — быстрый decay


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
class PlayerMemory:
    """
    Память игрока — in-memory, без персистенции.
    Копия backend/app/services/player_cognition/memory_layer.py:PlayerMemory
    """
    _entries: Dict[str, MemoryEntry] = field(default_factory=dict)
    _turn_count: int = 0

    # === Decay параметры ===
    MEDIUM_DECAY_PER_TURN: float = 0.05
    LONG_DECAY_PER_TURN: float = 0.15
    MEDIUM_MAX_TURNS: int = 10
    MIN_MEMORY: float = 0.1

    def new_turn(self) -> None:
        """Вызвать в начале каждого хода — применяет decay"""
        self._turn_count += 1
        for entry in self._entries.values():
            if self._turn_count - entry.last_seen_time > self.MEDIUM_MAX_TURNS:
                entry.last_clarity *= (1.0 - self.LONG_DECAY_PER_TURN)
            elif self._turn_count - entry.last_seen_time > 1:
                entry.last_clarity *= (1.0 - self.MEDIUM_DECAY_PER_TURN)

    def update_from_perception(self, entities: List[PerceivedEntity]) -> None:
        """Обновляет память из текущего PerceivedScene"""
        now = float(self._turn_count)

        for entity in entities:
            if not entity.visible:
                continue

            eid = entity.entity_id
            if eid in self._entries:
                entry = self._entries[eid]
                entry.encounter_count += 1
                entry.last_seen_time = now
                entry.last_clarity = max(entry.last_clarity, entity.clarity)
                entry.display_name = entity.display_name or entry.display_name
                for obs in entity.observations:
                    if obs not in entry.key_observations:
                        entry.key_observations.append(obs)
                        if len(entry.key_observations) > 5:
                            entry.key_observations.pop(0)
            else:
                self._entries[eid] = MemoryEntry(
                    entity_id=eid,
                    entity_type=entity.entity_type,
                    display_name=entity.display_name,
                    last_seen_time=now,
                    encounter_count=1,
                    last_clarity=entity.clarity,
                    key_observations=list(entity.observations),
                )

    def get_memory(self, entity_id: str) -> Optional[MemoryEntry]:
        """Возвращает запись памяти или None"""
        entry = self._entries.get(entity_id)
        if entry and entry.last_clarity < self.MIN_MEMORY:
            return None
        return entry

    def get_tier(self, entity_id: str) -> MemoryTier:
        """Определяет уровень памяти о сущности"""
        entry = self._entries.get(entity_id)
        if not entry:
            return MemoryTier.LONG
        age = self._turn_count - entry.last_seen_time
        if age <= 1:
            return MemoryTier.SHORT
        elif age <= self.MEDIUM_MAX_TURNS:
            return MemoryTier.MEDIUM
        else:
            return MemoryTier.LONG


@dataclass
class EncounterHistory:
    """
    История встреч с NPC — in-memory, без персистенции.
    Копия backend/app/services/player_cognition/recognition_layer.py:EncounterHistory
    """
    _encounters: Dict[str, int] = field(default_factory=dict)
    _known_ids: Set[str] = field(default_factory=set)

    def record_encounter(self, npc_id: str) -> None:
        """Записывает встречу с NPC"""
        self._encounters[npc_id] = self._encounters.get(npc_id, 0) + 1
        self._known_ids.add(npc_id)

    def encounter_count(self, npc_id: str) -> int:
        return self._encounters.get(npc_id, 0)

    def is_known(self, npc_id: str) -> bool:
        return npc_id in self._known_ids


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
    encounter_history: Optional[EncounterHistory] = None
    player_memory: Optional[PlayerMemory] = None
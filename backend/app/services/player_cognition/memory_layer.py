"""
app/services/player_cognition/memory_layer.py
Memory Layer — память игрока о воспринятых сущностях.

3 уровня:
  краткосрочная — точная, текущий ход (обязана быть в PerceivedScene)
  средняя — сжатая, последние ходы (decay медленный)
  дальняя — искажённая, прошлые сессии (decay быстрый)

path: /backend/app/services/player_cognition/memory_layer.py
Назначение: Управляет памятью игрока о сущностях — краткосрочная, средняя, дальняя с деградацией
Зависимости: types (PerceivedEntity), time
Основные сущности: PlayerMemory, apply_memory()

TODO: после реализации PlayerMemory persistence — заменить in-memory на persisted.
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from app.services.player_cognition.types import PerceivedEntity


class MemoryTier(Enum):
    SHORT = auto()    # текущий ход — нет decay
    MEDIUM = auto()   # последние 5-10 ходов — медленный decay
    LONG = auto()      # прошлые сессии — быстрый decay


@dataclass
class MemoryEntry:
    """Одна запись в памяти о сущности"""
    entity_id: str
    entity_type: str
    display_name: str
    last_seen_time: float          # _turn_count (ticks, not wall-clock)
    encounter_count: int = 0
    last_clarity: float = 0.0      # чёткость при последней встрече
    key_observations: List[str] = field(default_factory=list)


@dataclass
class PlayerMemory:
    """
    Память игрока — in-memory, без персистенции.
    Вызывающий код может сохранять/загружать через pickle/json при необходимости.
    """
    _entries: Dict[str, MemoryEntry] = field(default_factory=dict)
    _turn_count: int = 0

    # === Decay параметры ===
    MEDIUM_DECAY_PER_TURN = 0.05    # 5% за ход
    LONG_DECAY_PER_TURN = 0.15      # 15% за ход
    MEDIUM_MAX_TURNS = 10           # после — переходит в LONG
    MIN_MEMORY = 0.1                # ниже — "забыто"

    def new_turn(self) -> None:
        """Вызвать в начале каждого хода — применяет decay"""
        self._turn_count += 1
        for entry in self._entries.values():
            if self._turn_count - entry.last_seen_time > self.MEDIUM_MAX_TURNS:
                # Средняя → дальняя (быстрый decay)
                entry.last_clarity *= (1.0 - self.LONG_DECAY_PER_TURN)
            elif self._turn_count - entry.last_seen_time > 1:
                # Не текущий ход → средний decay
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
                # Добавляем новые наблюдения
                for obs in entity.observations:
                    if obs not in entry.key_observations:
                        entry.key_observations.append(obs)
                        # Ограничиваем длину — старые забываются
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


def apply_memory(
    entities: List[PerceivedEntity],
    memory: PlayerMemory,
) -> None:
    """
    Применяет Memory Layer — заполняет memory_tag и memory_decay.
    Вызывать ПОСЛЕ recognition и interpretation.

    Мутирует entities in-place.
    """
    for entity in entities:
        entry = memory.get_memory(entity.entity_id)

        if entry is None:
            entity.memory_tag = "new"
            entity.memory_decay = 1.0
        else:
            tier = memory.get_tier(entity.entity_id)
            entity.memory_decay = entry.last_clarity

            if tier == MemoryTier.SHORT:
                entity.memory_tag = "known"
            elif tier == MemoryTier.MEDIUM:
                entity.memory_tag = "familiar"
            else:
                entity.memory_tag = "forgotten"
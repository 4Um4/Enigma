"""
SceneContinuity — эпизодическая фиксация сцены.

path: backend/app/services/verbalization/scene_continuity.py
Назначение: Эпизодическая фиксация сцены — убирает repetition, фиксирует "правду сцены"
Зависимости: нет (чистый dataclass + простая логика)
Основные сущности: SceneContinuity

НЕ память. НЕ state.
А фиксация ЧЕГО УЖЕ ПРОИЗОШЛО в текущей сцене для DM prompt.

Принцип: DM не должен повторять события из flags.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class SceneContinuity:
    """
    Эпизодическая фиксация сцены.
    
    НЕ персистируется между сессиями — только в рамках одной сцены.
    """
    # Флаги событий которые УЖЕ произошли
    active_flags: Set[str] = field(default_factory=set)
    
    # Последние события (cap=5) — для контекста
    recent_events: List[str] = field(default_factory=list)
    
    # Факты сцены — что DM должен считать истинным
    scene_facts: List[str] = field(default_factory=list)
    
    # Текущее напряжение (инерция)
    tension: float = 0.0
    
    # Эмоциональный вектор (B.4: Micro-History)
    emotional_vector: Dict[str, float] = field(default_factory=lambda: {
        "trust": 0.0,
        "tension": 0.0,
        "confusion": 0.0,
    })
    
    # TODO: миграция в core/constants.py после калибровки
    # Капы
    MAX_RECENT: int = 5
    MAX_FLAGS: int = 20

    def add_flag(self, flag: str) -> None:
        """Добавить флаг произошедшего события."""
        self.active_flags.add(flag)
        # Кап
        if len(self.active_flags) > self.MAX_FLAGS:
            # Удаляем самые старые (произвольно из set)
            self.active_flags = set(list(self.active_flags)[-self.MAX_FLAGS:])

    def has_flag(self, flag: str) -> bool:
        """Проверить было ли событие."""
        return flag in self.active_flags

    def add_event(self, event: str) -> None:
        """Добавить событие в recent (cap=5). Дедупликация."""
        if event in self.recent_events:
            return
        self.recent_events.append(event)
        if len(self.recent_events) > self.MAX_RECENT:
            self.recent_events = self.recent_events[-self.MAX_RECENT:]

    def add_fact(self, fact: str) -> None:
        """Добавить факт сцены."""
        if fact not in self.scene_facts:
            self.scene_facts.append(fact)

    def update_tension(self, delta: float) -> None:
        """Обновить напряжение. Не может уйти ниже 0."""
        self.tension = max(0.0, min(1.0, self.tension + delta))

    def update_emotional_vector(self, deltas: Dict[str, float]) -> None:
        """Обновить эмоциональный вектор (инерция, не замена)."""
        for key, delta in deltas.items():
            if key in self.emotional_vector:
                current = self.emotional_vector[key]
                # Инерция: 70% текущее + 30% новое
                self.emotional_vector[key] = round(
                    current * 0.7 + delta * 0.3, 2
                )

    def to_prompt_block(self) -> str:
        """Сгенерировать блок для DM prompt."""
        lines = []
        
        # Tension
        if self.tension > 0.05:
            lines.append(f"tension: {self.tension:.2f}")
        
        # Flags
        if self.active_flags:
            flags_str = ", ".join(sorted(self.active_flags))
            lines.append(f"flags: {flags_str}")
        
        # Recent events — что только что произошло
        if self.recent_events:
            for evt in self.recent_events[-9:]:  # последние 9
                lines.append(f"event: {evt}")
        
        # Facts
        if self.scene_facts:
            for fact in self.scene_facts:
                lines.append(f"fact: {fact}")
        
        if not lines:
            return ""
        
        return "СОСТОЯНИЕ СЦЕНЫ:\n" + "\n".join(lines)

    def to_emotional_line(self) -> str:
        """Компактная строка эмоционального вектора для DM prompt."""
        parts = []
        for key, val in self.emotional_vector.items():
            if abs(val) > 0.05:
                sign = "+" if val > 0 else ""
                parts.append(f"{key}={sign}{val:.1f}")
        if not parts:
            return ""
        return "эмоциональный фон: " + ", ".join(parts)
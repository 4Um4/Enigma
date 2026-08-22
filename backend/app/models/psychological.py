from __future__ import annotations

"""
path: backend/app/models/psychological.py
Назначение: Централизованные типы психологического слоя ENIGMA.
Зависимости: нет внешних (только stdlib)
Основные сущности: DistortionProfile, CausalEntry

Используется:
- CognitiveDistortionEngine → возвращает DistortionProfile
- ProjectionLayer (_project_psychology) → принимает DistortionProfile
- StateApplicator → пишет CausalEntry (Шаг 3)
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class DistortionProfile:
    """
    Три оси когнитивного искажения NPC.
    Сумма abs(threat) + abs(trust) + abs(salience) ≤ 1.0 (Governor).

    Передаётся от CognitiveDistortionEngine в ProjectionLayer.
    LLM эти числа НЕ получает — только производный режим (PsychologicalSignature).
    """

    threat_bias: float = 0.0  # [-1, +1]: усиление воспринимаемой угрозы
    trust_bias: float = 0.0  # [-1,  0]: снижение доверия к источнику
    salience_bias: float = 0.0  # [ 0, +1]: фокусировка на угрозах

    @classmethod
    def neutral(cls) -> "DistortionProfile":
        """Нулевой профиль — нет искажений."""
        return cls()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DistortionProfile":
        """Создаёт из ad-hoc dict для обратной совместимости."""
        return cls(
            threat_bias=float(d.get("threat_bias", 0.0)),
            trust_bias=float(d.get("trust_bias", 0.0)),
            salience_bias=float(d.get("salience_bias", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "threat_bias": self.threat_bias,
            "trust_bias": self.trust_bias,
            "salience_bias": self.salience_bias,
        }


@dataclass(frozen=True)
class Cause:
    """Stage 1 Task 1.2: Provenance for state changes."""
    source_event_id: Optional[UUID] = None
    source_action_id: Optional[UUID] = None
    source_belief_id: Optional[UUID] = None
    source_memory_id: Optional[UUID] = None
    trigger_chain: Tuple[UUID, ...] = ()


@dataclass(frozen=True)
class CausalChain:
    """Stage 1 Task 1.4: Полная причинная цепочка (8 шагов)."""
    source_event: Optional[Any] = None
    observation: Optional[Any] = None
    memory: Optional[Any] = None
    belief: Optional[Any] = None
    decision: Optional[Any] = None
    action: Optional[Any] = None
    state_delta: Optional[Any] = None
    world_change: Optional[Any] = None


@dataclass
class CausalEntry:
    """
    Паспорт одного изменения состояния NPC.
    Пишется StateApplicator при каждой дельте (Шаг 3).

    Позволяет отследить: откуда пришло изменение, как долго действует.
    emotional_impact > 0.7 — триггер для генерации TemporaryDrive (ФАЗА 4-ROLE.2).
    """

    npc_id: str
    field: str  # "stress", "trust", "fear" и т.д.
    delta: float  # величина изменения
    source: str  # "player_insults", "life_engine", "break_system" и т.д.
    tick: int  # игровой тик
    persistence_time: int = 0  # тиков до затухания (0 = постоянное)
    emotional_impact: float = (
        0.0  # сила эмоционального удара [0..1], для генерации drives
    )
    cause: Optional[Cause] = None  # Stage 1 Task 1.2

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация для JSON persistence и API."""
        return {
            "npc_id": self.npc_id,
            "field": self.field,
            "delta": self.delta,
            "source": self.source,
            "tick": self.tick,
            "persistence_time": self.persistence_time,
            "emotional_impact": self.emotional_impact,
            "cause": {
                "source_event_id": str(self.cause.source_event_id) if self.cause and self.cause.source_event_id else None,
                "source_action_id": str(self.cause.source_action_id) if self.cause and self.cause.source_action_id else None,
            } if self.cause else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CausalEntry":
        """Десериализация из JSON persistence."""
        _cause_dict = d.get("cause")
        _cause = None
        if _cause_dict and isinstance(_cause_dict, dict):
            _cause = Cause(
                source_event_id=UUID(_cause_dict["source_event_id"]) if _cause_dict.get("source_event_id") else None,
                source_action_id=UUID(_cause_dict["source_action_id"]) if _cause_dict.get("source_action_id") else None,
            )
        return cls(
            npc_id=d.get("npc_id", ""),
            field=d.get("field", ""),
            delta=float(d.get("delta", 0.0)),
            source=d.get("source", ""),
            tick=int(d.get("tick", 0)),
            persistence_time=int(d.get("persistence_time", 0)),
            emotional_impact=float(d.get("emotional_impact", 0.0)),
            cause=_cause,
        )

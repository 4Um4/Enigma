# backend/app/models/physical.py
"""
Physical models — структуры для боевой физики.

ПРИНЦИП: Физика = факты мира. НЕ текст. НЕ решения.
PhysicalOutcome → StateChanges → NPCState (через StateApplicator).

Назначение: Физические структуры — урон, условия, раны, угроза
Зависимости: typing, dataclasses (чистый слой)
Основные сущности: PhysicalOutcome, Condition, Wound, ThreatAccumulator

ЗАПРЕЩЕНО:
  - LLM в этом файле
  - Текстовые описания (кровь, крик) — это SceneEvents, не физика
  - Решения (бежать, атаковать) — это DecisionSignals, не физика
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class DamageType(Enum):
    SLASHING = "slashing"
    PIERCING = "piercing"
    BLUDGEONING = "bludgeoning"
    FIRE = "fire"
    COLD = "cold"
    POISON = "poison"
    PSYCHIC = "psychic"


class WoundSeverity(Enum):
    """Степень раны — влияет на persistency и последствия."""
    MINOR = "minor"           # царапина, заживёт за день
    MODERATE = "moderate"     # порез, шрам останется
    SEVERE = "severe"         # глубокий порез, влияет на возможности
    CRIPPLING = "crippling"   # перелом/отруб, перманентный эффект


# Маппинг: какой DamageType даёт какие Condition
_DAMAGE_CONDITION_MAP: Dict[DamageType, List[str]] = {
    DamageType.SLASHING: ["bleeding"],
    DamageType.PIERCING: ["bleeding"],
    DamageType.BLUDGEONING: ["stunned"],
    DamageType.FIRE: ["burning"],
    DamageType.COLD: ["slowed"],
    DamageType.POISON: ["poisoned"],
    DamageType.PSYCHIC: ["confused"],
}


@dataclass(frozen=True)
class PhysicalOutcome:
    """
    Результат разрешения физического действия.
    Генерируется PhysicalResolver (чистый Python, без LLM).
    
    НЕ содержит текста — только факты для StateApplicator.
    Визуал (кровь, крик) генерируется ReflexResolver отдельно.
    """
    hit: bool                              # попал ли
    damage: int = 0                        # количество урона
    damage_type: DamageType = DamageType.BLUDGEONING
    critical: bool = False                 # критический удар
    attacker_id: str = ""                  # кто нанёс
    
    @property
    def potential_conditions(self) -> List[str]:
        """Какие condition типы может вызвать этот урон."""
        return _DAMAGE_CONDITION_MAP.get(self.damage_type, [])
    
    @property
    def wound_severity(self) -> Optional[WoundSeverity]:
        """Степень раны на основе урона (без контекста NPC — только дельта)."""
        if self.damage <= 0:
            return None
        if self.damage >= 25:
            return WoundSeverity.CRIPPLING
        if self.damage >= 15:
            return WoundSeverity.SEVERE
        if self.damage >= 8:
            return WoundSeverity.MODERATE
        return WoundSeverity.MINOR


class OutcomeBand(str, Enum):
    """
    Градиентная полоса исходов (Фаза R7).
    Заменяет бинарный hit/miss на 5 уровней результата.
    
    d20 roll → OutcomeBand через пороги. Нет хардкода — пороги конфигурируемы.
    """
    CRITICAL_FAIL = "critical_fail"     # natural 1 — катастрофа, осложнение следующих проверок
    FAIL = "fail"                 # ниже target_ac
    PARTIAL = "partial"             # выше target_ac, но ниже success_threshold
    SUCCESS = "success"             # в полосе [success_threshold, critical_threshold)
    CRITICAL_SUCCESS = "critical_success" # natural 20 — усиленный эффект


# Пороги для d20 → OutcomeBand (конфигурируемы для R8 разных кубиков)
OUTCOME_THRESHOLDS_D20: Dict[OutcomeBand, int] = {
    OutcomeBand.CRITICAL_FAIL: 1,          # natural 1
    OutcomeBand.FAIL: 10,             # ниже target_ac
    OutcomeBand.PARTIAL: 10,            # target_ac (попадает в PARTIAL при = target_ac)
    OutcomeBand.SUCCESS: 15,           # выше target_ac + margin
    OutcomeBand.CRITICAL_SUCCESS: 20,       # natural 20
}
SUCCESS_MARGIN: int = 5  # сколько выше target_ac нужно для PARTIAL → SUCCESS


@dataclass
class OutcomeResult:
    """
    Расширенный результат физического действия (Фаза R7).
    Оборачивает PhysicalOutcome градиентной полосой OutcomeBand.
    
    Выход PhysicalResolver → OutcomeResult → StateApplicator/SceneEvents.
    """
    band: OutcomeBand
    hit: bool                            # backward compat: hit = SUCCESS или CRITICAL_SUCCESS
    damage: int = 0
    damage_modifier: float = 1.0              # множитель урона по полосе
    damage_type: DamageType = DamageType.BLUDGEONING
    critical: bool = False
    attacker_id: str = ""
    raw_roll: int = 0                        # исходный бросок для трассировки
    target_ac: int = 0                         # порог попадания для логов
    description: str = ""                     # описание для SceneEvents/DM контекста
    
    @property
    def outcome_damage(self) -> int:
        """Урон с учётом damage_modifier."""
        return max(0, int(self.damage * self.damage_modifier))
    
    @staticmethod
    def from_physical(outcome: PhysicalOutcome, roll: int, target_ac: int = 0) -> "OutcomeResult":
        """Создаёт OutcomeResult из PhysicalOutcome + броска."""
        if outcome.critical:
            band = OutcomeBand.CRITICAL_SUCCESS
            modifier = 2.0
            desc = "Критический успех — удар усилен"
        elif roll == 1:
            band = OutcomeBand.CRITICAL_FAIL
            modifier = 0.0
            desc = "Критический провал — катастрофа"
        elif roll <= target_ac - SUCCESS_MARGIN:
            band = OutcomeBand.FAIL
            modifier = 0.5
            desc = "Промах — действие не удалось"
        elif roll < target_ac:
            band = OutcomeBand.PARTIAL
            modifier = 0.75
            desc = "Частичный успех — действие выполнено частично"
        else:
            band = OutcomeBand.SUCCESS
            modifier = 1.0
            desc = "Успех — действие выполнено"
        
        return OutcomeResult(
            band=band,
            hit=band in (OutcomeBand.SUCCESS, OutcomeBand.CRITICAL_SUCCESS),
            damage=outcome.damage,
            damage_modifier=modifier,
            damage_type=outcome.damage_type,
            critical=outcome.critical,
            attacker_id=outcome.attacker_id,
            raw_roll=roll,
            target_ac=target_ac,
            description=desc,
        )


@dataclass
class Condition:
    """
    Временное состояние NPC (status effect).
    Тикает каждый ход через ConditionEngine.
    
    duration_ticks=0 → indefinite (не затухает сам, только через лечение/событие)
    """
    type: str                  # bleeding, stunned, prone, burning, slowed, poisoned, confused
    severity: float = 0.0      # 0.0-1.0 — сила эффекта
    duration_ticks: int = 0    # 0 = indefinite
    decay_per_tick: float = 0.0  # затухание severity за тик
    tick_applied: int = 0      # когда применён (для logging)
    
    def tick(self) -> bool:
        """
        Один тик жизни condition.
        Returns True если condition ещё активен, False если истёк.
        """
        if self.duration_ticks <= 0:
            # Indefinite — не затухает по времени
            # Но severity может decay
            if self.decay_per_tick > 0:
                self.severity = max(0.0, self.severity - self.decay_per_tick)
                return self.severity > 0.01  # умирает когда severity ~0
            return True
        
        self.duration_ticks -= 1
        if self.duration_ticks <= 0:
            return False
        
        # Затухание severity
        if self.decay_per_tick > 0:
            self.severity = max(0.0, self.severity - self.decay_per_tick)
        
        return True
    
    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "severity": round(self.severity, 4),
            "duration_ticks": self.duration_ticks,
            "decay_per_tick": self.decay_per_tick,
            "tick_applied": self.tick_applied,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> Condition:
        return cls(
            type=data.get("type", ""),
            severity=data.get("severity", 0.0),
            duration_ticks=data.get("duration_ticks", 0),
            decay_per_tick=data.get("decay_per_tick", 0.0),
            tick_applied=data.get("tick_applied", 0),
        )


@dataclass(frozen=True)
class Wound:
    """
    Необратимое (или труднообратимое) изменение тела NPC.
    НЕ затухает. НЕ исчезает. Формирует идентичность NPC.
    
    persistent=True → шрам навсегда (cosmetic + психологический)
    persistent=False → заживёт за N тиков (deep wound)
    """
    body_part: str           # head, torso, arm_left, arm_right, leg_left, leg_right
    severity: WoundSeverity
    cause: str               # "sword_slash", "blunt_impact", "arrow_pierce"
    tick_received: int       # когда получена
    persistent: bool = False  # True = навсегда
    heal_ticks: int = 0      # при persistent=False: через сколько заживёт (0 = не заживёт)
    
    @property
    def is_healing(self) -> bool:
        """Рана в процессе заживления (не persistent и heal_ticks > 0)."""
        return not self.persistent and self.heal_ticks > 0
    
    @property
    def capability_penalty(self) -> float:
        """Штраф к способностям (0.0-1.0). DecisionHub читает это."""
        base = {
            WoundSeverity.MINOR: 0.0,
            WoundSeverity.MODERATE: 0.05,
            WoundSeverity.SEVERE: 0.15,
            WoundSeverity.CRIPPLING: 0.4,
        }
        return base.get(self.severity, 0.0)
    
    def to_dict(self) -> Dict:
        return {
            "body_part": self.body_part,
            "severity": self.severity.value,
            "cause": self.cause,
            "tick_received": self.tick_received,
            "persistent": self.persistent,
            "heal_ticks": self.heal_ticks,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> Wound:
        severity = WoundSeverity(data.get("severity", "minor"))
        return cls(
            body_part=data.get("body_part", ""),
            severity=severity,
            cause=data.get("cause", ""),
            tick_received=data.get("tick_received", 0),
            persistent=data.get("persistent", False),
            heal_ticks=data.get("heal_ticks", 0),
        )


@dataclass
class ThreatAccumulator:
    """
    Накопленная угроза от конкретных источников.
    Медленнее деградирует чем stress (decay 0.02 vs 0.1).
    
    Формирует "память об опасности" — NPC помнит кто его бил.
    """
    sources: Dict[str, float] = field(default_factory=dict)
    decay_rate: float = 0.02      # за тик
    
    @property
    def total(self) -> float:
        return sum(self.sources.values())
    
    @property
    def primary_threat(self) -> tuple[str, float]:
        """Кто самый опасный: (source_id, threat_level)."""
        if not self.sources:
            return ("", 0.0)
        return max(self.sources.items(), key=lambda x: x[1])
    
    def add_threat(self, source_id: str, amount: float) -> None:
        """Добавить угрозу от источника."""
        if source_id not in self.sources:
            self.sources[source_id] = 0.0
        self.sources[source_id] = min(100.0, self.sources[source_id] + amount)
    
    def decay(self) -> Dict[str, float]:
        """
        Один тик деградации.
        Returns: Dict с дельтами для CausalLedger.
        """
        deltas: Dict[str, float] = {}
        to_remove: List[str] = []
        
        for source_id, threat in self.sources.items():
            if threat <= 0:
                to_remove.append(source_id)
                continue
            decayed = threat * self.decay_rate
            self.sources[source_id] = max(0.0, threat - decayed)
            deltas[f"threat.{source_id}"] = -round(decayed, 4)
        
        for src in to_remove:
            del self.sources[src]
        
        return deltas
    
    def get_threat(self, source_id: str) -> float:
        return self.sources.get(source_id, 0.0)
    
    def to_dict(self) -> Dict:
        return {
            "sources": {k: round(v, 4) for k, v in self.sources.items()},
            "decay_rate": self.decay_rate,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> ThreatAccumulator:
        return cls(
            sources=data.get("sources", {}),
            decay_rate=data.get("decay_rate", 0.02),
        )
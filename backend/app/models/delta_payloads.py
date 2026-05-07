# -*- coding: utf-8 -*-
"""
path: backend/app/models/delta_payloads.py
Назначение: Типизированные payload'ы для StateDeltas v2 (Domain-Tagged Typed Payloads).
Зависимости: typing
Основные сущности: SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload

Принцип: Каждый DeltaDomain имеет свой frozen dataclass payload.
Это предотвращает «Unity syndrome» — потерю discoverability через string keys.
IDE видит поля, опечатка вызывает TypeError, рефакторинг делается в один клик.

TODO:
- Добавить CombatPayload для боевых дельт (hp, pain, injuries).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SocialPayload:
    """Дельты социальных отношений (NPC→Player, NPC→NPC)."""
    trust_delta: float = 0.0
    fear_delta: float = 0.0
    affection_delta: float = 0.0
    debt_delta: float = 0.0


@dataclass(frozen=True)
class EmotionPayload:
    """Дельты эмоционального состояния и стресса."""
    stress_delta: float = 0.0
    emotion_delta: float = 0.0
    emotion_tag: Optional[str] = None
    new_trauma: Optional[str] = None


@dataclass(frozen=True)
class ReputationPayload:
    """Дельты репутации во фракциях."""
    reputation_delta: float = 0.0


@dataclass(frozen=True)
class IdentityPayload:
    """Дельты воли, давления и целостности личности (R6.4 система слома)."""
    identity_integrity_delta: float = 0.0
    pressure_resistance_delta: float = 0.0
    will_state_override: Optional[str] = None


# БУДУЩЕЕ — не создаются сейчас, но структура готова
# @dataclass(frozen=True)
# class CombatPayload:
#     hp_delta: float = 0.0
#     pain_delta: float = 0.0
#     injuries: Tuple[InjuryDTO, ...] = ()
#     bleeding_delta: float = 0.0

# @dataclass(frozen=True)
# class PhysiologyPayload:
#     hunger_delta: float = 0.0
#     fatigue_delta: float = 0.0

# @dataclass(frozen=True)
# class SpatialPayload:
#     position_delta: Optional[Dict] = None
#     location_delta: Optional[str] = None
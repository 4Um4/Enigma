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
- Добавить SpatialPayload для пространственных дельт.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


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
    # ADR-049: Интеграл аффективного давления (передается в StateApplicator для NPCState.affective_load)
    affective_load: Optional[float] = None


@dataclass(frozen=True)
class ReputationPayload:
    """Дельты репутации во фракциях."""
    reputation_delta: float = 0.0


@dataclass(frozen=True)
class IdentityPayload:
    identity_integrity_delta: float = 0.0
    pressure_resistance_delta: float = 0.0
    # S28: Топология деформации пространства решений (PerceptualKernel)
    aggression_inhibition_delta: float = 0.0
    initiative_suppression_delta: float = 0.0
    compliance_bias_delta: float = 0.0
    will_state_override: Optional[str] = None
    # ADR-055: Труба захвата внимания (без магических коэффициентов подавления)
    recent_directive_data: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class PerceptionPayload:
    """ADR-O: Дельта обновления PerceptualKernel.
    Реальность течёт в восприятие, а не напрямую в эмоцию."""
    threat_gradient_delta: float = 0.0    # Рост ощущения угрозы
    uncertainty_delta: float = 0.0        # Рост неопределённости
    anomaly_score_delta: float = 0.0      # Рост ощущения аномальности
    dominant_emotion_hint: Optional[str] = None  # Подсказка для DecisionHub (fear/panic)


@dataclass(frozen=True)
class InjuryDTO:
    """Типизированная модель травмы (Injury — контейнер причины).
    
    Мастер Тай: 
    - severity != injury type. loss of function != destruction.
    - body_part — это combat interaction zone → target_zone.
    """
    damage_type: str              # slash, blunt, burn, disease
    target_zone: str              # head_eye_l, torso_groin, arm_r (функциональная зона)
    structural_damage: float      # 0.0 - 1.0 (физическое разрушение тканей)
    functional_loss: float        # 0.0 - 1.0 (потеря функции зоны)
    critical_effects: Tuple[str, ...] = ()  # severed, bleeding, infected


@dataclass(frozen=True)
class PhysiologyPayload:
    """Дельты физиологического состояния (Damage & Stress Propagation System).
    
    Мастер Тай: 
    - HP — производная (derived abstraction), центр модели — Functional Capacity.
    - Резолвер не пишет эмоции, он пишет физические последствия и сигналы (shock_impulse).
    - Эмоции и социалка реагируют на EventDTO с этими сигналами сами.
    """
    hp_delta: float = 0.0                  # Макро-LOD: агрегированная потеря функции
    pain_delta: float = 0.0                # Боль (0-100)
    fatigue_delta: float = 0.0             # Усталость (0-100)
    blood_loss_delta: float = 0.0          # Кровопотеря (0-1.0 шкала)
    shock_impulse: float = 0.0             # Физический шок / болевой удар (0-1.0) — сигнал для EmotionSubscriber
    add_injuries: Tuple[InjuryDTO, ...] = ()
    add_statuses: Tuple[str, ...] = ()     # bleeding, unconscious, crippled
    remove_statuses: Tuple[str, ...] = ()  # снятие статусов
# -*- coding: utf-8 -*-
"""
path: backend/app/models/state_delta.py
Назначение: Единый контракт мутаций NPCState — StateDeltas.
Зависимости: app.models.npc_state (EmotionTag, WillState)
Основные сущности: StateDeltas

Любой мутатор возвращает StateDeltas. StateApplicator — единственный потребитель.
Никаких dict-мутаций.

NOTE: psyche_engine — DEPRECATED (мёртвый код). WorldTickEngine использует
ProactiveDecision.deltas_dict → мигрировано в StateDeltas.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Union

from app.models.delta_payloads import (
    EmotionPayload,
    IdentityPayload,
    PhysiologyPayload,
    ReputationPayload,
    SocialPayload,
)
from app.models.npc_state import EmotionTag, WillState


class DeltaDomain(Enum):
    SOCIAL = "social"
    EMOTION = "emotion"
    REPUTATION = "reputation"
    IDENTITY = "identity"
    PHYSIOLOGY = "physiology"
    SPATIAL = "spatial"
    PERCEPTION = "perception"  # ADR-040: Обновление субъективной модели восприятия (PerceptualKernel)
    WILL = "WILL"  # Каузальный след конфликта воли (ADR-039)
    DOPAMINE = "dopamine"  # S-93: Reward Prediction Error (FEP). Эфемерный сигнал ошибки предсказания.


class ReductionPolicy(Enum):
    """Закон композиции мира (Мастер Тай): как дельты агрегируются во времени.

    ADDITIVE — линейная физика (Σ). Социальные изменения, репутация.
    BOUNDED_ADDITIVE — накопление с насыщением (Σ + clamp). Эмоции, стресс.
    OVERWRITE — дискретная реальность (last-write-wins). Идентичность, флаги.
    PHYSICS_COMPOSITE — эволюция состояния (S_t = F(S_{t-1}, impacts)).
        Тело не складывается, оно интегрирует историю воздействий.
        В _aggregate_deltas пропускается без merge, направляется в StateApplicator/ImpactEngine.
    """

    ADDITIVE = "additive"
    BOUNDED_ADDITIVE = "bounded_additive"
    OVERWRITE = "overwrite"
    PHYSICS_COMPOSITE = "physics_composite"


# Конституция мира: каждый домен знает свой закон редукции
DELTA_POLICY_REGISTRY: Dict[DeltaDomain, ReductionPolicy] = {
    DeltaDomain.SOCIAL: ReductionPolicy.ADDITIVE,
    DeltaDomain.EMOTION: ReductionPolicy.BOUNDED_ADDITIVE,
    DeltaDomain.REPUTATION: ReductionPolicy.ADDITIVE,
    DeltaDomain.IDENTITY: ReductionPolicy.OVERWRITE,
    DeltaDomain.PHYSIOLOGY: ReductionPolicy.PHYSICS_COMPOSITE,
    DeltaDomain.SPATIAL: ReductionPolicy.OVERWRITE,  # Позиция = факт
    # DEBT-DET-03: Явная политика для ранее неявных доменов
    DeltaDomain.PERCEPTION: ReductionPolicy.ADDITIVE,  # Угрозы/аномалии накапливаются
    DeltaDomain.WILL: ReductionPolicy.OVERWRITE,  # Конфликт воли = факт текущего тика
    DeltaDomain.DOPAMINE: ReductionPolicy.ADDITIVE,  # Ошибки предсказания накапливаются
}


# Union тип — IDE знает все варианты, autocomplete работает
DeltaPayload = Union[
    SocialPayload, EmotionPayload, ReputationPayload, IdentityPayload, PhysiologyPayload
]


@dataclass
class StateDeltas:
    """Дельты которые StateApplicator применит к NPCState атомарно.

    Единый язык мутаций для всех подсистем (Устав §2.3):
    - DecisionHub.compute() → DecisionResult.deltas: StateDeltas
    - WorldTickEngine → StateDeltas
    - SocialDecayHandler / ReputationDecayHandler → StateDeltas
    - Social propagation → StateDeltas

    # LOCKED v1: StateDeltas. Новые домены (physiology/spatial/economy)
    # → отдельный рефакторинг на type: Enum + payload.
    # Поля damage_delta, position_delta и т.д. в v1 НЕ добавляются.
    # TODO v2: split → SocialDelta/FactionDelta/EmotionDelta(BaseDelta)

    StateApplicator принимает только StateDeltas — никаких dict.
    """

    npc_id: Optional[str] = None  # маршрутизация к конкретному NPC

    # --- Маршрутизация: только один тип таргета в одной дельте ---
    intent_target: Optional[str] = None  # DecisionHub → player-facing
    social_target: Optional[str] = None  # Social decay/propagation → NPC→NPC
    faction_id: Optional[str] = None  # Reputation decay → фракция

    stress_delta: float = 0.0
    stress_delta_effective: float = 0.0
    emotion_delta: float = 0.0
    emotion_tag: Optional[EmotionTag] = None
    trust_delta: float = 0.0  # NPC→NPC, NPC→Player только
    fear_delta: float = 0.0  # NPC→NPC, NPC→Player только
    reputation_delta: float = 0.0  # Фракции только. Семантически изолировано от trust
    trait_updates: Dict[str, float] = field(default_factory=dict)
    new_trauma: Optional[str] = None

    # --- Причинность: источник дельты (Шаг A.3) ---
    source: str = "unknown"  # event_type или "break_system", "life_engine"

    # --- R6.4: Команды для системы слома ---
    identity_integrity_delta: float = 0.0
    pressure_resistance_delta: float = 0.0
    will_state_override: Optional[WillState] = None

    # --- v2: Domain-Tagged Typed Payloads ---
    domain: Optional[DeltaDomain] = None  # Домен мутации (v2)
    target: Optional[str] = (
        None  # Универсальный таргет (v2): player, npc_id, faction_id
    )
    payload: Optional[DeltaPayload] = None  # Типизированный payload (v2)

    def __post_init__(self) -> None:
        """Валидация: v1 (один тип таргета) + v2 (payload соответствует domain)."""
        _DOMAIN_PAYLOAD_MAP = {
            DeltaDomain.SOCIAL: SocialPayload,
            DeltaDomain.EMOTION: EmotionPayload,
            DeltaDomain.REPUTATION: ReputationPayload,
            DeltaDomain.IDENTITY: IdentityPayload,
            DeltaDomain.PHYSIOLOGY: PhysiologyPayload,
        }

        # v2 валидация: если указан domain, payload должен соответствовать
        if self.domain is not None and self.payload is not None:
            expected = _DOMAIN_PAYLOAD_MAP.get(self.domain)
            if expected and not isinstance(self.payload, expected):
                raise TypeError(
                    f"StateDeltas v2: domain {self.domain.value} требует {expected.__name__}, "
                    f"получен {type(self.payload).__name__}"
                )

        # v1 валидация (обратная совместимость, пока миграция не завершена)
        if self.domain is None:
            _targets = [
                t
                for t in (self.intent_target, self.social_target, self.faction_id)
                if t is not None
            ]
            if len(_targets) > 1:
                raise ValueError(
                    f"StateDeltas: только один тип таргета, "
                    f"получено: intent={self.intent_target}, "
                    f"social={self.social_target}, faction={self.faction_id}"
                )
            # reputation_delta допустим только с faction_id
            if self.reputation_delta != 0.0 and self.faction_id is None:
                raise ValueError("StateDeltas: reputation_delta требует faction_id")
            # trust_delta/fear_delta несовместимы с faction_id
            if self.faction_id is not None and (
                self.trust_delta != 0.0 or self.fear_delta != 0.0
            ):
                raise ValueError(
                    "StateDeltas: faction_id несовместим с trust_delta/fear_delta "
                    "(используйте reputation_delta)"
                )

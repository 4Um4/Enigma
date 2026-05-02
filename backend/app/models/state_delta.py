# -*- coding: utf-8 -*-
"""
path: backend/app/models/state_delta.py
Назначение: Единый контракт мутаций NPCState — StateDeltas.
Зависимости: app.models.npc_state (EmotionTag, WillState)
Основные сущности: StateDeltas

Любой мутатор возвращает StateDeltas. StateApplicator — единственный потребитель.
Никаких dict-мутаций.

NOTE: psyche_engine — DEPRECATED (мёртвый код). WorldTickEngine использует
ProactiveDecision.deltas_dict — кандидат на миграцию (отдельная задача).
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

from app.models.npc_state import EmotionTag, WillState


@dataclass
class StateDeltas:
    """Дельты которые StateApplicator применит к NPCState атомарно.
    
    Единый язык мутаций для всех подсистем (Устав §2.3):
    - DecisionHub.compute() → DecisionResult.deltas: StateDeltas
    - psyche_engine.apply_stress() → DEPRECATED (мёртвый код, не мигрировать)
    - WorldTickEngine → StateDeltas (после миграции)
    
    StateApplicator принимает только StateDeltas — никаких dict.
    """
    stress_delta:           float = 0.0
    stress_delta_effective: float = 0.0
    emotion_delta:          float = 0.0
    emotion_tag:     Optional[EmotionTag] = None
    trust_delta:     float = 0.0
    fear_delta:      float = 0.0
    trait_updates:   Dict[str, float] = field(default_factory=dict)
    new_trauma:      Optional[str] = None
    
    # --- Причинность: источник дельты (Шаг A.3) ---
    source:          str = "unknown"   # event_type или "break_system", "life_engine"
    
    # --- R6.4: Команды для системы слома ---
    identity_integrity_delta:   float = 0.0
    pressure_resistance_delta:  float = 0.0
    will_state_override: Optional[WillState] = None
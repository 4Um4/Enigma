"""
path: backend/app/services/calibration/profile.py
Назначение: Единный источник истины для калибруемых параметров.
            Регулирует поведение, НЕ определяет архитектуру (max_workers,
            causal stages, SSOT — вне Profile).
Зависимости: dataclasses
Основные сущности: CalibrationProfile
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationProfile:
    """Все калибруемые параметры ENIGMA. Значения = текущие runtime
    значения (behavior-identical). Изменение значений — через preset
    overlay (experiment_runner / config_overlay), НЕ прямой мутацией.

    INVARIANT: max_workers=1 (ADR-O-343) — НЕ ЗДЕСЬ.
    INVARIANT: SUM(drives)==1.0 (ADR-O-207) — НЕ ЗДЕСЬ.
    """

    # ── Opportunity (opportunity_engine.py) ──
    opp_w_attention: float = 0.35
    opp_w_distance: float = 0.30
    opp_w_weapon: float = 0.20
    opp_w_allies: float = 0.15
    opp_threshold: float = 0.65
    opp_max_distance_m: float = 30.0
    opp_max_ally_count: int = 4

    # ── OpportunityProducer (npc_tick_pipeline.py) ──
    opp_attention_range_m: float = 10.0

    # ── Epistemic ──
    accuse_confidence_threshold: float = 0.5
    enemy_trust_threshold: float = -30.0
    unknown_source_trust: float = 50.0
    direct_observation_reliability: float = 0.9
    claim_weight: float = 1.0
    same_source_boost: float = 0.2

    # ── Perception ──
    observation_sight_radius: float = 10.0
    hearing_radius: float = 10.0
    default_action_radius: float = 15.0

    # ── Dialogue Infra (safety: operational envelope) ──
    max_pending_tasks: int = 20
    max_rate_per_minute: int = 20
    llm_timeout_sec: float = 30.0
    max_sentences: int = 2
    dialogue_ttl: float = 180.0
    ui_ttl_sec: float = 7.0
    max_tasks_per_tick: int = 1

    # ── Windup (core/constants.py) ──
    attack_windup_duration_ticks: int = 2
    steal_windup_duration_ticks: int = 2

    # ── Decision (core/constants.py — already overlay-covered by S213) ──
    commitment_base_threshold: float = 0.15
    commitment_k: float = 2.5
    commitment_bonus_k: float = 0.10
    intent_decay_rate: float = 0.03
    intent_exhaustion_rate: float = 0.08
    intent_inertia_max_ticks: int = 10
    intent_inertia_weight: float = 0.20
    reactive_urgency_threshold: float = 0.8
    idle_pressure_accum_rate: float = 0.1
    idle_pressure_decay_rate: float = 0.05

    # ── Body / Physiology (vital_state.py) ──
    consciousness_threshold: float = 0.1
    pain_incapacitated: float = 70.0
    shock_incapacitated: float = 0.7

    @classmethod
    def default(cls) -> "CalibrationProfile":
        """Production-default profile. Behavior-identical to pre-021."""
        return cls()
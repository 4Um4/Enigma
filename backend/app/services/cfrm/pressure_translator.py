import logging
from typing import Any, Dict, Optional

from app.domain.decision_context import (
    ActionSpaceCompression,
    DecisionContext,
    UtilityFieldDeformation,
)
from app.models.cfrm import PsychologicalPressure
from app.models.npc_state import PerceptualKernel
from app.services.npc.behavior_modifiers import compute_behavior_modifiers

logger = logging.getLogger(__name__)


def translate_pressure_to_context(pressure: PsychologicalPressure) -> DecisionContext:
    """
    Непрерывная математическая проекция топологии давления в деформацию пространства решений.
    Страх подавляет агрессию и усиливает бегство. Доминирование усиливает подчинение.
    """
    # 1. Топологическая деформация (90% случаев)
    aggression_sup = min(1.0, (pressure.fear * 0.7) + pressure.dominance_shift)
    compliance_bias = pressure.directive_obedience + (pressure.dominance_shift * 0.5)
    escape_sal = pressure.fear * 0.6 + pressure.uncertainty * 0.2
    initiative_sup = (
        pressure.dominance_shift * 0.6
    )  # Доминирование подавляет инициативу

    # 2. Экстремальное сжатие (10% случаев - паралич воли)
    constraints = {}
    if pressure.fear > 0.8 and pressure.dominance_shift > 0.7:
        constraints["ATTACK"] = 0.1
        constraints["INTIMIDATE"] = 0.1

    return DecisionContext(
        deformation=UtilityFieldDeformation(
            aggression_suppression=aggression_sup,
            compliance_bias=compliance_bias,
            escape_salience=escape_sal,
            initiative_suppression=initiative_sup,
        ),
        compression=ActionSpaceCompression(constraints=constraints),
        source="cfrm_pressure",
    )


def translate_kernel_to_context(
    kernel: PerceptualKernel,
    body_state: Optional[Dict[str, Any]] = None,
    social_input_ema: float = 0.0,
    gregariousness: float = 0.5,
    has_active_commitment: bool = False,
) -> DecisionContext:
    """
    Проекция консолидированного восприятия (T-1) в топологию решений.
    Вызывается из LifeEngine/WorldTickEngine для передачи каузального контекста в DecisionHub.
    Разделение reactive (прерывание) и deliberative (решение) слоев.
    """
    # 1. Экстремальное сжатие (паралич воли — жесткие блокировки)
    constraints = {}
    if kernel.initiative_suppression > 0.8:
        constraints["ATTACK"] = 0.0
        constraints["INTIMIDATE"] = 0.0
    if kernel.aggression_inhibition > 0.9 and kernel.compliance_bias > 0.7:
        constraints["RESIST"] = 0.0

    # S189 ARCH-SLEEP Phase C: ActiveCommitment.
    # Если NPC куда-то идёт (активный транзит), он не может инициировать новые проактивные действия.
    # Оставляем только EMERGENCY (flee, attack).
    if has_active_commitment:
        for action in ["AMBUSH", "BLOCK_PATH", "OFFER_JOB", "REQUEST_SERVICE", "SPREAD_RUMOR", "CALL_FOR_HELP", "WARN", "TALK", "TRADE", "APPROACH"]:
            constraints[action] = 0.0

    # GAP3 FIX & NPIC: Соматическое Вето. Физиология vetoирует решения мозга.
    # §ENIGMA-003: Если тело неизвестно, агент не может действовать (Unknown ≠ Neutral).
    if not body_state:
        # Нет физического субстрата = полная невозможность физических действий
        logger.warning("[SOMATIC_VETO] body_state missing. Applying FULL VETO (NPIC).")
        for action in ["FLEE", "ATTACK", "APPROACH", "MANIPULATE", "INTIMIDATE"]:
            constraints[action] = 0.0
    else:
        pain = body_state.get("pain", 0.0) / 100.0  # ADR-094: Нормализация 0-100 → 0-1
        shock = body_state.get("shock_impulse", 0.0)
        blood_loss = body_state.get("blood_loss", 0.0)

        # ADR-O-383 (V1): хронические оси → feasibility. Action-set =
        # семантический прецедент acute blood_loss (физические/locomotion);
        # INTIMIDATE исключён — социально-поведенческое (вердикт Q2).
        # cap 0.3 = «существенно затруднено» (не «невозможно» — chronic).
        _fatigue = float(body_state.get("fatigue", 0.0)) / 100.0  # ADR-094
        _energy = float(body_state.get("energy", 100.0)) / 100.0
        if _fatigue > self._FATIGUE_HIGH_CANDIDATE or _energy < self._ENERGY_LOW_CANDIDATE:
            for action in ("FLEE", "ATTACK", "APPROACH", "MANIPULATE"):
                constraints[action] = min(constraints.get(action, 1.0), 0.3)

        if pain > 0.8:
            constraints["FLEE"] = 0.0  # Боль не позволяет бегствовать
        if shock > 0.7:
            constraints["ATTACK"] = 0.0  # Шок гасит агрессию
        if blood_loss > 0.6:
            # Кровопотеря снижает feasibility всех физических действий до 0.3
            for action in ["FLEE", "ATTACK", "APPROACH", "MANIPULATE"]:
                constraints[action] = min(constraints.get(action, 1.0), 0.3)

    # Социальные модификаторы из Field Channel (ADR-O-312)
    _social_mods = compute_behavior_modifiers(social_input_ema, gregariousness)

    # 2. Топологическая деформация (искривление utility-space)
    return DecisionContext(
        deformation=UtilityFieldDeformation(
            aggression_suppression=kernel.aggression_inhibition,
            initiative_suppression=kernel.initiative_suppression,
            compliance_bias=kernel.compliance_bias,
            escape_salience=kernel.threat_gradient * 0.5,
        ),
        compression=ActionSpaceCompression(constraints=constraints),
        source="perceptual_kernel",
        social_outgoing=_social_mods.social_outgoing,
        social_incoming=_social_mods.social_incoming,
    )

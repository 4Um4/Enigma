"""
path: /project/backend/app/services/npc/activity_catalog.py
Назначение: Living Activity — каталог деятельностей (L-A2 Catalog Freedom:
    индекс по потребностям желаний; роли дают приоры, не гейты — каталог
    НЕ тюрьма). v1: единственная запись EAT. SLEEP не входит (телесный
    контур Phase 0.6 — эталон, не мигрируемый случай). Расширение записи
    = правка реестра + тест (класс ADR-O-349).
Зависимости: app.domain.activity, app.domain.semantic_action
Основные сущности: EAT_SPEC, ACTIVITY_CATALOG
"""
from __future__ import annotations

from typing import Dict

from app.domain.activity import (
    ActivitySpec,
    ActivityStep,
    ActivityType,
    InterruptionPolicy,
    StepKind,
    SuccessCriterion,
    SuccessCriterionKind,
)
from app.domain.semantic_action import WorldActionType

# EAT — первое вертикальное доказательство петли
# PRESSURE → DESIRE → SEARCH → WORLD → ACTIVITY → SUCCESS/FAILURE →
# CONSEQUENCE → MEMORY. Потребление = BODY_ACTION (реестр WorldActionType
# не расширялся); истощение порции — damage-закон О6.
EAT_SPEC = ActivitySpec(
    activity_type=ActivityType.EAT,
    serves_subject="food",
    target_archetype="food_portion",
    steps=(
        ActivityStep(step_kind=StepKind.MOVE, action_type="", target_ref="", duration_ticks=1),
        ActivityStep(
            step_kind=StepKind.OBJECT_ACTION,
            action_type=WorldActionType.TAKE.value,
            target_ref="",
            duration_ticks=1,
        ),
        ActivityStep(
            step_kind=StepKind.BODY_ACTION,
            action_type="CONSUME",
            target_ref="",
            duration_ticks=3,
        ),
    ),
    success=SuccessCriterion(
        kind=SuccessCriterionKind.NEED_BELOW, need_name="hunger", threshold=0.2
    ),
    interruption_policy=InterruptionPolicy.STUB,
    priority_hint=6.0,
)

# ADR-O-391 (WORK, S256): SERVE — деятельность продавца по заказу.
# Материализация — work-pass (цель = order_id, не WorldObject-архетип:
# target_archetype пуст, desire-онсет этот spec не подберёт); запись в
# каталоге = честный реестр + терминальные lookup'ы (_SPEC_BY_TYPE).
# SuccessCriterion с пустым need_name: guard _terminate пропускает —
# SERVE не обнуляет потребностей (насыщается покупатель, не продавец).
SERVE_SPEC = ActivitySpec(
    activity_type=ActivityType.SERVE,
    serves_subject="service",
    steps=(
        ActivityStep(
            step_kind=StepKind.BODY_ACTION,
            action_type="SERVE",
            target_ref="",
            duration_ticks=2,
        ),
    ),
    success=SuccessCriterion(
        kind=SuccessCriterionKind.NEED_BELOW, need_name="", threshold=0.2
    ),
    interruption_policy=InterruptionPolicy.STUB,
    priority_hint=5.0,
)

ACTIVITY_CATALOG: Dict[str, ActivitySpec] = {
    EAT_SPEC.serves_subject: EAT_SPEC,
    SERVE_SPEC.serves_subject: SERVE_SPEC,
}

_SPEC_BY_TYPE: Dict[ActivityType, ActivitySpec] = {
    spec.activity_type: spec for spec in ACTIVITY_CATALOG.values()
}
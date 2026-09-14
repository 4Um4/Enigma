"""
path: /project/backend/app/domain/activity.py
Назначение: Living Activity — деятельность как ФАКТ (сон-прецедент:
    body_state["sleep_onset_tick"]), не ярлык. Состояние персистентно в
    npc["activity_state"]; владение/инерция — scene_state["active_commitments"]
    (reconcile-паттерн ADR-O-365 D-3). Activity ≠ Intent (амнезия тика):
    переживает тики через round-trip персист (ответ на вопрос 10.1.3).
Зависимости: dataclasses, typing (чистый домен)
Основные сущности: ActivityType, InterruptionPolicy, StepKind, ActivityStep,
    SuccessCriterion, ActivityState, ActivitySpec
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Tuple

# §12.1: ключи — константы
_KEY_ACTIVITY_ID = "activity_id"
_KEY_ACTIVITY_TYPE = "activity_type"
_KEY_DESIRE_ID = "desire_id"
_KEY_TARGET_REF = "target_ref"
_KEY_STEPS = "steps"
_KEY_STEP_INDEX = "step_index"
_KEY_STEP_STARTED = "step_started_tick"
_KEY_STARTED_TICK = "started_tick"
_KEY_POLICY = "interruption_policy"

_KEY_SK_KIND = "step_kind"
_KEY_SK_ACTION = "action_type"
_KEY_SK_TARGET = "target_ref"
_KEY_SK_DURATION = "duration_ticks"

_KEY_SC_KIND = "kind"
_KEY_SC_NEED = "need_name"
_KEY_SC_THRESHOLD = "threshold"


class ActivityType(str, Enum):
    """Закрытый реестр видов деятельности. Расширение = мини-ADR (O-349).
    SLEEP сюда НЕ входит: реализован телесным контуром Phase 0.6 и является
    эталоном, а не мигрируемым случаем (ТЗ 7.2)."""

    EAT = "eat"
    # ADR-O-389 (WORK, S256): обслуживание заказа. Материализуется
    # work-pass Фазы 0 (services/economy/work_orders.py): цель — заказ,
    # не WorldObject (D6: эль — эконом-онтология goods). Desire-онсет
    # конвертера для SERVE сознательно не используется.
    SERVE = "serve"


class InterruptionPolicy(str, Enum):
    """Что происходит с целью при прерывании (ответ на 10.1.4).
    STUB — цель сохраняется и возобновляется (INTERRUPTED → parent_id);
    ABANDON — осознанная отмена с записью причины в память."""

    STUB = "stub"
    ABANDON = "abandon"


class StepKind(str, Enum):
    """Куда исполняется шаг (закрытый реестр, расширение = мини-ADR).
    MOVE — MacroMovementGoal (движение = побочный эффект деятельности);
    OBJECT_ACTION — SemanticAction → WorldObjectStore (типизированные ops);
    BODY_ACTION — телесная петля конвертера (сон-прецедент, без LLM)."""

    MOVE = "move"
    OBJECT_ACTION = "object_action"
    BODY_ACTION = "body_action"


@dataclass(frozen=True)
class ActivityStep:
    """Шаг деятельности. action_type — строка-контракт: валидация против
    закрытых реестров (WorldActionType / Intent) — на исполнителе, не здесь:
    домен не знает W2 (чистота слоя 1.2)."""

    step_kind: StepKind
    action_type: str = ""
    target_ref: str = ""
    duration_ticks: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.step_kind, StepKind):
            object.__setattr__(self, "step_kind", StepKind(self.step_kind))
        if int(self.duration_ticks) < 1:
            object.__setattr__(self, "duration_ticks", 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            _KEY_SK_KIND: self.step_kind.value,
            _KEY_SK_ACTION: self.action_type,
            _KEY_SK_TARGET: self.target_ref,
            _KEY_SK_DURATION: int(self.duration_ticks),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActivityStep":
        return ActivityStep(
            step_kind=d.get(_KEY_SK_KIND, StepKind.MOVE.value),
            action_type=d.get(_KEY_SK_ACTION, ""),
            target_ref=d.get(_KEY_SK_TARGET, ""),
            duration_ticks=int(d.get(_KEY_SK_DURATION, 1)),
        )


class SuccessCriterionKind(str, Enum):
    """Структурированный критерий успеха (ответ на 10.1.5): predicate в Goal,
    НЕ строка (L4: ядро не парсит текст). TemporalSpec-реинкарнация."""

    NEED_BELOW = "need_below"   # потребность ниже порога: hunger < 0.2


@dataclass(frozen=True)
class SuccessCriterion:
    """Декларативный предикат успеха деятельности. Оценивается исполнителем
    в терминальной фазе конвертера (сон-прецедент: wake-факт пишет сам контур)."""

    kind: SuccessCriterionKind
    need_name: str = ""
    threshold: float = 0.2

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SuccessCriterionKind):
            object.__setattr__(self, "kind", SuccessCriterionKind(self.kind))

    def to_dict(self) -> Dict[str, Any]:
        return {
            _KEY_SC_KIND: self.kind.value,
            _KEY_SC_NEED: self.need_name,
            _KEY_SC_THRESHOLD: round(float(self.threshold), 4),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SuccessCriterion":
        return SuccessCriterion(
            kind=d.get(_KEY_SC_KIND, SuccessCriterionKind.NEED_BELOW.value),
            need_name=d.get(_KEY_SC_NEED, ""),
            threshold=float(d.get(_KEY_SC_THRESHOLD, 0.2)),
        )


@dataclass(frozen=True)
class ActivityState:
    """ФАКТ деятельности — персистентная часть npc-словаря.

    INVARIANT (ACTIVITY_ONSET_FACT): рождается с записанной причиной
    (desire_id) и адресом цели (target_ref), а не с ярлыком.
    INVARIANT (INTERRUPTION_PRESERVES_GOAL): политика прерывания хранится
    в факте; resume-токен = step_index.
    elapsed НЕ хранится: вычисляется из started_tick (§14 — единое время,
    никакого накопительного аккумулятора).
    """

    activity_id: str            # build_id(): детерминированный
    activity_type: ActivityType
    desire_id: str              # причина (ACTIVITY_ONSET_FACT)
    target_ref: str             # WorldTarget ref (v1: object_id)
    steps: Tuple[ActivityStep, ...]
    step_index: int = 0
    # Прогресс телесного шага: шаги BODY_ACTION длятся duration_ticks —
    # считается от step_started_tick (§14: производная времени, не счётчик)
    step_started_tick: int = -1
    started_tick: int = 0
    interruption_policy: InterruptionPolicy = InterruptionPolicy.STUB

    def __post_init__(self) -> None:
        if not isinstance(self.activity_type, ActivityType):
            object.__setattr__(self, "activity_type", ActivityType(self.activity_type))
        if not isinstance(self.interruption_policy, InterruptionPolicy):
            object.__setattr__(
                self, "interruption_policy", InterruptionPolicy(self.interruption_policy)
            )
        if not self.activity_id:
            raise ValueError("ActivityState без activity_id — нарушение детерминизма")
        if not self.desire_id:
            raise ValueError("ActivityState без desire_id — нарушение ACTIVITY_ONSET_FACT")

    def to_dict(self) -> Dict[str, Any]:
        return {
            _KEY_ACTIVITY_ID: self.activity_id,
            _KEY_ACTIVITY_TYPE: self.activity_type.value,
            _KEY_DESIRE_ID: self.desire_id,
            _KEY_TARGET_REF: self.target_ref,
            _KEY_STEPS: [s.to_dict() for s in self.steps],
            _KEY_STEP_INDEX: int(self.step_index),
            _KEY_STEP_STARTED: int(self.step_started_tick),
            _KEY_STARTED_TICK: int(self.started_tick),
            _KEY_POLICY: self.interruption_policy.value,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActivityState":
        return ActivityState(
            activity_id=d.get(_KEY_ACTIVITY_ID, ""),
            activity_type=d.get(_KEY_ACTIVITY_TYPE, ActivityType.EAT.value),
            desire_id=d.get(_KEY_DESIRE_ID, ""),
            target_ref=d.get(_KEY_TARGET_REF, ""),
            steps=tuple(ActivityStep.from_dict(s) for s in d.get(_KEY_STEPS, [])),
            step_index=int(d.get(_KEY_STEP_INDEX, 0)),
            step_started_tick=int(d.get(_KEY_STEP_STARTED, -1)),
            started_tick=int(d.get(_KEY_STARTED_TICK, 0)),
            interruption_policy=d.get(_KEY_POLICY, InterruptionPolicy.STUB.value),
        )

    @staticmethod
    def build_id(npc_id: str, activity_type: ActivityType, started_tick: int) -> str:
        """Детерминированный id (INV-REPLAY-DETERMINISM; uuid4 запрещён)."""
        return f"{npc_id}:{activity_type.value}:{int(started_tick)}"


@dataclass(frozen=True)
class ActivitySpec:
    """Каталожная запись (контракт; инстансы — в activity-каталоге сервиса).

    L-A2 (Catalog Freedom): каталог индексируется по потребностям желаний
    (serves_subject) и capabilities; роли дают ПРИОРЫ, не гейты.
    v1 инстансы не сериализуются (статический реестр кода); конфигурация —
    при появлении контента (WORK).
    """

    activity_type: ActivityType
    serves_subject: str                          # какое желание обслуживает: "food"
    steps: Tuple[ActivityStep, ...]              # шаблон шагов
    success: SuccessCriterion
    # WorldObject-архетип цели (строка W2-таблицы); после обязательных — default
    target_archetype: str = ""
    interruption_policy: InterruptionPolicy = InterruptionPolicy.STUB
    priority_hint: float = 6.0                   # шкала s203.4 (SURVIVAL≈6)
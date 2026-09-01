"""
path: backend/app/domain/object_fsms.py
Назначение: W3 — Object State Machine (ТЗ Часть II §22).
    Доменные ЧИСТЫЕ переходы: FSM-семантика объекта; слой НЕ знает о
    WorldObjectStore, НЕ делает IO, НЕ мутирует scene_state.
    Архитектура (вердикт Мастера): «FSM определяет семантический
    переход; Store определяет, где переход становится World State» —
    домен не вызывает стор (W3 не создаёт coupling, который W1 убрал).
    О1 (В10-наследие): OPEN в состоянии OPEN — легальный NO_OP:
    физическая доступность ≠ FSM-легальность; легальность решает
    ЭТОТ слой.
    О2 (chair): ТЗ-состояния AVAILABLE/OCCUPIED/HELD нормализованы
    W1 в отношения — переходы chair = ПОЛИТИКА над операциями
    отношений (apply_relation_transition), НЕ state-хирургия.
    W1-модель строго БОГАЧЕ ТЗ-состояний: HELD+BROKEN представимо
    (state=BROKEN при живом holder; auto-release запрещён,
    ADR-O-371) — effective_state (ADR-O-372) проецирует по
    приоритету BROKEN > HELD > OCCUPIED > AVAILABLE.
    О3 (MOVED): legacy-состояние ТЗ; перемещение = relocate_object
    (пространственная операция исполнителя), не FSM-переход.
    О4 (bed): FSM §22.1 есть, потребителя нет — честный
    REJECT(UNKNOWN_ARCHETYPE) до W4.
    О6 (damage): damage_object — pure; порог damage >= 1.0 →
    state=BROKEN — ДОМЕННЫЙ ЗАКОН в одном месте, без рекурсии в
    transition_object (damage — физика, не FSM-команда и не
    persistence-операция). Закон срабатывает в момент нанесения
    урона; после BREAK FSM живёт по ТЗ (BROKEN→OPEN легален) при
    сохранном damage-track — state это FSM, damage это физика.
    О7: TransitionResult (PASS | NO_OP | REJECT + reason), не bool —
    L4 Silent Failure Prohibition. Каждый REJECT несёт непустую
    причину. Политика chair проверяет предусловия ДО доменного
    вызова: расхождение policy/domain = ГРОМКИЙ баг (исключение
    propagate'ится; except→REJECT запрещён — INV-SILENT-FAILURE).
    Авторизация актёра (OCCUPANT_IS/HOLDER_IS) — НЕ здесь: гейт
    исполнения = ревалидация precondition-кортежей W2 (ADR-O-372,
    В9). actor_id в transition_object — только ДАННЫЕ (цель
    отношения для SIT/TAKE).
Зависимости: dataclasses, enum, typing, app.domain.world_object,
    app.domain.semantic_action
Основные сущности: TransitionVerdict, TransitionResult,
    transition_object, damage_object
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Optional

from app.domain.semantic_action import WorldActionType
from app.domain.world_object import (
    CarrierMode,
    ObjectRelationKind,
    WorldObject,
    apply_relation_transition,
    dataclass_replace,
)


class TransitionVerdict(str, Enum):
    """Вердикты доменного FSM-перехода (О7: структура, не bool)."""
    PASS = "PASS"
    NO_OP = "NO_OP"    # О1: действие легально, состояние уже целевое
    REJECT = "REJECT"  # всегда с непустой reason (L4)


@dataclass(frozen=True)
class TransitionResult:
    """Результат доменного перехода. new_obj — при PASS и NO_OP
    (NO_OP возвращает исходный объект для единообразия caller'а);
    при REJECT — None (мир не изменился).

    О8 (вердикт Мастера, ADR-O-376): структурированный факт перехода —
    old_state + topology_effect. W3 НЕ перестраивает spatial graph —
    он порождает факт; invalidate/recompile решает spatial-слой (W5).
    Граница сохранена: FSM-семантика не знает о графе."""
    verdict: TransitionVerdict
    reason: str = ""
    new_obj: Optional[WorldObject] = None
    old_state: Optional[str] = None

    @property
    def topology_effect(self) -> bool:
        """True = PASS-переход объекта, влияющего на проходимость
        (door — wall openings, graph_compiler). NO_OP/REJECT мир не
        меняют. Консервативен (LOCK/UNLOCK тоже помечены): релевантность
        решает spatial-потребитель, не источник факта."""
        return (
            self.verdict is TransitionVerdict.PASS
            and self.new_obj is not None
            and self.new_obj.archetype == "door"
        )


# ── FSM-таблицы ТЗ §22.1 (state-based архетипы) ─────────────────────
# door/container хранят FSM в state-поле (настоящий FSM, W1).
# chair FSM живёт в отношениях W1 — отдельная политика ниже.
# KNOCK / PASS_THROUGH / KICK / DISCARD — НЕ FSM-переходы (события,
# damage-пайплайн О6, despawn): этот слой их честно REJECT'ит.
# ТЗ-точность: LOCKED→CLOSED только через UNLOCK; BROKEN→CLOSED
# только через REPAIR; container DESTROYED — terminal без REPAIR.

_DOOR_FSM: Dict[str, Dict[WorldActionType, str]] = {
    "CLOSED": {
        WorldActionType.OPEN: "OPEN",
        WorldActionType.LOCK: "LOCKED",
        WorldActionType.BREAK: "BROKEN",
    },
    "OPEN": {WorldActionType.CLOSE: "CLOSED"},
    "LOCKED": {
        WorldActionType.UNLOCK: "CLOSED",
        WorldActionType.BREAK: "BROKEN",
    },
    "BROKEN": {
        WorldActionType.OPEN: "OPEN",      # ТЗ: BROKEN→{OPEN, CLOSED}
        WorldActionType.REPAIR: "CLOSED",  # CLOSED-цель из BROKEN = REPAIR
    },
}

_CONTAINER_FSM: Dict[str, Dict[WorldActionType, str]] = {
    "CLOSED": {
        WorldActionType.OPEN: "OPEN",
        WorldActionType.LOCK: "LOCKED",
        WorldActionType.BREAK: "DESTROYED",
    },
    "OPEN": {WorldActionType.CLOSE: "CLOSED"},
    "LOCKED": {
        WorldActionType.UNLOCK: "CLOSED",
        WorldActionType.BREAK: "DESTROYED",
    },
    "DESTROYED": {},  # terminal (ТЗ §22.1)
}

# ── Damage-policy (О6, вердикт Мастера): archetype-specific ────────
# damage >= 1.0 → терминальное состояние АРХЕТИПА, не универсальный
# BROKEN: container DESTROYED — терминален и не ремонтопригоден (ТЗ
# §22.1: из DESTROYED переходов нет); door/chair BROKEN — ремонтопригодны
# (REPAIR). Unknown archetype → W0 damage-track default. Физический
# закон — над-FSM: таблицы §22.1 — действие-переходы; damage-порог —
# физика, которая их обгоняет (открытую дверь тоже можно сломать).
_DAMAGE_TERMINAL_STATE: Dict[str, str] = {
    "door": "BROKEN",
    "chair": "BROKEN",
    "container": "DESTROYED",
}
_DAMAGE_TERMINAL_DEFAULT = "BROKEN"


def _transition_simple_fsm(
    obj: WorldObject,
    action: WorldActionType,
    fsm: Dict[str, Dict[WorldActionType, str]],
) -> TransitionResult:
    """Переход для state-based архетипов (door, container).

    О1 (В10-наследие): resolver выдаёт пару OPEN+CLOSE в состоянии
    OPEN — исполнение OPEN при уже-OPEN легально как NO_OP
    (каузального изменения мира нет). Поведение синхронизировано с
    физикой: BREAK ставит damage=1.0, REPAIR сбрасывает в 0.0.
    """
    if obj.state == "OPEN" and action is WorldActionType.OPEN:
        return TransitionResult(
            TransitionVerdict.NO_OP, reason="ALREADY_OPEN", new_obj=obj)

    allowed = fsm.get(obj.state, {})
    target = allowed.get(action)
    if target is None:
        return TransitionResult(
            TransitionVerdict.REJECT,
            reason=f"INVALID_TRANSITION({obj.archetype}:{obj.state}"
                   f"+{action.value})")
    if action is WorldActionType.BREAK:
        # Слом согласован с законом О6: damage-track = 1.0.
        return TransitionResult(
            TransitionVerdict.PASS,
            new_obj=dataclass_replace(obj, state=target, damage=1.0))
    if action is WorldActionType.REPAIR:
        # Починка восстанавливает и физический track (damage=0.0).
        return TransitionResult(
            TransitionVerdict.PASS,
            new_obj=dataclass_replace(obj, state=target, damage=0.0))
    return TransitionResult(
        TransitionVerdict.PASS,
        new_obj=dataclass_replace(obj, state=target))


def _transition_chair(
    obj: WorldObject,
    action: WorldActionType,
    actor_id: Optional[str],
) -> TransitionResult:
    """Переход chair (О2: ПОЛИТИКА над отношениями W1).

    Отображение ТЗ §22.1 → операции отношений:
      SIT → establish OCCUPIED_BY(actor)
      STAND_UP → release OCCUPIED_BY
      TAKE → establish HELD_BY(actor)
      PLACE / DROP / THROW → release HELD_BY (пространственная часть
        — relocate, составляется исполнителем ПОСЛЕ release)
      BREAK → state=BROKEN + damage=1.0 (отношения НЕ трогаем)
      REPAIR → state=AVAILABLE + damage=0.0 (отношения НЕ трогаем)

    Предусловия проверяются ДО доменного вызова — детерминированный
    REJECT с причиной; исключение из apply_relation_transition после
    прошедших предусловий = рассинхрон policy/domain → propagate
    (громкий баг, L4; except-конверсия запрещена).
    """
    if obj.state == "BROKEN":
        if action is WorldActionType.REPAIR:
            # Отношения сохраняются: held-сломанный-починенный
            # проецируется как HELD (модель W1 богаче ТЗ, О2).
            return TransitionResult(
                TransitionVerdict.PASS,
                new_obj=dataclass_replace(
                    obj, state="AVAILABLE", damage=0.0))
        return TransitionResult(
            TransitionVerdict.REJECT,
            reason=f"IS_BROKEN({action.value} недоступен)")

    if action is WorldActionType.BREAK:
        # ТЗ §22.1: OCCUPIED→{AVAILABLE} — ломать занятое нельзя.
        if obj.occupancy is not None:
            return TransitionResult(
                TransitionVerdict.REJECT, reason="OCCUPIED_NO_BREAK")
        # holder сохраняется: auto-release запрещён (ADR-O-371);
        # effective_state приоритизирует BROKEN (ADR-O-372).
        return TransitionResult(
            TransitionVerdict.PASS,
            new_obj=dataclass_replace(obj, state="BROKEN", damage=1.0))

    if action is WorldActionType.SIT:
        if not actor_id:
            return TransitionResult(
                TransitionVerdict.REJECT, reason="ACTOR_REQUIRED")
        if obj.occupancy is not None:
            return TransitionResult(
                TransitionVerdict.REJECT, reason="ALREADY_OCCUPIED")
        if obj.carrier_mode is not CarrierMode.FREE:
            return TransitionResult(
                TransitionVerdict.REJECT,
                reason=f"NOT_FREE({obj.carrier_mode.value})")
        return TransitionResult(
            TransitionVerdict.PASS,
            new_obj=apply_relation_transition(
                obj, ObjectRelationKind.OCCUPIED_BY, target_id=actor_id))

    if action is WorldActionType.TAKE:
        if not actor_id:
            return TransitionResult(
                TransitionVerdict.REJECT, reason="ACTOR_REQUIRED")
        if obj.occupancy is not None:
            # ТЗ §22.1: OCCUPIED→{AVAILABLE} — взять занятое нельзя.
            return TransitionResult(
                TransitionVerdict.REJECT, reason="OCCUPIED_NO_TAKE")
        if obj.carrier_mode is not CarrierMode.FREE:
            return TransitionResult(
                TransitionVerdict.REJECT,
                reason=f"NOT_FREE({obj.carrier_mode.value})")
        return TransitionResult(
            TransitionVerdict.PASS,
            new_obj=apply_relation_transition(
                obj, ObjectRelationKind.HELD_BY, target_id=actor_id))

    if action is WorldActionType.STAND_UP:
        if obj.occupancy is None:
            return TransitionResult(
                TransitionVerdict.REJECT, reason="NOT_OCCUPIED")
        return TransitionResult(
            TransitionVerdict.PASS,
            new_obj=apply_relation_transition(
                obj, ObjectRelationKind.OCCUPIED_BY, target_id=None))

    if action in (WorldActionType.PLACE, WorldActionType.DROP,
                  WorldActionType.THROW):
        if obj.holder is None:
            return TransitionResult(
                TransitionVerdict.REJECT, reason="NOT_HELD")
        return TransitionResult(
            TransitionVerdict.PASS,
            new_obj=apply_relation_transition(
                obj, ObjectRelationKind.HELD_BY, target_id=None))

    if action is WorldActionType.MOVE:
        # О3: MOVED — legacy; перемещение = relocate (исполнитель).
        return TransitionResult(
            TransitionVerdict.REJECT, reason="SPATIAL_OPERATION")

    return TransitionResult(
        TransitionVerdict.REJECT,
        reason=f"INVALID_TRANSITION(chair:{action.value})")


def transition_object(
    obj: WorldObject,
    action: WorldActionType,
    actor_id: Optional[str] = None,
) -> TransitionResult:
    """W3: доменный FSM-переход (ТЗ §22.1). Pure: без IO, без store."""
    if obj.archetype == "door":
        _result = _transition_simple_fsm(obj, action, _DOOR_FSM)
    elif obj.archetype == "container":
        _result = _transition_simple_fsm(obj, action, _CONTAINER_FSM)
    elif obj.archetype == "chair":
        _result = _transition_chair(obj, action, actor_id)
    else:
        # О4: bed и прочие — до W4 нет ни реестра, ни потребителя.
        _result = TransitionResult(
            TransitionVerdict.REJECT,
            reason=f"UNKNOWN_ARCHETYPE({obj.archetype})")
    # О8: факт перехода несёт происхождение (old_state); заполняется
    # в единой точке диспетчера — фабрики не дублируют.
    if _result.old_state is None:
        _result = replace(_result, old_state=obj.state)
    return _result


def damage_object(obj: WorldObject, amount: float) -> WorldObject:
    """W3 О6: pure физика повреждения. ДОМЕННЫЙ ЗАКОН (не политика,
    не рекурсия в transition_object): damage >= 1.0 → state=BROKEN —
    порог определён ровно в одном месте. Закон срабатывает при
    нанесении урона; после BREAK FSM живёт по ТЗ (BROKEN→OPEN), а
    damage-track сохраняется — REPAIR единственный сброс.
    Кинетика урона (сколько наносит удар) — W4+ (combat wiring);
    этот слой применяет готовое число. Отношения W1 не трогает.
    """
    if amount < 0.0:
        raise ValueError(
            f"damage_object {obj.object_id}: отрицательный amount "
            f"({amount}) — лечение не через damage (REPAIR)")
    new_damage = min(1.0, obj.damage + amount)
    if new_damage >= 1.0:
        new_state = _DAMAGE_TERMINAL_STATE.get(
            obj.archetype, _DAMAGE_TERMINAL_DEFAULT)
    else:
        new_state = obj.state
    return dataclass_replace(obj, damage=new_damage, state=new_state)

"""
path: backend/app/domain/world_object.py
Назначение: W0/W1 — семантический объект мира (ADR-O-371).
    WorldObject — immutable dataclass с реляционно-нормализованными
    отношениями: каждое топологическое отношение хранится канонически
    НА ОДНОЙ СТОРОНЕ (single-side canonical). Зеркальные/derived ПОЛЯ
    запрещены (mirror = зомби-истина, урок S215): список содержимого
    контейнера — ЗАПРОС, не поле.
    CarrierMode (FREE | HELD | CONTAINED | ATTACHED) — онтология
    авторитета позиции: ровно ОДИН источник истины координат объекта.
    Матрица конфликтов сверх carrier-режимов — калибруемая ПОЛИТИКА,
    не онтология (вердикт Мастера, S226): W1 policy-правил не содержит.
    Мутация guarded-полей — ТОЛЬКО через типизированные операции
    (apply_relation_transition / relocate_object, вызываемые
    WorldObjectStore); generic update(**changes) отсутствует
    by construction — нелегального пути записи просто нет.
    INVARIANT (W0): ни одно поле не ссылается на sprite, mesh,
    texture, animation (ТЗ §17, §19.3).
Зависимости: dataclasses, typing, app.domain.exceptions
Основные сущности: WorldObject, WorldObjectState, ObjectRelationKind,
    CarrierMode, ObjectRelation, build_world_object,
    apply_relation_transition, relocate_object
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.domain.exceptions import OntologyViolationError

# ═══ Ключи сериализации — КОНСТАНТЫ (Устав §12.1: inline-строки в
# сериализационных адаптерах запрещены — следующий баг после W0) ═══

_K_OBJECT_ID = "object_id"
_K_ARCHETYPE = "archetype"
_K_LOCATION_ID = "location_id"
_K_POSITION = "position"
_K_STATE = "state"
_K_HOLDER = "holder"
_K_CONTAINER_ID = "container_id"
_K_SUPPORTED_BY = "supported_by"
_K_ATTACHMENT = "attachment"
_K_OCCUPANCY = "occupancy"
_K_USED_BY = "used_by"
_K_OWNERSHIP = "ownership"
_K_DAMAGE = "damage"
_K_INTERACTION_HISTORY_REF = "interaction_history_ref"


class WorldObjectState(str, Enum):
    """Базовые состояния объекта (damage track).
    Archetype-specific FSMs (CLOSED/OPEN/LOCKED) — в W3."""
    INTACT = "INTACT"
    DAMAGED = "DAMAGED"
    BROKEN = "BROKEN"
    DESTROYED = "DESTROYED"


class ObjectRelationKind(str, Enum):
    """Семь топологических отношений W1 (ТЗ §20.3). Каноническое
    хранение — single-side: каждое отношение живёт ровно в одном поле
    WorldObject. ObjectRelation (DTO ниже) — только проекция для
    запросов, никогда не источник истины."""
    LOCATED_AT = "LOCATED_AT"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTAINED_BY = "CONTAINED_BY"
    OCCUPIED_BY = "OCCUPIED_BY"
    HELD_BY = "HELD_BY"
    ATTACHED_TO = "ATTACHED_TO"
    USED_BY = "USED_BY"


class CarrierMode(str, Enum):
    """Онтология авторитета позиции: РОВНО ОДИН режим — кто владелец
    координат объекта. Это не удобство, а единственность источника
    истины. Конфликты сверх carrier-режимов (можно ли взять занятый
    стул и т.п.) — калибруемая ПОЛИТИКА (W2/W3), не онтология
    (вердикт Мастера, S226)."""
    FREE = "FREE"              # авторитет позиции: location_id + position
    HELD = "HELD"              # позиция производная от holder (npc_id)
    CONTAINED = "CONTAINED"    # позиция производная от container_id
    ATTACHED = "ATTACHED"      # позиция производная от attachment (host)


@dataclass(frozen=True)
class ObjectRelation:
    """Query/projection DTO отношения (ТЗ §20.2). Не хранится — строится
    из полей WorldObject по запросу. Семантика target_id зависит от kind:
    npc_id (OCCUPIED_BY, HELD_BY, USED_BY), object_id (SUPPORTED_BY,
    CONTAINED_BY, host ATTACHED_TO), location_id (LOCATED_AT)."""
    kind: ObjectRelationKind
    target_id: str
    slot: Optional[str] = None   # только ATTACHED_TO


@dataclass(frozen=True)
class WorldObject:
    """Семантический объект мира. Существует независимо от renderer.

    INVARIANT (W0): ни одно поле не ссылается на sprite, mesh, texture
    или animation (ТЗ §17, §19.3).

    INVARIANT (W1): реляционная нормализация — canonical single-side.
    Позиция авторитетна ТОЛЬКО в carrier_mode == FREE; у производных
    режимов (HELD/CONTAINED/ATTACHED) position вычисляется владельцем
    (W3/W4), хранимое значение — кэш последней известной, не истина.
    """

    # ── Идентичность и размещение ──────────────────────────────────
    object_id: str                                # детерминированный; uuid4 запрещён
    archetype: str                                # "door", "chair", "container", ...
    location_id: str                              # LOCATED_AT: текущая локация
    position: Tuple[float, float]                 # мир (метры); авторитетна только в FREE
    state: str                                    # archetype-specific FSM (W3)

    # ── Топологические отношения (canonical, single-side) ──────────
    holder: Optional[str] = None                  # HELD_BY: npc_id
    container_id: Optional[str] = None            # CONTAINED_BY: object_id
    supported_by: Optional[str] = None            # SUPPORTED_BY: object_id
    attachment: Optional[Tuple[str, str]] = None  # ATTACHED_TO: (host_id, slot) — атомарно
    occupancy: Optional[str] = None               # OCCUPIED_BY: npc_id (chair/bed)
    used_by: Optional[str] = None                 # USED_BY: npc_id (tool in hand)

    # ── Прочее ─────────────────────────────────────────────────────
    ownership: Optional[str] = None               # npc_id владельца
    damage: float = 0.0                           # 0.0 (intact) ... 1.0 (destroyed)
    interaction_history_ref: Optional[str] = None # ref в L1Chronicle (W3)

    def __post_init__(self) -> None:
        """Онтологическая валидация на границе создания — контракт,
        не policy. Чистая: без IO, без знания о других объектах
        (существование целей и циклы связей — зона WorldObjectStore)."""
        if not self.object_id:
            raise OntologyViolationError("WorldObject: object_id пуст")
        if not self.location_id:
            raise OntologyViolationError(
                f"WorldObject {self.object_id}: location_id пуст")
        if not 0.0 <= self.damage <= 1.0:
            raise OntologyViolationError(
                f"WorldObject {self.object_id}: damage={self.damage} вне [0.0, 1.0]")
        if self.attachment is not None:
            _host, _slot = self.attachment
            if not _host or not _slot:
                raise OntologyViolationError(
                    f"WorldObject {self.object_id}: attachment обязан быть "
                    f"(host_id, slot) с непустыми компонентами — атомарность")
        # Carrier exclusivity: ровно один источник авторитета позиции.
        _carriers = [
            _c for _c in (self.holder, self.container_id, self.attachment)
            if _c is not None
        ]
        if len(_carriers) > 1:
            raise OntologyViolationError(
                f"WorldObject {self.object_id}: несколько carrier-отношений "
                f"(holder/container_id/attachment) — позиция не может иметь "
                f"два источника истины")
        # SUPPORTED_BY онтологически совместим только с FREE: держимая/
        # вложенная/прикреплённая вещь не может одновременно «лежать на».
        if self.supported_by is not None and _carriers:
            raise OntologyViolationError(
                f"WorldObject {self.object_id}: SUPPORTED_BY несовместим с "
                f"carrier-отношением")
        # OCCUPIED_BY совместим только с FREE: сидящий NPC привязан к
        # позиции стула; стул в чужом carrier-режиме рвёт эту цепочку.
        if self.occupancy is not None and _carriers:
            raise OntologyViolationError(
                f"WorldObject {self.object_id}: OCCUPIED_BY несовместим с "
                f"carrier-отношением")

    @property
    def carrier_mode(self) -> CarrierMode:
        """Ровно один режим (exclusivity гарантирован __post_init__)."""
        if self.holder is not None:
            return CarrierMode.HELD
        if self.container_id is not None:
            return CarrierMode.CONTAINED
        if self.attachment is not None:
            return CarrierMode.ATTACHED
        return CarrierMode.FREE

    def project_relations(self) -> Tuple[ObjectRelation, ...]:
        """Чистая проекция всех отношений объекта (query DTO, свежий
        tuple). Содержимое контейнера сюда НЕ входит — это запрос к
        WorldObjectStore по container_id (inverse-проекция)."""
        rels: List[ObjectRelation] = [
            ObjectRelation(kind=ObjectRelationKind.LOCATED_AT,
                           target_id=self.location_id),
        ]
        if self.supported_by is not None:
            rels.append(ObjectRelation(
                kind=ObjectRelationKind.SUPPORTED_BY,
                target_id=self.supported_by))
        if self.container_id is not None:
            rels.append(ObjectRelation(
                kind=ObjectRelationKind.CONTAINED_BY,
                target_id=self.container_id))
        if self.occupancy is not None:
            rels.append(ObjectRelation(
                kind=ObjectRelationKind.OCCUPIED_BY,
                target_id=self.occupancy))
        if self.holder is not None:
            rels.append(ObjectRelation(
                kind=ObjectRelationKind.HELD_BY,
                target_id=self.holder))
        if self.attachment is not None:
            rels.append(ObjectRelation(
                kind=ObjectRelationKind.ATTACHED_TO,
                target_id=self.attachment[0],
                slot=self.attachment[1]))
        if self.used_by is not None:
            rels.append(ObjectRelation(
                kind=ObjectRelationKind.USED_BY,
                target_id=self.used_by))
        return tuple(rels)

    def to_dict(self) -> Dict[str, Any]:
        """Serialization для scene_state (только JSON-безопасные типы)."""
        return {
            _K_OBJECT_ID: self.object_id,
            _K_ARCHETYPE: self.archetype,
            _K_LOCATION_ID: self.location_id,
            _K_POSITION: list(self.position),
            _K_STATE: self.state,
            _K_HOLDER: self.holder,
            _K_CONTAINER_ID: self.container_id,
            _K_SUPPORTED_BY: self.supported_by,
            _K_ATTACHMENT: (
                [self.attachment[0], self.attachment[1]]
                if self.attachment is not None else None
            ),
            _K_OCCUPANCY: self.occupancy,
            _K_USED_BY: self.used_by,
            _K_OWNERSHIP: self.ownership,
            _K_DAMAGE: self.damage,
            _K_INTERACTION_HISTORY_REF: self.interaction_history_ref,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "WorldObject":
        """Deserialization из scene_state. Сейвов старой W0-схемы не
        существует (subtree никогда не персистился — ADR-O-371 W0
        CONTRACT CORRECTION), поэтому старые ключи (topology_relations,
        containment, affordances) молча игнорируются без fallback."""
        _att_raw = d.get(_K_ATTACHMENT)
        return WorldObject(
            object_id=d[_K_OBJECT_ID],
            archetype=d[_K_ARCHETYPE],
            location_id=d[_K_LOCATION_ID],
            position=tuple(d.get(_K_POSITION, (0.0, 0.0))),
            state=d.get(_K_STATE, WorldObjectState.INTACT.value),
            holder=d.get(_K_HOLDER),
            container_id=d.get(_K_CONTAINER_ID),
            supported_by=d.get(_K_SUPPORTED_BY),
            attachment=(
                (_att_raw[0], _att_raw[1])
                if _att_raw is not None else None
            ),
            occupancy=d.get(_K_OCCUPANCY),
            used_by=d.get(_K_USED_BY),
            ownership=d.get(_K_OWNERSHIP),
            damage=float(d.get(_K_DAMAGE, 0.0)),
            interaction_history_ref=d.get(_K_INTERACTION_HISTORY_REF),
        )


def build_world_object(
    object_id: str,
    archetype: str,
    location_id: str,
    position: Tuple[float, float],
    state: str = WorldObjectState.INTACT.value,
    *,
    ownership: Optional[str] = None,
    damage: float = 0.0,
    interaction_history_ref: Optional[str] = None,
) -> WorldObject:
    """Единственная фабрика рождения объекта (§13.4: фабрика вместо
    конструктор-синтеза в тестах). Объект рождается ТОЛЬКО в FREE без
    отношений: связывание — отдельная операция. Рождение и связывание
    не смешиваются — каузальная цепочка остаётся явной (W3 запишет её
    в L1)."""
    return WorldObject(
        object_id=object_id,
        archetype=archetype,
        location_id=location_id,
        position=position,
        state=state,
        ownership=ownership,
        damage=damage,
        interaction_history_ref=interaction_history_ref,
    )


# ── Карта «отношение → поле» для переходов ────────────────────────
# Carrier-поля: именно они конфликтуют за авторитет позиции.
_CARRIER_FIELDS: Dict[ObjectRelationKind, str] = {
    ObjectRelationKind.HELD_BY: "holder",
    ObjectRelationKind.CONTAINED_BY: "container_id",
    ObjectRelationKind.ATTACHED_TO: "attachment",
}
# Не-carrier отношения: совместимы только с FREE (SUPPORTED, OCCUPIED)
# или независимы (USED).
_FREE_ONLY_FIELDS: Dict[ObjectRelationKind, str] = {
    ObjectRelationKind.SUPPORTED_BY: "supported_by",
    ObjectRelationKind.OCCUPIED_BY: "occupancy",
}
_INDEPENDENT_FIELDS: Dict[ObjectRelationKind, str] = {
    ObjectRelationKind.USED_BY: "used_by",
}


def apply_relation_transition(
    obj: WorldObject,
    kind: ObjectRelationKind,
    target_id: Optional[str],
    slot: Optional[str] = None,
) -> WorldObject:
    """Pure переход ОДНОГО отношения (прецедент: transition_commitment).

    target_id=None  → RELEASE (сброс отношения).
    target_id!=None → ESTABLISH (установка).

    ОНТОЛОГИЯ (проверяется здесь):
      - carrier exclusivity: establish carrier'а при живом любом
        другом carrier → OntologyViolationError. Никаких auto-release:
        путь W3 — явная цепочка release → establish (честность перехода
        важнее удобства, каузальная цепочка не скрывается);
      - SUPPORTED_BY / OCCUPIED_BY устанавливаются только в FREE;
      - ATTACHED_TO атомарен: (target_id, slot) вместе;
      - release не-установленного отношения → OntologyViolationError
        (STRICT: молчаливый no-op маскировал бы рассинхрон конвейера).

    ПОЛИТИКА (НЕ проверяется — W2/W3): можно ли взять занятый стул,
    существует ли слот у host, достаточно ли рук у NPC, вес, encumbrance.
    Существование target-объекта и циклы связей — WorldObjectStore
    (шаг 2): domain не знает о других объектах.
    """
    if kind is ObjectRelationKind.LOCATED_AT:
        raise OntologyViolationError(
            f"WorldObject {obj.object_id}: LOCATED_AT меняется только "
            f"через relocate_object — позиция не отношение")

    if target_id is None:
        # ── RELEASE ────────────────────────────────────────────────
        _field = (
            _CARRIER_FIELDS.get(kind)
            or _FREE_ONLY_FIELDS.get(kind)
            or _INDEPENDENT_FIELDS.get(kind)
        )
        if _field is None:
            raise OntologyViolationError(f"Неизвестный kind отношения: {kind}")
        if getattr(obj, _field) is None:
            raise OntologyViolationError(
                f"WorldObject {obj.object_id}: release {kind.value} — "
                f"отношение не установлено (STRICT: рассинхрон конвейера)")
        return dataclass_replace(obj, **{_field: None})

    if not target_id:
        raise OntologyViolationError(
            f"WorldObject {obj.object_id}: пустой target_id для {kind.value}")

    # ── ESTABLISH ─────────────────────────────────────────────────
    if kind in _CARRIER_FIELDS:
        if obj.carrier_mode is not CarrierMode.FREE:
            raise OntologyViolationError(
                f"WorldObject {obj.object_id}: establish {kind.value} при "
                f"carrier_mode={obj.carrier_mode.value} — сначала явный "
                f"release текущего carrier (auto-release запрещён)")
        if kind is ObjectRelationKind.ATTACHED_TO:
            if slot is None or not slot:
                raise OntologyViolationError(
                    f"WorldObject {obj.object_id}: ATTACHED_TO требует slot "
                    f"— отношение атомарно (host_id, slot)")
            return dataclass_replace(
                obj, attachment=(target_id, slot))
        return dataclass_replace(obj, **{_CARRIER_FIELDS[kind]: target_id})

    if kind in _FREE_ONLY_FIELDS:
        if obj.carrier_mode is not CarrierMode.FREE:
            raise OntologyViolationError(
                f"WorldObject {obj.object_id}: {kind.value} совместим только "
                f"с FREE (carrier={obj.carrier_mode.value})")
        return dataclass_replace(obj, **{_FREE_ONLY_FIELDS[kind]: target_id})

    # USED_BY — независимое отношение: атомарная замена = передача
    # инструмента от одного пользователя другому (легитимный переход).
    return dataclass_replace(obj, used_by=target_id)


def relocate_object(
    obj: WorldObject,
    location_id: str,
    position: Tuple[float, float],
) -> WorldObject:
    """Pure перемещение (LOCATED_AT). Требует чистого FREE: ни carrier,
    ни SUPPORTED_BY — позиция производных объектов вычисляется их
    владельцем (W3/W4). Переставить миску со стола:
    release(SUPPORTED_BY) → relocate — явная цепочка вместо скрытого
    авто-сброса (тот же принцип, что и в carrier-переходах)."""
    if obj.carrier_mode is not CarrierMode.FREE:
        raise OntologyViolationError(
            f"WorldObject {obj.object_id}: relocate при carrier_mode="
            f"{obj.carrier_mode.value} — позиция неавторитетна, двигают "
            f"владельца (holder/container/host)")
    if obj.supported_by is not None:
        raise OntologyViolationError(
            f"WorldObject {obj.object_id}: relocate при SUPPORTED_BY="
            f"{obj.supported_by} — сначала явный release")
    if not location_id:
        raise OntologyViolationError(
            f"WorldObject {obj.object_id}: relocate с пустым location_id")
    return dataclass_replace(
        obj, location_id=location_id, position=position)


def dataclass_replace(obj: WorldObject, **changes: Any) -> WorldObject:
    """Локальный алиас replace: все переходы проходят через КОНСТРУКТОР,
    значит __post_init__-валидация онтологии неизбежна — невозможно
    построить невалидный объект через переход (safe by construction)."""
    from dataclasses import replace as _replace
    return _replace(obj, **changes)

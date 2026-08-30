"""
path: backend/app/services/world/world_object_store.py
Назначение: W1 (ADR-O-371) — единственный фасад семантической топологии
    мира. Статический сервис над scene_state["world_objects"]
    (прецеденты: CommitmentRegistry / RelationshipStateStore).
    Persistence lifecycle стору НЕ принадлежит: диск — только через
    существующий atomic_commit_all (Foundation Freeze), собственные
    файловые пути запрещены. SSOT — scene_state; стор stateless,
    ничего не держит между вызовами.
    Runtime-writers в W1 НЕТ (доктрина M1a: место хранения, не
    механизм изменения): вызовы — тестовые fixtures и будущий W3
    causal writer. Caller-guard отложен до W3 (вердикт Мастера).
    READ-контракт: чтение НЕ мутирует scene_state (нет lazy-init на
    read); отсутствующий subtree = легитимный дефолт (старые сейвы);
    повреждённая структура — громкий отказ (маскировка дефолтом =
    DOUBLE TRUTH). READ возвращает frozen DTO в свежих коллекциях.
    WRITE-контракт: только типизированные операции (spawn /
    establish_relation / release_relation / relocate); generic-мутации
    нет — protected-поля меняются исключительно переходами domain-слоя.
    Error-поверхность W1 — OntologyViolationError (классификация в
    сообщении; новый тип не вводим — Two-Domain Rule).
Зависимости: app.domain.world_object, app.domain.exceptions
Основные сущности: WorldObjectStore
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from app.domain.exceptions import OntologyViolationError
from app.domain.world_object import (
    CarrierMode,
    ObjectRelation,
    ObjectRelationKind,
    WorldObject,
    WorldObjectState,
    apply_relation_transition,
    build_world_object,
    relocate_object,
)

# ═══ Ключ scene_state — КОНСТАНТА (Устав §12.1) ═══
_KEY_WORLD_OBJECTS = "world_objects"

# Отношения с ОБЪЕКТНОЙ целью: референциальная целостность проверяема
# в пределах subtree. NPC-цели — структурно: существование NPC — зона
# W3/W4 (stale-intent validation), W1 его не знает.
_OBJECT_TARGET_KINDS: Tuple[ObjectRelationKind, ...] = (
    ObjectRelationKind.SUPPORTED_BY,
    ObjectRelationKind.CONTAINED_BY,
)


def _read_subtree(scene_state: Dict[str, Any]) -> Dict[str, Any]:
    """Read-view subtree. Отсутствие = легитимный дефолт (старые сейвы
    без объектов); повреждённая структура — громкий отказ."""
    subtree = scene_state.get(_KEY_WORLD_OBJECTS)
    if subtree is None:
        return {}
    if not isinstance(subtree, dict):
        raise OntologyViolationError(
            f"scene_state['{_KEY_WORLD_OBJECTS}'] повреждён: "
            f"{type(subtree).__name__}, ожидается dict")
    return subtree


def _write_subtree(scene_state: Dict[str, Any]) -> Dict[str, Any]:
    """Mutable subtree для write-пути. Ленивое создание — ТОЛЬКО здесь
    (прецедент M1a: чтение никогда не создаёт subtree)."""
    subtree = scene_state.get(_KEY_WORLD_OBJECTS)
    if subtree is None:
        subtree = {}
        scene_state[_KEY_WORLD_OBJECTS] = subtree
        return subtree
    if not isinstance(subtree, dict):
        raise OntologyViolationError(
            f"scene_state['{_KEY_WORLD_OBJECTS}'] повреждён: "
            f"{type(subtree).__name__}, ожидается dict")
    return subtree


def _load_required(subtree: Dict[str, Any], object_id: str) -> WorldObject:
    """Загрузка на write-пути: отсутствие цели = рассинхрон конвейера —
    громкий отказ (L4), не тихий None."""
    raw = subtree.get(object_id)
    if raw is None:
        raise OntologyViolationError(
            f"world_objects: объект '{object_id}' не существует — "
            f"операция невозможна")
    return WorldObject.from_dict(raw)


def _parent_id(obj: WorldObject) -> Optional[str]:
    """Единственный восходящий родитель по отношениям. Carrier
    exclusivity гарантирует не более одного из container/supported/
    attachment — цепочка детерминирована. NPC-хост не резолвится:
    цепочка законно заканчивается."""
    if obj.container_id is not None:
        return obj.container_id
    if obj.supported_by is not None:
        return obj.supported_by
    if obj.attachment is not None:
        return obj.attachment[0]
    return None


def _assert_no_cycle(
    subtree: Dict[str, Any], start_id: str, first_target_id: str
) -> None:
    """Цикл в цепочке отношений (A в B, B в A) онтологически невозможен:
    позиция не может зависеть сама от себя. Поднимаемся по родителям;
    встреча start или повтор узла = нарушение. Существующий чужой цикл —
    тоже громко: subtree уже повреждён."""
    current: Optional[str] = first_target_id
    visited: set = set()
    while current is not None:
        if current == start_id:
            raise OntologyViolationError(
                f"world_objects: цикл отношений через '{start_id}' — "
                f"позиция не может зависеть от самой себя")
        if current in visited:
            raise OntologyViolationError(
                f"world_objects: существующий цикл отношений в "
                f"'{current}' — subtree повреждён")
        visited.add(current)
        raw = subtree.get(current)
        if raw is None:
            return  # NPC-хост / внешняя цель — цепочка законно кончается
        current = _parent_id(WorldObject.from_dict(raw))


class WorldObjectStore:
    """Единственный путь мутации семантической топологии мира.
    Прямая dict-хирургия scene_state["world_objects"] вне стора =
    архитектурное нарушение (ADR-O-371)."""

    # ════════════════ READ (не мутируют scene_state) ════════════════

    @staticmethod
    def get(
        scene_state: Dict[str, Any], object_id: str
    ) -> Optional[WorldObject]:
        raw = _read_subtree(scene_state).get(object_id)
        return WorldObject.from_dict(raw) if raw is not None else None

    @staticmethod
    def get_all(
        scene_state: Dict[str, Any],
        location_id: Optional[str] = None,
    ) -> Tuple[WorldObject, ...]:
        """Все объекты (опционально — локации) в порядке вставки."""
        objs = [WorldObject.from_dict(raw)
                for raw in _read_subtree(scene_state).values()]
        if location_id is not None:
            objs = [o for o in objs if o.location_id == location_id]
        return tuple(objs)

    @staticmethod
    def query_object_relations(
        scene_state: Dict[str, Any], object_id: str
    ) -> Optional[Tuple[ObjectRelation, ...]]:
        """ТЗ §20.2: все отношения объекта (projection DTO).
        None = объект не существует (легитимное отсутствие на read)."""
        obj = WorldObjectStore.get(scene_state, object_id)
        # Легитимный read: None = объект не существует (см. docstring выше)
        return obj.project_relations() if obj is not None else None  # noqa: ENIGMA001

    @staticmethod
    def query_container_contents(
        scene_state: Dict[str, Any], container_id: str
    ) -> Tuple[WorldObject, ...]:
        """Inverse-проекция CONTAINED_BY: canonical хранится на
        содержимом; список содержимого — ЗАПРОС, не хранимое поле
        (mirror-поле = зомби-истина, урок S215)."""
        result = []
        for raw in _read_subtree(scene_state).values():
            obj = WorldObject.from_dict(raw)
            if obj.container_id == container_id:
                result.append(obj)
        return tuple(result)

    @staticmethod
    def query_objects_at(
        scene_state: Dict[str, Any],
        location_id: str,
        position: Tuple[float, float],
        radius: float = 0.0,
    ) -> Tuple[str, ...]:
        """ТЗ §20.2: object_id объектов в точке/радиусе (linear scan —
        Two-Domain Rule: индекс при доказанной нужде). Только carrier
        FREE: позиция HELD/CONTAINED/ATTACHED — производная владельца,
        хранимое значение не истина. radius=0.0 — точное совпадение
        (контракт ТЗ)."""
        px, py = position
        result = []
        for raw in _read_subtree(scene_state).values():
            obj = WorldObject.from_dict(raw)
            if obj.location_id != location_id:
                continue
            if obj.carrier_mode != CarrierMode.FREE:
                continue
            if math.hypot(obj.position[0] - px, obj.position[1] - py) <= radius:
                result.append(obj.object_id)
        return tuple(result)

    # ════════════════ WRITE (типизированные операции) ═══════════════

    @staticmethod
    def spawn(
        scene_state: Dict[str, Any],
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
        """Рождение объекта (единственная фабрика входа в мир).
        Рождается ТОЛЬКО в FREE без отношений — связывание отдельной
        операцией (каузальная цепочка явная)."""
        subtree = _write_subtree(scene_state)
        if object_id in subtree:
            raise OntologyViolationError(
                f"world_objects: дубликат object_id '{object_id}' — "
                f"рождение уже рождённого")
        obj = build_world_object(
            object_id=object_id,
            archetype=archetype,
            location_id=location_id,
            position=position,
            state=state,
            ownership=ownership,
            damage=damage,
            interaction_history_ref=interaction_history_ref,
        )
        subtree[object_id] = obj.to_dict()
        return obj

    @staticmethod
    def establish_relation(
        scene_state: Dict[str, Any],
        object_id: str,
        kind: ObjectRelationKind,
        target_id: str,
        slot: Optional[str] = None,
    ) -> WorldObject:
        """Установка отношения. Онтология перехода — в domain
        (apply_relation_transition); store добавляет МЕЖОБЪЕКТНУЮ
        валидацию, недоступную domain-слою (он не знает других
        объектов): существование объектных целей, циклы, позиционные
        правила опоры."""
        subtree = _read_subtree(scene_state)
        obj = _load_required(subtree, object_id)

        if kind in _OBJECT_TARGET_KINDS:
            raw_target = subtree.get(target_id)
            if raw_target is None:
                raise OntologyViolationError(
                    f"world_objects: цель {kind.value} '{target_id}' "
                    f"не существует")
            target = WorldObject.from_dict(raw_target)
            _assert_no_cycle(subtree, object_id, target_id)
            if kind is ObjectRelationKind.SUPPORTED_BY:
                # Опора обязана быть position-authoritative (FREE):
                # держимая/вложенная опора рвёт якорь позиции.
                if target.carrier_mode != CarrierMode.FREE:
                    raise OntologyViolationError(
                        f"world_objects: опора '{target_id}' не FREE "
                        f"(carrier={target.carrier_mode.value}) — "
                        f"опора обязана владеть своей позицией")
                if target.location_id != obj.location_id:
                    raise OntologyViolationError(
                        f"world_objects: SUPPORTED_BY через локации "
                        f"({obj.location_id} -> {target.location_id}) "
                        f"невозможен")
        elif kind is ObjectRelationKind.ATTACHED_TO and target_id in subtree:
            # host — объект: циклы невозможны. host — NPC: структурно
            # (существование NPC — W3/W4). Граница с BodyTopology
            # (L16.1, инвентарь) унифицируется в W8 — ADR-O-371.
            _assert_no_cycle(subtree, object_id, target_id)

        new_obj = apply_relation_transition(obj, kind, target_id, slot)
        _write_subtree(scene_state)[object_id] = new_obj.to_dict()
        return new_obj

    @staticmethod
    def release_relation(
        scene_state: Dict[str, Any],
        object_id: str,
        kind: ObjectRelationKind,
    ) -> WorldObject:
        """Сброс отношения (STRICT: неустановленное — громкий отказ)."""
        subtree = _read_subtree(scene_state)
        obj = _load_required(subtree, object_id)
        new_obj = apply_relation_transition(obj, kind, None)
        _write_subtree(scene_state)[object_id] = new_obj.to_dict()
        return new_obj

    @staticmethod
    def relocate(
        scene_state: Dict[str, Any],
        object_id: str,
        location_id: str,
        position: Tuple[float, float],
    ) -> WorldObject:
        """Перемещение (LOCATED_AT). Блокируется позиционными
        зависимыми (SUPPORTED_BY на этот объект): их позиция привязана
        к нам — сначала явный release каждого (перенос стола с миской:
        release миски -> relocate стола; физика следования — W3/W4).
        Вложенные/прикреплённые зависимые НЕ блокируют: их позиция
        производная, следует владельцу (перенос сундука с содержимым
        легален)."""
        subtree = _read_subtree(scene_state)
        obj = _load_required(subtree, object_id)
        dependents = [
            oid for oid, raw in subtree.items()
            if WorldObject.from_dict(raw).supported_by == object_id
        ]
        if dependents:
            raise OntologyViolationError(
                f"world_objects: relocate '{object_id}' заблокирован — "
                f"позиционные зависимые {dependents}; сначала явный "
                f"release SUPPORTED_BY для каждого")
        new_obj = relocate_object(obj, location_id, position)
        _write_subtree(scene_state)[object_id] = new_obj.to_dict()
        return new_obj

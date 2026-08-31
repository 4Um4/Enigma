"""
path: backend/app/services/world/world_object_spawner.py
Назначение: W3 (ADR-O-373) — production-spawner семантических объектов
    из editor-данных локации. Спавн = CREATE-операция lifecycle в
    контуре «editor — фабрика, runtime — истина» (вердикт Мастера):
    EditorType → SpawnMapping → WorldArchetype (реестр, не прямая
    проекция). Projection-only: переносит id/type/position; presentation-
    поля (sprite/color/name/show_name) и spatial-поля (size/passability/
    cover/wall_id/durability) отбрасываются — W0-инвариант; spatial
    потребляет их своим конвейером (graph_compiler) = две проекции одних
    editor-данных, не DOUBLE TRUTH.
    Identity (вердикт Мастера): object_id = wo_<md5(campaign:spawn_loc:
    editor_id)> — immutable identity мира; spawn_loc — provenance
    (editor_id уникален только внутри локации — хэш снимает коллизии
    cross-location), текущая локация — mutable поле. Детерминизм —
    replay-требование; uuid4 запрещён.
    Запись — ТОЛЬКО через WorldObjectStore.spawn (единственный путь
    записи W1/W3). Fault isolation per-object: нарушение author-data
    (дубль id) — error-лог + счётчик в отчёт, сцена живёт (прецедент
    BUG-SPATIAL-006a в initialize_scene). Логика не читает wall-clock,
    не зовёт LLM, не мутирует ничего кроме scene_state через стор.
Зависимости: hashlib, logging, dataclasses, typing, app.domain.world_object,
    app.domain.exceptions, app.services.world.world_object_store
Основные сущности: WorldObjectSpawner, SpawnReport,
    _EDITOR_TYPE_TO_ARCHETYPE, _deterministic_object_id
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from app.domain.exceptions import OntologyViolationError
from app.domain.world_object import WorldObjectState
from app.services.world.world_object_store import WorldObjectStore

logger = logging.getLogger(__name__)

# ═══ SpawnMapping (вердикт Мастера §9): EditorType → Archetype ═══
# Закрытый реестр v1 — только архетипы с полным покрытием W2 (таблица
# affordances) × W3 (FSM). door_transition → door: graph_compiler уже
# обрабатывает оба типа одним механизмом wall-opening — единая механика
# OPEN, переход в граф — свойство ребра, не объекта. Расширение реестра
# = мини-запись в ADR-O-373 (класс ADR-O-349). НЕ в реестре: table/bar/
# stool/bed (нет W2-таблицы, О4), wall/decoration (статика), portals[]
# и их type (spatial-рёбра, не объекты).
_EDITOR_TYPE_TO_ARCHETYPE: Dict[str, str] = {
    "door": "door",
    "door_transition": "door",
    "chair": "chair",
}

_OBJECT_ID_PREFIX = "wo"
_ID_HASH_LEN = 16


@dataclass(frozen=True)
class SpawnReport:
    """Телеметрия инициализации (не runtime-каузал). Наблюдаемость
    спавна без молчаливых пропусков: каждый editor-объект либо
    спавнится, либо попадает в skipped_unmapped (вне реестра), либо
    в faults (data-integrity, с причиной)."""
    spawned_ids: Tuple[str, ...] = ()
    skipped_unmapped: Tuple[str, ...] = ()
    faults: Tuple[str, ...] = ()

    @property
    def spawned(self) -> int:
        return len(self.spawned_ids)

    def summary(self) -> str:
        return (
            f"spawned={len(self.spawned_ids)} "
            f"skipped_unmapped={len(self.skipped_unmapped)} "
            f"faults={len(self.faults)}"
        )


def _deterministic_object_id(
    campaign_id: str, location_id: str, editor_id: str
) -> str:
    """Identity предмета: wo_<hash(campaign:spawn_location:editor_id)>.

    Закон identity (ADR-O-373): object_id — immutable identity на всю
    жизнь мира, НЕ содержит локацию как семантику. Перенос в другую
    локацию не меняет identity (location_id — mutable поле объекта).
    Прецеденты детерминизма: commitment_id (ADR-O-363), snapshot_id
    (BUG-FB-029).
    """
    _seed = f"{campaign_id}:{location_id}:{editor_id}".encode("utf-8")
    _digest = hashlib.md5(_seed).hexdigest()[:_ID_HASH_LEN]
    return f"{_OBJECT_ID_PREFIX}_{_digest}"


def _project_initial_state(
    archetype: str, properties: Dict[str, Any]
) -> str:
    """В-2 (вердикт Мастера): editor-свойства → FSM-старт.

    door: locked → LOCKED (приоритет), open → OPEN, иначе CLOSED.
    chair: state-поле — damage-track (ADR-O-372: chair-состояний в
    state-поле нет; AVAILABLE/OCCUPIED/HELD — деривация отношений W1);
    рождение честное — INTACT.
    """
    if archetype == "door":
        if properties.get("locked", False):
            return "LOCKED"
        if properties.get("open", False):
            return "OPEN"
        return "CLOSED"
    return WorldObjectState.INTACT.value


class WorldObjectSpawner:
    """W3 production-spawner: editor objects → WorldObject через стор.

    Вызывается ТОЛЬКО при рождении новой сцены (initialize_scene);
    загруженные сейвы не перезатираются — сейв выигрывает.
    """

    @staticmethod
    def spawn_from_editor(
        scene_state: Dict[str, Any],
        campaign_id: str,
        location_id: str,
        editor_data: Optional[Dict[str, Any]],
    ) -> SpawnReport:
        """Спавнит семантическое подмножество editor-объектов локации.

        Идемпотентность обеспечивается контуром вызова (один вызов на
        рождение сцены); повторный вызов на заполненном subtree даёт
        faults (STRICT duplicate стора) без падения сцены.
        """
        if not editor_data:
            return SpawnReport()

        _spawned: list = []
        _skipped: list = []
        _faults: list = []

        for _index, _editor_obj in enumerate(editor_data.get("objects", [])):
            _editor_type = str(_editor_obj.get("type", ""))
            _archetype = _EDITOR_TYPE_TO_ARCHETYPE.get(_editor_type)
            if _archetype is None:
                _skipped.append(f"{_editor_type}#{_index}")
                continue

            # editor id — счётчик внутри локации, местами отсутствует
            # (археология tavern.json: door без id) — fallback по
            # индексу, прецедент initialize_scene. Уникальность
            # гарантируется в рамках локации, глобальная — хэшем.
            _editor_id = str(_editor_obj.get("id") or f"obj_{_index}")
            _object_id = _deterministic_object_id(
                campaign_id, location_id, _editor_id)

            _pos = _editor_obj.get("position", {}) or {}
            _position = (float(_pos.get("x", 0.0)), float(_pos.get("y", 0.0)))

            _properties = _editor_obj.get("properties", {}) or {}
            _state = _project_initial_state(_archetype, _properties)

            try:
                WorldObjectStore.spawn(
                    scene_state,
                    _object_id,
                    _archetype,
                    location_id,
                    _position,
                    state=_state,
                )
                _spawned.append(_object_id)
            except OntologyViolationError as _e:
                # Data-integrity входа (дубль id): fault с наблюдаемостью,
                # сцена живёт (прецедент BUG-SPATIAL-006a). Runtime-баги
                # стора сюда не попадают — их поверхность другая.
                logger.error(
                    f"[W3_SPAWN] fault: editor_id={_editor_id} "
                    f"object_id={_object_id}: {_e}")
                _faults.append(f"{_editor_id}: {_e}")

        return SpawnReport(
            spawned_ids=tuple(_spawned),
            skipped_unmapped=tuple(_skipped),
            faults=tuple(_faults),
        )

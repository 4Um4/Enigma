"""
path: backend/app/services/world/world_objects_projection.py
Назначение: W3/ADR-O-376 — World-object projection: мост W1-snapshot →
    W2-resolver. Контракт (вердикт Мастера): типизированная READ-проекция
    замороженного WorldSnapshot.world_objects; сам resolver в storage
    НЕ лезет (Q1a) — внутреннее представление заменяемо без
    переписывания W2. from_dict — деталь реализации моста, не контракта.
    Pure: ноль IO/LLM/мутаций; вход deepcopy-безопасен по построению
    (snapshot уже заморожен S215-мостом).
Зависимости: typing, app.domain.world_object
Основные сущности: project_world_objects, WorldObjectProjection
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.domain.world_object import WorldObject


def project_world_objects(
    snapshot_world_objects: Optional[Dict[str, Dict[str, Any]]],
    location_id: str,
) -> Tuple[WorldObject, ...]:
    """Frozen subtree → Tuple[WorldObject] с фильтром по локации.

    Повреждённые записи пропускаются ГРОМКО: logger.warning + пропуск
    (тень — наблюдатель: отказ наблюдателя не роняет тик, CDS-принцип
    §11 ЧаСТИ XI CAUSAL CONTRACT; валидация онтологии — INV-WORLD-
    OBJECT-TOPOLOGY, это его зона).
    """
    import logging
    _logger = logging.getLogger(__name__)

    if not snapshot_world_objects:
        return ()
    _result: list = []
    for _oid, _raw in snapshot_world_objects.items():
        try:
            _obj = WorldObject.from_dict(_raw)
        except (KeyError, TypeError, ValueError) as _e:
            _logger.warning(
                f"[W3_PROJECTION] пропуск повреждённого объекта "
                f"'{_oid}': {_e}")
            continue
        if _obj.location_id == location_id:
            _result.append(_obj)
    return tuple(_result)

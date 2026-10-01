# path: /project/backend/app/services/world/object_target_facts.py
# Назначение: G3 Этап 2 (ADR-O-410 §6) — детерминированный целевой
#     резолвер воли: pure (замороженный снапшот тика) → per-NPC объектная
#     цель. ОБЩИЙ канал WorldState→Decision (сиблинг affordance_facts,
#     ADR-O-378): TARGETABLE_ARCHETYPES — calibration policy (вердикт
#     Мастера №3: chair — policy, не онтология; расширение = мини-ADR),
#     v1: chair→TAKE. Детерминизм (вердикт №4): nearest Euclidean +
#     лексикографический object_id tie-break; LLM НИКОГДА не выбирает
#     объект мира — только этот canonical resolver.
#     Читает ТОЛЬКО freeze-проекцию снапшота (INV-III). Ничего не
#     мутирует, ничего не пишет, executor не зовёт.
# Зависимости: app.domain.constants (AFFORDANCE_ADJACENCY_RADIUS_M)
# Основные сущности: TARGETABLE_ARCHETYPES, compute_object_target_facts
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, Tuple

from app.domain.constants import AFFORDANCE_ADJACENCY_RADIUS_M

logger = logging.getLogger(__name__)

# ═══ Calibration policy (вердикт Мастера №3, ADR-O-410 §6) ═══
# НЕ онтологическая истина: будущие cup/coin/book/... не требуют
# переписывания G3 — только строка в policy + мини-ADR в атлас.
TARGETABLE_ARCHETYPES: Dict[str, str] = {"chair": "TAKE"}


def compute_object_target_facts(
    snapshot: Any,
    npc_ids: Iterable[str],
    location_id: str,
) -> Dict[str, str]:
    """Pure: freeze-снапшот → {npc_id: object_id}.

    Семантика: цель = ближайший FREE-объект targetable-архетипа в
    радиусе AFFORDANCE_ADJACENCY_RADIUS_M от NPC (тот же радиус, что
    W2-предикат IS_ADJACENT_TO — единая membrane воли и ревалидации).
    Тай-брейк равных дистанций — лексикографический object_id.
    Честное отсутствие: нет NPC-позиции / нет объектов / вне радиуса
    → npc отсутствует в карте (потребитель читает None).
    """
    _facts: Dict[str, str] = {}
    if snapshot is None or not getattr(snapshot, "world_objects", None):
        return _facts

    from app.services.world.world_objects_projection import (
        project_world_objects,
    )

    _candidates = tuple(
        _o
        for _o in project_world_objects(snapshot.world_objects, location_id)
        if _o.archetype in TARGETABLE_ARCHETYPES
        and _o.carrier_mode.value == "FREE"
    )
    if not _candidates:
        return _facts

    _positions: Dict[str, Tuple[float, float]] = {}
    for _nid, _pos_d in (snapshot.npc_positions or {}).items():
        _lp = _pos_d.get("local_position") or {}
        try:
            _positions[_nid] = (
                float(_lp.get("x", 0.0)),
                float(_lp.get("y", 0.0)),
            )
        except (TypeError, ValueError) as _e:
            logger.warning(f"[G3_TGT] damaged npc_position '{_nid}': {_e}")
            continue

    for _nid in npc_ids:
        _pos = _positions.get(_nid)
        if _pos is None:
            continue
        _best: Tuple[float, str] | None = None
        for _o in _candidates:
            _d = math.hypot(_o.position[0] - _pos[0], _o.position[1] - _pos[1])
            if _d > AFFORDANCE_ADJACENCY_RADIUS_M:
                continue
            _key = (round(_d, 9), _o.object_id)
            if _best is None or _key < _best:
                _best = _key
        if _best is not None:
            _facts[_nid] = _best[1]
    if _facts:
        logger.info(f"[G3_TGT] targets={_facts}")
    return _facts

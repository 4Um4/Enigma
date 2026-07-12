"""
path: /project/backend/app/services/phases/validation.py
Назначение: Инкапсуляция логики валидации Shadow vs Legacy (Dual Rail Execution).
Зависимости: app.services.equivalence_validator
Основные сущности: validate_shadow_vs_legacy
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_shadow_vs_legacy(
    orchestrator: Any,
    snapshot: Any,
    tick: int,
    npc_id: str,
    thick: Any,
    scene_state: dict,
    phase_label: str = "",
) -> None:
    """Сравнение shadow ThickSceneChange с legacy состоянием.

    ФАЗА 2: Position (L0/L3) + Topology (L1) + Boundary (L2) + Traversal (L2).
    Class A/B → info (ожидаемый), Class C → warning+DEPRECATION,
    Class D/E → error+DEPRECATION.
    """
    _npc_entry = scene_state.get("npc_positions", {}).get(npc_id, {})
    _legacy_pos = _npc_entry.get("local_position")
    _legacy_node = _npc_entry.get("position", "")
    # FIX: _legacy_location должен браться из фактической позиции NPC в сцене,
    # а не из кэша LifeEngine (где хранится "должность" по расписанию).
    # Без этого возникает ложный boundary-дрейф, если NPC работает в другой локации.
    _legacy_location = _npc_entry.get("location_id", _npc_entry.get("location", ""))

    # Shadow state из ThickSceneChange
    _shadow_pos = thick.spatial.target_xy if thick.spatial else None
    _shadow_node = thick.spatial.target_node if thick.spatial else ""

    # Shadow boundary/target location
    _shadow_target_location = ""
    if thick.boundary and thick.boundary.neighbor_chunk:
        _shadow_target_location = thick.boundary.neighbor_chunk
    elif thick.spatial and thick.spatial.target_location:
        _shadow_target_location = thick.spatial.target_location

    _drifts: list = []

    # Position drift (L0 — ontological + L3 — presentation)
    _drifts += orchestrator._equivalence_validator.validate_position(
        snapshot_id=snapshot.snapshot_id,
        tick=tick,
        npc_id=npc_id,
        legacy_position=_legacy_pos,
        shadow_position=_shadow_pos,
    )

    # Topology drift (L1)
    # FIX: Пропускаем топологический дрейф при boundary transition.
    # При смене локации узлы гарантированно разные (exit_east vs exit_west),
    # и это не является ошибкой. Смену локации проверяет validate_boundary.
    if _shadow_node and _legacy_node and not _shadow_target_location:
        _drifts += orchestrator._equivalence_validator.validate_topology(
            snapshot_id=snapshot.snapshot_id,
            tick=tick,
            npc_id=npc_id,
            legacy_node=_legacy_node,
            shadow_node=_shadow_node,
        )

    # ── ФАЗА 2: Boundary drift (L2) ────────────────────────────
    # Legacy boundary: NPC оказался в другой локации после apply
    _legacy_is_boundary = bool(
        _legacy_location and _legacy_location != snapshot.location_id
    )
    _shadow_is_boundary = bool(thick.boundary and thick.boundary.is_boundary)
    _drifts += orchestrator._equivalence_validator.validate_boundary(
        snapshot_id=snapshot.snapshot_id,
        tick=tick,
        npc_id=npc_id,
        legacy_is_boundary=_legacy_is_boundary,
        shadow_is_boundary=_shadow_is_boundary,
        legacy_target_location=_legacy_location,
        shadow_target_location=_shadow_target_location,
    )

    # ── ФАЗА 2: Traversal drift (L2) ───────────────────────────
    _legacy_traversal = scene_state.get("active_traversals", {}).get(npc_id)
    _shadow_traversal = thick.traversal if thick.traversal else None
    _drifts += orchestrator._equivalence_validator.validate_traversal(
        snapshot_id=snapshot.snapshot_id,
        tick=tick,
        npc_id=npc_id,
        cause=thick.cause,
        legacy_traversal=_legacy_traversal,
        shadow_traversal=_shadow_traversal,
    )

    # Логируем и собираем статистику
    orchestrator._drift_stats["total_comparisons"] += 1
    if _drifts:
        orchestrator._equivalence_validator.log_drifts(_drifts)
        for _d in _drifts:
            orchestrator._drift_stats.setdefault(f"drift_{_d.drift_class.value}", 0)
            orchestrator._drift_stats[f"drift_{_d.drift_class.value}"] += 1
            logger.info(
                f"[DUAL_RAIL][{phase_label}] npc={npc_id} "
                f"class={_d.drift_class.value} field={_d.field}"
            )

    # Периодический отчёт (каждые 100 наблюдений)
    orchestrator._log_drift_summary()

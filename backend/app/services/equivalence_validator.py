# -*- coding: utf-8 -*-
"""
Суд причинности — сравнение legacy и shadow pipeline.

ADR-O-201: Causal Kernel Architecture — Equivalence Validator.
Сравнивает результат legacy apply_change с ThickSceneChange.
4 уровня (Identity/Topology/Causality/Presentation), 5 классов drift.

Rule 126: Drift Index с Class D (Causal) или E (Ontological) в production ЗАПРЕЩЁН.

Критерий переключения власти (ФАЗА 2→3):
  0 Ontological + 0 Causal + 0 Topological drift
  за 100k+ тиков + 100% replay determinism.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

logger = logging.getLogger(__name__)


class DriftClass(Enum):
    """Классы дрейфа между legacy и shadow pipeline."""

    COSMETIC = "A"  # x=10.1 vs x=10.2 — визуально неразличимо
    PROJECTION = "B"  # same node, different coords — разные проекции
    TOPOLOGICAL = "C"  # different nodes — разные узлы графа
    CAUSAL = "D"  # boundary_cross vs teleport — разные причины
    ONTOLOGICAL = "E"  # NPC exists vs missing — разные онтологии


class DriftLevel(Enum):
    """Уровни сравнения (иерархия — провал верхнего уровня = остановка)."""

    IDENTITY = "L0"  # npc_id, alive, location_id — FATAL при расхождении
    TOPOLOGY = "L1"  # location_id, node_id — ERROR при расхождении
    CAUSALITY = "L2"  # cause, event_type, transition_chain — CRITICAL
    PRESENTATION = "L3"  # local_position, rotation — WARNING


@dataclass
class DriftReport:
    """Отчёт о расхождении между legacy и shadow pipeline."""

    snapshot_id: UUID
    tick: int
    npc_id: str
    drift_class: DriftClass
    drift_level: DriftLevel
    field: str
    legacy_value: Any
    shadow_value: Any
    description: str

    @property
    def is_fatal(self) -> bool:
        """Является ли дрейф фатальным (Class D или E)."""
        return self.drift_class in (DriftClass.CAUSAL, DriftClass.ONTOLOGICAL)


class EquivalenceValidator:
    """Суд причинности (ADR-O-201).

    ФАЗА 0: структурная валидация ThickSceneChange.
    ФАЗА 1+: runtime сравнение legacy vs shadow результатов.
    """

    # Пороги классификации
    _COSMETIC_THRESHOLD = 0.01  # drifts ≤ 0.01 = Class A (cosmetic, визуально неразличимый)
    _PROJECTION_THRESHOLD = 0.5  # 0.01 < drifts ≤ 0.5 = Class B (projection, заметный в проекции)

    def validate_position(
        self,
        snapshot_id: UUID,
        tick: int,
        npc_id: str,
        legacy_position: Optional[Dict],
        shadow_position: Optional[Tuple[float, float]],
    ) -> List[DriftReport]:
        """Сравнивает позицию NPC между legacy и shadow (L0 + L3).

        legacy_position: {"x": float, "y": float} или None
        shadow_position: (x, y) или None
        """
        drifts: List[DriftReport] = []

        # L0: Ontological — NPC существует в одном, но не в другом
        if legacy_position is None and shadow_position is not None:
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.ONTOLOGICAL,
                    drift_level=DriftLevel.IDENTITY,
                    field="position",
                    legacy_value=None,
                    shadow_value=shadow_position,
                    description="NPC missing in legacy but present in shadow",
                )
            )
            return drifts

        if legacy_position is not None and shadow_position is None:
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.ONTOLOGICAL,
                    drift_level=DriftLevel.IDENTITY,
                    field="position",
                    legacy_value=legacy_position,
                    shadow_value=None,
                    description="NPC present in legacy but missing in shadow",
                )
            )
            return drifts

        if legacy_position is None and shadow_position is None:
            return drifts  # Оба отсутствуют — эквивалентно

        # L3: Presentation — координаты
        lx = legacy_position.get("x", 0.0)  # type: ignore[union-attr]
        ly = legacy_position.get("y", 0.0)  # type: ignore[union-attr]
        sx, sy = shadow_position  # type: ignore[misc]

        diff = ((lx - sx) ** 2 + (ly - sy) ** 2) ** 0.5

        if diff > self._PROJECTION_THRESHOLD:
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.PROJECTION,
                    drift_level=DriftLevel.PRESENTATION,
                    field="local_position",
                    legacy_value={"x": lx, "y": ly},
                    shadow_value={"x": sx, "y": sy},
                    description=f"Position drift: {diff:.2f} units",
                )
            )
        elif diff > self._COSMETIC_THRESHOLD:
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.COSMETIC,
                    drift_level=DriftLevel.PRESENTATION,
                    field="local_position",
                    legacy_value={"x": lx, "y": ly},
                    shadow_value={"x": sx, "y": sy},
                    description=f"Cosmetic drift: {diff:.3f} units",
                )
            )

        return drifts

    def validate_topology(
        self,
        snapshot_id: UUID,
        tick: int,
        npc_id: str,
        legacy_node: str,
        shadow_node: str,
    ) -> List[DriftReport]:
        """Сравнивает узел графа между legacy и shadow (L1)."""
        drifts: List[DriftReport] = []

        # Нормализация canonical ID — убираем префикс локации
        _legacy = legacy_node.split(":")[-1] if ":" in legacy_node else legacy_node
        _shadow = shadow_node.split(":")[-1] if ":" in shadow_node else shadow_node

        if _legacy != _shadow:
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.TOPOLOGICAL,
                    drift_level=DriftLevel.TOPOLOGY,
                    field="node",
                    legacy_value=legacy_node,
                    shadow_value=shadow_node,
                    description=f"Topological drift: {legacy_node} vs {shadow_node}",
                )
            )

        return drifts

    def validate_boundary(
        self,
        snapshot_id: UUID,
        tick: int,
        npc_id: str,
        legacy_is_boundary: bool,
        shadow_is_boundary: bool,
        legacy_target_location: str,
        shadow_target_location: str,
    ) -> List[DriftReport]:
        """Сравнивает boundary resolution между legacy и shadow (L2)."""
        drifts: List[DriftReport] = []

        # L2: Causal — boundary vs non-boundery = разные причины
        if legacy_is_boundary != shadow_is_boundary:
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.CAUSAL,
                    drift_level=DriftLevel.CAUSALITY,
                    field="boundary",
                    legacy_value=legacy_is_boundary,
                    shadow_value=shadow_is_boundary,
                    description=(
                        f"Causal drift: boundary={legacy_is_boundary} "
                        f"vs {shadow_is_boundary}"
                    ),
                )
            )
        elif legacy_is_boundary and shadow_is_boundary:
            # Оба boundary — проверяем target location
            if legacy_target_location != shadow_target_location:
                drifts.append(
                    DriftReport(
                        snapshot_id=snapshot_id,
                        tick=tick,
                        npc_id=npc_id,
                        drift_class=DriftClass.TOPOLOGICAL,
                        drift_level=DriftLevel.TOPOLOGY,
                        field="target_location",
                        legacy_value=legacy_target_location,
                        shadow_value=shadow_target_location,
                        description=(
                            f"Boundary target drift: {legacy_target_location} "
                            f"vs {shadow_target_location}"
                        ),
                    )
                )

        return drifts

    def validate_traversal(
        self,
        snapshot_id: UUID,
        tick: int,
        npc_id: str,
        legacy_traversal: Optional[Dict],
        shadow_traversal: Optional["TraversalContract"],
        cause: str = "",
    ) -> List[DriftReport]:
        """Сравнивает traversal contract между legacy и shadow (L2, ФАЗА 2).

        Legacy traversal = dict из scene_state["active_traversals"][npc_id].
        Shadow traversal = TraversalContract из ThickSceneChange.
        """
        drifts: List[DriftReport] = []

        _legacy_active = bool(
            legacy_traversal
            and legacy_traversal.get("status") in ("MOVING", "COMPLETED")
        )
        _shadow_active = bool(
            shadow_traversal and shadow_traversal.status in ("NEW", "COMPLETED")
        )

        # L2 Causal: один создал traversal, другой — нет
        # ИСКЛЮЧЕНИЯ:
        # 1. При cause="traversal_complete" Shadow возвращает None (ADR-O-201.4),
        #    а Legacy оставляет COMPLETED. Это норма, дрейфом не является.
        # 2. ADR-O-323: Если Legacy создал traversal (из proposal), а Shadow вернул None
        #    (например, для микро-перемещений или если proposal был невалидным),
        #    это не Rule 120. EventCompiler уже залогировал EQUIVALENCE_VIOLATION,
        #    если это было макро-перемещение. Здесь мы просто пропускаем проверку,
        #    чтобы избежать ложного спама.
        if _legacy_active != _shadow_active and cause != "traversal_complete":
            # ADR-O-323: Если Legacy создал traversal (из proposal), а Shadow вернул None
            # (например, для микро-перемещений или если proposal был невалидным),
            # это не Rule 120/122. EventCompiler уже залогировал EQUIVALENCE_VIOLATION,
            # если это было макро-перемещение. Здесь мы фиксируем дрейф для аудита.
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.CAUSAL,
                    drift_level=DriftLevel.CAUSALITY,
                    field="traversal_exists",
                    legacy_value=_legacy_active,
                    shadow_value=_shadow_active,
                    description="One pipeline created traversal, the other did not.",
                )
            )
            return drifts

        if not _legacy_active and not _shadow_active:
            return drifts  # Оба без traversal — эквивалентно

        # Оба имеют traversal — сравниваем ключевые поля
        # Статус: MOVING ≈ NEW (оба означают "в пути")
        _legacy_status = legacy_traversal.get("status", "") if legacy_traversal else ""
        _shadow_status = shadow_traversal.status if shadow_traversal else ""
        _status_equivalent = (
            _legacy_status == _shadow_status
            or (_legacy_status == "MOVING" and _shadow_status == "NEW")
            or (_legacy_status == "COMPLETED" and _shadow_status == "COMPLETED")
        )
        if not _status_equivalent and cause != "traversal_complete":
            drifts.append(
                DriftReport(
                    snapshot_id=snapshot_id,
                    tick=tick,
                    npc_id=npc_id,
                    drift_class=DriftClass.CAUSAL,
                    drift_level=DriftLevel.CAUSALITY,
                    field="traversal_status",
                    legacy_value=_legacy_status,
                    shadow_value=_shadow_status,
                    description=f"Traversal status drift: {_legacy_status} vs {_shadow_status}",
                )
            )

        # Target node (только для активных traversal)
        if _shadow_status == "NEW" and legacy_traversal:
            _legacy_target = legacy_traversal.get("target_node", "")
            _shadow_target = (
                shadow_traversal.fields.get("target_node", "")
                if shadow_traversal
                else ""
            )
            if _legacy_target and _shadow_target and _legacy_target != _shadow_target:
                drifts.append(
                    DriftReport(
                        snapshot_id=snapshot_id,
                        tick=tick,
                        npc_id=npc_id,
                        drift_class=DriftClass.TOPOLOGICAL,
                        drift_level=DriftLevel.TOPOLOGY,
                        field="traversal_target_node",
                        legacy_value=_legacy_target,
                        shadow_value=_shadow_target,
                        description=(
                            f"Traversal target drift: {_legacy_target} "
                            f"vs {_shadow_target}"
                        ),
                    )
                )

            # Duration ticks
            _legacy_dur = legacy_traversal.get("duration_ticks", 0)
            _shadow_dur = (
                shadow_traversal.fields.get("duration_ticks", 0)
                if shadow_traversal
                else 0
            )
            if _legacy_dur != _shadow_dur:
                drifts.append(
                    DriftReport(
                        snapshot_id=snapshot_id,
                        tick=tick,
                        npc_id=npc_id,
                        drift_class=DriftClass.PROJECTION,
                        drift_level=DriftLevel.PRESENTATION,
                        field="traversal_duration",
                        legacy_value=_legacy_dur,
                        shadow_value=_shadow_dur,
                        description=(
                            f"Traversal duration drift: "
                            f"{_legacy_dur} vs {_shadow_dur} ticks"
                        ),
                    )
                )

        return drifts

    # ФАЗА 2: Маппинг drift → DEPRECATION на конкретную мутацию apply_change
    _DRIFT_DEPRECATIONS: Dict[str, str] = {
        # Class C (Topological) → мутации, вызывающие топологический drift
        "C:position": "Rule 117: SpatialService.build_for_location() в apply_change",
        "C:traversal_target_node": "Rule 119: Pathfinding в apply_change",
        "C:target_location": "Rule 117: SpatialService query в apply_change",
        # Class D (Causal) → мутации, вызывающие причинный drift
        "D:boundary": "Rule 122: Прямая мутация state до apply_changes (_process_traversals)",
        "D:traversal_exists": "Rule 120: Traversal creation в apply_change",
        "D:traversal_status": "Rule 122: Прямая мутация state до apply_changes",
        "D:cause": "Rule 124: Branching logic >1 уровня в apply_change",
        "D:transition_chain": "Rule 122: Прямая мутация state до apply_changes",
        # Class E (Ontological) — баг, не DEPRECATION
    }

    def log_drifts(self, drifts: List[DriftReport]) -> None:
        """Логирует drift report'ы с уровнями ФАЗЫ 2.

        ФАЗА 2 Семантика:
        - Class A/B (cosmetic/projection): INFO — ожидаемый drift
        - Class C (topological): WARNING + DEPRECATION
        - Class D/E (causal/ontological): ERROR + DEPRECATION
        """
        for d in drifts:
            _tag = f"[DRIFT][{d.drift_class.value}]"
            _base = f"tick={d.tick} npc={d.npc_id} field={d.field} {d.description}"

            if d.drift_class in (DriftClass.COSMETIC, DriftClass.PROJECTION):
                # Class A/B — ожидаемый drift (jitter, rounding)
                logger.info(f"{_tag} {_base}")
            elif d.drift_class == DriftClass.TOPOLOGICAL:
                # Class C — WARNING + DEPRECATION
                _depr_key = f"C:{d.field}"
                _depr = self._DRIFT_DEPRECATIONS.get(_depr_key, "Unknown mutation")
                logger.debug(f"{_tag} {_base} | DEPRECATION: {_depr}")
                logger.warning(f"{_tag} {_base} | DEPRECATION: {_depr}")
            else:
                # Class D/E — ERROR + DEPRECATION (или FATAL для E)
                _depr_key = f"{d.drift_class.value}:{d.field}"
                _depr = self._DRIFT_DEPRECATIONS.get(
                    _depr_key, "Unknown causal mutation"
                )
                logger.error(f"{_tag} {_base} | DEPRECATION: {_depr}")

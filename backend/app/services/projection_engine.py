# -*- coding: utf-8 -*-
"""
ProjectionEngine — единственный автор записи пространственного состояния.

ADR-O-201 ФАЗА 3: Causal Single Source Enforcement (CSSE).

Инварианты:
- Ноль вычислений (no random, no pathfinding, no spatial queries)
- Ноль решений (no branching, no fallback)
- Единственный writer пространственного состояния

СЕЙЧАС: Изолированный модуль — НЕ подключён к real state.
Только shadow buffer для верификации через CEH.

path: backend/app/services/projection_engine.py
Назначение: Чистая проекция ThickSceneChange в scene_state
Зависимости: app.models.thick_scene_change (ThickSceneChange)
Основные сущности: ProjectionEngine
"""
from __future__ import annotations


import copy
import logging
from typing import List

from app.models.thick_scene_change import ThickSceneChange

logger = logging.getLogger(__name__)


class ProjectionEngine:
    """Чистая проекция — единственный автор записи состояния.

    Принцип: state[t+1] = state[t] ⊕ ThickSceneChange[]

    Правила:
    - НЕ вычисляет (всё предвычислено EventCompiler)
    - НЕ решает (никаких branching, fallback)
    - НЕ читает мир для принятия решений (только пишет)
    - Применяет ThickSceneChange как deterministic fold

    Нарушение любого правила = вторая физика = Rule 124.
    """

    def apply(self, scene_state: dict, thick: ThickSceneChange) -> bool:
        """Применяет один ThickSceneChange к scene_state.

        Чистая проекция: записывает предвычисленную физику.
        Возвращает True если изменение применено.
        """
        if not thick.is_spatial:
            # Non-spatial — не юрисдикция ProjectionEngine
            return False

        if thick.field == "position":
            return self._apply_position(scene_state, thick)
        elif thick.field == "local_position":
            return self._apply_local_position(scene_state, thick)

        return False

    def apply_batch(
        self,
        scene_state: dict,
        thick_changes: List[ThickSceneChange],
    ) -> int:
        """Применяет пакет ThickSceneChange к scene_state.

        Возвращает количество применённых изменений.
        """
        applied = 0
        for thick in thick_changes:
            if self.apply(scene_state, thick):
                applied += 1
        return applied

    def project(
        self,
        scene_state: dict,
        thick_changes: List[ThickSceneChange],
    ) -> dict:
        """Создаёт shadow projection — копию scene_state с применёнными изменениями.

        НЕ мутирует оригинальный scene_state.
        Используется для CEH (Causal Equivalence Harness).
        """
        shadow = copy.deepcopy(scene_state)
        self.apply_batch(shadow, thick_changes)
        return shadow

    # ── Приватные методы ──────────────────────────────────────────

    def _apply_position(self, scene_state: dict, thick: ThickSceneChange) -> bool:
        """Проецирует NPC_POSITION field='position'.

        Записывает:
        1. entry["position"] = node_id (каузальная позиция)
        2. entry["local_position"] = spatial.target_xy (геометрия)
        3. entry["location"] / entry["location_id"] = boundary (если boundary)
        4. scene_state["active_traversals"][npc_id] = traversal (если NEW/COMPLETED)
        """
        pos = scene_state.setdefault("npc_positions", {})
        entry = pos.setdefault(thick.target, {})

        # 1. Каузальная позиция (semantic truth)
        entry["position"] = thick.value

        # 2. Геометрическая позиция (Authoritative State)
        # Бэкенд мгновенно обновляет позицию на цель (target_xy).
        # Фронтенд сам отвечает за плавную интерполяцию (LERP) к этой точке.
        if thick.spatial and thick.spatial.target_xy:
            entry["local_position"] = {
                "x": thick.spatial.target_xy[0],
                "y": thick.spatial.target_xy[1],
            }

        # 3. Boundary resolution (кросс-локационное перемещение)
        if thick.boundary and thick.boundary.is_boundary:
            _neighbor = thick.boundary.neighbor_chunk
            if _neighbor:
                entry["location"] = _neighbor
                entry["location_id"] = _neighbor

        # 4. Traversal contract — ProjectionEngine = observer, SSM = lifecycle owner
        if thick.traversal:
            if thick.traversal.status == "NEW":
                # ADR-XXX: Рождение traversal — ProjectionEngine прокидывает dict,
                # но статусная мутация теперь через SSM FSM. Создание остаётся здесь,
                # так как это первичная запись (transition None→MOVING).
                # ADR-O-201: Immutability of ThickSceneChange — deep copy fields to prevent state mutation.
                import copy

                _fields = copy.deepcopy(thick.traversal.fields)
                scene_state.setdefault("active_traversals", {})[thick.target] = _fields
                logger.debug(
                    f"[PROJECTION] Traversal NEW: npc={thick.target} "
                    f"target={thick.value} "
                    f"duration={_fields.get('duration_ticks', '?')}"
                )
            elif thick.traversal.status == "COMPLETED":
                # ADR-XXX: ProjectionEngine = READ-ONLY observer.
                # Transition MOVING→COMPLETED выполняется ТОЛЬКО через SSM FSM.
                # ProjectionEngine больше не пишет статус в active_traversals.
                traversals = scene_state.get("active_traversals", {})
                if thick.target in traversals:
                    _current_status = traversals[thick.target].get("status")
                    if _current_status == "COMPLETED":
                        logger.debug(
                            f"[PROJECTION] Traversal COMPLETED confirmed (read-only): npc={thick.target}"
                        )
                    else:
                        logger.info(
                            f"[PROJECTION] Traversal COMPLETED shadow vs legacy drift: "
                            f"npc={thick.target} shadow=COMPLETED legacy={_current_status} "
                            f"(SSM FSM will transition)"
                        )

        return True

    def _apply_local_position(self, scene_state: dict, thick: ThickSceneChange) -> bool:
        """Проецирует NPC_POSITION field='local_position'.

        Записывает:
        1. entry["local_position"] = xy dict
        """
        pos = scene_state.setdefault("npc_positions", {})
        entry = pos.setdefault(thick.target, {})

        if isinstance(thick.value, dict):
            entry["local_position"] = thick.value
        else:
            logger.warning(
                f"[PROJECTION] local_position value is not dict: "
                f"npc={thick.target} type={type(thick.value).__name__}"
            )
            return False

        return True

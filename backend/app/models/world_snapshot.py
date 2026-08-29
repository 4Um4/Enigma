# -*- coding: utf-8 -*-
"""
Замороженный срез реальности в момент t.

ADR-O-201: Causal Kernel Architecture — Snapshot Kernel.
Единственный источник истины для EventCompiler.
Не вычисляет. Не мутирует. Только хранит.

Rule 125: Snapshot mutation после создания ЗАПРЕЩЕНА.

Первый закон причинности ENIGMA:
  Одинаковый Snapshot + Одинаковый Event = Одинаковый Result
"""
from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorldSnapshot:
    """Замороженный срез реальности в момент t.

    frozen=True предотвращает переназначение полей.
    Вложенные dict — логически immutable (architectural invariant, Rule 125).
    Нарушение = архитектурный баг уровня ADR-O-201.
    """

    # ── Идентификация снимка ──────────────────────────────────────
    snapshot_id: UUID
    created_at: float

    # ── Время симуляции ───────────────────────────────────────────
    tick: int
    campaign_id: str
    location_id: str

    # ── Пространственная истина ───────────────────────────────────
    # Reference на уже построенный SpatialService (НЕ rebuild!).
    # SpatialService immutable после конструирования (ADR-065).
    # build_for_location() вызывается ОДИН раз за сессию.
    spatial_service: Any  # Optional[SpatialService]

    # ── NPC позиции ───────────────────────────────────────────────
    # Frozen copy: {"npc_id": {"local_position": {"x":..., "y":...}, ...}}
    npc_positions: Dict[str, Dict[str, Any]]

    # ── Активные транзиты ─────────────────────────────────────────
    # Frozen copy: {"npc_id": {"status": "MOVING", "path_waypoints": [...], ...}}
    active_traversals: Dict[str, Dict[str, Any]]

    # (S203.1: поле перемещено в конец dataclass — см. behavioral ownership ниже)

    # ── Детерминизм ───────────────────────────────────────────────
    # RNG seed для воспроизведения jitter и других случайных выборов
    rng_seed: int

    # ── Поведенческое владение (S203.1 / Stage 2A, shadow) ────────
    # Frozen copy: {"npc_id": {"commitment_id": ..., "status": ..., ...}}
    # Только АКТИВНЫЕ обязательства. History/ordinals — audit-трейл,
    # не состояние мира в момент t: в снапшот не замораживаются.
    # Optional без дефолта: совместимость с прямыми конструкторами тестов.
    active_commitments: Optional[Dict[str, Dict[str, Any]]] = None

    # ── Геометрия мира ────────────────────────────────────────────
    # S212 FIX (чужая коллизия): блок в конце класса (поля без дефолта не могут
    # стоять после дефолтных — TypeError на импорте). Дефолты: сцена без
    # заявленной геометрии валидна. Стены для is_blocked_by_wall (EventCompiler).
    spatial_walls: Any = None
    # Мебель / препятствия (LOD0)
    spatial_obstacles: Any = None
    # W1 (ADR-O-371): семантическая объектная топология тика.
    # Замораживается deepcopy в build_snapshot (паттерн active_commitments,
    # S215). {} = объектов нет — легитимно до появления спавнера (W3+).
    # Presentation-проекция объектов — W7, НЕ здесь.
    world_objects: Optional[Dict[str, Dict[str, Any]]] = None


def build_snapshot(
    tick: int,
    campaign_id: str,
    location_id: str,
    spatial_service: Any,
    scene_state: Dict[str, Any],
    rng_seed: int = 0,
) -> WorldSnapshot:
    """Строит замороженный снимок из живого состояния.

    Принцип: не вычисляет, только фотографирует.
    SpatialService — reference (не rebuild, ADR-065).
    npc_positions / active_traversals — deep copy (гарантия immutability).
    """
    # Deep copy — гарантия что мутация scene_state не повлияет на снимок
    _npc_pos = copy.deepcopy(scene_state.get("npc_positions", {}))
    _active_travs = copy.deepcopy(scene_state.get("active_traversals", {}))
    # S203.1 (Stage 2A): заморозка поведенческого владения (shadow-реестр).
    _active_commitments = copy.deepcopy(scene_state.get("active_commitments", {}))
    # W1 (ADR-O-371): заморозка семантической топологии объектов.
    # Пассивная фотография subtree: стор не вызывается, ничего не
    # вычисляется — тот же контракт, что и у остальных deep-copy полей.
    _world_objects = copy.deepcopy(scene_state.get("world_objects", {}))

    # BUG-FB-029 FIX: Детерминированный snapshot_id и created_at (вместо wall-clock и uuid4).
    _seed_str = f"{tick}:{campaign_id}:{location_id}".encode("utf-8")
    _det_uuid = UUID(hex=hashlib.md5(_seed_str).hexdigest())

    snapshot = WorldSnapshot(
        snapshot_id=_det_uuid,
        created_at=float(tick),  # simulation time, not wall-clock
        tick=tick,
        campaign_id=campaign_id,
        location_id=location_id,
        spatial_service=spatial_service,
        npc_positions=_npc_pos,
        active_traversals=_active_travs,
        active_commitments=_active_commitments,
        spatial_walls=scene_state.get("spatial_walls"),
        spatial_obstacles=scene_state.get("spatial_obstacles"),
        world_objects=_world_objects,
        rng_seed=rng_seed,
    )

    # Observability: лог создания снимка (ФАЗА 0 — shadow mode)
    logger.info(
        f"[SNAPSHOT_CREATED] id={snapshot.snapshot_id.hex[:8]} "
        f"tick={tick} location={location_id} "
        f"npcs={len(_npc_pos)} traversals={len(_active_travs)} "
        f"rng_seed={rng_seed}"
    )

    return snapshot

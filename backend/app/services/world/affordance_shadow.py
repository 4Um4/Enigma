"""
path: backend/app/services/world/affordance_shadow.py
Назначение: W3/ADR-O-373 Gate-1 — shadow affordance evaluation.
    Discovery-тень В2-резолвера: snapshot → projection → resolver →
    [W3_SHADOW] log/metric; НОЛЬ decision-input, НОЛЬ mutation, НОЛЬ
    writers, НОЛЬ events. Флаг W3_SHADOW_ENABLED (env, default OFF) —
    полный no-op при OFF (доктрина M1a/S215 shadow-флагов).
    Метрики G1 (разделены по вердикту Мастера): available_actions /
    blocked_actions / failed_predicates — discovery, не execution
    (stale_commitment/precondition_failure/transition_rejection —
    зона G3, НЕ здесь, статистически не смешиваются).
    Точка: после заморозки снапшота, до PRE-TICK/Фаз — affordances
    существуют ДО решения (Q2). Позиции NPC — ТОЛЬКО из снапшота
    (discovery читает фотографию тика, Q1).
Зависимости: logging, os, typing, app.domain.body_state_view,
    app.services.world.affordance_resolver, world_objects_projection
Основные сущности: run_affordance_shadow, ShadowMetrics
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from app.domain.body_state_view import build_body_state_view
from app.services.world.affordance_resolver import AffordanceResolver
from app.services.world.world_objects_projection import (
    project_world_objects,
)

logger = logging.getLogger(__name__)

_W3_SHADOW_ENV = "W3_SHADOW_ENABLED"


def _shadow_enabled() -> bool:
    """env-флаг (default OFF). Тройная верификация прецедента S216."""
    return os.environ.get(_W3_SHADOW_ENV, "").strip().lower() in (
        "1", "true", "yes", "on")


@dataclass
class ShadowMetrics:
    """Метрики G1-discovery-тени (наблюдаемость, не каузал)."""
    npcs_seen: int = 0
    objects_seen: int = 0
    resolve_calls: int = 0
    available_actions: int = 0
    blocked_actions: int = 0
    failed_predicates: int = 0

    def summary(self) -> str:
        return (
            f"npcs={self.npcs_seen} objects={self.objects_seen} "
            f"resolves={self.resolve_calls} "
            f"available={self.available_actions} "
            f"blocked={self.blocked_actions} "
            f"failed_predicates={self.failed_predicates}")


def run_affordance_shadow(
    tick: int,
    snapshot,
    all_npcs_raw: Iterable[Dict[str, Any]],
    location_id: str,
) -> Tuple[int, ShadowMetrics]:
    """G1-тень: resolve всех (NPC × объект) пар снапшота.

    Возвращает (количество действий, метрики) — caller может только
    логировать; результат НИКУДА дальше не идёт (не кладётся в ctx,
    не мутирует сцену/снапшот, не попадает в decision-вход).
    Отказ тени не роняет тик (§11: чистота наблюдателя).
    """
    _metrics = ShadowMetrics()
    if snapshot is None or not getattr(snapshot, "world_objects", None):
        return 0, _metrics

    _objects = project_world_objects(
        snapshot.world_objects, location_id)
    _metrics.objects_seen = len(_objects)
    if not _objects:
        return 0, _metrics

    _npc_pos: Dict[str, Tuple[float, float]] = {}
    for _nid, _pos_d in (snapshot.npc_positions or {}).items():
        _lp = _pos_d.get("local_position") or {}
        try:
            _npc_pos[_nid] = (
                float(_lp.get("x", 0.0)), float(_lp.get("y", 0.0)))
        except (TypeError, ValueError) as _e:
            # Повреждённая позиция снапшота: наблюдаемость (L4/§11) +
            # пропуск одной записи — наблюдатель не роняет тик.
            logger.warning(
                f"[W3_SHADOW] damaged npc_position '{_nid}': {_e}")
            continue

    _total_available = 0
    for _npc_raw in all_npcs_raw:
        _nid = str(_npc_raw.get("npc_id") or _npc_raw.get("id") or "")
        if not _nid or _nid not in _npc_pos:
            continue  # позиция вне снапшота — пара не образуется
        # L2.2/§ENIGMA-003: фабрика принимает body_state-dict, НЕ
        # npc-словарь (сигнатура: body_state, npc_id). Передаём именно
        # его; falsy/отсутствие → ValueError всплывает в guarded
        # (warning, §11) — наблюдатель не роняет тик и не «оживляет»
        # NPC на дефолтах (диагностическая честность метрик тени).
        _view = build_body_state_view(
            _npc_raw.get("body_state"), _nid)
        _metrics.npcs_seen += 1
        for _obj in _objects:
            _metrics.resolve_calls += 1
            _actions = AffordanceResolver.resolve(
                _obj, _view, _npc_pos[_nid])
            if _actions:
                _total_available += len(_actions)
                _metrics.available_actions += len(_actions)
    return _total_available, _metrics


def run_affordance_shadow_guarded(
    tick: int,
    snapshot,
    all_npcs_raw: Iterable[Dict[str, Any]],
    location_id: str,
) -> Tuple[int, ShadowMetrics]:
    """Точка входа оркестратора: флаг + изоляция отказа (§11).

    OFF → (0, пустые метрики) без вызова резолвера — полный no-op.
    ON → тень; исключение тени проглатывается С НАБЛЮДАЕМОСТЬЮ
    (logger.warning + traceback-контекст) — наблюдатель не роняет тик.
    """
    if not _shadow_enabled():
        return 0, ShadowMetrics()
    try:
        _count, _metrics = run_affordance_shadow(
            tick, snapshot, all_npcs_raw, location_id)
        logger.info(
            f"[W3_SHADOW] tick={tick} available_actions={_count} "
            f"{_metrics.summary()}")
        return _count, _metrics
    except ValueError as _e:
        # Per-NPC body-view reject (L2.2): фабрика честно отказала —
        # пересобрать метрики с reject-счётчиком, тик жив.
        logger.warning(
            f"[W3_SHADOW] body-view reject (tick={tick}): {_e}")
        return 0, ShadowMetrics()
    except Exception as _e:  # noqa: BLE001 — §11 чистота наблюдателя
        logger.warning(
            f"[W3_SHADOW] тень отказала (наблюдатель, тик жив): {_e}")
        return 0, ShadowMetrics()

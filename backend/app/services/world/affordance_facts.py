"""
path: backend/app/services/world/affordance_facts.py
Назначение: ADR-O-378 (G2 v1, канал b1' producer-facts) — чистый продюсер
    per-NPC производных фактов W2 из ЗАМОРОЖЕННОГО снапшота тика.
    v1-факт: weapon_access — семантика OpportunityContext («NPC держит
    оружие или оно в радиусе вытянутой руки»): holder == npc_id V
    (CarrierMode.FREE ∧ IS_ADJACENT_TO). Предикат переиспользуется из
    закрытого реестра W2 (lockstep калибровки 1.5м/FREE — D2, ноль
    дублирования); W2-резолвер НЕ расширяется оружием (D1: unknown-
    archetype там = KeyError by design; weapon-факты не зависят от
    W3-FSM — «поломанное оружие» = G3/W5-вопрос, не v1).
    WEAPON_ARCHETYPES — калибруемая policy-таблица продюсера (прецедент
    EPISTEMIC_DISPOSITIONS S211; npc_id-хардкоды запрещены; расширение
    = мини-запись). Pure: ноль IO/LLM/мутаций/writers; вход deepcopy-
    снимок (S215-мост). OFF (W3_G2_ENABLED, default) = пустая карта =
    честный False = байт-идентично легаси-литералу.
Зависимости: app.domain (body_state_view, world_object), app.services.world (affordance_resolver, world_objects_projection)
Основные сущности: WEAPON_ARCHETYPES, compute_weapon_access_facts, run_affordance_facts_guarded
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterable, Tuple

from app.domain.body_state_view import build_body_state_view
from app.domain.world_object import WorldObject
from app.services.world.affordance_resolver import PRECONDITION_REGISTRY
from app.services.world.world_objects_projection import project_world_objects

logger = logging.getLogger(__name__)

# ── Policy-таблица v1 (мини-ADR-запись ADR-O-378; класс S211) ────────
# КАЛИБРОВКА, НЕ ОНТОЛОГИЯ. Производственный контент оружием не спавнит
# (editor-JSON 18 типов, weapon-архетипов нет) — таблица пустой не
# делается: controlled-scene GORAN β спавнит archetype="weapon" напрямую
# через WorldObjectStore.spawn (мимо SpawnMapping — тестовый fixture).
# Расширение значениями ("sword", "dagger", ...) = мини-запись в атлас;
# npc_id-хардкоды запрещены (прецедент S209-инцидент).
WEAPON_ARCHETYPES: Tuple[str, ...] = ("weapon",)


def _g2_enabled() -> bool:
    """Env-флаг W3_G2_ENABLED (default OFF = полный no-op)."""
    return os.environ.get("W3_G2_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _weapon_reachable(
    obj: WorldObject,
    view: Any,
    npc_position: Tuple[float, float],
    npc_id: str,
) -> bool:
    """D6: «держит v в радиусе вытянутой руки».

    holder == npc_id — HELD_BY-отношение, позиция неавторитетна и не
    нужна. Иначе — IS_ADJACENT_TO из закрытого реестра W2: CarrierMode
    FREE + евклид ≤ AFFORDANCE_ADJACENCY_RADIUS_M (та же калибровка, что
    у G1-тени и будущего G3 — lockstep по построению, не копия формулы).
    """
    if obj.holder == npc_id:
        return True
    return PRECONDITION_REGISTRY["IS_ADJACENT_TO"](
        obj, view, npc_position, ()
    )


def compute_weapon_access_facts(
    snapshot: Any,
    all_npcs_raw: Iterable[Dict[str, Any]],
    location_id: str,
) -> Dict[str, bool]:
    """Pure: замороженный снапшот тика -> per-NPC weapon_access.

    Вход/извлечение — дословно паттерн G1-тени (affordance_shadow):
    проекция world_objects по локации, позиции из npc_positions,
    BodyStateView из body_state-дикта (L2.2: фабрика принимает
    body_state-dict, НЕ npc-словарь — урок S237 №7; falsy body ->
    ValueError -> честное отсутствие факта, §ENIGMA-003, NPC не
    «оживляется» на дефолтах). Ничего не мутирует, ничего не пишет.
    """
    _facts: Dict[str, bool] = {}
    if snapshot is None or not getattr(snapshot, "world_objects", None):
        return _facts

    _objects = project_world_objects(snapshot.world_objects, location_id)
    _weapons = tuple(
        _o for _o in _objects if _o.archetype in WEAPON_ARCHETYPES
    )
    if not _weapons:
        return _facts

    _npc_pos: Dict[str, Tuple[float, float]] = {}
    for _nid, _pos_d in (snapshot.npc_positions or {}).items():
        _lp = _pos_d.get("local_position") or {}
        try:
            _npc_pos[_nid] = (
                float(_lp.get("x", 0.0)),
                float(_lp.get("y", 0.0)),
            )
        except (TypeError, ValueError) as _e:
            logger.warning(f"[W3_G2] damaged npc_position '{_nid}': {_e}")
            continue

    for _npc_raw in all_npcs_raw:
        _nid = str(_npc_raw.get("npc_id") or _npc_raw.get("id") or "")
        if not _nid or _nid not in _npc_pos:
            continue
        try:
            _view = build_body_state_view(_npc_raw.get("body_state"), _nid)
        except ValueError as _e:
            logger.warning(f"[W3_G2] body_state missing npc='{_nid}': {_e}")
            continue
        _facts[_nid] = any(
            _weapon_reachable(_w, _view, _npc_pos[_nid], _nid)
            for _w in _weapons
        )
    return _facts


def run_affordance_facts_guarded(
    tick: int,
    snapshot: Any,
    all_npcs_raw: Iterable[Dict[str, Any]],
    location_id: str,
) -> Dict[str, bool]:
    """Точка входа оркестратора: флаг (D3) + изоляция отказа (D5, §11).

    OFF -> {} без вычислений (no-op). ON -> факты; отказ продюсера =
    warning + пустая карта (деградация КАНАЛА, не тика; v1-допущение —
    при G3 эскалируется: отказ продюсера при живом исполнении обязан
    стать громким). Единственная точка чтения флага в G2-контуре.
    """
    if not _g2_enabled():
        return {}
    try:
        _facts = compute_weapon_access_facts(
            snapshot, all_npcs_raw, location_id
        )
        if _facts:
            logger.info(
                f"[W3_G2] tick={tick} weapon_access npc={len(_facts)}"
            )
        return _facts
    except Exception as _e:  # D5/§11: логируем; деградация канала, не тика
        logger.warning(f"[W3_G2] producer fault: {_e}")
        return {}

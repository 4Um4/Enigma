# -*- coding: utf-8 -*-
"""
path: /project/backend/app/services/npc/exploration_target_resolver.py
Назначение: Phase D Э-3 — frontier-выбор exploration-цели. Отвечает ровно на
    один вопрос (вердикт Мастера): «Какую физически видимую границу ТЕКУЩЕЙ
    локации этот NPC ещё лично не проходил?». Frontier = boundary-узлы
    boundary_map (перцепция среды, факты graph_compiler:985-993) минус узлы с
    персональным EpistemicRecord(EXITS_TO, subject="<loc>:<node>") (пройденные).
    Выбор детерминирован: минимальная дистанция до двери (x/y из boundary_map),
    tie-break лексикографический — без RNG-прокидки.
    ГРАНИЦЫ (вердикт): НЕ читает neighbor_chunk; не строит маршрутов по
    WorldGraph; НЕ пишет EXITS_TO; НЕ мутирует EpistemicStore; НЕ двигает NPC;
    НЕ создаёт Intent; НЕ решает priority/arbitration.
Зависимости: typing/logging (чтение записей — паттерн personal_route_resolver:44-58)
Основные сущности: resolve_exploration_target
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_exploration_target(
    agent_id: str,
    store: Any,
    spatial_service: Any,
    current_loc: str,
    npc_xy: Tuple[float, float],
) -> Optional[str]:
    """Pure function: frontier boundary-узел текущей локации или None."""
    if spatial_service is None or not current_loc:
        return None
    try:
        bmap: Dict[str, Dict[str, Any]] = dict(
            getattr(spatial_service, "boundary_map", {}) or {}
        )
    except Exception:
        bmap = {}
    if not bmap:
        return None

    # Канон чтения EXITS_TO (personal_route_resolver:44-58): только doorы,
    # лично пройденные ИЗ текущей локации (subject = "<loc>:<node>")
    traversed: set = set()
    if store is not None:
        try:
            records = store.get_all_for_agent(agent_id) or []
        except Exception:
            records = []
        for rec in records:
            prop = getattr(rec, "proposition", None)
            if prop is None:
                continue
            pred = getattr(prop.predicate, "value", prop.predicate)
            if str(pred) != "exits_to":
                continue
            subject = getattr(prop, "subject_id", "") or ""
            if subject.split(":", 1)[0] == current_loc:
                traversed.add(subject)

    # Frontier: neighbor_chunk не читается — сосед узнается после crossing
    frontier: List[Tuple[float, str]] = []
    for node_id, info in bmap.items():
        if node_id in traversed:
            continue
        x = info.get("x")
        y = info.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        dist = ((x - npc_xy[0]) ** 2 + (y - npc_xy[1]) ** 2) ** 0.5
        frontier.append((dist, node_id))
    if not frontier:
        logger.info(
            f"[EXPLORATION] npc={agent_id} loc={current_loc}: frontier пуст "
            f"(все {len(bmap)} дверей пройдены)"
        )
        return None

    frontier.sort()  # (dist, node_id) — детерминизм
    selected = frontier[0][1]
    # «Почему выбран этот boundary» — обязательная печать acceptance
    logger.info(
        f"[EXPLORATION] npc={agent_id} loc={current_loc}: "
        f"visible={[n for _, n in sorted(frontier, key=lambda t: t[1])]} "
        f"known={sorted(traversed)} -> selected={selected} dist={frontier[0][0]:.2f}"
    )
    return selected

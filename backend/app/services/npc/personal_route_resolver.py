# -*- coding: utf-8 -*-
"""
path: /project/backend/app/services/npc/personal_route_resolver.py
Назначение: Phase C — personal epistemic routing. Детерминированный BFS по
    ЛИЧНОМУ графу NPC, реконструированному из EpistemicRecord(EXITS_TO).
    Направленные рёбра: subject_id = boundary-узел-исток ("loc:node"),
    object_id = целевая локация. НИКАКОГО доступа к WorldGraph/SpatialService
    — anti-leakage by construction (модуль не импортирует spatial-*).
Зависимости: app.domain.epistemology (чтение записей)
Основные сущности: PersonalRouteResult, resolve_personal_route
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersonalRouteResult:
    status: str  # KNOWN_ROUTE | UNKNOWN_ROUTE
    agent_id: str
    from_loc: str
    to_loc: str
    path: Tuple[str, ...] = ()   # локации по порядку
    edges: Tuple[Tuple[str, str, float], ...] = ()  # (from, to, conf)
    min_confidence: float = 0.0
    known_edges: Tuple[Tuple[str, str], ...] = ()   # диагностика UNKNOWN


def resolve_personal_route(
    agent_id: str,
    store: Any,
    from_loc: str,
    to_loc: str,
) -> PersonalRouteResult:
    """BFS по личному графу NPC из EpistemicStore. KNOWN_ROUTE ≠ CERTAIN."""
    edges: Dict[str, List[Tuple[str, float]]] = {}
    known_flat: List[Tuple[str, str]] = []
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
            obj = getattr(prop, "object_id", "") or ""
            frm = subject.split(":", 1)[0] if ":" in subject else subject
            if frm and obj:
                edges.setdefault(frm, []).append(
                    (obj, float(getattr(rec, "confidence", 0.0) or 0.0))
                )
                known_flat.append((frm, obj))
    known = tuple(sorted(set(known_flat)))

    if from_loc == to_loc:
        return PersonalRouteResult(
            "KNOWN_ROUTE", agent_id, from_loc, to_loc, (from_loc,), (), 1.0, known
        )

    prev: Dict[str, Optional[str]] = {from_loc: None}
    edge_used: Dict[str, Tuple[str, float]] = {}
    q = deque([from_loc])
    while q:
        cur = q.popleft()
        for nxt, conf in edges.get(cur, ()):
            if nxt not in prev:
                prev[nxt] = cur
                edge_used[nxt] = (cur, conf)
                if nxt == to_loc:
                    q.clear()
                    break
                q.append(nxt)

    if to_loc not in prev:
        return PersonalRouteResult(
            "UNKNOWN_ROUTE", agent_id, from_loc, to_loc, (), (), 0.0, known
        )

    path = [to_loc]
    cur = to_loc
    while prev[cur] is not None:
        cur = prev[cur]  # type: ignore[assignment]
        path.append(cur)
    path.reverse()
    used = tuple(
        (path[i], path[i + 1], edge_used[path[i + 1]][1])
        for i in range(len(path) - 1)
    )
    return PersonalRouteResult(
        "KNOWN_ROUTE",
        agent_id,
        from_loc,
        to_loc,
        tuple(path),
        used,
        min(c for _, _, c in used),
        known,
    )

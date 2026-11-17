from __future__ import annotations

# backend/app/models/world/world_predicate.py
"""
Назначение: Предикат над состоянием мира для слоя Process/Planner (ТЗ Отчёт №6 §2-3, ADR-O-445).
            Здесь же — единственная реализация сопоставления значений value_matches
            (диапазоны '>5', '>=2', '<3', '<=4') для всех предикатов онтологии.
Зависимости: stdlib only (dataclasses, re, typing).
Основные сущности: WorldPredicate, value_matches
"""

import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple

_RANGE_RE = re.compile(r"^(>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)$")


def _parse_range(v: Any) -> Optional[Tuple[str, float]]:
    if isinstance(v, str):
        m = _RANGE_RE.match(v.strip())
        if m is not None:
            return m.group(1), float(m.group(2))
    return None


def _cmp(value: float, op: str, bound: float) -> bool:
    if op == ">":
        return value > bound
    if op == ">=":
        return value >= bound
    if op == "<":
        return value < bound
    if op == "<=":
        return value <= bound
    return False


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def value_matches(candidate: Any, constraint: Any) -> bool:
    """Сопоставление значения с допуском (fail-closed).

    Ровно одна из сторон может нести диапазон-строку; вторая обязана быть числом.
    Диапазон в constraint проверяет candidate; диапазон в candidate проверяет
    constraint (симметрия для AffordancePredicate.matches). Несравнимое -> False.
    """
    rc = _parse_range(constraint)
    if rc is not None:
        return _is_number(candidate) and _cmp(float(candidate), rc[0], rc[1])
    rr = _parse_range(candidate)
    if rr is not None:
        return _is_number(constraint) and _cmp(float(constraint), rr[0], rr[1])
    if isinstance(candidate, bool) != isinstance(constraint, bool):
        return False
    return bool(candidate == constraint)


@dataclass(frozen=True)
class WorldPredicate:
    """Требование к состоянию мира: (domain, attribute, value).

    Потребители: Process.requires_world_state, ProcessSource.requires_provider_state,
    WorldGraph.find_paths(target_predicates). Снапшот удовлетворяет предикату,
    если значение по (domain, attribute) проходит value_matches(snapshot_value, value).
    """

    domain: str
    attribute: str
    value: Any

    def is_satisfied_by(self, snapshot_value: Any) -> bool:
        return value_matches(snapshot_value, self.value)

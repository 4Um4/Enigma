from __future__ import annotations

# backend/app/models/world/affordance.py
"""
Назначение: Композиционная открытая онтология возможностей мира (ТЗ Отчёт №6 §5, ADR-O-445).
            Параллельный слой к физическому AffordanceVector (domain/motion_core.py — НЕ ТРОГАЕМ):
            социальные/торговые/духовные возможности как предикаты над миром.
            Открытая онтология: новый домен = запись в config/world/ontology/domains.yaml,
            НЕ правка кода и НЕ новый enum.
Зависимости: app.models.world.world_predicate (value_matches); app.domain.motion_core (AffordanceVector, только чтение).
Основные сущности: AffordancePredicate, vector_to_predicates
"""

from dataclasses import dataclass
from typing import Any, FrozenSet, List

from app.domain.motion_core import AffordanceVector
from app.models.world.world_predicate import value_matches


@dataclass(frozen=True)
class AffordancePredicate:
    """Композиционный предикат возможности мира.

    НЕ enum. Domain и attribute — открытые идентификаторы (любые строки).
    Planner ищет по предикату: world.find_where(domain='resource', attribute='alcohol').
    """

    domain: str
    attribute: str
    value: Any
    props: FrozenSet[str] = frozenset()

    def matches(self, other: "AffordancePredicate") -> bool:
        """Совпадение с допуском: value может быть диапазоном или точным значением."""
        if self.domain != other.domain:
            return False
        if self.attribute != other.attribute:
            return False
        return value_matches(self.value, other.value)


# Примеры предикатов (НЕ enum — просто именованные предикаты; словарь расширяется
# новыми константами/YAML-записями, старые не меняются):
ALCOHOL_AVAILABLE = AffordancePredicate(
    domain="resource",
    attribute="alcohol",
    value="present",
    props=frozenset({"consumable", "intoxicating"}),
)
WARM_AREA = AffordancePredicate(domain="environment", attribute="temperature", value="warm")
CONCEALMENT = AffordancePredicate(domain="cover", attribute="visual", value="available", props=frozenset({"partial"}))
CROWD_PRESENT = AffordancePredicate(domain="social", attribute="crowd_density", value="high")
AUTHORITY_PRESENT = AffordancePredicate(
    domain="authority", attribute="presence", value="armed", props=frozenset({"corruptible"})
)


def vector_to_predicates(vec: AffordanceVector) -> List[AffordancePredicate]:
    """Мост AffordanceVector -> AffordancePredicate (только для чтения).

    Позволяет Planner'у использовать оба слоя единообразно. Вектор не мутируется.
    """
    preds: List[AffordancePredicate] = []
    if vec.can_conceal > 0.5:
        preds.append(AffordancePredicate("cover", "visual", "available"))
    if vec.light_level < 0.3:
        preds.append(AffordancePredicate("environment", "light_level", "low"))
    return preds

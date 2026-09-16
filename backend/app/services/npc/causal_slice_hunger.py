# path: /project/backend/app/services/npc/causal_slice_hunger.py
# Назначение: R6 CAUSAL SLICE 2a — продюсер DesiredChange из голода
#   (мини-АДР CS7-CS13): hunger ≥ NEED_GATE + отсутствие своего ресурса
#   → capability-скан мира (EconomicProfile.has_stock — ПРОЕКЦИЯ, не
#   новый SSOT; оговорка Тай: решение действительно только для
#   hunger-домена) → выбор addressee (capability × trust ×
#   достижимость) → оценка способов из СУЩЕСТВУЮЩИХ интентов (CS6):
#   trade / request_service / steal. Чистая функция; capability-вакуум
#   = честный None (CS9), не fallback на ближайшего. Каждый вес —
#   композиция ИМЕНОВАННЫХ факторов (CS13: причинная читаемость).
#   ГРАНИЦА: SOCIAL-сессия (S262+) владеет target-stage — файл НЕ
#   трогает social_target_resolver / _resolve_target (интеграция 2b,
#   координация после их baseline).
# Зависимости: app.domain.desired_change
# Основные сущности: HungerDesiredChangeProducer

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.desired_change import DesiredChange, acquire_resource

logger = logging.getLogger(__name__)

# Калибровочные параметры (вердикт Тай §3: НЕ законы ENIGMA)
NEED_GATE: float = 0.5        # hunger уже причина (точка выхода LifeEngine)
REACH_RADIUS: float = 5.0     # достижимость (SPEAK_RADIUS-прецедент S96)
VIABILITY_GATE: float = 0.1   # ниже — ни один способ не жив → честный None
GOOD_ID = "food"

# S209-паттерн (архетип, не npc_id-хардкод): базовая близость к краже
_ARCHETYPE_STEAL_BASE: Dict[str, float] = {"thief": 0.8}
_DEFAULT_STEAL_BASE: float = 0.08


class HungerDesiredChangeProducer:
    """Собирает существующие машины в причинный контур (CS4).

    Ничего не мутирует; не создаёт интентов; вердикт способа не
    выносит — готовит веса и адресата, выбор остаётся за DecisionHub
    (CS2). Интеграция addressee в target-стейдж — срез 2b."""

    @staticmethod
    def resolve(
        who: str,
        hunger: float,
        own_profile: Any,
        profiles: Dict[str, Any],
        distances: Dict[str, float],
        rel: Dict[str, Dict[str, float]],
        food_price: float = 2.0,
        archetype: str = "commoner",
        will_state: str = "free",
    ) -> Optional[DesiredChange]:
        # T1 (CS1): причина первична — без голода нет цели
        if float(hunger) < NEED_GATE:
            return None

        # CS11: свой ресурс есть → путь предшественника (EAT/авто-
        # насыщение NeedEngine), продюсер молчит. has_good = ЛИЧНЫЙ
        # запас (goods); has_stock = stock_for_sale (товар на
        # продажу) — поле НЕ имеет production-писателей (находка
        # R6: вакуум класса WorldObject.ownership). Срез читает
        # живое поле; «B can sell» ≠ «B has» — будущая проекция.
        if (
            own_profile is not None
            and callable(getattr(own_profile, "has_good", None))
            and own_profile.has_good(GOOD_ID)
        ):
            return None

        # ── Capability-скан (CS7): проекция EconomicProfile (has_good) ──
        candidates = [
            nid
            for nid, prof in (profiles or {}).items()
            if nid != who
            and callable(getattr(prof, "has_good", None))
            and prof.has_good(GOOD_ID)
            and float((distances or {}).get(nid, float("inf"))) <= REACH_RADIUS
        ]
        if not candidates:
            return None  # CS9: вакуум = честное отсутствие цели

        # ── Выбор addressee (CS10): trust-доминанта, дистанция-тайбрейк ──
        def _trust(nid: str) -> float:
            axes = (rel or {}).get(nid) or {}
            return float(axes.get("trust", 50.0))  # 50 = prior незнакомца (S206)

        addressee = max(
            candidates,
            key=lambda nid: (
                _trust(nid),
                -float((distances or {}).get(nid, 0.0)),
            ),
        )
        trust = _trust(addressee)
        trust_norm = max(-1.0, min(1.0, trust / 100.0))

        # ── Ограничения A (CS4: существующие машины) ──
        gold = (
            float(getattr(own_profile, "gold", 0.0) or 0.0)
            if own_profile is not None
            else 0.0
        )
        afford = 1.0 if gold >= float(food_price) else 0.0

        steal_base = _ARCHETYPE_STEAL_BASE.get(archetype, _DEFAULT_STEAL_BASE)
        # S209: скрытное действие — привилегия broken/deceptive воли
        if will_state not in ("broken", "deceptive"):
            steal_base = 0.0

        # ── Способы: именованные факторы (CS13) ──
        w: Dict[str, float] = {}
        # купить: деньги × доверие-комфорт сделки с B
        w["trade"] = round(afford * (0.4 + 0.6 * max(0.0, trust_norm)), 4)
        # попросить: доверие выше нейтрального (ниже 40 — не просим)
        w["request_service"] = round(max(0.0, (trust - 40.0) / 60.0), 4)
        # украсть: натура × нужда (безденежье) — S209-паттерн
        w["steal"] = round(steal_base * (1.0 - 0.5 * afford), 4)

        # CS12: нормировка суммы ≤ 1.0 — анти-двойной-счёт с eco_modifiers
        _sum = sum(w.values())
        if _sum > 1.0:
            _factor = 1.0 / _sum
            w = {k: round(v * _factor, 4) for k, v in w.items()}
            _drift = round(1.0 - sum(w.values()), 6)
            if _drift != 0.0:
                _top = max(w, key=w.get)
                w[_top] = round(w[_top] + _drift, 4)

        # Viability (W4): все способы мертвы (враг + нечем платить +
        # не вор) → наличие capability ≠ наличие пути → честный None
        if max(w.values(), default=0.0) < VIABILITY_GATE:
            return None

        return acquire_resource(who=who, addressee=addressee, method_weights=w)

    @staticmethod
    def to_modifiers(dc: Optional[DesiredChange]) -> Dict[str, float]:
        """CS2: проекция в Modifier Contract (ADR-O-355). None → {} —
        срез аддитивен, мир без причины не меняется (зеркально срезу-1)."""
        if dc is None:
            return {}
        _SCALE = 0.6  # V1-калибровка: сдвигает, не переворачивает скоринг
        return {k: round(v * _SCALE, 4) for k, v in dc.method_weights.items()}
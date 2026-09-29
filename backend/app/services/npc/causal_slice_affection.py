# path: /project/backend/app/services/npc/causal_slice_affection.py
# Назначение: R8 CAUSAL SLICE 4 — продюсер DesiredChange из тёплой связи
#   (CS17-CS19, ADR-O-398). ПЕРВОЕ структурное who ≠ target_of_change:
#   A меняет состояние ДРУГОГО (B.food↑). CS17: affection = проекция
#   тёплых осей RelationshipStore (trust ≥ 40 ∧ тёплая ось ≥ 40, шкала
#   0-100), не сущность; флаги is_loving/сare Store запрещены. CS18:
#   чужое distress читается из world-снапшота (all_npcs_raw body_state,
#   0-100) — proxy; полноценная perception-мембрана «A видит голод B» —
#   эпистемический долг честности (регистрируется). CS19: capacity —
#   забота без ресурса и денег = честный None (желание без возможности
#   не действие). Способы — существующие: talk (разделить трапезу) /
#   trade (купить ДЛЯ B) / call_for_help (тяжёлый distress). Чистая
#   функция; fail-молчание.
# Зависимости: app.domain.desired_change
# Основные сущности: AffectionDesiredChangeProducer

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.desired_change import DesiredChange, nurture

logger = logging.getLogger(__name__)

# Калибровки (НЕ законы): пороги согласованы с SSOT-шкалой 0-100
WARM_TRUST_GATE: float = 40.0
WARM_AFFECTION_GATE: float = 40.0
DISTRESS_GATE: float = 50.0    # hunger B ≥ 50 (зеркало NEED_GATE R6)
REACH_RADIUS: float = 5.0
VIABILITY_GATE: float = 0.1


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class AffectionDesiredChangeProducer:
    """Собирает существующие машины (CS4): тёплые оси SSOT, профили
    экономики (R6-проекция инвертированная: не «кто даст мне», а
    «кому могу дать я»). Ничего не мутирует; выбор — DecisionHub."""

    @staticmethod
    def resolve(
        who: str,
        rel: Dict[str, Dict[str, float]],
        others_state: Dict[str, Dict[str, float]],
        own_profile: Any,
        distances: Dict[str, float],
        food_price: float = 2.0,
    ) -> Optional[DesiredChange]:
        try:
            # ── CS17: тёплая пара = проекция осей (attraction с
            #    фоллбэком affection — runtime-имя оси не угадываем) ──
            best_tid, best_warmth = None, 0.0
            for _tid, _axes in (rel or {}).items():
                if not _axes:
                    continue
                _trust = float(_axes.get("trust", 0.0))
                _warm_axis = float(
                    _axes.get("attraction", _axes.get("affection", 0.0))
                )
                if _trust < WARM_TRUST_GATE or _warm_axis < WARM_AFFECTION_GATE:
                    continue
                _warmth = _clamp01(
                    (_trust / 100.0 + _warm_axis / 100.0) / 2.0
                )
                if _warmth > best_warmth:
                    best_warmth, best_tid = _warmth, _tid
            if best_tid is None:
                return None  # T1: забота = проекция тепла (CS17)

            # ── CS18: видимое distress B (world-снапшот, 0-100) ──
            _b_state = (others_state or {}).get(best_tid) or {}
            _distress = _clamp01(float(_b_state.get("hunger", 0.0)) / 100.0)
            if _distress < DISTRESS_GATE / 100.0:
                return None  # T2: B сыт — нет желаемого изменения

            # ── Достижимость (зеркало W5) ──
            _dist = float((distances or {}).get(best_tid, float("inf")))
            if _dist > REACH_RADIUS:
                return None

            # ── CS19: capacity ──
            _own_food = False
            _gold = 0.0
            if own_profile is not None:
                _own_food = bool(own_profile.has_good("food"))
                _gold = float(getattr(own_profile, "gold", 0.0) or 0.0)
            _afford = _gold >= float(food_price)
            if not _own_food and not _afford:
                return None  # T3: желание без возможности не действие

            # ── Способы: именованные факторы ──
            w: Dict[str, float] = {}
            # разделить трапезу: тепло × distress × свой ресурс
            # (без своей еды — сжимается до сотрапезничества ×0.3)
            _res_factor = 1.0 if _own_food else 0.3
            w["talk"] = round(best_warmth * _distress * _res_factor, 4)
            # купить ДЛЯ B: деньги × тепло × distress
            w["trade"] = round(
                (1.0 if _afford else 0.0) * best_warmth * _distress * 0.8, 4
            )
            # тяжёлый случай: привлечь помощь (distress > 0.6)
            w["call_for_help"] = round(
                best_warmth * max(0.0, _distress - 0.6) * 0.5, 4
            )

            _sum = sum(w.values())
            if _sum > 1.0:
                _f = 1.0 / _sum
                w = {k: round(v * _f, 4) for k, v in w.items()}
            if max(w.values(), default=0.0) < VIABILITY_GATE:
                return None

            return nurture(
                who=who,
                target=best_tid,
                method_weights=w,
            )
        except Exception as exc:
            logger.warning(f"[CAUSAL_SLICE_AFFECTION] resolve failed: {exc}")
            return None

    @staticmethod
    def to_modifiers(dc: Optional[DesiredChange]) -> Dict[str, float]:
        """CS2: проекция в Modifier Contract. None → {}."""
        if dc is None:
            return {}
        _SCALE = 0.6
        return {k: round(v * _SCALE, 4) for k, v in dc.method_weights.items()}
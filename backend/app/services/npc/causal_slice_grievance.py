# path: /project/backend/app/services/npc/causal_slice_grievance.py
# Назначение: R7 CAUSAL SLICE 3 — продюсер DesiredChange из накопленного
#   вреда (CS14-CS16, ADR-O-396). CS14: обида = проекция осей
#   RelationshipStore A→B (trust-дефицит), НЕ новая сущность; флаги
#   is_angry/planning_revenge/GrievanceStore запрещены. CS15: активен
#   ТОЛЬКО в холодной фазе (threat_gradient < THREAT_GATE 0.35) —
#   горячая угроза принадлежит R5. CS16: подавленная жертва (страх ×
#   бессилие × одиночество) молчит — честный None, наличие вреда ≠
#   наличие пути. Способы — СУЩЕСТВУЮЩИЕ интенты (CS6): intimidate /
#   warn / spread_rumor / call_for_help. Чистая функция; fail-молчание.
# Зависимости: app.domain.desired_change
# Основные сущности: GrievanceDesiredChangeProducer

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.desired_change import DesiredChange, grievance_hold

logger = logging.getLogger(__name__)

# Горячее/холодное разделение (CS15): тот же порог, что THREAT_GATE R5
HOT_THREAT_GATE: float = 0.35
# Глубина вреда: trust ≤ -12 (одна угроза -8 не обида; предательство -20+ — да)
HARM_GATE: float = 0.3          # harm = clamp01((-trust)/40)
VIABILITY_GATE: float = 0.1     # все способы мертвы → жертва молчит (CS16)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class GrievanceDesiredChangeProducer:
    """Собирает существующие машины (CS4): оси SSOT, disposition S211,
    drives L3, союзники. Ничего не мутирует; выбор остаётся DecisionHub."""

    @staticmethod
    def resolve(
        who: str,
        state: Any,
        rel: Dict[str, Dict[str, float]],
        disposition: Dict[str, float],
        allies: int = 0,
    ) -> Optional[DesiredChange]:
        try:
            # CS15: горячая фаза — территория R5, обида молчит
            kernel = getattr(state, "perceptual_kernel", None)
            threat = getattr(kernel, "threat_gradient", 0.0) if kernel else 0.0
            if threat >= HOT_THREAT_GATE:
                return None

            # Атрибуция вредителя: максимальный trust-дефицит A→B
            target_id: Optional[str] = None
            harm = 0.0
            for _tid, _axes in (rel or {}).items():
                _trust = float(_axes.get("trust", 0.0)) if _axes else 0.0
                if _trust < 0:
                    _h = _clamp01((-_trust) / 40.0)
                    if _h > harm:
                        harm, target_id = _h, _tid
            if target_id is None or harm < HARM_GATE:
                return None  # T1: нет вреда — нет обиды (CS14)

            # ── Ограничения агента (CS4: существующие машины) ──
            drives: Dict[str, float] = getattr(state, "drives", {}) or {}
            fear_d = _clamp01(float(drives.get("fear", 0.3)))
            control_d = _clamp01(float(drives.get("control", 0.3)))
            signif_d = _clamp01(float(drives.get("significance", 0.3)))

            hp = 1.0
            try:
                _ehp = getattr(state, "effective_hp", None)
                _max = getattr(state, "effective_max_hp", None)
                if _ehp is not None and _max:
                    hp = max(0.05, min(1.0, float(_ehp) / float(_max)))
            except Exception:
                hp = 1.0

            allies_factor = min(1.0, allies / 2.0)
            _disp_intim = float(disposition.get("intimidate", 0.3))
            _disp_warn = float(disposition.get("warn", 0.3))

            # ── Способы: именованные факторы (контрольный вопрос Тай) ──
            w: Dict[str, float] = {}
            # прямое противостояние: контроль × вред × храбрость × тело
            w["intimidate"] = round(
                control_d * harm * (1.0 - fear_d) * (0.5 + _disp_intim)
                * (0.5 + 0.5 * hp), 4
            )
            # публичное предупреждение: значимость × натура × вред
            w["warn"] = round(signif_d * _disp_warn * harm * 0.5, 4)
            # непрямой путь трусливых — репутационная месть: вред ×
            # бессилие контроля × социальная храбрость (не страх)
            w["spread_rumor"] = round(
                harm * (1.0 - control_d) * (1.0 - fear_d), 4
            )
            # привлечение силы: страх × значимость × союзники × вред
            w["call_for_help"] = round(
                fear_d * signif_d * (0.3 + 0.7 * allies_factor) * harm, 4
            )

            _sum = sum(w.values())
            if _sum > 1.0:
                _f = 1.0 / _sum
                w = {k: round(v * _f, 4) for k, v in w.items()}

            # CS16: все способы подавлены → жертва молчит (честный None)
            if max(w.values(), default=0.0) < VIABILITY_GATE:
                return None

            return grievance_hold(
                who=str(who),
                target=target_id,
                method_weights=w,
            )
        except Exception as exc:
            logger.warning(f"[CAUSAL_SLICE_GRIEVANCE] resolve failed: {exc}")
            return None

    @staticmethod
    def to_modifiers(dc: Optional[DesiredChange]) -> Dict[str, float]:
        """CS2: проекция в Modifier Contract. None → {} (no-op)."""
        if dc is None:
            return {}
        _SCALE = 0.6  # V1: деформирует, не приказывает
        return {k: round(v * _SCALE, 4) for k, v in dc.method_weights.items()}
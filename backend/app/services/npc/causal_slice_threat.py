# path: /project/backend/app/services/npc/causal_slice_threat.py
# Назначение: R5 CAUSAL SLICE 1 — продюсер DesiredChange из угрозы
#   (CS1): threat_gradient + атрибуция (отношения A→B с fear-осью /
#   belief Proposition.ATTACKED) → DesiredChange(stop_hostile) с
#   оценкой способов из СУЩЕСТВУЮЩИХ машин (CS4): disposition
#   (S211), drives (L3), отношения (SSOT), союзники
#   (OpportunityContext-паттерн), тело (body_state). to_modifiers —
#   вход в Modifier Contract (CS2). Чистая функция (A/A, T7);
#   fail-молчание: нет гейтов → None (мир без угроз не меняется).
# Зависимости: app.domain.desired_change
# Основные сущности: ThreatDesiredChangeProducer

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.domain.desired_change import DesiredChange, stop_hostile

logger = logging.getLogger(__name__)

# Порог восприятия угрозы как причины (калибровка; V1 консервативно
# ниже превентивно-агрессивного 0.5, чтобы слой возникал РАНЬше
# физической эскалации и мог её деформировать).
THREAT_GATE: float = 0.35

# Порог fear-оси отношения для атрибуции (шкала SSOT 0-100).
FEAR_ATTRIBUTION_THRESHOLD: float = 40.0


class ThreatDesiredChangeProducer:
    """Собирает СУЩЕСТВУЮЩИЕ вычислители в причинный контур (CS4).

    Ничего не мутирует; не создаёт интентов; вердикт способа не
    выносит — готовит веса, выбор остаётся DecisionHub (CS2).
    """

    @staticmethod
    def resolve(
        state: Any,
        rel: Dict[str, Dict[str, float]],
        disposition: Dict[str, float],
        allies: int = 0,
        belief_source: Any = None,
    ) -> Optional[DesiredChange]:
        """rel: {target_id: {trust, fear}} — существующий SSOT-вид
        (V2 get / _get_rel_value). disposition: веса архетипа (S211).
        belief_source: Proposition-подобный объект (predicate.value
        в {ATTACKED, ...}, subject_id = источник угрозы)."""
        try:
            kernel = getattr(state, "perceptual_kernel", None)
            threat = getattr(kernel, "threat_gradient", 0.0) if kernel else 0.0
            if threat < THREAT_GATE:
                return None  # T1: без причины нет цели (CS1)

            # ── Атрибуция: КТО угрожает (два живых источника, CS4) ──
            target_id: Optional[str] = None
            # Источник 1: отношения — fear A→B, накопленный
            # npc_threatens-дельтами (SocialDeltaEngine, -8/+5..)
            if rel:
                _best_fear, _best_tgt = 0.0, None
                for _tid, _axes in rel.items():
                    _fear = float(_axes.get("fear", 0.0)) if _axes else 0.0
                    if _fear > _best_fear:
                        _best_fear, _best_tgt = _fear, _tid
                if _best_tgt is not None and _best_fear >= FEAR_ATTRIBUTION_THRESHOLD:
                    target_id = _best_tgt
            # Источник 2: belief (Proposition ATTACKED — subject_id)
            if target_id is None and belief_source is not None:
                _pred = getattr(belief_source.predicate, "value",
                                str(belief_source.predicate))
                if str(_pred).upper() in ("ATTACKED", "OPPOSES"):
                    target_id = getattr(belief_source, "subject_id", None)

            if not target_id:
                return None  # T2: причина без «кого менять» не цель

            # ── Оценка способов из существующих машин (CS4) ──
            drives: Dict[str, float] = getattr(state, "drives", {}) or {}
            fear_d = float(drives.get("fear", 0.25))
            control_d = float(drives.get("control", 0.25))
            signif_d = float(drives.get("significance", 0.25))

            hp = 1.0
            try:
                _ehp = getattr(state, "effective_hp", None)
                _max = getattr(state, "effective_max_hp", None)
                if _ehp is not None and _max:
                    hp = max(0.05, min(1.0, float(_ehp) / float(_max)))
            except Exception:
                hp = 1.0
            body_factor = hp  # сила тела = доля здоровья
            allies_factor = min(1.0, allies / 2.0)  # OpportunityContext-паттерн

            _disp_intim = float(disposition.get("intimidate", 0.3))
            _disp_warn = float(disposition.get("warn", 0.3))

            w: Dict[str, float] = {}
            # Конфронтационное давление: контроль × легитимность натуры × тело
            w["intimidate"] = round(
                control_d * (0.5 + _disp_intim) * (0.5 + 0.5 * body_factor), 4
            )
            # Привлечение силы: значимость × союзники × (слабость тела)
            w["call_for_help"] = round(
                signif_d * (0.3 + 0.7 * allies_factor) * (1.0 - 0.5 * body_factor), 4
            )
            # Физическое преграждение: контроль × тело (без союзников)
            w["block_path"] = round(control_d * body_factor * 0.6, 4)
            # Прямая конфронтация: сосуществует с превентивно-агрессивной
            # деформацией :1564-1567 — НЕ конкурирует, усиливает при силе
            w["attack"] = round(control_d * body_factor * 0.8, 4)
            # Информационное предупреждение (для свидетелей/окружения)
            w["warn"] = round(signif_d * _disp_warn * 0.5, 4)
            # Цель-невыход (R4-4: self-change): изменение недостижимо/
            # дорого → изменить себя (дистанцию). Страх × слабость ×
            # одиночество; ОТРИЦАТЕЛЬНЫЙ вклад в конфликтные способы
            # формулируется как доминирующий flee-вес.
            w["flee"] = round(
                fear_d * (1.0 - 0.6 * body_factor) * (1.0 - 0.7 * allies_factor), 4
            )

            return stop_hostile(who=getattr(state, "npc_id", ""), target=target_id,
                                method_weights=w)
        except Exception as _e:
            logger.warning(f"[CAUSAL_SLICE_THREAT] resolve failed: {_e}")
            return None

    @staticmethod
    def to_modifiers(dc: Optional[DesiredChange]) -> Dict[str, float]:
        """CS2: проекция DesiredChange в числовые модификаторы
        существующих интентов (Modifier Contract, ADR-O-355).
        None → {} (no-op). Веса намеренно консервативны (V1: сдвигают,
        не переворачивают скоринг — срез аддитивен к живому балансу)."""
        if dc is None:
            return {}
        _SCALE = 0.6  # V1-калибровка: максимум сдвига < единичного шага
        return {k: round(v * _SCALE, 4) for k, v in dc.method_weights.items()}
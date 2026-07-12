from __future__ import annotations

# backend/app/services/npc/decision/social_deltas.py
"""
R2-P1: Социальные дельты — как события меняют отношения между агентами.

Архитектурный инвариант:
  DecisionHub НЕ определяет "что значит событие".
  Этот модуль определяет "как событие меняет связь" — модулированное личностью.

Формула:
  effective_delta = base_delta × event.intensity × profile_multiplier

При нейтральных drives (все 0.25): profile_multiplier = 1.0 → обратная совместимость.

Исправлен баг: player_threatens объединил два перезаписанных блока
(оригинал: первый блок (-5 trust, +4 fear) терялся, второй перезаписывал).
"""


from typing import Any, Dict, List, Optional, Tuple

from app.models.npc_state import NPCState
from app.models.state_delta import DeltaDomain, SocialPayload, StateDeltas
from app.services.npc.decision.relationship_profile import RelationshipResponseProfile
from app.services.npc.math_utils import apply_saturation

# ── Базовые дельты: объективная сила события (ДО модуляции личностью) ──
# Формат: (trust_base, fear_base, fear_category)
# fear_category: "aggression" | "threat" | "relief"
#   — определяет, какой множитель из RelationshipResponseProfile применять к страху
#
# Эти значения — "насколько сильно событие в вакууме",
# "насколько NPC это чувствует" — определяет профиль личности.

_BASE_DELTAS: Dict[str, Tuple[float, float, str]] = {
    # Оскорбление: доверие падает, страх снижается (просто разговор, не атака)
    "player_insults": (-8.0, -5.0, "relief"),
    # Угроза: объединены два перезаписанных блока (было -5/+4 + -6/+2.5 = -11/+6.5)
    "player_threatens": (-11.0, +6.5, "threat"),
    # Физическое насилие: сильнейший удар по доверию и страху
    "player_attacks": (-10.0, +8.0, "aggression"),
    # Бой/насилие в мире: то же что атака, но от третьих лиц
    "combat": (-10.0, +8.0, "aggression"),
    # Запугивание: ближе к угрозе, чем к насилию
    "intimidation": (-10.0, +8.0, "threat"),
    # Помощь: доверие растёт, страх снижается
    "help": (+12.0, -5.0, "relief"),
}


def _get_rel_value(state: Any, target_id: str, attr: str) -> Optional[float]:
    """Precedence Contract: Graph (SSOT) > Scalar (Legacy) > Vacuum (None).
    Standalone-копия DecisionHub._get_rel_value — устраняет circular dependency.
    """
    _graph_val = state.relationship_cache.get(target_id, {}).get(attr)
    if _graph_val is not None:
        return float(_graph_val)
    _scalar_val = state.relationship_cache.get(attr)
    if _scalar_val is not None:
        return float(_scalar_val)
    return None


def _modulate_trust(base_trust: float, profile: RelationshipResponseProfile) -> float:
    """Модулирует дельту доверия через профиль личности.
    trust < 0 (потеря) → × trust_from_betrayal (значимость усиливает боль предательства)
    trust > 0 (рост)   → × trust_from_help (желание+значимость усиливают благодарность)
    """
    if base_trust < 0:
        return base_trust * profile.trust_from_betrayal
    elif base_trust > 0:
        return base_trust * profile.trust_from_help
    return 0.0


def _modulate_fear(
    base_fear: float, fear_category: str, profile: RelationshipResponseProfile
) -> float:
    """Модулирует дельту страха через профиль личности.
    fear > 0 + "aggression" → × fear_from_aggression (трусы пугаются сильнее)
    fear > 0 + "threat"     → × fear_from_threat (угрозы страшнее для параноиков)
    fear < 0 + "relief"     → × fear_relief_from_help (трусы чувствуют больше облегчения)
    """
    if base_fear > 0:
        if fear_category == "aggression":
            return base_fear * profile.fear_from_aggression
        elif fear_category == "threat":
            return base_fear * profile.fear_from_threat
        return base_fear  # неизвестная категория — без модуляции
    elif base_fear < 0:
        return base_fear * profile.fear_relief_from_help
    return 0.0


class SocialDeltaEngine:
    """Вычисляет социальные дельты, модулированные личностью NPC.

    Чистая функция: не мутирует state. Возвращает List[StateDeltas].
    DecisionHub делегирует сюда вместо инлайн-кода в _compute_deltas.

    Примеры (player_attacks, intensity=1.0):
      Нейтральный NPC (fear=0.25, significance=0.25):
        trust=-10.0, fear=+8.0   (как было до P1)
      Трус (fear=0.6, significance=0.2):
        trust=-8.0,  fear=+17.0  (страх усилен ×2.12, предательство приглушено ×0.8)
      Фанатик (fear=0.05, significance=0.6):
        trust=-21.2, fear=+2.9   (предательство усилено ×2.12, страх приглушён ×0.36)
    """

    def process(
        self,
        state: NPCState,
        personality: Any,
        event: Any,
        intent: str,
    ) -> List[StateDeltas]:
        """Главная точка входа. Заменяет DecisionHub._compute_deltas."""
        # 1. Определить тип события
        _et = event.event_type
        _et_val = _et.value if hasattr(_et, "value") else str(_et)

        # 2. Найти базовые дельты
        base = _BASE_DELTAS.get(_et_val)
        if base is None:
            return []  # Неизвестный тип события — нет социальных дельт

        base_trust, base_fear, fear_category = base

        # 3. Построить профиль личности из drives_base
        drives = personality.drives_base if hasattr(personality, "drives_base") else {}
        profile = RelationshipResponseProfile.from_drives(drives)

        # 4. Модулировать дельты через профиль
        personalized_trust = _modulate_trust(base_trust, profile)
        personalized_fear = _modulate_fear(base_fear, fear_category, profile)

        # 5. Применить интенсивность события
        intensity = getattr(event, "intensity", 1.0)
        _trust_raw = personalized_trust * intensity
        _fear_raw = personalized_fear * intensity

        # 6. Применить saturation (эффект слабеет у границ шкалы 0-100)
        s_trust = 0.0
        s_fear = 0.0

        if _trust_raw != 0.0:
            _, s_trust = apply_saturation(
                current=_get_rel_value(state, "player", "trust") or 0.0,
                delta=_trust_raw,
                min_val=-100.0,
                max_val=100.0,
            )

        if _fear_raw != 0.0:
            _, s_fear = apply_saturation(
                current=_get_rel_value(state, "player", "fear") or 0.0,
                delta=_fear_raw,
                min_val=-100.0,
                max_val=100.0,
            )

        # 7. Собрать результат (одна дельта = один домен — ADR-013)
        result_deltas = []
        if s_trust != 0.0 or s_fear != 0.0:
            result_deltas.append(
                StateDeltas(
                    npc_id=state.npc_id,
                    domain=DeltaDomain.SOCIAL,
                    target="player",
                    payload=SocialPayload(
                        trust_delta=s_trust,
                        fear_delta=s_fear,
                    ),
                    source=event.event_type,
                )
            )

        return result_deltas

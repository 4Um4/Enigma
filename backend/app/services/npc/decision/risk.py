# backend/app/services/npc/decision/risk.py
"""
R2-P2: Объективный риск + субъективное восприятие.

Двухфазная модель:
  Phase 1: compute_objective_risk() — опасность из контекста (свидетели, оружие, дистанция)
  Phase 2: RiskPerceptionProfile.perceive() — модуляция личностью

Архитектурный инвариант:
  Объективный риск НЕ знает про личность.
  Личность НЕ знает про свидетелей и оружие.
  Они встречаются только в perceive_risk().
"""

from typing import List, Any, Dict

from app.models.npc_state import NPCState
from app.services.npc.decision.risk_profile import RiskPerceptionProfile


# ── Видимая сила актора: броня, оружие, габариты ──
_THREAT_MARKER_VALUES: Dict[str, float] = {
    "heavy_armor": 0.20,
    "medium_armor": 0.10,
    "weapon_melee": 0.15,
    "weapon_ranged": 0.18,
    "weapon_magic": 0.25,
    "large_build": 0.08,
    "battle_wounds": 0.05,
}


def compute_objective_risk(event: Any, state: NPCState) -> float:
    """Объективная опасность события. Чистая функция, НЕ зависит от личности.

    Учитывает:
      - тип события (социальное vs агрессивное)
      - свидетелей и дистанцию
      - видимую силу актора (броня, оружие)
      - сцену (активный бой)
      - память о прошлом насилии
      - недавнее давление

    НЕ учитывает:
      - fear_drive, control_drive, desire (это профиль восприятия)
    """
    _et = event.event_type
    _et_val = _et.value if hasattr(_et, "value") else str(_et)

    _social_events = {
        "player_interacts",
        "player_spoke",
        "npc_spoke",
        "help",
        "move",
        "player_moved",
    }
    base_risk = 0.1 if _et_val in _social_events else 0.3

    # Свидетели и дистанция — только для агрессивных событий
    if _et_val not in _social_events:
        base_risk += min(event.witness_count * 0.08, 0.4)
        if event.distance <= 2.0:
            base_risk += 0.2

    if not event.success:
        base_risk *= 0.5

    # Видимая сила — NPC реагирует на броню и оружие, не на скрытые stats
    power_risk = sum(
        _THREAT_MARKER_VALUES.get(m, 0.0) for m in event.visible_threat_markers
    )
    base_risk += min(power_risk, 0.5)

    # Сцена: активный бой повышает объективную угрозу
    _scene_flags = event.scene_flags if hasattr(event, "scene_flags") else set()
    if "combat_started" in _scene_flags:
        base_risk += 0.25

    # Память и давление — только для агрессивных событий
    if _et_val not in _social_events:
        _pressure = state.relationship_cache.get("recent_pressure", 0.0)
        if _pressure > 0.01:
            base_risk += min(_pressure * 0.5, 0.3)

        _memory_penalty = 0.0
        for _m in state.narrative_cache:
            if not hasattr(_m, "importance") or _m.importance < 0.1:
                continue
            _type = getattr(_m, "event_type", "")
            _weight = (
                0.15
                if _type in ("player_attacks", "combat", "intimidation", "theft")
                else 0.05
            )
            _memory_penalty += _m.importance * _weight
        if _memory_penalty > 0.01:
            base_risk += min(_memory_penalty, 0.3)

    return min(base_risk, 1.0)


def perceive_risk(event: Any, state: NPCState, drives_base: Dict[str, float]) -> float:
    """Объективный риск, модулированный личностью NPC.

    Двухфазная модель:
      1. compute_objective_risk() — "насколько опасно?"
      2. RiskPerceptionProfile.perceive() — "насколько ЭТОТ NPC это чувствует?"

    При нейтральных drives (0.25): результат = объективный риск (обратная совместимость).
    """
    objective = compute_objective_risk(event, state)
    profile = RiskPerceptionProfile.from_drives(drives_base)
    return profile.perceive(objective)

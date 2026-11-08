"""
path: /project/backend/app/services/npc/desire_generator.py
Назначение: Living Activity (шаг 2) — продюсер DesireSet в Фазе 0.
    Пишет персистентные желания в npc["desires"] (L2.8-класс: история,
    decay, обучение — НЕ L3-эфемерные драйвы). Guarded: DESIRES_ENABLED
    (default OFF) = no-op, байт-идентично легаси; отказ продюсера =
    деградация канала, не тика (G2-паттерн ADR-O-378, D5).
    Заменяет прокси _NEED_TO_ACTIVITY — код сам просил замену («позже
    можно заменить на интеграцию с NeedEngine через DTO»).
Зависимости: app.domain.desire
Основные сущности: update_all, update_npc_desires
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from app.domain.desire import Desire, DesireSource

logger = logging.getLogger(__name__)

# Флаг канала (G2-паттерн): default OFF = no-op; включение — dev-профиль среза EAT
_DESIRES_ENABLED_ENV = "DESIRES_ENABLED"

# v1-таблица needs → (subject_class, target_class). Генератор общий на все
# четыре needs-источника (онтология рождается полной — L-M1); каталог
# деятельностей v1 имеет только EAT — желания без исполнителя ждут своих
# срезов (давление без деятельности, не мёртвый код).
_NEED_TO_DESIRE: Dict[str, tuple] = {
    "hunger": ("food", "food_portion"),
    # ADR-O-391 (WORK): жажда → желание эля; цель — человек-продавец.
    # "ale" в каталоге деятельностей нет → легаси-движение не подавляется
    # (legacy_need_suppressed: субъект вне каталога → False).
    "thirst": ("ale", "person"),
    "shelter_urge": ("shelter", "bed"),
    "social_urge": ("social", "person"),
    "fatigue": ("rest", "bed"),
}


def _desires_enabled() -> bool:
    return os.environ.get(_DESIRES_ENABLED_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _clamp01(value: Any) -> float:
    return max(0.0, min(1.0, float(value)))


def update_npc_desires(npc: Dict[str, Any], tick: int) -> None:
    """Идемпотентный upsert желаний одного NPC из его needs.

    Мутация npc-словаря на уровне Фазы 0 — тот же слой и путь записи, что
    _tick_needs у LifeEngine (прецедент легальности). Детерминизм: без RNG;
    urgencies округляются (round 4) — стабильный JSON-репр.
    """
    needs = npc.get("needs")
    if not isinstance(needs, dict) or not needs:
        return

    desires_list = npc.get("desires")
    if not isinstance(desires_list, list):
        desires_list = []
        npc["desires"] = desires_list

    index = {d.get("desire_id"): i for i, d in enumerate(desires_list)}

    for need_name, (subject, target_class) in _NEED_TO_DESIRE.items():
        raw_value = needs.get(need_name)
        if raw_value is None:
            continue
        urgency = round(_clamp01(raw_value), 4)
        desire_id = Desire.stable_id(subject)

        if desire_id in index:
            # upsert: свежие — только urgency и target_class;
            # born_tick / last_fulfilled / weight / provenance — история
            # (L-M1: born-структура причинности не перезаписывается)
            existing = desires_list[index[desire_id]]
            existing["urgency"] = urgency
            existing["target_class"] = target_class
            continue

        desires_list.append(
            {
                "desire_id": desire_id,
                "subject_class": subject,
                "urgency": urgency,
                "target_class": target_class,
                "provenance": [
                    {
                        "source": DesireSource.NEED.value,
                        "weight": 1.0,
                        "origin_ref": need_name,
                    }
                ],
                "born_tick": int(tick),
                "last_fulfilled_tick": -1,
                "weight": 1.0,
                "learned_from": [],
            }
        )


# S2B.10: body_state.nutrition = STOCK (0-100, full→empty), НЕ hunger.
# Avatar (npc_id="player") не проходит through LifeEngine._tick_needs
# (ROUTINE gate для player-entries не активен). Этот adapter — мост
# между persisted физиологией Avatar и существующим needs-словарём:
# body_state → needs dict → update_npc_desires → Desire.
#
# Mapping направлений (важно: шкалы body_state неоднородны):
#   nutrition/hydration: 100=full (no need), 0=empty (max need) → INVERT
#   fatigue:             0=rested (no need), 100=tired (max need) → NO INVERT
#   sleep_pressure:      0.0-1.0, 1.0=max need → NO INVERT (already 0-1)
_AVATAR_BODY_TO_NEEDS = {
    "nutrition": "hunger",            # S2B.4: stock; S2B.10: derived hunger
    "hydration": "thirst",             # S2B.3: 0-100
    "fatigue": "fatigue",              # S2B.5: 0-100 (0=rested, 100=tired)
    "sleep_pressure": "shelter_urge",  # ADR-O-375: 0.0-1.0
}

# Поля, где шкала инвертируется (100 = no need, 0 = max need)
_AVATAR_INVERTED_FIELDS = frozenset({"nutrition", "hydration"})


def _ensure_avatar_needs(npc: Dict[str, Any]) -> None:
    """Создаёт/обновляет needs dict для Avatar из его body_state.

    Avatar не проходит через LifeEngine._tick_needs (ROUTINE gate
    для player-entries не активен — нет schedule/routine). Поэтому
    needs dict не создаётся, и update_npc_desires выходит на line 63
    (if not needs: return). Этот adapter — недостающая связь между
    persisted физиологией Avatar и существующим desire-generator.

    Не дублирует Desire (использует существующий _NEED_TO_DESIRE mapping).
    Не создаёт новую систему потребностей (использует те же 5 needs).
    Источник: body_state Avatar (loaded from player_avatar.json).

    Не маппит social_urge — нет источника в body_state. Честное
    отсутствие (§ENIGMA-003: UNKNOWN ≠ NEUTRAL), не выдумываем.

    Направления шкалы (см. _AVATAR_INVERTED_FIELDS):
      - nutrition/hydration: 100=full → INVERT → need = (100 - val) / 100
      - fatigue: 100=tired → NO INVERT → need = val / 100
      - sleep_pressure: 0.0-1.0 → need = val (no scaling)
    """
    body_state = npc.get("body_state")
    if not isinstance(body_state, dict):
        return

    needs = npc.get("needs")
    if not isinstance(needs, dict):
        needs = {}
        npc["needs"] = needs

    for body_field, need_name in _AVATAR_BODY_TO_NEEDS.items():
        raw = body_state.get(body_field)
        if raw is None:
            continue
        if body_field in _AVATAR_INVERTED_FIELDS:
            # 100=full (no need) → 0.0; 0=empty (max need) → 1.0
            need_val = round(_clamp01((100.0 - float(raw)) / 100.0), 4)
        elif body_field == "sleep_pressure":
            # 0.0-1.0, already normalized
            need_val = round(_clamp01(float(raw)), 4)
        else:
            # fatigue: 0=rested (no need) → 0.0; 100=tired (max need) → 1.0
            need_val = round(_clamp01(float(raw) / 100.0), 4)
        needs[need_name] = need_val


def update_all(all_npcs: Optional[List[Any]], tick: int) -> None:
    """Guarded-продюсер Фазы 0 (G2-паттерн ADR-O-378, вердикт D5).

    OFF (default) = no-op без итераций. Отказ = деградация канала
    (громкий лог + тик живёт), не краш симуляции: желание — давление,
    не жизненный орган тика.
    """
    if not _desires_enabled() or not all_npcs:
        return
    try:
        _born = 0
        for npc in all_npcs:
            if not isinstance(npc, dict):
                continue
            # Avatar: bridge body_state → needs (Avatar не проходит
            # LifeEngine._tick_needs). Не дублирует Desire — использует
            # существующий _NEED_TO_DESIRE mapping через update_npc_desires.
            if npc.get("npc_id") == "player" or npc.get("id") == "player":
                _ensure_avatar_needs(npc)
            _before = len(npc.get("desires") or [])
            update_npc_desires(npc, tick)
            _after = len(npc.get("desires") or [])
            _born += _after - _before
        if _born:
            logger.info(f"[DESIRES] tick={tick}: born {_born} desires")
    except Exception as exc:
        # Деградация канала, не тика (G2 D5); L4: отказ логируется громко
        logger.warning(f"[DESIRES] producer fault (degraded, tick continues): {exc}")

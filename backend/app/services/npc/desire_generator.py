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
            _before = len(npc.get("desires") or [])
            update_npc_desires(npc, tick)
            _after = len(npc.get("desires") or [])
            _born += _after - _before
        if _born:
            logger.info(f"[DESIRES] tick={tick}: born {_born} desires")
    except Exception as exc:
        # Деградация канала, не тика (G2 D5); L4: отказ логируется громко
        logger.warning(f"[DESIRES] producer fault (degraded, tick continues): {exc}")
# -*- coding: utf-8 -*-
"""
path: backend/app/domain/attention_dispositions.py
Назначение: P3d — интерпретация направленного приближения из ХАРАКТЕРА
    наблюдателя: трёхмерной пирамиды драйвов (fear/desire/control, L3
    EffectiveDrives, sum==1.0, ADR-O-207). НЕ из профессии: таблиц
    архетипов нет — чистая формула, масштабируемая на 1000+ NPC без
    добавления строк (табу npc_id/архетип-хардкодов, S211-канон).
    Семантика осей (§ENIGMA-S72.7 — характер = направление разрядки):
      fear    → настороженность: замечает раньше/дольше смотрит,
                сближение подавлено (страх гасит общительность);
      desire  → интерес: наблюдение с любопытством, сам идёт навстречу;
      control → поглощённость делом: не бросает работу (сценарий В),
                ожидание для него наименее доступно.
    Ключи возврата — СУЩЕСТВУЮЩИЕ Intent-имена (lowercase); веса ∈ [0,1]
    по построению → при base ≤ 0.5 санкционная граница ±0.5 недостижима
    (инвариант покрывается grid-тестом).
Зависимости: typing (домен чист, §1.2).
Основные сущности: get_attention_disposition.
"""
from typing import Dict, Mapping, Optional

# Дефолт недоступных драйвов — нейтральная середина пирамиды (не 0: ноль
# означал бы вырожденный характер, §ENIGMA-003 по духу).
_NEUTRAL: float = 1.0 / 3.0


def _c01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def get_attention_disposition(
    drives: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """Веса внимания из характера. drives — значения L3 (fear/desire/
    control); None/неполные → нейтральные недостающие оси. Чистая
    функция: одинаковый характер → одинаковая интерпретация (детерминизм)."""
    _d = drives or {}
    fear = _c01(float(_d.get("fear", _NEUTRAL)))
    desire = _c01(float(_d.get("desire", _NEUTRAL)))
    control = _c01(float(_d.get("control", _NEUTRAL)))

    # Настороженность: страх обостряет внимание, любопытство добавляет.
    observe = _c01(0.25 + 0.65 * fear + 0.15 * desire)
    # Общительность: желание тянет навстречу, страх гасит.
    approach = _c01(max(0.0, 0.9 * desire - 0.5 * fear))
    # Готовность прервать дело ради ожидания: контроль удерживает за работой.
    idle = _c01(max(0.0, 0.5 - 0.8 * control))

    return {
        "observe": round(observe, 4),
        "approach": round(approach, 4),
        "idle": round(idle, 4),
    }
# path: /project/backend/app/domain/desired_change.py
# Назначение: R5 CAUSAL SLICE 1 (мини-АДР CS1-CS6) — доменное
#   представление причинно определённого изменения, которого агент
#   хочет добиться, ДО выбора способа действия. Форма R4:
#   who/reason/state_type/target_of_change/addressee + оценка
#   способов. ЧИСТЫЕ ДАННЫЕ: не знает сервисов, не мутирует мир,
#   LLM-независимо (CS5). target_of_change ≠ addressee — контрактное
#   различение R4-5·2 (у stop-hostile совпадают; у STEAL-класса нет).
# Зависимости: dataclasses, typing
# Основные сущности: DesiredChange, stop_hostile

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

# Типы желаемых изменений (R4-5·1: типизация — не расширение, а
# конкретизация; все 17 проверенных случаев ложатся на этот набор).
STATE_TYPE_BEHAVIOR = "behavior"
STATE_TYPE_POSITION = "position"
STATE_TYPE_BELIEF = "belief"
STATE_TYPE_EMOTION = "emotion"
STATE_TYPE_RELATION = "relation"
STATE_TYPE_RESOURCE = "resource"
STATE_TYPE_SELF = "self"
STATE_TYPE_SHARED = "shared_state"

# Причины (R4-5·3: reason допускает неутилитарные источники).
REASON_THREAT = "threat"
REASON_NEED = "need"
REASON_BELIEF = "belief"
REASON_AFFECTION = "affection"
REASON_EXPRESSION = "expression"


@dataclass(frozen=True)
class DesiredChange:
    """Причинно определённое изменение, которого who хочет добиться.

    Рождается из состояния/правил ENIGMA (CS1), существует ДО и
    НЕЗАВИСИМО от победы какого-либо интента в скоринге. Способы —
    взвешенное множество СУЩЕСТВУЮЩИХ интентов (CS6): выбор остаётся
    за DecisionHub через Modifier Contract (CS2).
    """

    who: str                          # агент-инициатор
    reason: str                       # REASON_* — почему возникло
    state_type: str                   # STATE_TYPE_* — тип изменения
    target_of_change: str             # чьё состояние должно измениться
    addressee: Optional[str]          # на кого оказывается воздействие
    method_weights: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.who:
            raise ValueError("DesiredChange.who не может быть пустым")
        if not self.target_of_change:
            raise ValueError("DesiredChange.target_of_change не может быть пустым")


def stop_hostile(
    who: str,
    target: str,
    method_weights: Dict[str, float],
) -> DesiredChange:
    """Фабрика среза 1: «target должен прекратить враждебное
    поведение». target_of_change == addressee (частный случай);
    контракт различения сохранён полями, а не слиянием (CS3)."""
    return DesiredChange(
        who=who,
        reason=REASON_THREAT,
        state_type=STATE_TYPE_BEHAVIOR,
        target_of_change=target,
        addressee=target,
        method_weights=dict(method_weights),
    )
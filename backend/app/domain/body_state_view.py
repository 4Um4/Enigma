"""
path: backend/app/domain/body_state_view.py
Назначение: W2 (ADR-O-372) — frozen read-model телесного состояния:
    тонкая проекция body_state (dict, SSOT — NPCState.body_state) на
    типизированный вход предикатов AffordanceResolver. Оси ADR-123
    (жизнь/сознание/дееспособность) вычисляются ДЕЛЕГАЦИЕЙ доменному
    vital_state — ноль дублирования логики. npc_id — носитель
    идентичности для HOLDER_IS/OCCUPANT_IS (вердикт В2).
    Энергия/гидратация/питание (S2B) сознательно НЕ входят: ни один
    предикат v1 их не потребляет; расширение — W4 (CapabilityEvaluator).
    DISABLED-sentinel (NPIC) даёт все оси False через сами функции —
    спецобработка не нужна.
Зависимости: dataclasses, typing, app.domain.vital_state
Основные сущности: BodyStateView, build_body_state_view
"""
from dataclasses import dataclass
from typing import Any, Dict

from app.domain.vital_state import (
    LifeStatus,
    evaluate_vital_state,
    is_capable,
    is_conscious,
)


@dataclass(frozen=True)
class BodyStateView:
    """Типизированный вход предикатов W2. Frozen, самодостаточен.

    Ось — снапшот на момент построения (вычислена доменными функциями
    ADR-123); view эфемерен и не кэшируется между тиками (прецедент
    L3-P1: производная не хранится).
    """

    npc_id: str
    is_alive: bool
    is_conscious: bool
    is_capable: bool


def build_body_state_view(body_state: Dict[str, Any], npc_id: str) -> BodyStateView:
    """Единственная фабрика view (§13.4: фабрика вместо конструктора).

    falsy body_state → ValueError (громкий): L2.2 гарантирует body_state
    каждому NPC, DISABLED-sentinel инжектируется на NPIC-границе — falsy
    здесь = разрыв инварианта upstream (§ENIGMA-003: отсутствие данных
    ≠ нейтральное состояние; L4 Silent Failure).
    """
    if not body_state:
        raise ValueError(
            f"body_state отсутствует (npc_id={npc_id!r}): нарушение L2.2 "
            "(ADR-O-201) — NPC рождается с body_state; absence ≠ neutral "
            "(§ENIGMA-003)"
        )
    return BodyStateView(
        npc_id=npc_id,
        is_alive=evaluate_vital_state(body_state) == LifeStatus.ALIVE,
        is_conscious=is_conscious(body_state),
        is_capable=is_capable(body_state),
    )

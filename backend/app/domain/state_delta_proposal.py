"""
Назначение: E2.0 — сырьё интерпретации (LLM или механики), НЕ команда; валидируется DeltaGate; rationale для аудита, не для игры
Зависимости: dataclasses
Основные сущности: StateDeltaProposal
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateDeltaProposal:
    """E2.0: предложение дельты состояния — сырьё, не команда.

    Источник (сейчас — механика: semantic_action='THREATEN'; позже —
    LLM-интерпретатор по ADR-O-373) НЕ имеет права писать в психику.
    Proposal проходит DeltaGate (whitelist/клампы/идемпотентность) —
    и только тогда становится дельтой.

    INV-LLM-NOT-SSOT: между Interpretation и State нет прямого пути.
    """

    trace_id: str          # content_reference:owner:source (E1.0)
    field: str             # ключ DeltaGate.WHITELIST
    value: float           # предложенная дельта (клампится гейтом)
    rationale: str = ""    # объяснение — лог/аудит, не для игры
    source: str = "mechanical"  # mechanical | llm
    # E2.0-b AG1-п.13: каузальный родитель — event.id источника.
    # Связывает belief, возникший на тиковой ветке позже, с тем же
    # событием: один event.id → один trace (AG1-INV-TRACE-ONCE).
    causal_parent: str = ""
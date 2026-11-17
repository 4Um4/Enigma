from __future__ import annotations

# backend/app/models/world/plan.py
"""
Назначение: План NPC — последовательность шагов в графе состояний мира
            (ТЗ Отчёт №6 §3/§6, ADR-O-445). Plan короткоживущий: НЕ кэшируется
            дольше ревизии мира, пересчитывается каждые N тиков или при значимом
            изменении мира (§3.1). Снапшот — иммутабельное отображение
            (domain, attribute) -> значение; ключ снапшота для BFS считает
            WorldGraph (Спринт 2), не PlanStep.
Зависимости: stdlib only (dataclasses, typing); app.models.world.process (Process, ProcessSource).
Основные сущности: PlanStep, Plan, WorldSnapshotData
"""

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from app.models.world.process import Process, ProcessSource

WorldSnapshotData = Mapping[Tuple[str, str], Any]


@dataclass(frozen=True)
class PlanStep:
    """Один шаг плана: запуск Process через ProcessSource, результат — снапшот."""

    process: Process
    source: ProcessSource
    snapshot: WorldSnapshotData


@dataclass(frozen=True)
class Plan:
    """Путь от текущего снапшота мира к состоянию, удовлетворяющему цели."""

    steps: Tuple[PlanStep, ...] = ()

    @property
    def duration_ticks(self) -> int:
        return sum(step.process.duration_ticks for step in self.steps)

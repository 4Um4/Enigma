"""
DEGOD ITER5: внутренний результат пайплайна (перенос из game_loop/__init__.py).
Назначение: внутренний результат пайплайна (_PipelineState) + сборка traces. DEGOD ITER5: перенос из game_loop/init.py (:86–101, :2751–2762).
Зависимости: dataclasses, time, typing, app.models.pipeline_context, app.models.schemas
Основные сущности: _PipelineState, build_traces
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.pipeline_context import PipelineContext
from app.models.schemas import AgentTrace


@dataclass
class _PipelineState:
    """Всё что нужно знать агентам после Python-этапа."""

    shared_context: PipelineContext
    classification_results: List[Dict[str, Any]]
    world_tick_meta: Dict[str, Any]
    rules_result: Dict[str, Any] = field(default_factory=dict)
    npc_result: Dict[str, Any] = field(default_factory=dict)
    python_engines_result: Dict[str, Any] = field(default_factory=dict)
    # N-02 FIX: Используем time.monotonic() для измерения реального времени (latency, TPS).
    # time.time() подменяется time_freezer во время replay, что ломает метрики.
    start_ms: float = field(default_factory=lambda: time.monotonic() * 1000)
    # Sprint P9: Факты, донесённые до игрока (для UI и DM)
    observed_facts: list = field(default_factory=list)
    world_snapshot: Optional[Any] = None  # BUG-FB-031 FIX: Проброс WorldSnapshotDTO из ядра


def build_traces(state: _PipelineState, dm_result: dict, elapsed_ms: int) -> list:
    """DEGOD ITER5: перенос _build_traces из GameLoop (pure-сборка AgentTrace)."""
    return [
        AgentTrace(agent="performance", output={"turn_elapsed_ms": elapsed_ms}),
        AgentTrace(agent="world_scheduler", output=state.world_tick_meta),
        AgentTrace(agent="rules", output=state.rules_result),
        AgentTrace(agent="npc", output=state.npc_result),
        AgentTrace(agent="dm", output=dm_result),
        AgentTrace(agent="python_engines", output=state.python_engines_result),
        AgentTrace(agent="game_loop", output={"pipeline_duration_ms": elapsed_ms}),
    ]

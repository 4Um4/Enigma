# backend/app/services/probes/probe_registry.py
"""
Контракт Probe и ProbeContext.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Protocol, runtime_checkable

@dataclass(frozen=True)
class ProbeContext:
    """Immutable snapshot пост-tick состояния для проб."""
    tick_id: int
    game_time_seconds: float
    scene_state: dict
    all_npcs_raw: List[dict]

@dataclass
class ProbeResult:
    name: str
    severity: str  # "INFO" | "WARN" | "ERROR"
    passed: bool
    details: str = ""

@runtime_checkable
class Probe(Protocol):
    name: str
    severity: str
    def check(self, ctx: ProbeContext) -> ProbeResult: ...
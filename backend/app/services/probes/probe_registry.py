# backend/app/services/probes/probe_registry.py
"""
Контракт Probe и ProbeContext.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Protocol, runtime_checkable, Optional

@dataclass(frozen=True)
class ProbeContext:
    """Immutable snapshot пост-tick состояния для проб."""
    tick_id: int
    game_time_seconds: float
    scene_state: dict
    all_npcs_raw: List[dict]
    mvp_controller: Any = None  # ENIGMA SELF-HEALING (Level 1)
    tick_mutation: Any = None   # Подсистема 3: Инвариант I (Causal Provenance)
    tick_state_hash_before: Optional[int] = None  # Подсистема 3: Инвариант III
    tick_state_hash_after: Optional[int] = None   # Подсистема 3: Инвариант III
    tick_state_mutated_fields: Optional[List[str]] = None # S179 FIX: Список мутировавших полей
    effective_drives_map: Any = None              # Подсистема 3: Инвариант II (Historical Constraint)
    spatial_service: Any = None                   # BUG-SPATIAL-036: Для проверки SC-3..SC-8+

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
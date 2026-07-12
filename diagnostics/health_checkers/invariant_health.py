"""
path: diagnostics/health_checkers/invariant_health.py
Назначение: Ловит ТИХИЕ деградации симуляции, которые pattern-матчинг не видит.
            Хранит скользящее окно последних 10 тиков и проверяет инварианты
            по РАЗНИЦЕ между значениями, а не по наличию строк в логе.
Зависимости: diagnostics.health_checkers
Основные сущности: InvariantHealthChecker, InvariantViolation
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class InvariantViolation:
    """Одно нарушение инварианта, обнаруженное post-mortem."""

    invariant_id: str
    severity: str  # CRITICAL / WARNING
    source: str  # POST-MORTEM / RUNTIME
    message: str
    suspect_files: List[str] = field(default_factory=list)
    powershell_check: str = ""


class InvariantHealthChecker:
    """
    Скользящее окно по 10 тикам. Каждая строка лога с [TICK_ORCH] или
    [SCENE_EVENTS] кормится в on_tick_complete / on_dialogue_emitted.
    После 10 тиков — проверяет инварианты.
    """

    WINDOW_SIZE = 10

    def __init__(self):
        self._window: list = []
        self._violations: List[InvariantViolation] = []
        self._runtime_violations: List[InvariantViolation] = []

    def on_tick_complete(
        self,
        tick: int,
        game_time_seconds: float,
        decisions_count: int,
        verbal_intents_count: int,
        npc_moved_count: int,
    ) -> None:
        self._window.append(
            {
                "tick": tick,
                "game_time": game_time_seconds,
                "decisions": decisions_count,
                "verbal_intents": verbal_intents_count,
                "dialogues": 0,
                "npc_moved": npc_moved_count,
            }
        )
        if len(self._window) > self.WINDOW_SIZE:
            self._window.pop(0)
        self._check_invariants()

    def on_dialogue_emitted(self, count: int) -> None:
        if self._window:
            self._window[-1]["dialogues"] += count

    def on_sim_integrity(self, invariant_id: str, file: str, line: int) -> None:
        self._runtime_violations.append(
            InvariantViolation(
                invariant_id=invariant_id,
                severity="CRITICAL",
                source="RUNTIME",
                message=f"Игра упала с SimulationIntegrityError в {file}:{line}",
                suspect_files=[file],
            )
        )

    def _check_invariants(self) -> None:
        if len(self._window) < 5:
            return

        # INV-TIME-FREEZE
        if self._window[-1]["game_time"] <= self._window[0]["game_time"]:
            self._add_postmortem(
                InvariantViolation(
                    invariant_id="INV-TIME-FREEZE",
                    severity="CRITICAL",
                    source="POST-MORTEM",
                    message=(
                        f"game_time_seconds не изменился за {len(self._window)} тиков: "
                        f"был {self._window[0]['game_time']}, "
                        f"стал {self._window[-1]['game_time']}"
                    ),
                    suspect_files=[
                        "backend/app/core/calendar.py:advance()",
                        "backend/app/services/tick_orchestrator.py (Фаза 0)",
                        "backend/app/services/game_loop/scene_init.py:73",
                    ],
                    powershell_check='Select-String -Path "backend/app/core/calendar.py" -Pattern "def advance"',
                )
            )

        # INV-DIALOGUE-PIPELINE-BROKEN
        total_verbal = sum(w["verbal_intents"] for w in self._window)
        total_dialogues = sum(w["dialogues"] for w in self._window)
        if total_verbal > 0 and total_dialogues == 0:
            self._add_postmortem(
                InvariantViolation(
                    invariant_id="INV-DIALOGUE-PIPELINE-BROKEN",
                    severity="CRITICAL",
                    source="POST-MORTEM",
                    message=(
                        f"За {len(self._window)} тиков было {total_verbal} вербальных интентов, "
                        f"но 0 реплик в recent_dialogues. Цепочка порвана."
                    ),
                    suspect_files=[
                        "backend/app/services/npc/decision_hub.py:_build_communication (строка 286)",
                        "backend/app/services/npc/life_engine.py:719 (communication_intents.append)",
                        "backend/app/services/pipeline_runner.py:87 (ctx.communication_intents = ...)",
                        "backend/app/services/phases/post_decision.py:23",
                        "backend/app/services/game_loop/task_scheduler.py:114 (executor.execute)",
                    ],
                    powershell_check='Get-Content backend/logs/cds_session_*.log | Select-String "Фаза 6"',
                )
            )

        # INV-NPC-FROZEN
        recent_5 = self._window[-5:]
        total_moved = sum(w["npc_moved"] for w in recent_5)
        if total_moved == 0 and len(self._window) >= 5:
            self._add_postmortem(
                InvariantViolation(
                    invariant_id="INV-NPC-FROZEN",
                    severity="CRITICAL",
                    source="POST-MORTEM",
                    message="За 5 тиков ни один NPC не сменил позицию. MovementEngine или RELOCATE сломаны.",
                    suspect_files=[
                        "backend/app/services/spatial/movement_engine.py",
                        "backend/app/services/scene_state_manager.py (RELOCATE handler)",
                        "backend/app/services/integration/world_snapshot_builder.py:_extract_active_traversals",
                    ],
                )
            )

    def _add_postmortem(self, v: InvariantViolation) -> None:
        if not any(
            x.invariant_id == v.invariant_id and x.source == "POST-MORTEM"
            for x in self._violations
        ):
            self._violations.append(v)

    def build(self) -> List[InvariantViolation]:
        return self._runtime_violations + self._violations

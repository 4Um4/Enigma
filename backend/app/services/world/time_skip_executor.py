"""
TZ-08 Addendum — Time Skip Architecture (v0.1)

Архитектурная истина:
Kernel.execute() — ВСЕГДА одинаковый, deterministic.
SkipPolicy — это observation policy (когда остановиться, что запомнить), а не режим выполнения.
TimeSkipExecutor не содержит собственной симуляции — только многократный вызов Kernel.
SSOT для NPC читается через коллбек, чтобы не создавать жестких связей с LifeEngine.
SkipPolicy принимают решения на основе Detector'ов и не содержат знаний о физиологии напрямую.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# DATACLASSES (Контракты результатов)
# =============================================================================


@dataclass
class SignificantEvent:
    type: str
    tick: int
    details: Dict[str, Any]


@dataclass
class Milestone:
    type: str
    tick: int
    details: Dict[str, Any]
    requires_playback: bool = False


@dataclass
class MilestoneCheckpoint:
    tick: int
    state: Dict[str, Any]
    milestone: Milestone


@dataclass
class PeriodSummary:
    total_ticks: int
    milestone_count: int
    playback_scenes: List[Milestone]
    periods: List[Dict[str, Any]]
    highlights: List[str]


@dataclass
class TimeSkipResult:
    final_state: Dict[str, Any]
    event_log: List[Any]  # List[StateDeltas]
    stop_reason: str
    ticks_skipped: int
    stops: List[SignificantEvent]
    significant_event: Optional[SignificantEvent] = None
    checkpoints: Optional[List[MilestoneCheckpoint]] = None
    summary: Optional[PeriodSummary] = None


# =============================================================================
# DETECTORS (Чистые функции анализа)
# =============================================================================


class SignificanceDetector:
    """Определяет, когда остановить time skip (Policy B).

    Читает state после kernel.execute() (через TickResultDTO и get_npcs_callback).
    НЕ мутирует state.
    """

    SIGNIFICANT_EVENT_TYPES = frozenset(
        {
            "npc_death",
            "combat_start",
            "faction_war",
            "marriage",
            "succession",
            "npc_enters_player_location",
            "trauma_event",
            "npc_speaks_about_player",
        }
    )

    TRAUMA_THRESHOLD = 0.3  # identity_integrity < 0.3 = trauma

    def check(
        self,
        tick: int,
        result_dto: Any,  # TickResultDTO
        prev_npcs: List[dict],
        curr_npcs: List[dict],
    ) -> Optional[SignificantEvent]:
        """Проверяет, произвёл ли тик значимое событие."""

        # 1. Проверка значимых событий из TickResultDTO.significant_events (npc_deltas)
        # Детекция боя через shock_impulse убрана — это может быть падение или реакция, а не бой.
        # Полагаемся только на явные типы событий от ядра (если они появятся) и абсолютные значения.
        for delta in result_dto.significant_events:
            event_type = getattr(delta, "source", None) or (
                delta.get("source", "") if isinstance(delta, dict) else ""
            )
            if event_type in self.SIGNIFICANT_EVENT_TYPES:
                return SignificantEvent(
                    type=event_type, tick=tick, details={"raw_delta": delta}
                )

        # 2. Проверка абсолютных состояний NPC (через коллбек SSOT)
        prev_map = {n.get("npc_id"): n for n in prev_npcs}
        curr_map = {n.get("npc_id"): n for n in curr_npcs}

        for npc_id, curr_npc in curr_map.items():
            prev_npc = prev_map.get(npc_id, {})

            # Проверка смерти
            prev_status = prev_npc.get("body_state", {}).get("life_status", "ALIVE")
            curr_status = curr_npc.get("body_state", {}).get("life_status", "ALIVE")
            if prev_status != "DEAD" and curr_status == "DEAD":
                return SignificantEvent(
                    type="npc_death", tick=tick, details={"npc_id": npc_id}
                )

            # Проверка травмы (identity_integrity < 0.3)
            prev_integrity = prev_npc.get("psyche", {}).get("identity_integrity", 1.0)
            curr_integrity = curr_npc.get("psyche", {}).get("identity_integrity", 1.0)
            if prev_integrity > self.TRAUMA_THRESHOLD >= curr_integrity:
                return SignificantEvent(
                    type="trauma_event",
                    tick=tick,
                    details={
                        "npc_id": npc_id,
                        "prev": prev_integrity,
                        "curr": curr_integrity,
                    },
                )

        return None


class SemanticMilestoneFilter:
    """Агрессивный фильтр для Policy C. Запоминает ТОЛЬКО milestones.

    НЕ останавливает kernel. Collects checkpoints for later playback.
    """

    MILESTONE_TYPES = frozenset(
        {
            "attachment_formed",
            "trauma_received",
            "separation_event",
            "discovery",
            "socialization",
            "language_milestone",
            "personality_trait_formed",
            "loss_event",
            "combat_won",
            "combat_lost",
            "ally_gained",
            "ally_lost",
            "skill_mastered",
            "secret_discovered",
            "betrayal_committed",
            "reputation_threshold_crossed",
            "faction_joined",
            "faction_left",
        }
    )

    DRIVE_CHANGE_THRESHOLD = 0.05

    def check(
        self,
        tick: int,
        result_dto: Any,
        prev_npcs: List[dict],
        curr_npcs: List[dict],
        context: Dict[str, Any],
    ) -> Optional[Milestone]:
        """Проверяет, произвёл ли тик milestone."""

        # 1. Event-based milestones
        for event in result_dto.significant_events:
            event_type = getattr(event, "source", None) or (
                event.get("source") if isinstance(event, dict) else ""
            )
            if event_type in self.MILESTONE_TYPES:
                return Milestone(
                    type=event_type,
                    tick=tick,
                    details={"raw_event": event},
                    requires_playback=self._requires_playback(event_type),
                )

        # 2. Drive formation milestones (для младенчества/долгих периодов)
        child_id = context.get("child_id")
        if child_id:
            child = next((n for n in curr_npcs if n.get("npc_id") == child_id), None)
            prev_child = next(
                (n for n in prev_npcs if n.get("npc_id") == child_id), None
            )

            if child and prev_child:
                drives = child.get("drives", {})
                prev_drives = prev_child.get("drives", {})
                for drive_name in ["control", "significance", "fear", "desire"]:
                    curr_val = drives.get(drive_name, 0.25)
                    prev_val = prev_drives.get(drive_name, 0.25)
                    if abs(curr_val - prev_val) > self.DRIVE_CHANGE_THRESHOLD:
                        return Milestone(
                            type="personality_trait_formed",
                            tick=tick,
                            details={
                                "npc_id": child_id,
                                "drive": drive_name,
                                "prev": prev_val,
                                "curr": curr_val,
                            },
                            requires_playback=True,
                        )

        # 3. Trauma threshold
        for curr_npc in curr_npcs:
            npc_id = curr_npc.get("npc_id")
            prev_npc = next((n for n in prev_npcs if n.get("npc_id") == npc_id), {})
            prev_integrity = prev_npc.get("psyche", {}).get("identity_integrity", 1.0)
            curr_integrity = curr_npc.get("psyche", {}).get("identity_integrity", 1.0)
            if prev_integrity > 0.3 >= curr_integrity:
                return Milestone(
                    type="trauma_received",
                    tick=tick,
                    details={
                        "npc_id": npc_id,
                        "prev": prev_integrity,
                        "curr": curr_integrity,
                    },
                    requires_playback=True,
                )

        return None

    def _requires_playback(self, milestone_type: str) -> bool:
        playback_required = {
            "trauma_received",
            "separation_event",
            "loss_event",
            "attachment_formed",
            "personality_trait_formed",
            "combat_won",
            "combat_lost",
            "ally_lost",
            "betrayal_committed",
        }
        return milestone_type in playback_required


# =============================================================================
# SKIP POLICIES (Observation Layers)
# =============================================================================


class SkipPolicyA:
    """Headless batch. No stops. Full kernel execution."""

    def execute(
        self,
        kernel_execute: Callable,
        campaign_id: str,
        scene_state: Dict[str, Any],
        ticks: int,
        spatial_service: Any,
        npc_services: Any,
        get_npcs: Callable,
    ) -> TimeSkipResult:
        event_log = []
        _state = scene_state
        _tick = _state.get("tick", 0)  # SSOT: время берётся только из scene_state

        for _ in range(ticks):
            _tick += 1
            _state["tick"] = _tick

            result = kernel_execute(
                campaign_id=campaign_id,
                scene_state=_state,
                tick_number=_tick,
                spatial_service=spatial_service,
                npc_services=npc_services,
            )
            event_log.extend(result.significant_events)

        return TimeSkipResult(
            final_state=_state,
            event_log=event_log,
            stop_reason="completed",
            ticks_skipped=ticks,
            stops=[],
        )


class SkipPolicyB:
    """Event-threshold stop. Kernel executes, stops on significance."""

    def __init__(self, detector: SignificanceDetector):
        self._detector = detector

    def execute(
        self,
        kernel_execute: Callable,
        campaign_id: str,
        scene_state: Dict[str, Any],
        max_ticks: int,
        spatial_service: Any,
        npc_services: Any,
        get_npcs: Callable,
    ) -> TimeSkipResult:
        event_log = []
        stops = []
        _state = scene_state
        _tick = _state.get("tick", 0)  # SSOT: время берётся только из scene_state
        _prev_npcs = get_npcs(campaign_id)

        for _ in range(max_ticks):
            _tick += 1
            _state["tick"] = _tick

            result = kernel_execute(
                campaign_id=campaign_id,
                scene_state=_state,
                tick_number=_tick,
                spatial_service=spatial_service,
                npc_services=npc_services,
            )
            event_log.extend(result.significant_events)

            _curr_npcs = get_npcs(campaign_id)
            significant = self._detector.check(_tick, result, _prev_npcs, _curr_npcs)

            if significant:
                stops.append(significant)
                return TimeSkipResult(
                    final_state=_state,
                    event_log=event_log,
                    stop_reason=significant.type,
                    ticks_skipped=_tick - start_tick,
                    stops=stops,
                    significant_event=significant,
                )
            _prev_npcs = _curr_npcs

        return TimeSkipResult(
            final_state=_state,
            event_log=event_log,
            stop_reason="max_ticks_reached",
            ticks_skipped=max_ticks,
            stops=stops,
        )


class SkipPolicyC:
    """Milestone sampling + aggressive compression."""

    def __init__(self, milestone_filter: SemanticMilestoneFilter):
        self._filter = milestone_filter

    def execute(
        self,
        kernel_execute: Callable,
        campaign_id: str,
        scene_state: Dict[str, Any],
        max_ticks: int,
        spatial_service: Any,
        npc_services: Any,
        get_npcs: Callable,
        context: Dict[str, Any],
    ) -> TimeSkipResult:
        checkpoints = []
        event_log = []
        _state = scene_state
        _tick = _state.get("tick", 0)  # SSOT: время берётся только из scene_state
        _prev_npcs = get_npcs(campaign_id)

        for _ in range(max_ticks):
            _tick += 1
            _state["tick"] = _tick

            result = kernel_execute(
                campaign_id=campaign_id,
                scene_state=_state,
                tick_number=_tick,
                spatial_service=spatial_service,
                npc_services=npc_services,
            )
            event_log.extend(result.significant_events)

            _curr_npcs = get_npcs(campaign_id)
            milestone = self._filter.check(
                _tick, result, _prev_npcs, _curr_npcs, context
            )

            if milestone:
                # Sparse checkpoint: сохраняем state ТОЛЬКО на milestones
                checkpoints.append(
                    MilestoneCheckpoint(
                        tick=_tick, state=copy.deepcopy(_state), milestone=milestone
                    )
                )
            _prev_npcs = _curr_npcs

        summary = self._compress(checkpoints, event_log, context)

        return TimeSkipResult(
            final_state=_state,
            event_log=event_log,
            stop_reason="completed",
            ticks_skipped=max_ticks,
            stops=[],
            checkpoints=checkpoints,
            summary=summary,
        )

    def _compress(
        self,
        checkpoints: List[MilestoneCheckpoint],
        event_log: List[Any],
        context: Dict[str, Any],
    ) -> PeriodSummary:
        milestones = [cp.milestone for cp in checkpoints]
        playback_scenes = [m for m in milestones if m.requires_playback]

        periods = self._group_by_period(checkpoints, context)

        return PeriodSummary(
            total_ticks=len(event_log),
            milestone_count=len(milestones),
            playback_scenes=playback_scenes,
            periods=periods,
            highlights=[m.type for m in milestones],
        )

    def _group_by_period(
        self, checkpoints: List[MilestoneCheckpoint], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        period_type = context.get("period", "year")
        if period_type == "year":
            TICKS_PER_YEAR = 24 * 365
            groups = {}
            for cp in checkpoints:
                year = cp.tick // TICKS_PER_YEAR
                groups.setdefault(year, []).append(cp)
            return [
                {"period": f"Year {y}", "milestones": [cp.milestone for cp in cps]}
                for y, cps in sorted(groups.items())
            ]
        return [{"period": "all", "milestones": [cp.milestone for cp in checkpoints]}]


# =============================================================================
# TIME SKIP EXECUTOR (Единая точка входа)
# =============================================================================


class TimeSkipExecutor:
    """Единая точка входа для time skip.

    Kernel.execute() — ВСЕГДА одинаковый.
    SkipPolicy — определяет observation (когда остановиться, что запомнить).
    """

    def __init__(self, kernel: Any):
        """Инициализация.

        Args:
            kernel: TickOrchestrator (унифицированное ядро)
        """
        self._kernel = kernel
        self._policy_a = SkipPolicyA()
        self._policy_b = SkipPolicyB(SignificanceDetector())
        self._policy_c = SkipPolicyC(SemanticMilestoneFilter())

    def _kernel_execute_wrapper(
        self,
        campaign_id: str,
        scene_state: Dict[str, Any],
        tick_number: int,
        spatial_service: Any,
        npc_services: Any,
    ):
        """Обёртка для вызова ядра."""
        return self._kernel.execute(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=tick_number,
            spatial_service=spatial_service,
            npc_services=npc_services,
        )

    def skip(
        self,
        campaign_id: str,
        scene_state: Dict[str, Any],
        ticks: int,
        policy: str = "A",
        spatial_service: Any = None,
        npc_services: Any = None,
        get_npcs_callback: Callable = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> TimeSkipResult:
        """Промотать время. Kernel выполняется, policy определяет observation.

        Args:
            policy: "A" (headless batch), "B" (stop on event), "C" (milestone sampling)
            get_npcs_callback: Функция для получения актуальных NPC (SSOT), напр. GameLoop._resolve_npcs_snapshot
            context: доп. контекст для Policy C (child_id, period, etc.)
        """
        if get_npcs_callback is None:
            raise ValueError("get_npcs_callback is required for SSOT access")

        logger.info(
            f"[TIME_SKIP] policy={policy} ticks={ticks} start={scene_state.get('tick', 0)} "
            f"context={context}"
        )

        if policy == "A":
            return self._policy_a.execute(
                self._kernel_execute_wrapper,
                campaign_id,
                scene_state,
                ticks,
                spatial_service,
                npc_services,
                get_npcs_callback,
            )
        elif policy == "B":
            return self._policy_b.execute(
                self._kernel_execute_wrapper,
                campaign_id,
                scene_state,
                ticks,
                spatial_service,
                npc_services,
                get_npcs_callback,
            )
        elif policy == "C":
            return self._policy_c.execute(
                self._kernel_execute_wrapper,
                campaign_id,
                scene_state,
                ticks,
                spatial_service,
                npc_services,
                get_npcs_callback,
                context or {},
            )
        else:
            raise ValueError(f"Unknown skip policy: {policy}")

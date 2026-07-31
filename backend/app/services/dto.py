# -*- coding: utf-8 -*-
"""
path: backend/app/services/dto.py
Назначение: Изоляция DTO и контекста тика (ReductionPolicy, _TickContext, DMContextDTO, TickPlayerResultDTO) из God-object TickOrchestrator.
Зависимости: dataclasses, enum, typing, app.services.drf_bus, app.services.npc.kernel_rng, app.models.state_delta, app.models.cfrm, app.models.will, app.domain.intent
Основные сущности: ReductionPolicy, DELTA_POLICY_REGISTRY, SemanticFrame, TickPlayerResultDTO, _TickContext, DMContextDTO

"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.domain.identity_events import EffectiveDrives
from app.domain.intent import IntentDTO
from app.models.cfrm import ClusterOccupancy, EventBuffer
from app.models.state_delta import DeltaDomain
from app.models.will import IntentPressureProfile
from app.services.drf_bus import DRFBus
from app.services.npc.kernel_rng import KernelRNG


class ReductionPolicy(Enum):
    """Политика редукции дельт при агрегации"""

    ADDITIVE = "additive"
    BOUNDED_ADDITIVE = "bounded_additive"
    OVERWRITE = "overwrite"
    PHYSICS_COMPOSITE = "physics_composite"


DELTA_POLICY_REGISTRY = {
    DeltaDomain.SOCIAL: ReductionPolicy.ADDITIVE,
    DeltaDomain.EMOTION: ReductionPolicy.BOUNDED_ADDITIVE,
    DeltaDomain.REPUTATION: ReductionPolicy.ADDITIVE,
    DeltaDomain.IDENTITY: ReductionPolicy.OVERWRITE,
    DeltaDomain.PHYSIOLOGY: ReductionPolicy.PHYSICS_COMPOSITE,
}


@dataclass
class SemanticFrame:
    """SIL: Изолированный фрейм интерпретации мира (S-слой).
    Эмоции и восприятие существуют здесь до сброса в M-слой в Phase 10.
    tick_id предотвращает утечку эмоций (afterimage bug) между тиками."""

    emotion_tag: Optional[str] = None
    affective_load: Optional[float] = None
    stress_delta: Optional[float] = None
    perception_label: Optional[str] = None
    tick_id: int = -1


@dataclass
class TickPlayerResultDTO:
    """Результат NPC-тика для player turn."""

    status: str = "ok"
    error: Optional[str] = None
    npc_contexts: list = field(default_factory=list)
    snapshot: Optional[dict] = None
    events: List[Any] = field(default_factory=list)
    dirty_npcs: set = field(default_factory=set)
    activity_overrides: Dict[str, str] = field(default_factory=dict)
    max_npc_stress: float = 0.0
    # MovementIntent — реактивное движение NPC (APPROACH и др.)
    # Оркестратор передаёт в MovementEngine → SceneChange → apply_changes
    movement_intents: list = field(default_factory=list)
    # Результат _phase_finalize (R3 frame, npc_reactions, npc_actions) —
    # доступен только если execute() прошёл фазы 8-10 (Устав §3)
    finalize_result: Optional[dict] = None
    # Sprint P9: Список строк фактов для DMContractBuilder
    observed_facts: list = field(default_factory=list)


@dataclass
class _TickContext:
    """Внутренний контекст тика — живёт только внутри execute()."""

    campaign_id: str
    scene_state: dict
    tick_number: int
    # ADR-134: Instance-level bus — обязательно передаётся без дефолта (выше полей с default_factory)
    drf_bus: DRFBus
    # Слой 4: позиции NPC ДО тика (для детекции переходов)
    old_npc_positions: dict = field(default_factory=dict)
    # Фаза 0: изменения от LifeEngine
    scene_changes: list = field(default_factory=list)
    # Фаза 2: spatial events для Phase 3 (memory)
    phase_2_events: list = field(default_factory=list)
    # Фаза 4: извлечённые темы для каждого NPC (npc_id → topic)
    npc_topics: dict = field(default_factory=dict)
    # S129: Адресат ответа для NPC (npc_id → speaker_id)
    response_targets: dict = field(default_factory=dict)
    # Фаза 5: CommunicationIntent для каждого NPC (пока пустой — legacy pipeline)
    communication_intents: list = field(default_factory=list)
    # V8-TICK-2/7 FIX: Добавлено объявление movement_intents (используется в pipeline_runner и tick_orchestrator)
    movement_intents: list = field(default_factory=list)
    # TZ-08 v0.2: Narrative Projection (для LLM/UI). Артефакт тика, а не player_result.
    npc_contexts: list = field(default_factory=list)
    # Sprint P9: Список строк фактов для DMContractBuilder
    observed_facts_for_dm: list = field(default_factory=list)
    # Fix: Счётчик изменений для TickResultDTO
    changes_count: int = 0
    # Sprint P3: SpatialQueryService для PerceptionPhysicsEngine
    spatial_query: Optional[Any] = None
    # ADR-O-313: Проброс TaskScheduler для чтения свежих реплик (S128 FIX)
    task_scheduler: Optional[Any] = None

    # KERNEL-ISOLATION: per-tick RNG factory.
    # Создаёт KernelRNG для каждого NPC по запросу (lazy).
    # НЕ хранит RNG state напрямую — хранит factory, чтобы каждый NPC
    # получил независимый deterministic stream.
    rng_factory: Optional[Callable[[str], "KernelRNG"]] = None

    def rng_for(self, npc_id: str) -> KernelRNG:
        """Возвращает deterministic KernelRNG для данного NPC на текущем тике.

        Использование:
            rng = ctx.rng_for("maid_lusya")
            if rng.random() < 0.4:
                ...
        """
        if self.rng_factory is None:
            # Fallback для legacy тестов, где factory не задан.
            # В production этого быть не должно.
            import logging

            logging.getLogger(__name__).warning(
                f"[TICK_CONTEXT] rng_factory is None, creating ad-hoc KernelRNG "
                f"for npc={npc_id} tick={self.tick_number}. "
                f"This indicates incomplete initialization."
            )
            return KernelRNG(tick=self.tick_number, npc_id=npc_id)
        return self.rng_factory(npc_id)

    # Фаза 5: решения DecisionHub
    decision_events: list = field(default_factory=list)
    # SIL: S-слой (интерпретация). Визуализация читает отсюда (T+0), DecisionHub из M-слоя (T-1)
    semantic_buffer: Dict[str, "SemanticFrame"] = field(default_factory=dict)
    # DSTC: Interpretation Snapshot (замороженный M₀ + Deltas).
    # Phase 9 читает ТОЛЬКО его. Мутация запрещена (Pure Read invariant).
    interpretation_snapshot: Optional[list] = None
    # Фаза 9: финальный снимок
    world_snapshot: Optional[Any] = None
    # TZ-08 v0.2: interventions replace dm_ctx. Kernel не знает "player".
    interventions: list = field(default_factory=list)
    # Player turn: сервисы для legacy pipeline (передаёт npc_orchestration)
    npc_services: Optional[Any] = None
    # Player turn: результат legacy pipeline
    player_result: Optional["TickPlayerResultDTO"] = None
    # Player turn: контекст GameLoop для фаз 7-10 (Устав §3 — единая последовательность)
    shared_context: Any = None
    actions: list = field(default_factory=list)
    player_intent: Optional["IntentDTO"] = None  # ADR-031: Канонический интент
    is_player_turn: bool = False  # S116 FIX: Флаг хода игрока для execute_persistence
    player_pressure: Optional["IntentPressureProfile"] = (
        None  # ADR-031 Fix: Вектор давления из Фазы 1
    )
    rules_result: Dict[str, Any] = field(default_factory=dict)
    r3_direct_mode: bool = True
    # Фаза 10: данные для коммита (мостируются из TickBuffer GameLoop)
    all_npcs_raw: list = field(default_factory=list)
    dirty_npcs: set = field(default_factory=set)
    wt_dirty: bool = False
    prop_dirty: bool = False
    max_npc_stress: float = 0.0
    # Фаза 10: данные для атомарного коммита
    npc_states: list[dict] = field(default_factory=list)
    # TZ-09: significant_events для аудита/персиста (маппируется из TickMutation.npc_deltas)
    significant_events: list = field(default_factory=list)
    # STEP B: L3 проекция (EffectiveDrives). Вычисляется один раз за тик, доступна обоим путям.
    effective_drives_map: Dict[str, "EffectiveDrives"] = field(default_factory=dict)
    # TSHL: Обновления для StateApplicator (пока в безопасном режиме)
    drives_updates: Dict[str, Dict[str, float]] = field(default_factory=dict)
    strain_updates: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # tick_events: все события тика для аудита (decision_events + spatial + handlers)
    tick_events: list[dict] | None = None
    # Фаза 0.5: буфер idle-дельт (social decay, reputation decay)
    delta_buffer: list = field(default_factory=list)
    # ── CFRM Layer 1 & P1: Причинная физика мира ──────────────────────
    event_buffer: EventBuffer = field(default_factory=EventBuffer)
    cluster_occupancy: ClusterOccupancy = field(default_factory=ClusterOccupancy)
    # DRF: Unified Causal Bus — единая память причинных напряжений тика.
    # (Перемещён выше, до полей с дефолтами)
    # ADR-O-310: windup_registry перенесён на уровень TickOrchestrator (self._windup_registry)
    # чтобы переживать тики. Здесь больше не определяется.


# ── Мостовые DTO для player turn (P1.1b) ──────────────────────────────
@dataclass(frozen=True)
class DMContextDTO:
    """Мост: DM-интерпретация → TickOrchestrator."""

    hub_event: Any
    nearby_npcs: list
    line_of_sight: dict
    scene_continuity: Any
    action_type: str
    player_target_id: str
    spatial_events: list
    raw_input: str
    is_session_start: bool
    current_tick: int = 0
    all_npcs_raw: list = field(default_factory=list)
    # SHI-FIX COMMAND: проброс intent_resolution для DirectiveInterpretationSubscriber.
    # Без этого _process_player_dm_action не видит semantic_action → compliance_bias не растёт.
    intent_resolution: Any = None

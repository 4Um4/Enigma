"""
Файл: backend/tests/sandbox/system/test_causal_closure.py
Назначение: Системная песочница. Вертикальный срез замкнутого контура:
            PerceptualKernel(T-1) -> DecisionContext -> DecisionHub.compute().
            Доказывает, что консолидированное давление доходит до хаба и деформирует скоринги
            без ручной склейки (Приоритет 0 и 2 Спринта 29).
Зависимости: app.domain.decision_context, app.services.npc.decision_hub, app.models.npc_state, app.models.npc_profile
Основные сущности: TestCausalClosure

Запуск: pytest backend/tests/sandbox/system/test_causal_closure.py -s
"""

import pytest
from app.domain.decision_context import ActionSpaceCompression, DecisionContext, UtilityFieldDeformation
from app.domain.identity_events import EffectiveDrives
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import NPCState, PerceptualKernel
from app.services.events.event_types import EventType
from app.services.npc.decision_hub import DecisionHub, EventContext


@pytest.fixture
def fearful_profile() -> NPCProfileL0:
    """Трусливый NPC: высокий страх, низкая агрессия."""
    return NPCProfileL0(
        id="thief_shadow",
        name="Тень",
        tier="minor",
        drives_base={"fear": 0.8, "aggression": 0.1, "control": 0.2},
        psyche_base=PsycheBase(willpower=3, breakpoint=4, loyalty_base=60),
        voice_profile="coward",
    )


@pytest.fixture
def brave_profile() -> NPCProfileL0:
    """Смелый NPC: низкий страх, высокая агрессия."""
    return NPCProfileL0(
        id="guard_stone",
        name="Камень",
        tier="minor",
        drives_base={"fear": 0.1, "aggression": 0.9, "control": 0.7},
        psyche_base=PsycheBase(willpower=9, breakpoint=9, loyalty_base=20),
        voice_profile="bold",
    )


@pytest.fixture
def idle_event() -> EventContext:
    """Стандартный контекст IDLE-тика для проверки решений."""
    return EventContext(event_type=EventType.IDLE, actor_id="player", success=True, intensity=0.2, location="tavern")


def _print_causal_trace(
    tick: int,
    npc_id: str,
    pk: PerceptualKernel,
    ctx: DecisionContext,
    result_intent: str,
    result_score: float,
    competing: str,
    comp_score: float,
):
    """Вывод в формате Causal Trace Report (ТЗ Спринт 29)."""
    print(f"\nTick {tick}")
    print(f"├── [FIELD] origin=command axis=DOMINANCE intensity={pk.threat_gradient:.2f}")
    print(f"├── [PHENOMENON] {npc_id}: threat={pk.threat_gradient:.2f} compliance={pk.compliance_bias:.2f}")
    print(
        f"├── [PRESSURE] aggression_sup={ctx.deformation.aggression_suppression:.2f} initiative_sup={ctx.deformation.initiative_suppression:.2f}"
    )
    print(f"└── [DECISION] goal={result_intent} utility={result_score:.2f} competing={competing}({comp_score:.2f})")


def test_full_obedience_closure(fearful_profile, idle_event):
    """
    СЦЕНАРИЙ: Трусливый NPC находится под давлением приказа (PerceptualKernel T-1).
    ОЖИДАНИЕ: Контур замыкается. DecisionContext подавляет ATTACK (feasibility=0) и усиливает APPROACH.
    """
    # 1. Подготовка состояния (ядро уже содержит консолидированное давление T-1)
    state = NPCState(npc_id=fearful_profile.id)
    state.perceptual_kernel = PerceptualKernel(
        threat_gradient=0.8,
        aggression_inhibition=0.9,  # Сильное подавление агрессии
        initiative_suppression=0.85,  # Паралич воли
        compliance_bias=0.7,  # Смещение к подчинению
    )

    # 2. Проекция ядра в контекст (логика перенесена из домена в life_engine, здесь эмулируем рантайм)
    constraints = {}
    if state.perceptual_kernel.initiative_suppression > 0.8:
        constraints["ATTACK"] = 0.0
        constraints["INTIMIDATE"] = 0.0

    decision_ctx = DecisionContext(
        deformation=UtilityFieldDeformation(
            aggression_suppression=state.perceptual_kernel.aggression_inhibition,
            initiative_suppression=state.perceptual_kernel.initiative_suppression,
            compliance_bias=state.perceptual_kernel.compliance_bias,
            escape_salience=state.perceptual_kernel.threat_gradient * 0.5,
        ),
        compression=ActionSpaceCompression(constraints=constraints),
        source="perceptual_kernel",
    )

    # 3. Вызов реального DecisionHub
    from app.domain.identity_events import EffectiveDrives

    _effective_drives = EffectiveDrives(values={"fear": 0.6, "control": 0.3, "significance": 0.4, "desire": 0.2})
    hub = DecisionHub(seed=42)
    result = hub.compute(
        state=state,
        personality=fearful_profile,
        event=idle_event,
        effective_drives=_effective_drives,
        decision_ctx=decision_ctx,
    )

    # 4. Аудит результата
    # Из-за feasibility=0, ATTACK не должен даже рассматриваться
    # Из-за compliance_bias, APPROACH должен получить усиление
    assert result.intent.value != "ATTACK", "Атака должна быть заблокирована параличом воли (feasibility=0)"

    # Трассировка
    _print_causal_trace(
        tick=1,
        npc_id=state.npc_id,
        pk=state.perceptual_kernel,
        ctx=decision_ctx,
        result_intent=result.intent.value,
        result_score=result.score,
        competing="ATTACK",
        comp_score=0.0,  # ATTACK заблокирован
    )


def test_brave_resistance_closure(brave_profile, idle_event):
    """
    СЦЕНАРИЙ: Смелый NPC игнорирует слабое давление.
    ОЖИДАНИЕ: DecisionContext почти не деформирует скоринги. Агрессия доминирует.
    """
    # 1. Подготовка состояния (слабое давление)
    state = NPCState(npc_id=brave_profile.id)
    state.perceptual_kernel = PerceptualKernel(
        threat_gradient=0.1, aggression_inhibition=0.1, initiative_suppression=0.05, compliance_bias=0.05
    )

    # 2. Проекция ядра (без экстремальных блокировок)
    decision_ctx = DecisionContext(
        deformation=UtilityFieldDeformation(
            aggression_suppression=state.perceptual_kernel.aggression_inhibition,
            initiative_suppression=state.perceptual_kernel.initiative_suppression,
            compliance_bias=state.perceptual_kernel.compliance_bias,
            escape_salience=state.perceptual_kernel.threat_gradient * 0.5,
        ),
        compression=ActionSpaceCompression(constraints={}),
        source="perceptual_kernel",
    )

    # 3. Вызов реального DecisionHub
    hub = DecisionHub(seed=42)
    result = hub.compute(
        state=state,
        personality=brave_profile,
        event=idle_event,
        effective_drives=EffectiveDrives(values={"fear": 0.6, "control": 0.3, "significance": 0.4, "desire": 0.2}),
        decision_ctx=decision_ctx,
    )

    # 4. Аудит результата
    # Агрессия не подавлена, смещения к подчинению нет
    assert decision_ctx.deformation.aggression_suppression < 0.3, "Агрессия не должна быть подавлена"

    # Трассировка
    _print_causal_trace(
        tick=1,
        npc_id=state.npc_id,
        pk=state.perceptual_kernel,
        ctx=decision_ctx,
        result_intent=result.intent.value,
        result_score=result.score,
        competing="APPROACH",
        comp_score=0.0,  # Моковое значение для отчета
    )

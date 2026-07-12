"""
Файл: backend/tests/sandbox/system/test_life_direction_crisis.py
Назначение: Интеграционный тест каузальной цепи:
            Кризис (BreakProgressEngine) -> Смена LifeDirection (LifeProjectResolver) -> Изменение решений (DecisionHub).
Зависимости: pytest, app.services.npc.decision_hub, app.services.npc.break_progress_engine, app.services.npc.life_project_resolver
Основные сущности: test_crisis_changes_life_direction_and_intent

Запуск: cd backend; python -m pytest tests/sandbox/system/test_life_direction_crisis.py -s -v; cd ..
"""

import pytest
from app.domain.identity_events import EffectiveDrives
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import Intent, NPCState, PerceptualKernel
from app.services.events.event_types import EventType
from app.services.npc.break_progress_engine import BreakProgressEngine
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.npc.life_project_resolver import LifeProjectResolver


@pytest.fixture
def family_profile() -> NPCProfileL0:
    """Люся: family_builder, низкая воля."""
    return NPCProfileL0(
        id="maid_lusya",
        name="Люся",
        tier="major",
        gender="female",
        archetype="maid",
        drives_base={"control": 0.15, "significance": 0.2, "fear": 0.45, "desire": 0.2},
        psyche_base=PsycheBase(willpower=35, breakpoint=55, loyalty_base=0),
        voice_profile="Тихая речь",
        backstory="Служанка",
        core_orientation="family_builder",
    )


@pytest.fixture
def world_tick_event() -> EventContext:
    """Стандартный контекст WORLD_TICK для проверки проактивных решений."""
    return EventContext(event_type=EventType.WORLD_TICK, actor_id="world", location="tavern")


def test_crisis_changes_life_direction_and_intent(family_profile, world_tick_event):
    """
    СЦЕНАРИЙ: NPC (family_builder) находится в глубоком кризисе (identity_integrity < 0.2).
    ОЖИДАНИЕ:
        1. BreakProgressEngine фиксирует кризис.
        2. LifeProjectResolver меняет life_direction на 'isolation'.
        3. DecisionHub на следующем тике выбирает 'FLEE' или 'BLOCK_PATH' вместо 'SEEK_ALLY'.
    """
    
    _effective_drives = EffectiveDrives(values={"fear": 0.2, "control": 0.3, "significance": 0.3, "desire": 0.2})
    hub = DecisionHub(seed=42)

    # --- ТИК 0: PRE-CRISIS (NPC здоров, direction=family_builder) ---
    state_healthy = NPCState(
        npc_id=family_profile.id,
        life_direction="family_builder",
        identity_integrity=1.0,
        stress=0.0,
        affective_load=0.0,
        emotion="neutral",
    )
    state_healthy.perceptual_kernel = PerceptualKernel(threat_gradient=0.0)

    pre_crisis_result = hub.compute(
        state=state_healthy,
        personality=family_profile,
        event=world_tick_event,
        effective_drives=_effective_drives,
    )
    print(f"\n[PRE-CRISIS] life_direction={state_healthy.life_direction}, intent={pre_crisis_result.intent.value}, score={pre_crisis_result.score:.2f}")
    assert pre_crisis_result.intent.value != Intent.FLEE.value, "Family builder без кризиса не должен бежать"

    # --- СИМУЛЯЦИЯ КРИЗИСА (BreakProgressEngine -> LifeProjectResolver) ---
    state_broken = NPCState(
        npc_id=family_profile.id,
        life_direction="family_builder",
        identity_integrity=0.1,
        stress=95.0,
        affective_load=0.95,
        emotion="fearful",
    )
    state_broken.perceptual_kernel = PerceptualKernel(threat_gradient=0.9)

    deltas = BreakProgressEngine.calculate(
        state=state_broken,
        willpower=family_profile.psyche_base.willpower,
        recent_failures=2,
    )
    assert deltas.identity_crisis, "NPC в стадии deformation должен иметь identity_crisis=True"

    new_direction = LifeProjectResolver.resolve(state_broken)
    assert new_direction == "isolation", "Family builder в кризисе должен уйти в изоляцию"
    state_broken.life_direction = new_direction
    print(f"\n[CRISIS RESOLVED] life_direction changed to: {state_broken.life_direction}")

    # --- ТИК 1: POST-CRISIS (NPC сломлен, direction=isolation) ---
    post_crisis_result = hub.compute(
        state=state_broken,
        personality=family_profile,
        event=world_tick_event,
        effective_drives=_effective_drives,
    )
    print(f"\n[POST-CRISIS] life_direction={state_broken.life_direction}, intent={post_crisis_result.intent.value}, score={post_crisis_result.score:.2f}")

    isolation_intents = [Intent.FLEE.value, Intent.BLOCK_PATH.value]
    assert post_crisis_result.intent.value in isolation_intents, \
        f"NPC в изоляции должен выбирать FLEE или BLOCK_PATH, но выбрал {post_crisis_result.intent.value}"

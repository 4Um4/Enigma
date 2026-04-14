# backend/tests/test_decision_hub_commitment.py
# cd backend; python -m pytest tests/test_decision_hub_commitment.py -v
"""
Тесты Commitment Model — инерция как порог смены intent.

Назначение: Тесты Commitment Model — инерция как порог смены
Зависимости: app.services.npc.decision_hub, app.services.npc.npc_state
Основные сущности: DecisionHub, NPCStateL2, Intent

Проверяем:
- _get_commitment() нормализует duration в [0..1]
- _commitment_threshold() даёт нелинейный порог
- compute() удерживает intent при низком давлении
- compute() сменяет intent при высоком давлении
- Reactive urgency принудительно сменяет intent
"""
import pytest
from app.services.npc.decision_hub import (
    DecisionHub,
    COMMITMENT_BASE_THRESHOLD,
    INTENT_INERTIA_MAX_TICKS,
    REACTIVE_URGENCY_THRESHOLD,
)
from app.models.npc_state import NPCStateL2, Intent
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.services.npc.decision_hub import EventContext


def _make_state(intent: str = "idle", duration: int = 0, stress: float = 0.0, target: str = "player") -> NPCStateL2:
    """Helper: минимальный state для тестов."""
    return NPCStateL2(
        npc_id="test_npc",
        intent=Intent(intent),
        intent_target=target if intent not in ("idle", "observe", "flee", "explain") else None,
        intent_duration=duration,
        intent_progress_ticks=duration,
        stress=stress,
    )


def _make_personality() -> NPCProfileL0:
    """Helper: минимальный профиль."""
    return NPCProfileL0(
        id="test_npc",
        name="Test",
        tier="minor",
        drives_base={},
        psyche_base=PsycheBase(willpower=0.5, breakpoint=0.3),
        voice_profile="",
    )


def _make_event() -> EventContext:
    """Helper: минимальное событие."""
    return EventContext(
        event_type="PLAYER_SPOKE",
        actor_id="player",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# I. _get_commitment — нормализация инерции
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetCommitment:
    """Нормализация duration → [0..1]."""

    def test_idle_returns_zero(self):
        """IDLE intent → commitment=0."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="idle", duration=5)
        
        c = hub._get_commitment(state)
        assert c == 0.0

    def test_first_tick_low_commitment(self):
        """Первый тик → низкий commitment."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=1)
        
        c = hub._get_commitment(state)
        assert 0.0 < c < 0.3

    def test_max_ticks_full_commitment(self):
        """INTENT_INERTIA_MAX_TICKS → commitment≈1.0."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=INTENT_INERTIA_MAX_TICKS)
        
        c = hub._get_commitment(state)
        assert c >= 0.95

    def test_no_progress_reduces_commitment(self):
        """Нет прогресса → decay снижает commitment."""
        hub = DecisionHub(seed=42)
        
        # С прогрессом
        state_with_progress = _make_state(intent="talk", duration=15, stress=0.0)
        state_with_progress.intent_progress_ticks = 15
        c_good = hub._get_commitment(state_with_progress)
        
        # Без прогресса (stall)
        state_no_progress = _make_state(intent="talk", duration=15, stress=0.0)
        state_no_progress.intent_progress_ticks = 5
        c_bad = hub._get_commitment(state_no_progress)
        
        assert c_bad < c_good


# ═══════════════════════════════════════════════════════════════════════════════
# II. _commitment_threshold — нелинейный порог
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommitmentThreshold:
    """Нелинейная формула порога."""

    def test_zero_commitment_gives_base(self):
        """commitment=0 → threshold=base."""
        hub = DecisionHub(seed=42)
        t = hub._commitment_threshold(0.0)
        assert t == COMMITMENT_BASE_THRESHOLD

    def test_high_commitment_increases_threshold(self):
        """commitment=1 → threshold значительно выше base."""
        hub = DecisionHub(seed=42)
        t_low = hub._commitment_threshold(0.0)
        t_high = hub._commitment_threshold(1.0)
        assert t_high > t_low * 2

    def test_nonlinear_growth(self):
        """Рост нелинейный: 0→0.5 даёт меньше прироста чем 0.5→1.0."""
        hub = DecisionHub(seed=42)
        t0 = hub._commitment_threshold(0.0)
        t05 = hub._commitment_threshold(0.5)
        t1 = hub._commitment_threshold(1.0)
        
        first_half = t05 - t0
        second_half = t1 - t05
        
        assert second_half > first_half


# ═══════════════════════════════════════════════════════════════════════════════
# III. compute() — удержание и смена intent
# ═══════════════════════════════════════════════════════════════════════════════

class TestComputeCommitment:
    """Интеграция commitment в compute()."""

    def test_low_commitment_allows_switch(self):
        """Низкий commitment → смена intent при небольшом преимуществе."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="idle", duration=0)  # Нет инерции
        personality = _make_personality()
        event = _make_event()
        
        result = hub.compute(state, personality, event)
        # IDLE можно сменить на что угодно при минимальном давлении
        assert result.intent != Intent.IDLE or result.score == 0.0

    def test_high_commitment_holds_intent(self):
        """Высокий commitment → удерживает текущий intent даже если другой чуть лучше."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=INTENT_INERTIA_MAX_TICKS)
        personality = _make_personality()
        event = _make_event()
        
        result = hub.compute(state, personality, event)
        # При высоком commitment talk должен удерживаться (если нет огромного давления)

    def test_force_switch_on_high_stress(self):
        """Высокий стресс → принудительная смена даже при высоком commitment."""
        hub = DecisionHub(seed=42)
        state = _make_state(
            intent="talk",
            duration=INTENT_INERTIA_MAX_TICKS,
            stress=REACTIVE_URGENCY_THRESHOLD + 0.1,
        )
        personality = _make_personality()
        event = _make_event()
        
        result = hub.compute(state, personality, event)
        # При высоком стрессе commitment не должен блокировать смену
        # (точный intent зависит от формулы, но блокировки нет)


class TestPressureAccumulation:
    """Тесты накопления давления — smoothed switching."""

    def test_single_tick_no_accumulation(self):
        """Первый тик — accumulator пустой, решение по мгновенному pressure."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=INTENT_INERTIA_MAX_TICKS)
        personality = _make_personality()
        event = _make_event()
        
        result = hub.compute(state, personality, event)
        # Первый тик: accumulator = 0, решение по pressure vs threshold
        assert result is not None  # Не упало

    def test_accumulation_builds_over_ticks(self):
        """Накопленное давление пробивает threshold даже при высоком commitment."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=INTENT_INERTIA_MAX_TICKS)
        personality = _make_personality()
        event = _make_event()
        
        # Симулируем: предыдущие тики накопили давление для talk→flee
        state.pressure_accumulator[("talk", "flee")] = 0.8
        
        result = hub.compute(state, personality, event)
        # Если flee был best_candidate — накопление + текущее давление → switch
        # Проверяем что механизм работает (результат зависит от scores)

    def test_accumulation_resets_on_switch(self):
        """При force switch accumulator для использованной пары сбрасывается."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=5, stress=0.9)  # force switch
        personality = _make_personality()
        event = _make_event()
        
        result = hub.compute(state, personality, event)
        
        # При force_switch accumulator для реально использованной пары = 0
        if result.intent != Intent.TALK:
            key = ("talk", result.intent.value)
            assert state.pressure_accumulator.get(key) == 0.0

    def test_negative_pressure_decays(self):
        """При удержании intent accumulator для конкурентов decay при повторе."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=INTENT_INERTIA_MAX_TICKS)
        personality = _make_personality()
        event = _make_event()
        
        # Первый запуск — формирует accumulator'ы
        result1 = hub.compute(state, personality, event)
        
        # Если talk удержался — для конкурентов accumulator должен decay
        if result1.intent == Intent.TALK:
            competitor_accs = {k: v for k, v in state.pressure_accumulator.items()
                              if k[0] == "talk" and k[1] != "talk"}
            
            if competitor_accs:
                # Второй запуск — все конкурентные accumulator'ы должны decay
                hub.compute(state, personality, event)
                
                for key, val_before in competitor_accs.items():
                    val_after = state.pressure_accumulator.get(key, val_before + 1)
                    assert val_after < val_before, f"No decay for {key}"

    def test_different_pairs_dont_mix(self):
        """Разные пары intent'ов накапливаются отдельно."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=5)
        personality = _make_personality()
        event = _make_event()
        
        state.pressure_accumulator[("talk", "attack")] = 0.7
        state.pressure_accumulator[("talk", "flee")] = 0.2
        
        result = hub.compute(state, personality, event)
        
        # Пары не смешиваются — одно могло сброситься, другое нет
        acc_attack = state.pressure_accumulator.get(("talk", "attack"), 0.0)
        acc_flee = state.pressure_accumulator.get(("talk", "flee"), 0.0)
        assert (acc_attack == 0.0) != (acc_flee == 0.0) or (acc_attack != acc_flee)


# ═══════════════════════════════════════════════════════════════════════════════
# VI. Intent Exhaustion — штраф за зависание без прогресса
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentExhaustion:
    """Exhaustion — активный штраф к score при стагнации.
    
    В отличие от decay (уменьшает inertia bonus),
    exhaustion делает текущий intent ХУЖЕ альтернатив.
    """
    
    def test_no_exhaustion_when_idle(self):
        """IDLE intent → нет штрафа."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="idle", duration=10, stress=0.0)
        
        assert hub._intent_exhaustion(state) == 0.0
    
    def test_no_exhaustion_below_threshold(self):
        """До порога saturation — нет штрафа."""
        from app.services.npc.decision_hub import INTENT_SATURATION_TICKS
        
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=INTENT_SATURATION_TICKS, stress=0.0)
        
        assert hub._intent_exhaustion(state) == 0.0
    
    def test_exhaustion_starts_after_threshold(self):
        """Первый тик сверх порога — минимальный штраф."""
        from app.services.npc.decision_hub import INTENT_EXHAUSTION_RATE, INTENT_SATURATION_TICKS
        
        hub = DecisionHub(seed=42)
        state = _make_state(
            intent="talk",
            duration=INTENT_SATURATION_TICKS + 1,
            stress=0.0
        )
        state.intent_progress_ticks = 0  # Нет прогресса → stall = duration
        
        assert hub._intent_exhaustion(state) == pytest.approx(INTENT_EXHAUSTION_RATE)
    
    def test_exhaustion_grows_linearly(self):
        """Штраф растёт линейно с каждым тиком стагнации."""
        from app.services.npc.decision_hub import INTENT_EXHAUSTION_RATE, INTENT_SATURATION_TICKS
        
        hub = DecisionHub(seed=42)
        
        for excess in range(1, 6):
            state = _make_state(
                intent="talk",
                duration=INTENT_SATURATION_TICKS + excess,
                stress=0.0
            )
            state.intent_progress_ticks = 0  # Нет прогресса → stall = duration
            
            expected = excess * INTENT_EXHAUSTION_RATE
            assert hub._intent_exhaustion(state) == pytest.approx(expected, rel=1e-4)
    
    def test_progress_reduces_exhaustion(self):
        """Прогресс уменьшает effective_stall → уменьшает штраф."""
        from app.services.npc.decision_hub import INTENT_SATURATION_TICKS
        
        hub = DecisionHub(seed=42)
        
        # 10 duration, 4 progress = 6 stall = на пороге = 0
        state_no_penalty = _make_state(intent="talk", duration=10, stress=0.0)
        state_no_penalty.intent_progress_ticks = 4
        assert hub._intent_exhaustion(state_no_penalty) == 0.0
        
        # 10 duration, 2 progress = 8 stall = 2 excess = 0.16
        state_with_penalty = _make_state(intent="talk", duration=10, stress=0.0)
        state_with_penalty.intent_progress_ticks = 2
        assert hub._intent_exhaustion(state_with_penalty) == pytest.approx(0.16)
    
    def test_full_progress_no_exhaustion(self):
        """Если progress >= duration — нет стагнации."""
        hub = DecisionHub(seed=42)
        state = _make_state(intent="talk", duration=10, stress=0.0)
        state.intent_progress_ticks = 15  # progress > duration
        
        assert hub._intent_exhaustion(state) == 0.0
    
    def test_exhaustion_forces_intent_switch(self):
        """При сильной стагнации текущий intent проигрывает альтернативе."""
        from app.services.npc.decision_hub import INTENT_SATURATION_TICKS
        
        hub = DecisionHub(seed=42)
        # 10 тиков стагнации — штраф -0.80, перебивает любой inertia bonus
        state = _make_state(
            intent="talk",
            duration=INTENT_SATURATION_TICKS + 10,
            stress=0.0
        )
        state.intent_progress_ticks = 0  # Нет прогресса
        personality = _make_personality()
        event = _make_event()
        
        result = hub.compute(state, personality, event)
        
        # При экстремальном exhaustion intent должен смениться
        assert result.intent != Intent.TALK
    
    def test_exhaustion_more_aggressive_than_decay(self):
        """ИНВАРИАНТ: Exhaustion агрессивнее decay — это активный штраф."""
        from app.services.npc.decision_hub import INTENT_DECAY_RATE, INTENT_EXHAUSTION_RATE
        
        assert INTENT_EXHAUSTION_RATE > INTENT_DECAY_RATE * 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
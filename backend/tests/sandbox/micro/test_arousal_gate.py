"""
Файл: backend/tests/sandbox/micro/test_arousal_gate.py
Назначение: Верификация ADR-O-142A — Arousal Gate (behavior transition gate).
            Проверяет missing wake edge: sleeping → idle при достаточном wake_pressure.
            НЕ проверяет consciousness (физиологическая ось, не затронута).
Зависимости: app.services.npc.life_engine
Основные сущности: TestArousalGate

Запуск: pytest backend/tests/sandbox/micro/test_arousal_gate.py -v
"""
import pytest
from app.services.npc.life_engine import LifeEngine
from app.services.scene_change import ChangeType


@pytest.fixture
def engine() -> LifeEngine:
    """Инстанс LifeEngine без внешних IO зависимостей."""
    return LifeEngine()


def _sleeping_npc(**overrides) -> dict:
    """Фабрика спящего NPC. Все значения по умолчанию — безопасный сон."""
    base = {
        "id": "test_npc",
        "routine": {"current": "sleeping"},
        "perceptual_kernel": {
            "threat_gradient": 0.0,
            "recent_directive": None,
        },
        "body_state": {
            "pain": 0.0,
            "fatigue": 50.0,  # средняя усталость → resistance=0.25
        },
    }
    # Глубокое слияние overrides
    for key, val in overrides.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            base[key].update(val)
        else:
            base[key] = val
    return base


# ── Основные сценарии Arousal Gate ──────────────────────────────────────────

class TestArousalGateWakeScenarios:
    """Проверка: спящий NPC пробуждается при достаточном wake_pressure."""

    def test_threat_wakes_sleeping_npc(self, engine):
        """Угроза (threat=0.8) пробуждает даже умеренно уставшего NPC."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.8, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 30.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert len(result) > 0, "Угроза должна будить спящего NPC"

    def test_pain_wakes_sleeping_npc(self, engine):
        """Боль (pain=80/100) пробуждает спящего NPC."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.0, "recent_directive": None},
            body_state={"pain": 80.0, "fatigue": 30.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert len(result) > 0, "Сильная боль должна будить NPC"

    def test_combined_threat_and_pain_wakes(self, engine):
        """Угроза + боль → гарантированное пробуждение даже уставшего NPC."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.5, "recent_directive": None},
            body_state={"pain": 50.0, "fatigue": 60.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert len(result) > 0, "Угроза + боль должны будить даже уставшего"


class TestArousalGateSleepScenarios:
    """Проверка: спящий NPC остаётся спать при недостаточном wake_pressure."""

    def test_no_stimuli_tired_npc_stays_asleep(self, engine):
        """Нет стимулов + усталость → NPC продолжает спать."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.0, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 50.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Нет стимулов — NPC должен спать"

    def test_low_threat_tired_npc_stays_asleep(self, engine):
        """Слабая угроза (threat=0.1) + усталость → NPC спит."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.1, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 50.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Слабая угроза не будит уставшего"


class TestArousalGateGuardConditions:
    """Проверка: gate НЕ применяется к не-спящим или парализованным NPC."""

    def test_working_npc_not_affected(self, engine):
        """NPC на работе — gate не применяется."""
        npc = _sleeping_npc(routine={"current": "working"})
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Gate не применяется к работающему NPC"

    def test_idle_npc_not_affected(self, engine):
        """NPC без активности — gate не применяется."""
        npc = _sleeping_npc(routine={"current": ""})
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Gate не применяется к бодрствующему NPC"

    def test_initiative_suppression_blocks_wake(self, engine):
        """Когнитивный паралич (initiative_suppression > 0.7) блокирует пробуждение,
        даже при высокой угрозе."""
        npc = _sleeping_npc(
            perceptual_kernel={
                "threat_gradient": 0.9,
                "recent_directive": None,
                "initiative_suppression": 0.8,
            },
        )
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Паралич воли блокирует пробуждение"

    def test_attention_capture_blocks_wake(self, engine):
        """Attention Capture (recent_directive.interrupts_routine=True) блокирует
        пробуждение — ADR-052: когнитивный захват замораживает поведение."""
        npc = _sleeping_npc(
            perceptual_kernel={
                "threat_gradient": 0.8,
                "recent_directive": {
                    "source": "player",
                    "salience": 0.85,
                    "interrupts_routine": True,
                },
            },
        )
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Attention Capture блокирует Arousal Gate"


class TestArousalGateSceneChanges:
    """Проверка: корректность генерируемых SceneChange объектов."""

    def test_wake_produces_activity_scene_change(self, engine):
        """Пробуждение генерирует SceneChange(field="activity")."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.8, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 20.0},
        )
        result = engine._arousal_gate(npc, tick=42)
        activity_changes = [ch for ch in result if ch.field == "activity"]
        assert len(activity_changes) == 1, "Ровно 1 SceneChange для activity"
        ch = activity_changes[0]
        assert ch.type == ChangeType.NPC_POSITION
        assert ch.value == ""  # "awake" НЕ вводится как состояние мира
        assert ch.cause == "arousal_gate"
        assert ch.tick == 42

    def test_wake_produces_visible_scene_change(self, engine):
        """Пробуждение делает NPC видимым (visible=True)."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.8, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 20.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        visible_changes = [ch for ch in result if ch.field == "visible"]
        assert len(visible_changes) == 1, "Ровно 1 SceneChange для visible"
        assert visible_changes[0].value is True

    def test_wake_clears_routine_current(self, engine):
        """Пробуждение очищает routine["current"] (transition to no-activity)."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.8, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 20.0},
        )
        engine._arousal_gate(npc, tick=1)
        assert npc["routine"]["current"] == "", "routine['current'] должен быть очищен"

    def test_no_wake_does_not_mutate_routine(self, engine):
        """Если NPC не пробуждён — routine не мутируется."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.0, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 50.0},
        )
        engine._arousal_gate(npc, tick=1)
        assert npc["routine"]["current"] == "sleeping", "routine не должен меняться"


class TestArousalGateResting:
    """Проверка: gate работает для 'resting' так же как для 'sleeping'."""

    def test_resting_npc_wakes_on_threat(self, engine):
        """Отдыхающий (resting) NPC пробуждается при угрозе."""
        npc = _sleeping_npc(
            routine={"current": "resting"},
            perceptual_kernel={"threat_gradient": 0.8, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 20.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert len(result) > 0, "Resting NPC должен пробуждаться при угрозе"


class TestArousalGateBoundary:
    """Проверка: поведение на точных границах порогов (защита от рефакторинга > → >=)."""

    def test_exact_equality_stays_asleep(self, engine):
        """wake_pressure == sleep_resistance → NPC остаётся спать.
        Строгий > (не >=) — фундаментальное свойство: равновесие = сон."""
        # fatigue=50 → resistance = 0.5*0.4 + 0.05 = 0.25
        # Нужно pressure = 0.25 → threat = 0.25/0.35 ≈ 0.714
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.714, "recent_directive": None},
            body_state={"pain": 0.0, "fatigue": 50.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Точное равенство pressure==resistance → NPC спит"

    def test_initiative_suppression_exactly_0_7_allows_wake(self, engine):
        """initiative_suppression = 0.7 (ровно порог) → пробуждение РАЗРЕШЕНО.
        Guard использует > 0.7, значит 0.7 ещё не блокирует."""
        npc = _sleeping_npc(
            perceptual_kernel={
                "threat_gradient": 0.8,
                "recent_directive": None,
                "initiative_suppression": 0.7,
            },
            body_state={"pain": 0.0, "fatigue": 20.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert len(result) > 0, "initiative_suppression=0.7 не блокирует (строгий >)"


class TestArousalGateMSOC:
    """Проверка: корректная нормализация шкал (ADR-094 MSOC)."""

    def test_pain_0_100_scale_correctly_treated(self, engine):
        """pain=50 (0-100 шкала) — не должен будить при низком threat.
        Проверяем что 50/100=0.5 не равен 50 (без нормализации)."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.0, "recent_directive": None},
            body_state={"pain": 50.0, "fatigue": 50.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        # pain_norm=0.5 → pressure = 0 + 0.5*0.25 = 0.125
        # resistance = 0.5*0.4 + 0.05 = 0.25
        # 0.125 < 0.25 → спит
        assert result == [], "pain=50/100 не должен будить сам по себе"

    def test_pain_alone_does_not_overcome_extreme_fatigue(self, engine):
        """pain=100 (нормализованный 1.0) НЕ будит при extreme fatigue=90.
        wake_pressure=0.25 < sleep_resistance=0.41 — усталость доминирует.
        Это корректно: боль — не единственный сигнал пробуждения."""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.0, "recent_directive": None},
            body_state={"pain": 100.0, "fatigue": 90.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert result == [], "Боль одна не должна будить при extreme усталости"

    def test_pain_plus_threat_overcomes_extreme_fatigue(self, engine):
        """pain=100 + threat=0.5 вместе будят даже уставшего NPC (fatigue=90).
        wake_pressure = 0.5*0.35 + 1.0*0.25 = 0.425 > sleep_resistance=0.41"""
        npc = _sleeping_npc(
            perceptual_kernel={"threat_gradient": 0.5, "recent_directive": None},
            body_state={"pain": 100.0, "fatigue": 90.0},
        )
        result = engine._arousal_gate(npc, tick=1)
        assert len(result) > 0, "Боль + угроза должны будить даже при fatigue=90"
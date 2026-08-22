"""
path: backend/tests/calibration_lab/test_m0_metrics.py
Назначение: M0-6 — юнит-тесты метрик на синтетических снапшотах
    (известные значения) + интеграционная проверка бандла в реальном
    прогоне (3 тика golden): 5 ключей, диапазоны, causal_depth=None.
Зависимости: app.services.calibration.metrics, experiment_runner.
Основные сущности: TestCharacterChange, TestDecisionMetrics,
    TestEventResponsiveness, TestBundleIntegration.

Запуск: cd backend; python -m pytest tests/calibration_lab/test_m0_metrics.py  -q --tb=line; cd ..
"""
from pathlib import Path
from typing import Any, Dict, List

from app.services.calibration.metrics import build_metrics_bundle
from app.services.calibration.metrics.character_change import CharacterChangeRate
from app.services.calibration.metrics.decision_diversity import DecisionDiversity
from app.services.calibration.metrics.event_responsiveness import (
    EventResponsiveness,
)
from app.services.calibration.metrics.loop_rate import LoopRate

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRESETS_DIR = _REPO_ROOT / "config" / "calibration" / "test_presets"


def _npc(
    npc_id: str,
    stress: float = 10.0,
    trust: float = 0.0,
    intent: "str | None" = None,
) -> Dict[str, Any]:
    return {
        "id": npc_id,
        "psyche": {
            "stress": stress,
            "identity_integrity": 0.9,
            "pressure_resistance": 0.0,
            "recent_failures": 0,
        },
        "social_stats": {"trust": trust, "fear_of_player": 0.0},
        "intent": intent,
    }


class TestCharacterChange:
    def test_constant_state_zero(self) -> None:
        metric = CharacterChangeRate()
        for tick in range(3):
            metric.update(tick, {"a": _npc("a")})
        assert metric.compute() == 0.0

    def test_known_delta(self) -> None:
        metric = CharacterChangeRate()
        metric.update(0, {"a": _npc("a", stress=0.0)})
        metric.update(1, {"a": _npc("a", stress=100.0)})
        # одно поле из 6 сдвинулось на 1.0 (нормализовано) → sqrt(1/6)
        import math

        assert abs(metric.compute() - math.sqrt(1 / 6)) < 1e-9


class TestDecisionMetrics:
    def _ev(self, records: list) -> dict:
        return {"count": len(records), "records": records}

    def test_diversity_constant_label(self) -> None:
        metric = DecisionDiversity()
        for tick in range(3):
            metric.update(
                tick, {}, self._ev([("npc_spoke", "a", "talk")])
            )
        assert abs(metric.compute() - 1 / 3) < 1e-9

    def test_diversity_ignores_non_decision_events(self) -> None:
        metric = DecisionDiversity()
        for tick in range(3):
            metric.update(
                tick, {}, self._ev([("npc_moved", "a", "npc_moved")])
            )
        assert metric.compute() is None

    def test_loop_rate_constant_is_one(self) -> None:
        metric = LoopRate()
        for tick in range(4):
            metric.update(tick, {}, self._ev([("npc_spoke", "a", "talk")]))
        assert metric.compute() == 1.0

    def test_loop_rate_alternating_is_zero(self) -> None:
        metric = LoopRate()
        for intent in ("talk", "warn", "talk", "warn"):
            metric.update(0, {}, self._ev([("npc_spoke", "a", intent)]))
        assert metric.compute() == 0.0


class TestEventResponsiveness:
    def _ev(self, records: list) -> dict:
        return {"count": len(records), "records": records}

    def test_no_events_none(self) -> None:
        metric = EventResponsiveness()
        for tick in range(3):
            metric.update(tick, {}, {"count": 0, "records": []})
        assert metric.compute() is None

    def test_event_then_decision_change_is_one(self) -> None:
        metric = EventResponsiveness()
        metric.update(0, {}, self._ev([("npc_spoke", "a", "talk")]))
        metric.update(1, {}, self._ev([("npc_spoke", "a", "warn")]))
        assert metric.compute() == 1.0


class TestBundleIntegration:
    def test_golden_run_produces_metrics(self) -> None:
        from app.services.calibration.experiment_runner import (
            ExperimentConfig,
            ExperimentRunner,
        )

        result = ExperimentRunner().run(
            ExperimentConfig(
                preset_path=str(_PRESETS_DIR / "enigma_golden.yaml"),
                duration_ticks=3,
            )
        )
        assert set(result.metrics) == {
            "character_change_rate",
            "decision_diversity",
            "loop_rate",
            "event_responsiveness",
            "causal_depth",
        }
        assert result.metrics["causal_depth"] is None  # DEBT-CAUSAL-DEPTH
        # character_change — данные есть всегда; диапазон обязателен.
        cc = result.metrics["character_change_rate"]
        assert cc is not None and 0.0 <= cc <= 1.0, f"cc={cc}"
        # diversity/loop: None = ни одного intent за сессию (легитимно
        # для idle-smoke: MIN_INTENT_SCORE может не достигаться без
        # событий). Диагностика для M0-7: если None сохранится на 150
        # тиках при живых диалогах — источник интентов ≠ npc["intent"]
        # в снапшоте загрузчика (DEBT-INTENT-SOURCE).
        # Решенческий канал жив: diversity требует хотя бы одну запись
        # (жёстко), loop_rate — хотя бы один МЕЖТИКОВЫЙ переход (в 3-тиковом
        # smoke записи одного NPC не обязаны пересекать границу тика —
        # валидность канала подтверждена 150-тиковым зондом: loop=1.0).
        dv = result.metrics["decision_diversity"]
        assert dv is not None, "decision_diversity=None — Tap/labels отвалились"
        assert 0.0 <= dv <= 1.0
        lr = result.metrics["loop_rate"]
        assert lr is None or 0.0 <= lr <= 1.0
        with_intents = [
            sum(1 for n in tick if n.get("intent") is not None)
            for tick in result.npc_captures
        ]
        print(f"[DIAG_M06] NPC с intent по тикам: {with_intents}")
        assert len(result.events_per_tick) == 3
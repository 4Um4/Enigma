"""
Файл: backend/tests/calibration_lab/test_m1_trust_intervention.py
Назначение: M1 / Задача 1 — HELP-вмешательство через InterventionEvent
    поднимает trust цели в RelationshipStore (SSOT) в offline-сессии
    лаборатории (M1-AC-301 в миниатюре).
Зависимости: app.services.calibration.experiment_runner (start/step/stop).
Основные сущности: ExperimentRunner, ExperimentConfig.
"""
from pathlib import Path

from app.core.config import BASE_DIR
from app.services.calibration.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
)

_PRESET = Path(BASE_DIR) / "config" / "calibration" / "test_presets" / "enigma_golden.yaml"


def test_help_intervention_raises_trust():
    """Тик 10: HELP maid_lusya -> trust(maid_lusya -> player) в SSOT > 0."""
    runner = ExperimentRunner()
    config = ExperimentConfig(preset_path=str(_PRESET), duration_ticks=300)
    runner.start(config)
    try:
        # get_all возвращает плоский граф с ключами "source→target"
        # (relationship_store.py:106). HELP пишет source=цель, target=actor.
        key = "maid_lusya→player"
        for _ in range(10):
            state = runner.step(1)
        trust_before = float(
            state.get("relationships", {}).get(key, {}).get("trust", 0.0)
        )
        state = runner.step(1)  # 11-й тик: исполняется HELP-вмешательство
        trust_after = float(
            state.get("relationships", {}).get(key, {}).get("trust", 0.0)
        )
        # Ожидаемый скачок ~ +20 x headroom (saturation, store:112-115).
        # Дельта-ассерт устойчив к стартовым значениям канона.
        assert trust_after > trust_before, (
            "HELP-вмешательство не изменило RelationshipStore: "
            f"before={trust_before} after={trust_after}"
        )
    finally:
        result = runner.stop()

    # N1-регрессия (M1): тик вмешательства обязан доходить до Фазы 10
    # без TICK_CRASH ('SimpleNamespace' object has no attribute
    # 'scene_state', player-ветка commit_phase).
    assert "error" not in result.statuses, (
        "Тики упали с ошибкой: "
        f"{[i + 1 for i, s in enumerate(result.statuses) if s == 'error']}"
    )
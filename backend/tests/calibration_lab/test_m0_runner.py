"""
path: backend/tests/calibration_lab/test_m0_runner.py
Назначение: M0-5b — smoke интеграции runner'а с РЕАЛЬНЫМ конвейером:
    короткая сессия enigma_golden (чистый старт, offline-mock), патч
    личности виден сквозь полный конвейер (материализация + W-IR),
    replay-детерминизм двух прогонов (M0-AC-004 seed-семантика).
    Маркирован slow-намерением: полные сборки GameLoop.
Зависимости: app.services.calibration.experiment_runner.
Основные сущности: TestExperimentRunnerSmoke.

Запуск: 
"""
from pathlib import Path

import pytest

from app.services.calibration.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRESETS_DIR = _REPO_ROOT / "config" / "calibration" / "test_presets"


def _config(ticks: int) -> ExperimentConfig:
    return ExperimentConfig(
        preset_path=str(_PRESETS_DIR / "enigma_golden.yaml"),
        campaign_id="Open_road",
        duration_ticks=ticks,
    )


@pytest.mark.slow
class TestExperimentRunnerSmoke:
    def test_short_session_golden(self) -> None:
        result = ExperimentRunner().run(_config(ticks=3))
        assert result.preset_id == "enigma_golden"
        assert result.ticks_executed == 3
        assert len(result.npc_captures) == 3
        assert all(len(tick) > 0 for tick in result.npc_captures)
        assert result.nan_count == 0
        assert "maid_lusya" in result.final_npc_state
        # Патч личности виден СКВОЗЬ РЕАЛЬНЫЙ КОНВЕЙЕР (материализация
        # → загрузчик → тики): ключевая ценность лаборатории.
        lusya = result.final_npc_state["maid_lusya"]
        assert lusya.get("psyche", {}).get("identity_rigidity") == 0.42

    def test_replay_deterministic_short(self) -> None:
        replay = ExperimentRunner().replay_determinism(_config(ticks=2))
        assert replay.deterministic, f"diff_fields={replay.diff_fields}"

    def test_settings_restored_after_run(self) -> None:
        from app.core.config import settings

        saves_before = settings.saves_dir
        env_before = settings.environment
        provider_before = settings.available_models["qwen_7b"].provider_type
        ExperimentRunner().run(_config(ticks=1))
        assert settings.saves_dir == saves_before
        assert settings.environment == env_before
        assert settings.available_models["qwen_7b"].provider_type == provider_before
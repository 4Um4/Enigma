"""
path: backend/tests/calibration_lab/test_m0_presets.py
Назначение: M0-4 — приёмочные тесты пресетов: три контрольных пресета
    (МАНЕКЕН / ХАОС / ЗОЛОТАЯ ОБЛАСТЬ) грузятся и валидируются против
    РЕАЛЬНОГО app.core.constants (защита от дрейфа имён); валидатор
    громко отклоняет [PLAN]-параметры, неизвестные имена, диапазонные
    и структурные нарушения.
Зависимости: pytest, app.services.calibration.preset_io,
    config/calibration/test_presets/.
Основные сущности: TestControlPresets, TestPresetValidator.

Запуск: cd backend; python -m pytest tests/calibration_lab  -q --tb=line; cd .
"""
import types
from pathlib import Path

import pytest

from app.core import constants as C
from app.services.calibration.preset_io import (
    CalibrationPresetError,
    load_preset,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRESETS_DIR = _REPO_ROOT / "config" / "calibration" / "test_presets"


def _preset_path(name: str) -> Path:
    return _PRESETS_DIR / f"{name}.yaml"


class TestControlPresets:
    """Контрольные пресеты M0 (План 2.4): гипотезы зон, проверяемые
    метриками в M0-AC-001..003. Здесь — структурная валидность."""

    def test_mannequin_preset_loads(self) -> None:
        p = load_preset(_preset_path("mannequin"))
        assert p.preset_id == "mannequin"
        assert p.constants["THETA_UP"] == 0.95
        assert p.constants["TRAIT_DECAY_RATE"] == 0.001
        assert p.npc_overrides["*"].psyche["identity_rigidity"] == 0.95

    def test_chaos_preset_loads(self) -> None:
        p = load_preset(_preset_path("chaos"))
        assert p.preset_id == "chaos"
        assert p.constants["SCORE_NOISE_RANGE"] == 0.40
        assert p.constants["THETA_UP"] == 0.05
        assert p.constants["RESENTMENT_BIAS_FACTOR"] == 0.80
        assert p.npc_overrides["*"].psyche["identity_rigidity"] == 0.05

    def test_enigma_golden_preset_loads(self) -> None:
        p = load_preset(_preset_path("enigma_golden"))
        assert p.preset_id == "enigma_golden"
        assert p.constants["THETA_UP"] == 0.55
        assert p.constants["THETA_DOWN"] == 0.20
        assert p.constants["DISTRUST_STRESS_BOOST"] == 9.0
        assert p.constants["RESENTMENT_BIAS_FACTOR"] == 0.20
        assert p.npc_overrides["*"].psyche["identity_rigidity"] == 0.42

    def test_all_preset_constants_exist_in_production_module(self) -> None:
        """Каждое имя константы каждого пресета существует в реальном
        app.core.constants (гарант: overlay падает громко на unknown)."""
        for name in ("mannequin", "chaos", "enigma_golden"):
            p = load_preset(_preset_path(name))
            missing = [c for c in p.constants if not hasattr(C, c)]
            assert missing == [], f"{name}: константы отсутствуют: {missing}"


class TestPresetValidator:
    """Строгий валидатор: тихий no-op в пресете = ложный эксперимент."""

    def _write(self, tmp_path: Path, content: str) -> Path:
        f = tmp_path / "preset.yaml"
        f.write_text(content, encoding="utf-8")
        return f

    def test_unknown_constant_rejected(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path, "meta:\n  preset_id: x\nconstants:\n  SCORE_NOISE_RANGE_X: 0.1\n"
        )
        with pytest.raises(CalibrationPresetError, match="нет в app.core.constants"):
            load_preset(f)

    def test_plan_param_rejected_with_distinct_message(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path, "meta:\n  preset_id: x\nconstants:\n  forgiveness_rate: 0.8\n"
        )
        with pytest.raises(CalibrationPresetError, match="ЗАПЛАНИРОВАН"):
            load_preset(f)

    def test_direct_observation_reliability_taboo_enforced(self, tmp_path: Path) -> None:
        """Ограничение ADR-O-360 срабатывает до проверки существования имени —
        точный диагноз независимо от того, где живёт константа."""
        f = self._write(
            tmp_path,
            "meta:\n  preset_id: x\nconstants:\n  DIRECT_OBSERVATION_RELIABILITY: 1.0\n",
        )
        with pytest.raises(CalibrationPresetError, match="ADR-O-360"):
            load_preset(f)

    def test_direct_observation_reliability_valid_with_fake_module(
        self, tmp_path: Path
    ) -> None:
        fake = types.ModuleType("fake_constants")
        fake.DIRECT_OBSERVATION_RELIABILITY = 0.9
        f = self._write(
            tmp_path,
            "meta:\n  preset_id: x\nconstants:\n  DIRECT_OBSERVATION_RELIABILITY: 0.9\n",
        )
        p = load_preset(f, constants_module=fake)
        assert p.constants["DIRECT_OBSERVATION_RELIABILITY"] == 0.9

    def test_identity_rigidity_out_of_range_rejected(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            "meta:\n  preset_id: x\nnpc_overrides:\n  \"*\":\n    psyche:\n"
            "      identity_rigidity: 1.5\n",
        )
        with pytest.raises(CalibrationPresetError, match="вне диапазона"):
            load_preset(f)

    def test_unknown_psyche_key_rejected(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            "meta:\n  preset_id: x\nnpc_overrides:\n  \"*\":\n    psyche:\n"
            "      identity_rigidty: 0.5\n",
        )
        with pytest.raises(CalibrationPresetError, match="не поддержан"):
            load_preset(f)

    def test_drives_must_sum_to_one(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            "meta:\n  preset_id: x\nnpc_overrides:\n  \"*\":\n    drives:\n"
            "      control: 0.4\n      significance: 0.2\n      fear: 0.2\n"
            "      desire: 0.1\n",
        )
        with pytest.raises(CalibrationPresetError, match="сумма должна быть 1.0"):
            load_preset(f)

    def test_valid_drives_accepted(self, tmp_path: Path) -> None:
        f = self._write(
            tmp_path,
            "meta:\n  preset_id: x\nnpc_overrides:\n  \"*\":\n    drives:\n"
            "      control: 0.25\n      significance: 0.25\n      fear: 0.25\n"
            "      desire: 0.25\n",
        )
        p = load_preset(f)
        assert p.npc_overrides["*"].drives is not None
        assert p.constants == {}

    def test_bool_value_rejected(self, tmp_path: Path) -> None:
        f = self._write(tmp_path, "meta:\n  preset_id: x\nconstants:\n  THETA_UP: true\n")
        with pytest.raises(CalibrationPresetError, match="ожидается число"):
            load_preset(f)

    def test_unknown_root_key_rejected(self, tmp_path: Path) -> None:
        f = self._write(tmp_path, "meta:\n  preset_id: x\nparametrs:\n  a: 1\n")
        with pytest.raises(CalibrationPresetError, match="неизвестные ключи корня"):
            load_preset(f)

    def test_empty_override_rejected(self, tmp_path: Path) -> None:
        f = self._write(tmp_path, "meta:\n  preset_id: x\nnpc_overrides:\n  \"*\": {}\n")
        with pytest.raises(CalibrationPresetError, match="пустой оверрайд"):
            load_preset(f)

    def test_missing_preset_file_loud_fail(self, tmp_path: Path) -> None:
        with pytest.raises(CalibrationPresetError, match="не найден"):
            load_preset(tmp_path / "missing.yaml")
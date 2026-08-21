"""
path: backend/tests/calibration_lab/test_m0_config_overlay.py 
Назначение: Приёмочные тесты границы overlay (M0-AC-006 + регрессия A1:
    патч from-import биндингов decision_hub + отсутствие cross-patch
    интернированных равных значений).
Зависимости: pytest, app.core.constants, app.services.npc.decision_hub,
    app.services.calibration.config_overlay.
Основные сущности: TestConfigOverlay.

Запуск: cd backend; python -m pytest tests/calibration_lab/test_m0_config_overlay.py -v; cd ..
"""
import pytest

from app.core import constants as C
# Импорт ДО overlay: гарантирует наличие from-import биндингов в sys.modules.
from app.services.npc import decision_hub  # noqa: F401
from app.services.calibration.config_overlay import (
    CalibrationOverlayError,
    audit_constant_bindings,
    overlay_active,
    overlay_constants,
)


def test_m0_ac006_overlay_patches_and_restores() -> None:
    """M0-AC-006: подмена видна в constants И в decision_hub; после выхода —
    полное восстановление (регрессия A1 — from-import биндинги)."""
    original = C.SCORE_NOISE_RANGE
    original_hub = decision_hub.SCORE_NOISE_RANGE
    with overlay_constants({"SCORE_NOISE_RANGE": 0.42}):
        assert C.SCORE_NOISE_RANGE == 0.42
        assert decision_hub.SCORE_NOISE_RANGE == 0.42
    assert C.SCORE_NOISE_RANGE == original
    assert decision_hub.SCORE_NOISE_RANGE == original_hub


def test_overlay_restores_on_exception() -> None:
    original = C.AFFECT_DECAY_BASE_RATE
    with pytest.raises(RuntimeError):
        with overlay_constants({"AFFECT_DECAY_BASE_RATE": 0.5}):
            raise RuntimeError("boom")
    assert C.AFFECT_DECAY_BASE_RATE == original


def test_nested_overlay_forbidden() -> None:
    with overlay_constants({"SCORE_NOISE_RANGE": 0.2}):
        with pytest.raises(CalibrationOverlayError, match="Вложенный"):
            with overlay_constants({"THETA_UP": 0.1}):
                pass
    assert C.THETA_UP == 0.60


def test_unknown_constant_loud_fail() -> None:
    with pytest.raises(CalibrationOverlayError, match="SCORE_NOISE_RANGE_X"):
        with overlay_constants({"SCORE_NOISE_RANGE_X": 1.0}):
            pass


def test_require_loaded_guard() -> None:
    with pytest.raises(CalibrationOverlayError, match="не загружены"):
        with overlay_constants(
            {"SCORE_NOISE_RANGE": 0.2},
            require_loaded=["app.services.calibration.__missing_guard__"],
        ):
            pass


def test_no_cross_patch_of_interned_equal_values() -> None:
    """0.15 у THREAT_AMPLIFICATION_FACTOR / MIN_INTENT_SCORE /
    COMMITMENT_BASE_THRESHOLD (возможно один объект): патч одного имени
    не должен менять остальные."""
    with overlay_constants({"MIN_INTENT_SCORE": 0.99}):
        assert C.MIN_INTENT_SCORE == 0.99
        assert C.THREAT_AMPLIFICATION_FACTOR == 0.15
        assert C.COMMITMENT_BASE_THRESHOLD == 0.15
    assert C.MIN_INTENT_SCORE == 0.15


def test_dict_constant_overlay_restores_identity() -> None:
    ref = C.PERCEPTION_RADIUS
    patched = dict(ref)
    patched["minor"] = 7.5
    with overlay_constants({"PERCEPTION_RADIUS": patched}):
        assert C.PERCEPTION_RADIUS["minor"] == 7.5
    assert C.PERCEPTION_RADIUS is ref


def test_overlay_active_flag() -> None:
    assert overlay_active() is False
    with overlay_constants({"SCORE_NOISE_RANGE": 0.3}):
        assert overlay_active() is True
    assert overlay_active() is False


def test_audit_constant_bindings_sees_consumers() -> None:
    modules = {module for module, _attr in audit_constant_bindings("SCORE_NOISE_RANGE")}
    assert "app.core.constants" in modules
    assert "app.services.npc.decision_hub" in modules
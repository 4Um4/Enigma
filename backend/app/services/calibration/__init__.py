"""
path: backend/app/services/calibration/__init__.py
Назначение: Пакет лаборатории калибровки психики ENIGMA (ADR-O-361).
    Надстройка над ядром: подмена параметров, запуск экспериментов,
    пассивное наблюдение, метрики. Ядро не модифицируется — доступ только
    через существующие контракты (TickOrchestrator.execute, EventBus).
Зависимости: app.core.constants (только config_overlay на текущем шаге).
Основные сущности: overlay_constants, CalibrationOverlayError.
"""
from app.services.calibration.config_overlay import (
    CalibrationOverlayError,
    audit_constant_bindings,
    overlay_active,
    overlay_constants,
)
from app.services.calibration.preset_io import (
    CalibrationPresetError,
    NpcOverride,
    Preset,
    load_preset,
)
from app.services.calibration.preset_materializer import (
    MaterializationError,
    MaterializedNpcConfig,
    materialize_preset,
)
from app.services.calibration.experiment_runner import (
    ExperimentConfig,
    ExperimentError,
    ExperimentResult,
    ExperimentRunner,
    ReplayResult,
)

__all__ = [
    "CalibrationOverlayError",
    "ExperimentConfig",
    "ExperimentError",
    "ExperimentResult",
    "ExperimentRunner",
    "CalibrationPresetError",
    "MaterializationError",
    "MaterializedNpcConfig",
    "NpcOverride",
    "Preset",
    "audit_constant_bindings",
    "load_preset",
    "materialize_preset",
    "ReplayResult",
    "overlay_active",
    "overlay_constants",
]
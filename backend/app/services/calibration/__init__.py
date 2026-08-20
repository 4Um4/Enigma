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

__all__ = [
    "CalibrationOverlayError",
    "audit_constant_bindings",
    "overlay_active",
    "overlay_constants",
]
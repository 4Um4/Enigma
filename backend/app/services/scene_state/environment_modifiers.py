"""
Назначение: R4.4 — производные модификаторы среды (light/noise/density/danger) из time_variant и типа локации. DEGOD S3 ITER1: байт-в-байт перенос из scene_state_manager.py (:149–188); поведение неизменно.
Зависимости: нет (pure, без импортов)
Основные сущности: _NOISE_MAP, _LIGHT_MAP, _TYPE_MODIFIERS, _derive_environment_modifiers
"""

_NOISE_MAP: dict[str, float] = {
    "silent": 0.0,
    "low": 0.2,
    "moderate": 0.5,
    "loud": 0.8,
}

_LIGHT_MAP: dict[str, float] = {
    "dark": 0.0,
    "torchlit": 0.2,
    "dim": 0.4,
    "natural": 0.7,
    "bright": 1.0,
}

# Базовая плотность и опасность по типу локации
_TYPE_MODIFIERS: dict[str, dict[str, float]] = {
    "dungeon": {"density": 0.6, "danger": 0.6},
    "market": {"density": 0.7, "danger": 0.1},
    "tavern": {"density": 0.3, "danger": 0.1},
    "gate": {"density": 0.2, "danger": 0.2},
    "inn": {"density": 0.1, "danger": 0.0},
}


def _derive_environment_modifiers(
    time_variant: dict,
    location_type: str,
) -> dict[str, float]:
    """
    R4.4: вычисляет environment_modifiers из time_variant и типа локации.
    Заменяет захардкоженные нули — LOS и sound_reach теперь работают реально.
    """
    base = _TYPE_MODIFIERS.get(location_type, {"density": 0.0, "danger": 0.0})
    return {
        "light": _LIGHT_MAP.get(time_variant.get("light_level", "dim"), 0.4),
        "noise": _NOISE_MAP.get(time_variant.get("noise_level", "low"), 0.2),
        "density": base["density"],
        "danger": base["danger"],
    }

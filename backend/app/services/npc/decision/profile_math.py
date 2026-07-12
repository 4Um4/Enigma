# backend/app/services/npc/decision/profile_math.py
"""
R2: Общая математика профилей личности.

Изолирует relationship_profile от risk_profile.
Если завтра изменится формула — меняется один файл.

Цель системы — не «реалистичная модель», а «модель, которая создаёт историю».
NPC должны иметь характерные диапазоны поведения (аттракторы),
а не равномерно-случайное распределение эмоций.

Инвариант: drive=NEUTRAL_DRIVE → multiplier=1.0 (обратная совместимость).
Достигается нормализацией: выход _shape_drive делится на _NEUTRAL_SHAPED.
"""

# ── Фундаментальные константы системы ──
NEUTRAL_DRIVE = 0.25  # Точка равновесия: при этом значении multiplier = 1.0
MIN_MULTIPLIER = 0.2  # Пол: даже drive=0.0 даёт 20% от полной реакции
GAME_NORMAL = 0.35  # Игровая нормаль: аттрактор, к которому тянутся drives
ATTRACTOR_STRENGTH = 0.25  # Сила притяжения к игровой нормали (0=нет, 1=полный)
POWER_ALPHA = 1.35  # Нелинейность: >1 = усилена разница с центром

# Clamp для отношений drive-множителей
RATIO_FLOOR = 0.3
RATIO_CEIL = 3.0


def _shape_drive(drive: float) -> float:
    """Применяет аттрактор + нелинейность к drive. Внутренняя функция.

    Фаза 1: Притяжение к игровой нормали (аттрактор характера)
    Фаза 2: Нелинейность pow — усилена разница с центром
    """
    # Аттрактор: подтягивает drive к GAME_NORMAL
    d = drive + (GAME_NORMAL - drive) * ATTRACTOR_STRENGTH

    # Нелинейность: power curve с центром на NEUTRAL_DRIVE
    if d > NEUTRAL_DRIVE:
        excess = (d - NEUTRAL_DRIVE) / (1.0 - NEUTRAL_DRIVE)
        return NEUTRAL_DRIVE + (1.0 - NEUTRAL_DRIVE) * (excess ** (1.0 / POWER_ALPHA))
    elif d < NEUTRAL_DRIVE:
        deficit = (NEUTRAL_DRIVE - d) / NEUTRAL_DRIVE
        return NEUTRAL_DRIVE * (1.0 - deficit**POWER_ALPHA)
    else:
        return NEUTRAL_DRIVE


# Предвычисленный якорь: _shape_drive(NEUTRAL_DRIVE) для нормализации
_NEUTRAL_SHAPED = _shape_drive(NEUTRAL_DRIVE)


def drive_multiplier(drive: float, min_mult: float = MIN_MULTIPLIER) -> float:
    """drive=0.25 → ровно 1.0 (обратная совместимость). С аттрактором и нелинейностью.

    Трёхфазная модель:
      1. Притяжение к игровой нормали (аттрактор характера)
      2. Нелинейность pow(d', α) — усилена разница с центром
      3. Нормализованная развёртка → multiplier (якорь на NEUTRAL_DRIVE)

    Ключевой инвариант: _shape_drive(NEUTRAL_DRIVE) / _NEUTRAL_SHAPED = 1.0
    Поэтому drive=0.25 → min_mult + 1.0 * (1.0 - min_mult) = 1.0

    Целевое распределение на симплексе:
      60–70% — стабильная зона личности (0.5–1.5)
      20–30% — зона напряжения (0.3–0.5, 1.5–3.0)
       5–10% — крайние нарративные пики (clamp)
    """
    d_shaped = _shape_drive(drive)
    # Нормализованная развёртка: d_shaped=0 → min_mult, d_shaped=_NEUTRAL_SHAPED → 1.0
    return min_mult + (d_shaped / _NEUTRAL_SHAPED) * (1.0 - min_mult)


def clamped_drive_ratio(
    numerator_drive: float,
    denominator_drive: float,
    min_bound: float = RATIO_FLOOR,
    max_bound: float = RATIO_CEIL,
) -> float:
    """Отношение двух drive-множителей с clamp.

    Защищает от взрыва (fear=0.6/control=0.1 → ≈4.0 → clamp → 3.0).
    """
    num = drive_multiplier(numerator_drive)
    den = drive_multiplier(denominator_drive)
    return max(min_bound, min(max_bound, num / max(den, 0.2)))

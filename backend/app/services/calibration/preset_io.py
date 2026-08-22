"""
path: backend/app/services/calibration/preset_io.py
Назначение: Загрузка и строгая валидация пресетов лаборатории калибровки
    (ADR-O-361). Пресет = ТОЛЬКО калибровочные параметры: глобальные
    константы (применяются overlay_constants) + per-NPC оверрайды
    (psyche/drives; материализуются патчем NPC JSON во временной копии
    кампании, M0-5). seed/сценарий/длительность — в ExperimentConfig.
    Строгость принципиальна: неизвестное имя, [PLAN]-параметр или выход
    за диапазон = громкий отказ загрузки — тихий no-op в пресете
    превращает эксперимент в ложь (L4, табу ADR-O-361).
Зависимости: yaml, app.core.constants (референс существования имён).
Основные сущности: Preset, NpcOverride, CalibrationPresetError, load_preset.
"""
from __future__ import annotations

import math
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from yaml import safe_load

from app.core import constants as _default_constants

# ── Реестры валидации ────────────────────────────────────────────────────

# [PLAN]-параметры (ТЗ 5.1/5.2): заявлены, но НЕ подключены к DecisionHub.
# В машинно-читаемых пресетах запрещены: молча игнорировать нельзя
# (фейк = табу ADR-O-361), поэтому — громкий отказ с диагнозом,
# отличимым от опечатки. UI-маркировка «слайдер отключён» — M1.
PLAN_PARAMS: frozenset = frozenset({
    "trust_growth_rate",
    "trust_decay_rate",
    "forgiveness_rate",
    "epistemic_drive",
    "core_orientation",
})

# Табу-ограничения значений чужих ADR. Проверяются ДО существования имени —
# дают точный диагноз нарушения ADR, а не «неизвестная константа».
_SPECIAL_CONSTRAINTS: dict[str, tuple[str, Callable[[float], bool]]] = {
    # ADR-O-360: прямое наблюдение надёжнее свидетельства, но НЕ абсолютно
    # (>= 1.0 превращает эпистемику в оракула).
    "DIRECT_OBSERVATION_RELIABILITY": ("< 1.0 (ADR-O-360)", lambda v: v < 1.0),
}

# Per-NPC psyche-параметры, поддержанные материализатором M0. Whitelist:
# опечатка ловится ЗДЕСЬ, а не тихим no-op в рантайме.
_PSYCHE_PARAMS: dict[str, tuple[float, float]] = {
    "identity_rigidity": (0.0, 1.0),
    "willpower": (0.0, 100.0),
    "breakpoint": (0.0, 100.0),
    "loyalty_true": (0.0, 100.0),
}

_DRIVES_KEYS: tuple[str, ...] = ("control", "significance", "fear", "desire")

_ROOT_KEYS: frozenset = frozenset({"meta", "constants", "npc_overrides"})
_META_KEYS: frozenset = frozenset({"preset_id", "description"})
_OVERRIDE_KEYS: frozenset = frozenset({"psyche", "drives"})


class CalibrationPresetError(RuntimeError):
    """Громкий отказ загрузки пресета: перечисляет ВСЕ найденные проблемы."""


@dataclass(frozen=True)
class NpcOverride:
    """Per-NPC оверрайд. Ключ "*" в Preset.npc_overrides = все NPC кампании."""

    psyche: dict[str, float] = field(default_factory=dict)
    drives: Optional[dict[str, float]] = None


@dataclass(frozen=True)
class Preset:
    """Валидированный пресет (только параметры).

    constants: {имя из app.core.constants: значение} — применяется
        overlay_constants() (identity-патч, ADR-O-361).
    npc_overrides: {npc_id | "*": NpcOverride} — материализуется патчем
        NPC JSON во временной копии кампании (без мутации NPCState).
    """

    preset_id: str
    description: str = ""
    constants: dict[str, float] = field(default_factory=dict)
    npc_overrides: dict[str, NpcOverride] = field(default_factory=dict)


def _is_number(value: Any) -> bool:
    # bool — подкласс int: True прошёл бы как 1.0. Исключаем явно.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_meta(raw: Any, errors: list[str]) -> tuple[str, str]:
    if raw is None:
        errors.append("отсутствует секция meta (preset_id обязателен)")
        return "", ""
    if not isinstance(raw, Mapping):
        errors.append("meta должен быть отображением")
        return "", ""
    unknown = [k for k in raw if k not in _META_KEYS]
    if unknown:
        errors.append(f"meta: неизвестные ключи {unknown} (разрешены {sorted(_META_KEYS)})")
    preset_id = raw.get("preset_id", "")
    if not isinstance(preset_id, str) or not preset_id.strip():
        errors.append("meta.preset_id: непустая строка обязательна")
        preset_id = ""
    description = raw.get("description", "")
    if not isinstance(description, str):
        errors.append("meta.description: ожидается строка")
        description = ""
    return preset_id, description


def _validate_constants(
    raw: Any,
    constants_module: types.ModuleType,
    errors: list[str],
) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        errors.append("constants должен быть отображением {имя: число}")
        return {}
    result: dict[str, float] = {}
    for name, value in raw.items():
        if not isinstance(name, str):
            errors.append(f"constants: ключ {name!r} — ожидается строка")
            continue
        if not _is_number(value):
            errors.append(f"constants.{name}: ожидается число, получено {value!r}")
            continue
        if name in PLAN_PARAMS:
            errors.append(
                f"constants.{name}: параметр ЗАПЛАНИРОВАН и не подключён (ТЗ 5.2) — в пресетах запрещён"
            )
            continue
        if name in _SPECIAL_CONSTRAINTS:
            rule, check = _SPECIAL_CONSTRAINTS[name]
            if not check(float(value)):
                errors.append(f"constants.{name}: нарушение {rule}, получено {value!r}")
                continue
        if not hasattr(constants_module, name):
            errors.append(
                f"constants.{name}: имени нет в app.core.constants — сверь имя "
                f"(пресет не может применять несуществующее)"
            )
            continue
        result[name] = float(value)
    return result


def _validate_psyche(raw: Any, errors: list[str], npc_key: str) -> dict[str, float]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        errors.append(f"npc_overrides.{npc_key}.psyche: ожидается отображение")
        return {}
    result: dict[str, float] = {}
    for key, value in raw.items():
        if key not in _PSYCHE_PARAMS:
            errors.append(
                f"npc_overrides.{npc_key}.psyche.{key}: не поддержан "
                f"(разрешены {sorted(_PSYCHE_PARAMS)})"
            )
            continue
        if not _is_number(value):
            errors.append(
                f"npc_overrides.{npc_key}.psyche.{key}: ожидается число, получено {value!r}"
            )
            continue
        lo, hi = _PSYCHE_PARAMS[key]
        if not (lo <= float(value) <= hi):
            errors.append(
                f"npc_overrides.{npc_key}.psyche.{key}: вне диапазона [{lo}, {hi}]: {value!r}"
            )
            continue
        result[key] = float(value)
    return result


def _validate_drives(
    raw: Any, errors: list[str], npc_key: str
) -> Optional[dict[str, float]]:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        errors.append(f"npc_overrides.{npc_key}.drives: ожидается отображение")
        return None
    extra = [k for k in raw if k not in _DRIVES_KEYS]
    missing = [k for k in _DRIVES_KEYS if k not in raw]
    if extra or missing:
        errors.append(
            f"npc_overrides.{npc_key}.drives: лишние {extra}, отсутствуют {missing} "
            f"(обязательны все {_DRIVES_KEYS})"
        )
        return None
    values: dict[str, float] = {}
    for key, value in raw.items():
        if not _is_number(value) or float(value) < 0.0:
            errors.append(
                f"npc_overrides.{npc_key}.drives.{key}: ожидается число >= 0, получено {value!r}"
            )
            return None
        values[key] = float(value)
    total = sum(values.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        # NPCPersonality сам падает при sum != 1.0 — здесь ранний диагноз.
        errors.append(
            f"npc_overrides.{npc_key}.drives: сумма должна быть 1.0, получено {total:.6f}"
        )
        return None
    return values


def _validate_npc_overrides(raw: Any, errors: list[str]) -> dict[str, NpcOverride]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        errors.append("npc_overrides должен быть отображением {npc_id | '*': {psyche, drives}}")
        return {}
    result: dict[str, NpcOverride] = {}
    for npc_key, entry in raw.items():
        if not isinstance(npc_key, str) or not npc_key.strip():
            errors.append(f"npc_overrides: ключ {npc_key!r} — ожидается npc_id или '*'")
            continue
        if not isinstance(entry, Mapping):
            errors.append(f"npc_overrides.{npc_key}: ожидается отображение")
            continue
        unknown = [k for k in entry if k not in _OVERRIDE_KEYS]
        if unknown:
            errors.append(
                f"npc_overrides.{npc_key}: неизвестные ключи {unknown} (разрешены psyche, drives)"
            )
            continue
        psyche = _validate_psyche(entry.get("psyche"), errors, npc_key)
        drives = _validate_drives(entry.get("drives"), errors, npc_key)
        if not psyche and drives is None:
            errors.append(f"npc_overrides.{npc_key}: пустой оверрайд — укажи psyche и/или drives")
            continue
        result[npc_key] = NpcOverride(psyche=psyche, drives=drives)
    return result


def load_preset(
    path: "str | Path",
    *,
    constants_module: Optional[types.ModuleType] = None,
) -> Preset:
    """Загружает и валидирует пресет. Любая проблема = CalibrationPresetError
    со списком ВСЕХ нарушений (не только первой попавшейся).

    constants_module: референс существования имён констант (инъекция для
    тестов); по умолчанию — реальный app.core.constants.
    """
    module = _default_constants if constants_module is None else constants_module
    preset_path = Path(path)
    if not preset_path.is_file():
        raise CalibrationPresetError(f"Пресет не найден: {preset_path}")
    try:
        raw = safe_load(preset_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CalibrationPresetError(f"YAML не разобран ({preset_path}): {exc}") from exc
    if not isinstance(raw, Mapping):
        raise CalibrationPresetError(f"Пресет должен быть YAML-отображением: {preset_path}")

    errors: list[str] = []
    unknown_root = [k for k in raw if k not in _ROOT_KEYS]
    if unknown_root:
        errors.append(
            f"неизвестные ключи корня {unknown_root} (разрешены {sorted(_ROOT_KEYS)})"
        )
    preset_id, description = _validate_meta(raw.get("meta"), errors)
    constants = _validate_constants(raw.get("constants"), module, errors)
    npc_overrides = _validate_npc_overrides(raw.get("npc_overrides"), errors)

    if errors:
        raise CalibrationPresetError(
            f"Пресет невалиден ({preset_path}):\n  - " + "\n  - ".join(errors)
        )
    return Preset(
        preset_id=preset_id,
        description=description,
        constants=constants,
        npc_overrides=npc_overrides,
    )
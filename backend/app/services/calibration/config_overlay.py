"""
path: backend/app/services/calibration/config_overlay.py
Назначение: Граница подмены констант ENIGMA для экспериментов лаборатории
    калибровки (ADR-O-361). Identity-патч: значение подменяется в
    app.core.constants И во всех загруженных модулях, связавших имя через
    from-import. Причина: потребители (decision_hub.py:27-43) биндят имена
    напрямую — патч только модуля констант молча не действует, и эксперимент
    калибрует фантом (тихая ложь результатов, нарушение L4).
    Verify на входе, полный откат с verify на выходе, запрет вложенности.
Зависимости: app.core.constants (чтение атрибутов), sys, types.
    ЗАПРЕЩЕНО: импортировать модули-потребители (сканируем sys.modules,
    не импортируем — иначе появятся новые биндинги ПОСЛЕ патча).
Основные сущности: CalibrationOverlayError, overlay_constants,
    overlay_active, audit_constant_bindings.

Контракт (ADR-O-361):
    1. Overlay вводится ТОЛЬКО после полной сборки движка. Страховка —
       require_loaded (модуль, импортированный позже, свяжет оригинал
       мимо overlay).
    2. Одновременные эксперименты — только изоляция процессами.
    3. Слепые зоны (документированы, автоматически не детектируются):
       a) алиасы from-import (import X as Y) — см. audit_constant_bindings;
       b) модули, импортированные после входа;
       c) константы, вычисленные из других при import-time
          (TRAIT_ACTIVATION_RATE) — патчуются напрямую по имени.
"""
from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Mapping, Sequence, Tuple

from app.core import constants as _constants

if TYPE_CHECKING:
    from app.services.calibration.profile import CalibrationProfile

# Флаг вложенности (ADR-O-361: вложенный overlay = архитектурная ошибка)
_ACTIVE: bool = False

# Запись одного патча: (модуль, имя атрибута, оригинал, новое значение)
_PatchEntry = Tuple[types.ModuleType, str, object, object]


class CalibrationOverlayError(RuntimeError):
    """Громкий отказ границы overlay.

    L4 (Silent Failure Prohibition): неизвестная константа, незагруженный
    обязательный модуль, вложенный overlay, неверифицируемая подмена или
    повреждение состояния при восстановлении обязаны падать громко —
    тиходеградирующий эксперимент хуже упавшего (урок S207 / DEBT-R5).
    """


def _find_bindings(original: object, name: str) -> List[Tuple[types.ModuleType, str]]:
    """Все загруженные модули, где атрибут `name` указывает НА ТОТ ЖЕ объект,
    что и оригинал константы (identity-матч по точному имени).

    Ловит from-import без алиаса, включая цепочки реэкспорта.
    НЕ ловит алиасы и независимые одноимённые определения с равным значением
    (другой объект) — это осознанная граница: равные интернированные литералы
    (0.15 у трёх констант) не должны давать cross-patch.
    """
    bindings: List[Tuple[types.ModuleType, str]] = []
    for module in list(sys.modules.values()):
        if not isinstance(module, types.ModuleType):
            continue
        module_vars = vars(module)
        if module_vars.get(name) is original:
            bindings.append((module, name))
    return bindings


def _restore(patch_log: List[_PatchEntry]) -> None:
    """Полное восстановление. Записи уникальны по (модуль, атрибут),
    поэтому порядок не важен."""
    for module, attr_name, original, _new_value in patch_log:
        setattr(module, attr_name, original)


def _verify_applied(patch_log: List[_PatchEntry]) -> None:
    """Верификация: каждый патч реально виден потребителю. Громкий FAIL."""
    problems: List[str] = []
    for module, attr_name, _original, expected in patch_log:
        current = getattr(module, attr_name, None)
        if current != expected:
            problems.append(
                f"{module.__name__}.{attr_name}: ожидалось {expected!r}, "
                f"фактически {current!r}"
            )
    if problems:
        raise CalibrationOverlayError(
            "overlay verify FAILED (подмена не видна потребителям — "
            "эксперимент недостоверен): " + "; ".join(problems)
        )


def _verify_restored(patch_log: List[_PatchEntry]) -> None:
    """Верификация отката: каждый биндинг указывает на оригинал (identity)."""
    problems: List[str] = []
    for module, attr_name, original, _new_value in patch_log:
        current = getattr(module, attr_name, None)
        if current is not original:
            problems.append(
                f"{module.__name__}.{attr_name}: ожидался оригинал "
                f"{original!r}, фактически {current!r}"
            )
    if problems:
        raise CalibrationOverlayError(
            "overlay restore FAILED (состояние констант повреждено): "
            + "; ".join(problems)
        )


@contextmanager
def overlay_constants(
    overrides: Mapping[str, Any],
    *,
    require_loaded: Sequence[str] = (),
) -> Iterator[None]:
    """Подменяет константы ENIGMA на время эксперимента (ADR-O-361).

    Args:
        overrides: {имя константы: новое значение}. Имя обязано существовать
            в app.core.constants — иначе громкий FAIL до любых изменений
            (опечатка в пресете должна ломать эксперимент громко).
        require_loaded: модули, обязанные быть загружены ДО входа —
            страховка от overlay до сборки движка.

    Raises:
        CalibrationOverlayError: вложенный overlay; незагруженный
            require_loaded-модуль; неизвестная константа; неверифицируемая
            подмена; повреждение при восстановлении.
    """
    global _ACTIVE
    if _ACTIVE:
        raise CalibrationOverlayError(
            "Вложенный overlay запрещён (ADR-O-361): одновременные "
            "эксперименты — только изоляция процессами."
        )
    missing = [name for name in require_loaded if name not in sys.modules]
    if missing:
        raise CalibrationOverlayError(
            "Overlay до сборки движка: модули не загружены, их from-import "
            f"биндинги не будут пойманы: {missing}. Сначала собери движок."
        )
    safe_overrides: Dict[str, Any] = dict(overrides)
    unknown = [n for n in safe_overrides if not hasattr(_constants, n)]
    if unknown:
        raise CalibrationOverlayError(
            f"Неизвестные константы app.core.constants: {unknown}. "
            "Имена пресетов сверяются с фактическим модулем (§13)."
        )

    _ACTIVE = True
    patch_log: List[_PatchEntry] = []
    try:
        try:
            for name, new_value in safe_overrides.items():
                original = getattr(_constants, name)
                for module, attr_name in _find_bindings(original, name):
                    patch_log.append((module, attr_name, original, new_value))
                    setattr(module, attr_name, new_value)
            _verify_applied(patch_log)
        except BaseException:
            # Отказ на пути патча — откатить частичное и упасть громко.
            _restore(patch_log)
            raise
        try:
            yield
        finally:
            _restore(patch_log)
            _verify_restored(patch_log)
    finally:
        _ACTIVE = False


def audit_constant_bindings(name: str) -> List[Tuple[str, str]]:
    """Диагностика: все (модуль, атрибут), чьё значение — тот же объект,
    что у константы `name` (identity, независимо от имени атрибута).

    Зачем: поиск алиасов from-import и цепочек реэкспорта перед overlay
    (слепая зона «a»). Для интернированных равных литералов покажет и
    одноимённые константы с тем же значением — это честная диагностика.
    """
    original = getattr(_constants, name)
    found: List[Tuple[str, str]] = []
    for module in list(sys.modules.values()):
        if not isinstance(module, types.ModuleType):
            continue
        for attr_name, value in list(vars(module).items()):
            if value is original:
                found.append((module.__name__, attr_name))
    return found


def overlay_active() -> bool:
    """Активен ли overlay (для runner'а и тестов)."""
    return _ACTIVE

@contextmanager
def overlay_module_attrs(
    patches: Sequence[Tuple[str, str, Any]],
    *,
    require_loaded: Sequence[str] = (),
) -> Iterator[None]:
    """Direct module attribute patching для non-core/constants калибровок.
    patches: [(module_path, attr_name, new_value), ...]
    Verify на входе, полный откат с verify на выходе — как overlay_constants."""
    missing = [p[0] for p in patches if p[0] not in sys.modules]
    if missing:
        raise CalibrationOverlayError(f"Модули не загружены: {missing}")
    patch_log: List[_PatchEntry] = []
    for module_path, attr_name, new_value in patches:
        module = sys.modules[module_path]
        original = getattr(module, attr_name)
        patch_log.append((module, attr_name, original, new_value))
        setattr(module, attr_name, new_value)
    _verify_applied(patch_log)
    try:
        yield
    finally:
        _restore(patch_log)
        _verify_restored(patch_log)


@contextmanager
def overlay_profile(
    profile: CalibrationProfile,
    *,
    require_loaded: Sequence[str] = (),
) -> Iterator[None]:
    """Единая точка: core/constants (identity overlay) + other modules (direct).
    Behavior-identical при profile=CalibrationProfile.default()."""
    core_overrides = {
        "COMMITMENT_BASE_THRESHOLD": profile.commitment_base_threshold,
        "COMMITMENT_K": profile.commitment_k,
        "COMMITMENT_BONUS_K": profile.commitment_bonus_k,
        "INTENT_DECAY_RATE": profile.intent_decay_rate,
        "INTENT_EXHAUSTION_RATE": profile.intent_exhaustion_rate,
        "INTENT_INERTIA_MAX_TICKS": profile.intent_inertia_max_ticks,
        "INTENT_INERTIA_WEIGHT": profile.intent_inertia_weight,
        "REACTIVE_URGENCY_THRESHOLD": profile.reactive_urgency_threshold,
        "IDLE_PRESSURE_ACCUM_RATE": profile.idle_pressure_accum_rate,
        "IDLE_PRESSURE_DECAY_RATE": profile.idle_pressure_decay_rate,
        "ATTACK_WINDUP_DURATION_TICKS": profile.attack_windup_duration_ticks,
        "STEAL_WINDUP_DURATION_TICKS": profile.steal_windup_duration_ticks,
    }
    module_patches = [
        ("app.services.economy.opportunity_engine", "W_ATTENTION", profile.opp_w_attention),
        ("app.services.economy.opportunity_engine", "W_DISTANCE", profile.opp_w_distance),
        ("app.services.economy.opportunity_engine", "W_WEAPON", profile.opp_w_weapon),
        ("app.services.economy.opportunity_engine", "W_ALLIES", profile.opp_w_allies),
        ("app.services.economy.opportunity_engine", "OPPORTUNITY_THRESHOLD", profile.opp_threshold),
        ("app.services.economy.opportunity_engine", "MAX_DISTANCE_METERS", profile.opp_max_distance_m),
        ("app.services.economy.opportunity_engine", "MAX_ALLY_COUNT", profile.opp_max_ally_count),
        ("app.services.events.observation_subscriber", "_OBSERVATION_SIGHT_RADIUS", profile.observation_sight_radius),
        ("app.services.events.claim_event_subscriber", "HEARING_RADIUS", profile.hearing_radius),
        ("app.domain.constants", "_DEFAULT_ACTION_RADIUS", profile.default_action_radius),
        ("app.services.player_cognition.action_consequence_compiler", "_ACCUSE_CONFIDENCE_THRESHOLD", profile.accuse_confidence_threshold),
        ("app.services.npc.trust_based_reliability_provider", "_ENEMY_TRUST_THRESHOLD", profile.enemy_trust_threshold),
        ("app.services.npc.trust_based_reliability_provider", "_UNKNOWN_SOURCE_TRUST", profile.unknown_source_trust),
        ("app.services.npc.trust_based_reliability_provider", "DIRECT_OBSERVATION_RELIABILITY", profile.direct_observation_reliability),
        # Phase 2: dialogue_queue MAX_PENDING_TASKS/MAX_RATE_PER_MINUTE — class attrs,
        # need extraction to module-level first (same pattern as 7 extractions)
        ("app.domain.vital_state", "_CONSCIOUSNESS_THRESHOLD", profile.consciousness_threshold),
        ("app.domain.vital_state", "_PAIN_INCAPACITATED", profile.pain_incapacitated),
        ("app.domain.vital_state", "_SHOCK_INCAPACITATED", profile.shock_incapacitated),
    ]
    with overlay_constants(core_overrides, require_loaded=require_loaded):
        with overlay_module_attrs(module_patches):
            yield
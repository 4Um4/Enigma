"""
path: /project/backend/app/domain/arbitration.py
Назначение: Step 3.2 Etap A — доменные контракты BodyArbiter.
    Разделяет Compatibility, Arbitration, Authorization, Execution.
    НЕ содержит алгоритмов разрешения конфликтов или порогов поведения.
    Все сущности — frozen dataclasses / enums, domain-neutral.
Зависимости: stdlib (dataclasses, enum, typing)
Основные сущности: ArbitrationVerdict, ArbitrationResult, PhysicalEffectProfile,
                   ResistanceAssessment, ResistanceOutcome, ResistanceBehavior,
                   DerivedPhysicalIntent, EffectState, CompatibilityClass,
                   check_compatibility
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

# ── Compatibility ──────────────────────────────────────────────────


class CompatibilityClass(Enum):
    """Результат проверки совместимости двух намерений."""
    COMPATIBLE = "compatible"        # Разные ресурсы тела — оба могут исполняться
    CONFLICT = "conflict"            # Один ресурс тела — конфликт
    CONDITIONAL = "conditional"      # Зависит от состояния тела/мира
    UNKNOWN = "unknown"              # Недостаточно данных для классификации


@dataclass(frozen=True)
class PhysicalEffectProfile:
    """Описание физического эффекта намерения на тело.

    Не универсальная физическая симуляция. Конкретные ограничения,
    проверяемые BodyArbiter для совместимости.

    is_internal=True означает, что намерение не требует тела
    (внутренний диалог, размышление) — всегда COMPATIBLE.
    """
    requires_movement: bool = False       # Намерение требует движения тела
    requires_stop: bool = False           # Намерение требует неподвижности
    requires_hands: bool = False          # Намерение требует рук
    requires_voice: bool = False          # Намерение требует голоса
    target_position: Optional[Tuple[float, float]] = None  # Куда направлено
    requires_proximity: bool = False      # Требует близости к цели
    duration_ticks: int = 1               # Сколько тиков занимает (1=мгновенное)
    is_internal: bool = False             # Внутреннее (не требует тела)


def _profile_from_intent(
    action: str,
    target: Optional[str] = None,
) -> PhysicalEffectProfile:
    """Строит PhysicalEffectProfile из action и target.

    Mapping основан на существующем Intent enum (npc_state.py:105).
    НЕ вводит новые типы действий. UNKNOWN intent → is_internal=False,
    все requires_* = False → UNKNOWN compatibility.
    """
    _action = (action or "").lower().strip()

    # Движение (направление тела в пространстве)
    if _action in ("approach", "flee", "move", "stealth"):
        return PhysicalEffectProfile(
            requires_movement=True,
            requires_stop=False,
            requires_hands=False,
            requires_voice=False,
            target_position=None,  # Spatial resolution — отдельный шаг
            requires_proximity=False,
            duration_ticks=1,
            is_internal=False,
        )

    # Атака (требует рук и остановки)
    if _action in ("attack", "steal"):
        return PhysicalEffectProfile(
            requires_movement=False,
            requires_stop=True,
            requires_hands=True,
            requires_voice=False,
            target_position=None,
            requires_proximity=True,
            duration_ticks=1,
            is_internal=False,
        )

    # Речь (требует голоса и остановки)
    if _action in ("talk", "warn", "intimidate", "trade", "offer_job", "request_service"):
        return PhysicalEffectProfile(
            requires_movement=False,
            requires_stop=False,  # Голос совместим с движением (ноги + голос)
            requires_hands=False,
            requires_voice=True,
            target_position=None,
            requires_proximity=False,
            duration_ticks=1,
            is_internal=False,
        )

    # Наблюдение (не требует ресурсов, совместимо)
    if _action in ("observe", "idle", "explain"):
        return PhysicalEffectProfile(
            requires_movement=False,
            requires_stop=False,
            requires_hands=False,
            requires_voice=False,
            target_position=None,
            requires_proximity=False,
            duration_ticks=1,
            is_internal=False,
        )

    # Внутренний диалог (не требует тела)
    if _action in ("internal_dialogue", "think"):
        return PhysicalEffectProfile(
            requires_movement=False,
            requires_stop=False,
            requires_hands=False,
            requires_voice=False,
            target_position=None,
            requires_proximity=False,
            duration_ticks=1,
            is_internal=True,
        )

    # Звать на помощь
    if _action in ("call_for_help", "report", "spread_rumor", "seek_ally"):
        return PhysicalEffectProfile(
            requires_movement=False,
            requires_stop=True,
            requires_hands=False,
            requires_voice=True,
            target_position=None,
            requires_proximity=False,
            duration_ticks=1,
            is_internal=False,
        )

    # Смена роли
    if _action == "change_role":
        return PhysicalEffectProfile(
            requires_movement=False,
            requires_stop=True,
            requires_hands=False,
            requires_voice=False,
            target_position=None,
            requires_proximity=False,
            duration_ticks=1,
            is_internal=False,
        )

    # UNKNOWN — недостаточно данных
    return PhysicalEffectProfile(
        requires_movement=False,
        requires_stop=False,
        requires_hands=False,
        requires_voice=False,
        target_position=None,
        requires_proximity=False,
        duration_ticks=1,
        is_internal=False,
    )


def check_compatibility(
    player_action: Optional[str],
    avatar_action: Optional[str],
    player_target: Optional[str] = None,
    avatar_target: Optional[str] = None,
) -> CompatibilityClass:
    """Проверяет физическую совместимость двух намерений.

    Возвращает CompatibilityClass:
      - COMPATIBLE: разные ресурсы тела
      - CONFLICT: один ресурс тела
      - CONDITIONAL: зависит от состояния тела/мира
      - UNKNOWN: недостаточно данных

    НЕ выбирает победителя. НЕ разрешает конфликт.
    Только классифицирует.
    """
    # Если одного намерения нет — конфликта нет
    if player_action is None and avatar_action is None:
        return CompatibilityClass.UNKNOWN
    if player_action is None or avatar_action is None:
        return CompatibilityClass.COMPATIBLE  # Одно намерение — нет конфликта

    player_profile = _profile_from_intent(player_action, player_target)
    avatar_profile = _profile_from_intent(avatar_action, avatar_target)

    # Внутреннее намерение — всегда COMPATIBLE
    if player_profile.is_internal or avatar_profile.is_internal:
        return CompatibilityClass.COMPATIBLE

    # Если оба профиля пустые (UNKNOWN intent) — UNKNOWN
    if (
        not player_profile.requires_movement
        and not player_profile.requires_stop
        and not player_profile.requires_hands
        and not player_profile.requires_voice
        and not avatar_profile.requires_movement
        and not avatar_profile.requires_stop
        and not avatar_profile.requires_hands
        and not avatar_profile.requires_voice
    ):
        return CompatibilityClass.UNKNOWN

    # Движение в разных направлениях — CONFLICT
    if player_profile.requires_movement and avatar_profile.requires_movement:
        # Если target совпадает — COMPATIBLE (оба идут к одной цели)
        if player_target is not None and avatar_target is not None:
            if player_target == avatar_target:
                return CompatibilityClass.COMPATIBLE
        return CompatibilityClass.CONFLICT

    # Движение + остановка — CONFLICT
    if player_profile.requires_movement and avatar_profile.requires_stop:
        return CompatibilityClass.CONFLICT
    if player_profile.requires_stop and avatar_profile.requires_movement:
        return CompatibilityClass.CONFLICT

    # Две руки — CONFLICT, если target различается
    if player_profile.requires_hands and avatar_profile.requires_hands:
        if player_target is not None and avatar_target is not None:
            if player_target == avatar_target:
                return CompatibilityClass.COMPATIBLE
        return CompatibilityClass.CONFLICT

    # Два голоса — CONFLICT
    if player_profile.requires_voice and avatar_profile.requires_voice:
        # Если target совпадает — COMPATIBLE (оба говорят одному слушателю)
        if player_target is not None and avatar_target is not None:
            if player_target == avatar_target:
                return CompatibilityClass.COMPATIBLE
        return CompatibilityClass.CONFLICT

    # Проксимность к разным целям — CONDITIONAL
    if player_profile.requires_proximity and avatar_profile.requires_proximity:
        if player_target is not None and avatar_target is not None:
            if player_target != avatar_target:
                return CompatibilityClass.CONDITIONAL

    # Составные действия (duration_ticks > 1) — CONDITIONAL
    if player_profile.duration_ticks > 1 or avatar_profile.duration_ticks > 1:
        return CompatibilityClass.CONDITIONAL

    # Если ресурсы не пересекаются — COMPATIBLE
    return CompatibilityClass.COMPATIBLE


# ── Arbitration ────────────────────────────────────────────────────


class ArbitrationVerdict(Enum):
    """Тип разрешения конфликта. НЕ победитель."""
    NO_CONFLICT = "no_conflict"               # Нет конфликта (одно намерение или COMPATIBLE)
    RESOLVE_RESISTANCE = "resolve_resistance"  # Обычное сопротивление (режим B)
    RESOLVE_STRUGGLE = "resolve_struggle"      # Борьба за контроль (режим C, future)
    DEFER_BOTH = "defer_both"                  # Отложить оба (CONDITIONAL)
    FAIL_BOTH = "fail_both"                    # Отклонить оба (невозможно/UNKNOWN)


@dataclass(frozen=True)
class ArbitrationResult:
    """Результат арбитража. НЕ содержит победителя.

    Победитель определяется отдельным механизмом разрешения
    (сопротивление или борьба), не BodyArbiter.
    """
    verdict: ArbitrationVerdict
    player_intent_id: Optional[str]
    avatar_intent_id: Optional[str]
    compatibility_class: CompatibilityClass
    conflict_type: Optional[str]  # B (resistance) / C (struggle) / D (counter) / F (impossible) / G (interrupt)
    reason: str
    tick: int


# ── Authorization ──────────────────────────────────────────────────


class EffectState(Enum):
    """Состояние конкретного эффекта намерения."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


# ── Resistance (режим B) ───────────────────────────────────────────


class ResistanceBehavior(Enum):
    """Тип поведения Avatar при сопротивлении.

    НЕ предопределён алгоритмом. Выбор поведения — отдельная
    ответственность, калибруемая через существующие характеристики.
    """
    RESIST_PHYSICAL = "resist_physical"
    YIELD = "yield"
    NEGOTIATE = "negotiate"
    SELF_HARM = "self_harm"
    ESCALATE = "escalate"
    NO_DIALOGUE = "no_dialogue"


@dataclass(frozen=True)
class ResistanceAssessment:
    """Оценка сопротивления — четыре независимые оси.

    Значения вычисляются из существующих полей NPCState/Desire.
    НЕ сравниваются с порогами в коде. Передаются в калибровку.
    """
    desire_strength: float         # Из Desire.urgency
    willingness_to_resist: float    # Из psyche (willpower) + body_state (stress, fatigue)
    decision_to_struggle: float     # Из identity_integrity + история REJECTED
    physical_capability: float      # Из body_state (fatigue, pain, shock, sleep)


@dataclass(frozen=True)
class ResistanceOutcome:
    """Исход сопротивления. НЕ содержит победителя."""
    behavior: ResistanceBehavior
    avatar_intent_id: str
    player_intent_id: str
    assessment: ResistanceAssessment
    reason: str
    tick: int


# ── Derived Physical Intent ────────────────────────────────────────


@dataclass(frozen=True)
class DerivedPhysicalIntent:
    """Производное физическое намерение от Resistance Outcome.

    Связь с исходным Avatar Intent сохраняется через source_intent_id.
    Владелец — UUID-A (Avatar consciousness). Тело — UUID-B (общее).
    """
    derived_id: str               # Детерминированный ID
    source_intent_id: str          # intent_id породившего Avatar Intent
    owner: str                     # UUID-A (Avatar consciousness)
    body_id: str                   # UUID-B (shared body)
    derived_action: str            # "self_harm" / "resist_physical" / "redirect_movement"
    physical_effect: str           # "body_damage" / "movement_redirect" / "none"
    formed_tick: int

# backend/app/services/npc/resolution_engine.py
"""
ResolutionLayer — стохастическое разрешение намерений NPC.

Цепочка:
  DecisionHub.compute() → DecisionResult (expected_success)
       ↓
  ResolutionEngine.resolve() → ResolutionOutcome
       ↓
  StateApplicator.apply() (с учётом gap)

Принципы (из roadmap):
  - Кубик НЕ принимает решение — он фиксирует отклонение от ожидания
  - NPC учатся от gap = actual - expected, а не от результата
  - Нет 100% и 0%: clamp(0.05, 0.95)
  - Подготовка важнее броска: bias смещает, но не отменяет случайность
  - RNG не двойной: DecisionHub работает без noise при активном ResolutionEngine
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from app.services.npc.npc_state import EmotionTag, NPCPersonality, NPCState


# ─────────────────────────────────────────────────────────────────────────────
# Константы
# ─────────────────────────────────────────────────────────────────────────────

# Доля броска кубика в итоге: 65% хаос, 35% состояние системы
DICE_WEIGHT: float = 0.65
BIAS_WEIGHT: float = 0.35

# Кубик d20 → нормализация в [0..1]
D20_SIDES: int = 20

# Жёсткие границы — никогда 0% или 100%
OUTCOME_FLOOR:   float = 0.05
OUTCOME_CEILING: float = 0.95

# Порог сюрприза — выше → эмоциональная реакция
SURPRISE_THRESHOLD: float = 0.25

# Порог стресса для режима отчаяния — NPC действует вопреки шансам
DESPERATION_STRESS: float = 85.0


# ─────────────────────────────────────────────────────────────────────────────
# Таблица исходов (градиент, не бинарно)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OutcomeBand:
    """Диапазон final_value → текстовый и числовой исход."""
    label:        str    # для логов и VerbalizationContext
    success_weight: float  # 0.0 = полный провал, 1.0 = полный успех


# Диапазоны из roadmap: [low, high) → исход
_OUTCOME_BANDS: Tuple[Tuple[float, float, OutcomeBand], ...] = (
    (0.00, 0.05, OutcomeBand("critical_failure",   0.0)),
    (0.05, 0.25, OutcomeBand("failure",             0.1)),
    (0.25, 0.50, OutcomeBand("partial_negative",    0.3)),
    (0.50, 0.75, OutcomeBand("partial_positive",    0.7)),
    (0.75, 0.95, OutcomeBand("success",             0.9)),
    (0.95, 1.01, OutcomeBand("critical_success",    1.0)),
)


def _resolve_band(final_value: float) -> OutcomeBand:
    for lo, hi, band in _OUTCOME_BANDS:
        if lo <= final_value < hi:
            return band
    return _OUTCOME_BANDS[-1][2]  # ceiling


# ─────────────────────────────────────────────────────────────────────────────
# ResolutionOutcome — результат броска
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResolutionOutcome:
    """
    Результат ResolutionEngine.resolve().
    StateApplicator читает gap для обучения.
    VerbalizationContext получает outcome_label и surprise.
    """
    final_value:    float          # 0.05–0.95
    outcome_band:   OutcomeBand
    dice_roll:      int            # сырой бросок d20 (1–20) — для UI
    bias:           float          # суммарный bias до броска

    # Обучение NPC: разница ожидание vs реальность
    expected_success: float
    actual_success:   float        # = outcome_band.success_weight
    gap:              float        # actual - expected: < 0 → шок, > 0 → облегчение

    # Эмоциональная реакция на сюрприз
    surprise:         float        # |gap|
    surprise_emotion: Optional[str] = None   # "shocked", "relieved", "frustrated", None

    # Трейс для R4.2 калибровки
    trace: Dict[str, float] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.outcome_band.success_weight >= 0.7

    @property
    def is_critical(self) -> bool:
        return self.outcome_band.label in ("critical_success", "critical_failure")


# ─────────────────────────────────────────────────────────────────────────────
# ResolutionEngine
# ─────────────────────────────────────────────────────────────────────────────

class ResolutionEngine:
    """
    Стохастическое разрешение: кубик + bias → final_value → gap → обучение.

    Формула:
      roll  = d20 → normalized [0..1]
      bias  = stat_mod + context_mod + affinity_mod + npc_state_mod
      final = clamp(roll * 0.65 + bias * 0.35, 0.05, 0.95)

    Не имеет состояния. Не мутирует NPCState. Только возвращает ResolutionOutcome.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        # seed per-session — воспроизводимость при отладке
        self._rng = random.Random(seed)

    def resolve(
        self,
        state:            NPCState,
        personality:      NPCPersonality,
        expected_success: float,
        context_modifier: float = 0.0,
    ) -> ResolutionOutcome:
        """
        Главный метод.

        state:            текущий NPCState после DecisionHub
        personality:      NPCPersonality (static)
        expected_success: из DecisionResult.expected_success
        context_modifier: подготовка игрока, окружение, скрытность (+/-)
        """
        # ── Бросок d20 ────────────────────────────────────────────────────────
        raw_roll  = self._rng.randint(1, D20_SIDES)
        normalized = (raw_roll - 1) / (D20_SIDES - 1)   # → [0..1]

        # ── Bias — суммарное смещение от состояния системы ────────────────────
        bias = self._compute_bias(state, personality, context_modifier)

        # ── Итоговое значение ─────────────────────────────────────────────────
        raw_final = normalized * DICE_WEIGHT + bias * BIAS_WEIGHT
        final     = round(max(OUTCOME_FLOOR, min(OUTCOME_CEILING, raw_final)), 4)

        # ── Исход ─────────────────────────────────────────────────────────────
        band          = _resolve_band(final)
        actual_success = band.success_weight
        gap            = round(actual_success - expected_success, 4)
        surprise       = round(abs(gap), 4)
        surprise_emotion = self._compute_surprise_emotion(
            gap, surprise, personality
        )

        return ResolutionOutcome(
            final_value      = final,
            outcome_band     = band,
            dice_roll        = raw_roll,
            bias             = round(bias, 4),
            expected_success = round(expected_success, 4),
            actual_success   = actual_success,
            gap              = gap,
            surprise         = surprise,
            surprise_emotion = surprise_emotion,
            trace            = {
                "raw_roll":         raw_roll,
                "normalized":       round(normalized, 4),
                "bias":             round(bias, 4),
                "raw_final":        round(raw_final, 4),
                "final":            final,
                "outcome":          band.label,
                "gap":              gap,
                "surprise":         surprise,
            },
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Bias computation
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_bias(
        self,
        state:            NPCState,
        personality:      NPCPersonality,
        context_modifier: float,
    ) -> float:
        """
        bias = stat_modifier + calibration_bias + npc_state_modifier + context_modifier
        Суммарный bias: ограничивается [-0.5, +0.5].
        """
        # stat_modifier: drives дают смещение к успеху/провалу
        stat_mod = self._stat_modifier(personality)

        # calibration_bias: характер NPC — важняк завышает шансы, трус занижает
        calib = self._calibration_bias(personality)

        # npc_state_modifier: стресс и воля влияют на исполнение
        state_mod = self._npc_state_modifier(state)

        # context_modifier: подготовка игрока передаётся снаружи
        raw = stat_mod + calib + state_mod + context_modifier
        return max(-0.5, min(0.5, raw))

    def _stat_modifier(self, personality: NPCPersonality) -> float:
        """
        drives_base влияют на базовую эффективность действий.
        control → структурный подход → +0.1
        fear    → нерешительность → -0.1
        """
        drives   = personality.drives_base
        dominant = max(drives, key=drives.get)
        modifiers = {
            "control":      +0.10,
            "significance": +0.05,
            "desire":        0.00,
            "fear":         -0.10,
        }
        return modifiers.get(dominant, 0.0)

    def _calibration_bias(self, personality: NPCPersonality) -> float:
        """
        Личная точность прогнозов NPC.
        Высокий control → оптимист: завышает expected, рискует.
        Высокий fear → пессимист: занижает expected, осторожен.
        """
        control = personality.drives_base.get("control", 0.25)
        fear    = personality.drives_base.get("fear", 0.25)
        # Оптимизм/пессимизм — разница двух доминирующих сил
        return round((control - fear) * 0.3, 4)

    def _npc_state_modifier(self, state: NPCState) -> float:
        """
        Текущее состояние NPC влияет на качество исполнения.
        Высокий стресс: мешает концентрации → штраф.
        Режим отчаяния (stress > 85): NPC действует на адреналине — нейтрально.
        """
        stress = state.stress

        # Режим отчаяния: адреналин компенсирует панику
        if stress >= DESPERATION_STRESS:
            return 0.0

        # Нормальный стресс: снижает эффективность пропорционально
        stress_penalty = -(stress / 100.0) * 0.2
        return round(stress_penalty, 4)

    # ─────────────────────────────────────────────────────────────────────────
    # Surprise emotion
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_surprise_emotion(
        self,
        gap:         float,
        surprise:    float,
        personality: NPCPersonality,
    ) -> Optional[str]:
        """
        Эмоциональная реакция на расхождение ожидания и реальности.
        Только при значительном сюрпризе (> SURPRISE_THRESHOLD).
        Личность влияет на интерпретацию: гордый шокирован провалом, амбициозный торжествует победой.
        """
        if surprise <= SURPRISE_THRESHOLD:
            return None

        drives   = personality.drives_base
        dominant = max(drives, key=drives.get)

        if gap < 0:
            # Ожидал успеха — получил провал
            if dominant == "significance":
                return "devastated"    # гордость уязвлена
            elif dominant == "control":
                return "frustrated"    # потеря контроля
            else:
                return "shocked"

        else:
            # Ожидал провала — получил успех
            if dominant == "significance":
                return "triumphant"    # подтверждение величия
            elif dominant == "desire":
                return "elated"        # жажда реализовалась
            else:
                return "relieved"


# ─────────────────────────────────────────────────────────────────────────────
# Gap → StateDeltas (адаптация NPC после разрешения)
# ─────────────────────────────────────────────────────────────────────────────

def apply_gap_learning(
    outcome:      ResolutionOutcome,
    state:        NPCState,
    learning_rate: float = 0.1,
) -> Dict[str, float]:
    """
    Конвертирует gap в дельты для StateApplicator.
    Вызывается после resolve() — передаётся в StateDeltas.

    gap < 0 → неожиданный провал → стресс, осторожность
    gap > 0 → неожиданный успех → уверенность, снижение тревоги
    gap ≈ 0 → стабильность → нет изменений

    Возвращает dict с ключами для StateDeltas.
    """
    gap = outcome.gap

    # Нет значимого сюрприза — нет изменений
    if abs(gap) < 0.1:
        return {}

    deltas: Dict[str, float] = {}

    if gap < 0:
        # Неожиданный провал → стресс + рост suspicious trait
        stress_gain = round(abs(gap) * 20.0 * learning_rate, 2)
        deltas["stress_delta"] = stress_gain
        deltas["trait_suspicious"] = round(abs(gap) * 0.1, 4)

    else:
        # Неожиданный успех → снижение стресса + overconfidence trait
        stress_relief = round(gap * 10.0 * learning_rate, 2)
        deltas["stress_delta"]       = -stress_relief
        deltas["trait_overconfident"] = round(gap * 0.08, 4)

    # Эмоция от сюрприза → emotion_tag
    if outcome.surprise_emotion:
        deltas["surprise_emotion"] = outcome.surprise_emotion

    return deltas

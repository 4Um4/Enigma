from __future__ import annotations

# path: backend/app/services/npc/opportunity_engine.py
"""
R6.3 — OpportunityEngine: определяет момент скрытого действия сломленного NPC.

Логика: NPC с FAKE_SUBMISSION или BETRAYAL не действует немедленно.
Он ждёт момента: игрок отвлечён, далеко, оружие есть, союзники рядом.
OpportunityEngine вычисляет этот момент как числовой score.

Формула из Слом.md:
  opportunity_score =
      (1 - player_attention) * W_ATTENTION
    + normalize(distance)    * W_DISTANCE
    + weapon_access          * W_WEAPON
    + normalize(allies)      * W_ALLIES

Вызывается DecisionHub.compute() один раз — до _get_possible_intents().
READ ONLY. Никаких мутаций.

Основные сущности:
  OpportunityContext  — входные данные сцены (frozen dataclass)
  OpportunityResult   — результат оценки (frozen dataclass)
  OpportunityEngine   — статический метод calculate()
"""


from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet

from app.models.behavior_mask import BehaviorMask
from app.models.npc_state import Intent

# ─────────────────────────────────────────────────────────────────────────────
# Веса компонентов формулы (Слом.md)
# ─────────────────────────────────────────────────────────────────────────────

# Внимание — главный фактор: NPC не рискует пока игрок смотрит
W_ATTENTION: float = 0.35

# Дистанция и оружие равнозначны — оба условия критичны для успеха
W_DISTANCE: float = 0.30
W_WEAPON: float = 0.20

# Союзники усиливают уверенность, но не решают исход
W_ALLIES: float = 0.15

# Порог: выше — скрытое действие разрешено
OPPORTUNITY_THRESHOLD: float = 0.65

# Пределы нормализации входных данных
MAX_DISTANCE_METERS: float = 30.0  # дальше — максимум по дистанции
MAX_ALLY_COUNT: int = 4  # больше 4 союзников — предел нормализации


# ─────────────────────────────────────────────────────────────────────────────
# Таблица разблокированных интентов по типу маски (R6.4 prep)
# Не используется в calculate() — подключается в DecisionHub
# ─────────────────────────────────────────────────────────────────────────────

_MASK_UNLOCKS: Dict[str, FrozenSet[str]] = {
    BehaviorMask.FAKE_SUBMISSION.value: frozenset(
        {
            Intent.ATTACK.value,  # удар в спину когда игрок отвернулся
            Intent.REPORT.value,  # донести пока игрок не видит
            Intent.INTIMIDATE.value,  # попытка вернуть контроль
        }
    ),
    BehaviorMask.BETRAYAL.value: frozenset(
        {
            Intent.REPORT.value,  # оповестить врага игрока
            Intent.ATTACK.value,  # прямое предательство
        }
    ),
    BehaviorMask.COLLAPSE.value: frozenset(),  # паралич — никаких действий
    BehaviorMask.NONE.value: frozenset(),
}


# ─────────────────────────────────────────────────────────────────────────────
# OpportunityContext — входные данные сцены
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OpportunityContext:
    """
    Контекст сцены для оценки момента скрытого действия.
    Формируется в game_loop из SceneState.

    player_attention: 0.0 = полностью отвлечён, 1.0 = смотрит прямо на NPC.
    distance: текущее расстояние NPC–игрок в метрах.
    weapon_access: NPC держит оружие или оно в радиусе вытянутой руки.
    allies: число союзных NPC в радиусе действия.
    """

    player_attention: float = 1.0  # по умолчанию — игрок смотрит
    distance: float = 0.0  # по умолчанию — вплотную
    weapon_access: bool = False
    allies: int = 0

    def __post_init__(self) -> None:
        # Защита от невалидных значений из SceneState
        object.__setattr__(
            self, "player_attention", max(0.0, min(1.0, self.player_attention))
        )
        object.__setattr__(self, "distance", max(0.0, self.distance))
        object.__setattr__(self, "allies", max(0, self.allies))


# ─────────────────────────────────────────────────────────────────────────────
# OpportunityResult — результат оценки
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OpportunityResult:
    """
    Результат OpportunityEngine.calculate().
    DecisionHub читает при фильтрации интентов и расчёте score.

    score:                 0.0–1.0, итоговый opportunity_score.
    hidden_action_allowed: score >= OPPORTUNITY_THRESHOLD.
    unlocked_intents:      набор интентов доступных сломленному NPC.
    score_trace:           компоненты для калибровки R4.2.
    """

    score: float
    hidden_action_allowed: bool
    unlocked_intents: FrozenSet[str] = field(default_factory=frozenset)
    score_trace: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# OpportunityEngine
# ─────────────────────────────────────────────────────────────────────────────


class OpportunityEngine:
    """
    R6.3 — чистая функция оценки возможности скрытого действия.
    Не имеет состояния, не мутирует NPCState.
    """

    @staticmethod
    def calculate(
        ctx: OpportunityContext,
        will_state: str,
    ) -> OpportunityResult:
        """
        Главный метод. Вызывается DecisionHub и StateApplicator.
        will_state передаётся как строка — без импорта WillState enum.
        """
        # Только сломленный NPC получает opportunity
        if will_state != "broken":
            return OpportunityResult(
                score=0.0,
                hidden_action_allowed=False,
                unlocked_intents=frozenset(),
                score_trace={"reason": "will_state_not_broken"},
            )

        # ── Формула из Слом.md ────────────────────────────────────────────────

        # Внимание: чем меньше игрок смотрит — тем выше шанс
        attention_component = (1.0 - ctx.player_attention) * W_ATTENTION

        # Дистанция: нормализация 0–MAX_DISTANCE_METERS
        distance_component = min(ctx.distance / MAX_DISTANCE_METERS, 1.0) * W_DISTANCE

        # Оружие: бинарный фактор
        weapon_component = (1.0 if ctx.weapon_access else 0.0) * W_WEAPON

        # Союзники: нормализация 0–MAX_ALLY_COUNT
        allies_component = min(ctx.allies / MAX_ALLY_COUNT, 1.0) * W_ALLIES

        raw_score = (
            attention_component
            + distance_component
            + weapon_component
            + allies_component
        )

        final_score = round(min(raw_score, 1.0), 4)
        hidden_allowed = final_score >= OPPORTUNITY_THRESHOLD

        return OpportunityResult(
            score=final_score,
            hidden_action_allowed=hidden_allowed,
            unlocked_intents=(
                frozenset({"betray", "steal", "escape", "sabotage"})
                if hidden_allowed
                else frozenset()
            ),
            score_trace={
                "attention_component": round(attention_component, 4),
                "distance_component": round(distance_component, 4),
                "weapon_component": round(weapon_component, 4),
                "allies_component": round(allies_component, 4),
                "raw_score": round(raw_score, 4),
                "threshold": OPPORTUNITY_THRESHOLD,
            },
        )

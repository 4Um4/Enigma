"""
TensionSynthesizer — ADR-131: Трёхосевая модель напряжения.

Три оси:
  ST (State Tension) — интеграл аффекта NPC (что реально происходит)
  ET (Event Tension) — мгновенные дельты решений (что случилось сейчас)
  NE (Narrative Entropy) — искажение восприятия игрока (как это ощущается)

Вербализация НЕ импортирует аффект напрямую.
ST и NE передаются как скаляры через параметры — вызывающий код извлекает их.

TODO:

"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


@dataclass(frozen=True)
class ThreeAxisTension:
    """Трёхосевое напряжение сцены — выход TensionSynthesizer."""

    # Три оси — каждая в своей системе координат
    state_tension: float  # ST: mean(affective_load) — интеграл [0..1]
    event_tension: float  # ET: sum(deltas) / 0.5 — производная [0..1]
    narrative_entropy: float  # NE: 1.0 - coherence — шум восприятия [0..1]

    # Доминирующая ось — какая реальность управляет сценой
    dominant_axis: Literal["ST", "ET", "NE"] = "ST"

    # Финальное напряжение сцены (после арбитража)
    composite: float = 0.0

    # Какие оси были подавлены (для CDS диагностики)
    suppression: Dict[str, float] = field(default_factory=dict)


class TensionSynthesizer:
    """Вычисляет трёхосевое напряжение из трёх независимых источников.

    ADR-131 Инварианты:
    1. ST >= 0.6 → composite >= 0.3 (якорь реальности)
    2. NE без ST/ET → composite <= 0.4 (потолок искажения)
    3. ET затухает за 1 тик (нет памяти — вызывающий код не сохраняет)
    4. composite > 0.0 только если хотя бы одна ось > 0.0
    """

    # Веса для взвешенной суммы (Шаг 1 — без NDA Engine)
    ALPHA = 0.5  # ST: реальность (интеграл)
    BETA = 0.3  # ET: события (производная)
    GAMMA = 0.2  # NE: восприятие (шум)

    # Пороги
    ST_ANCHOR_THRESHOLD = (
        0.6  # Инвариант 1: ST выше этого → composite не может быть низким
    )
    ST_ANCHOR_MIN_COMPOSITE = 0.3
    NE_CAP_WITHOUT_SUPPORT = 0.4  # Инвариант 2: потолок NE без ST/ET

    def compute(
        self,
        npc_affective_loads: Dict[str, float],
        decisions: List[Any],
        avatar_coherence: float = 1.0,
    ) -> ThreeAxisTension:
        """Вычисляет трёхосевое напряжение.

        Args:
            npc_affective_loads: {npc_id: affective_load} — вызывающий извлекает из all_npcs_raw
            decisions: List[DecisionResult] — для ET (stress_delta + fear_delta)
            avatar_coherence: cognitive_coherence из AvatarStateDTO [0..1]

        Returns:
            ThreeAxisTension с composite после арбитража
        """
        # --- Ось 1: State Tension (интеграл) ---
        if npc_affective_loads:
            _loads = [v for v in npc_affective_loads.values() if v is not None]
            ST = sum(_loads) / len(_loads) if _loads else 0.0
        else:
            ST = 0.0
        ST = max(0.0, min(1.0, ST))

        # --- Ось 2: Event Tension (производная) ---
        ET = 0.0
        if decisions:
            from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter

            raw_stress = sum(
                abs(LegacyStateDeltaAdapter.collapse(d.deltas).stress_delta)
                for d in decisions
            )
            raw_fear = sum(
                abs(LegacyStateDeltaAdapter.collapse(d.deltas).fear_delta)
                for d in decisions
            )
            ET = min(1.0, (raw_stress + raw_fear) / 0.5)

        # --- Ось 3: Narrative Entropy (шум восприятия) ---
        NE = max(0.0, min(1.0, 1.0 - avatar_coherence))

        # --- Арбитраж (Шаг 1: простая режимная логика) ---
        dominant, composite, suppression = self._arbitrate(ST, ET, NE)

        return ThreeAxisTension(
            state_tension=round(ST, 4),
            event_tension=round(ET, 4),
            narrative_entropy=round(NE, 4),
            dominant_axis=dominant,
            composite=round(composite, 4),
            suppression=suppression,
        )

    def _arbitrate(
        self,
        ST: float,
        ET: float,
        NE: float,
    ) -> Tuple[Any, ...]:
        """Режимная логика арбитража — определяет доминирующую ось и composite.

        Шаг 1 ADR-131: простая логика с инвариантами.
        Шаг 2 (NDA Engine) заменит это на полную режимную модель.
        """
        suppression: Dict[str, float] = {}

        # Взвешенная сумма по умолчанию
        composite = self.ALPHA * ST + self.BETA * ET + self.GAMMA * NE

        # Определяем доминирующую ось
        if ST >= ET and ST >= NE:
            dominant = "ST"
        elif ET >= ST and ET >= NE:
            dominant = "ET"
        else:
            dominant = "NE"

        # --- Инвариант 1: ST — Якорь Реальности ---
        # Если мир реально напряжён, composite не может быть низким
        if ST >= self.ST_ANCHOR_THRESHOLD and composite < self.ST_ANCHOR_MIN_COMPOSITE:
            composite = max(composite, self.ST_ANCHOR_MIN_COMPOSITE)
            suppression["ET"] = 0.5
            suppression["NE"] = 0.3

        # --- Инвариант 2: NE — Потолок Искажения ---
        # Чистое искажение без поддержки реальности не создаёт сильное напряжение
        if ST < 0.1 and ET < 0.1 and composite > self.NE_CAP_WITHOUT_SUPPORT:
            composite = self.NE_CAP_WITHOUT_SUPPORT
            suppression["NE"] = 0.5

        # --- Инвариант 4: Не создаём tension из ничего ---
        if ST < 0.001 and ET < 0.001 and NE < 0.001:
            composite = 0.0
            dominant = "ST"  # по умолчанию

        # --- Режимная логика (Шаг 1: упрощённая) ---
        # Боевой всплеск: ET подавляет ST
        if ET > 0.6 and ET > ST * 2:
            dominant = "ET"
            composite = min(1.0, ET * 1.5)
            suppression["ST"] = 0.5
            suppression["NE"] = 0.3

        # Стабильный страх: ST доминирует
        elif ST > 0.3:
            dominant = "ST"
            # NE усиливает интерпретацию если есть
            _ne_contrib = NE * 0.3 if NE > 0.2 else 0.0
            composite = min(1.0, ST + _ne_contrib)

        # Пустота с искажением: NE ограничен
        elif NE > 0.3 and ST < 0.1 and ET < 0.1:
            dominant = "NE"
            composite = min(self.NE_CAP_WITHOUT_SUPPORT, NE * 0.5)
            suppression["ST"] = 1.0
            suppression["ET"] = 1.0

        return dominant, max(0.0, min(1.0, composite)), suppression

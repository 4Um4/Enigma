"""
Центральный реестр математических констант ENIGMA.

Файл: backend/app/core/constants.py
Назначение: Центральный реестр математических констант для калибровки
Зависимости: нет
Основные сущности: секции PERCEPTION, STATE_CAPS, RESOLUTION, BREAK_STAGES

ПРИНЦИПЫ:
- Сюда попадают ТОЛЬКО кросс-модульные значения (используются в 2+ файлах)
- Модуль-локальные константы остаются в своих файлах (инкапсуляция)
- Все значения — immutable (верхний регистр)
- Формулы с магическими числами — здесь же как функции

СЕКЦИИ:
- PERCEPTION: радиусы, капы восприятия
- STATE_CAPS: абсолютные лимиты состояния NPC
- RESOLUTION: механика бросков и исходов
- BREAK_STAGES: коэффициенты стадий слома (R8)
- DISTORTION: когнитивные искажения (2.1.1)
- DECISION_HUB: веса DecisionHub (кросс-модульные)
- BREAK_SYSTEM: механика психологического слома
- REACTION: пороги реагирования NPC
- LIFE_ENGINE: тайминги и вероятности макро-симуляции
"""

from typing import Final


# ═══════════════════════════════════════════════════════════════════════
# PERCEPTION — Пространственное восприятие
# ═══════════════════════════════════════════════════════════════════════

PERCEPTION_RADIUS: Final[dict[str, float]] = {
    "minor": 3.0,   # слышит только вплотную (экономит ресурсы, закрывает эксплойт фарма)
    "major": 15.0,  # полная симуляция
}
PERCEPTION_FALLBACK_DISTANCE: Final[float] = 8.0  # fallback если tier неизвестен


# ═══════════════════════════════════════════════════════════════════════
# RESOLUTION — Механика бросков (R5)
# ═══════════════════════════════════════════════════════════════════════

DICE_WEIGHT: Final[float] = 0.65  # вклад случайности
BIAS_WEIGHT: Final[float] = 0.35  # вклад ожидания/навыка
OUTCOME_FLOOR: Final[float] = 0.05  # минимальный успех (даже при крит провале)
OUTCOME_CEILING: Final[float] = 0.95  # максимальный успех (даже при крит успехе)
SURPRISE_THRESHOLD: Final[float] = 0.25  # порог "неожиданного" исхода
DESPERATION_STRESS: Final[float] = 85.0  # стресс, при котором NPC идёт на риск
D20_SIDES: Final[int] = 20  # нормализация броска в [0..1]


# ═══════════════════════════════════════════════════════════════════════
# DISTORTION — Когнитивные искажения (2.1.1)
# ═══════════════════════════════════════════════════════════════════════

THREAT_AMPLIFICATION_FACTOR: Final[float] = 0.15  # базовый множитель угрозы
RESENTMENT_BIAS_FACTOR: Final[float] = 0.20  # множитель обиды
DISTRUST_STRESS_BOOST: Final[float] = 8.0  # порог стресса для активации недоверия
DISTRUST_STRESS_THRESHOLD: Final[float] = -30.0  # trust < этого → +boost stress
MAX_DISTORTION_STRESS: Final[float] = 30.0  # стресс, при котором искажение максимальное


# ═══════════════════════════════════════════════════════════════════════
# CONTINUITY — Лимиты кэша сцены
# ═══════════════════════════════════════════════════════════════════════

NARRATIVE_CACHE_MAX: Final[int] = 10


# ═══════════════════════════════════════════════════════════════════════
# DECISION_HUB — Скоринг, инерция и пороги (источник правды: decision_hub.py)
# ═══════════════════════════════════════════════════════════════════════

# Контролируемый рандом ±N% — NPC предсказуем, но не робот
SCORE_NOISE_RANGE: Final[float] = 0.10

# Инерция intent
INTENT_INERTIA_MAX_TICKS: Final[int] = 10
INTENT_INERTIA_WEIGHT: Final[float] = 0.20
INTENT_SATURATION_TICKS: Final[int] = 6       # тиков без прогресса до начала decay
INTENT_DECAY_RATE: Final[float] = 0.03        # убывание за каждый лишний тик
TRAIT_DECAY_RATE: Final[float] = 0.02         # decay временных state_modifiers за тик
INTENT_EXHAUSTION_RATE: Final[float] = 0.08   # штраф за зависание сверх порога

# Пороги выбора
FEAR_FLEE_THRESHOLD: Final[float] = 0.65
MIN_INTENT_SCORE: Final[float] = 0.15

# Commitment Model
COMMITMENT_BASE_THRESHOLD: Final[float] = 0.15
COMMITMENT_K: Final[float] = 2.5
COMMITMENT_BONUS_K: Final[float] = 0.10

# Switching Cost
SWITCHING_COST_BASE: Final[float] = 0.05
SWITCHING_COST_AGE_K: Final[float] = 0.08
SWITCHING_COST_EMOTION_K: Final[float] = 0.06
SWITCHING_COST_IDENTITY_K: Final[float] = 0.04
REACTIVE_URGENCY_THRESHOLD: Final[float] = 0.8  # fear > this → force switch


# ═══════════════════════════════════════════════════════════════════════
# REACTION — Пороги реагирования NPC (Phase S.4.2)
# ═══════════════════════════════════════════════════════════════════════

MAX_SPEAKERS_PER_TURN: Final[int] = 6    # максимум NPC говорят за один ход


# ═══════════════════════════════════════════════════════════════════════
# LIFE ENGINE — Тайминги и вероятности макро-симуляции
# ═══════════════════════════════════════════════════════════════════════

MINOR_TICK_INTERVAL: Final[int] = 3
RANDOM_EVENT_CHANCE: Final[float] = 0.05
STRESS_RECOVERY_SAFE: Final[float] = 5.0
STRESS_RECOVERY_SLEEPING: Final[float] = 15.0
TICK_SAVE_INTERVAL: Final[int] = 10
# Сколько реальных секунд соответствует одному игровому тику
# 300с = 5 минут реального времени = 1 тик мира
TICK_REAL_SECONDS: Final[int] = 300
MAX_CATCH_UP_TICKS: Final[int] = 10  # лимит catch-up за одно подключение
MAX_CACHED_CAMPAIGNS: Final[int] = 100
CAMPAIGN_TTL_SECONDS: Final[int] = 3600
MACRO_SIM_THRESHOLD_SECONDS: Final[int] = 3600


# ═══════════════════════════════════════════════════════════════════════
# WORLD_TICK — Проактивный тик мира (Фаза 3.4)
# ═══════════════════════════════════════════════════════════════════════

WORLD_TICK_EVERY_TURNS: Final[int] = 3         # проактивный тик каждые N ходов игрока
MIN_PROACTIVE_SCORE: Final[float] = 0.3        # минимальный score для проактивного действия
PROACTIVE_INTENT_PENALTY: Final[float] = 0.2   # штраф за проактивность (NPC не спамят)
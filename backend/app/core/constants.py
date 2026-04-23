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
# ECONOMY — Единые цены и зарплаты (кросс-модульные)
# ═══════════════════════════════════════════════════════════════════════
# Золотой стандарт: 1G ≈ 1 день выживания бедняка
# Еда дешёвая (хлеб/каша), NPC ест 3×/день = 0.3G на пропитание
# Это 30% дохода служанки (sandbox: 0.3G/день) — реалистичная доля

GOODS_PRICES: Final[dict[str, float]] = {
    # Продовольствие — "жидкий хлеб", крайне дёшево по историческим меркам
    # 1G ≈ 1-2 денария, обед (хлеб+похлёбка) ≈ 3-6 денариев ≈ 0.03-0.05G
    "food": 0.03,          # похлёбка + хлеб — 1 порция (базовая выживаемость)
    "ale": 0.01,           # эль — кружка (слабый 1-3%, не утоляет голод)
    # Сырьё и материалы — ремесленный сегмент
    "cloth": 0.5,          # ткань — аршин
    "silk": 2.0,           # шёлк — аршин (роскошь)
    "iron": 0.8,           # железо — фунт
    "tools": 1.5,          # инструменты — комплект
    "lockpick": 0.5,       # отмычка — штука
    # Услуги и аренда
    "room_rent": 0.2,      # аренда комнаты — за ночь
    # Оружие (оценка богатства, не для торговли NPC-NPC)
    "iron_sword": 15.0,    # железный меч
    "dagger": 5.0,         # кинжал
    "torch": 0.1,          # факел
}

# Референсные дневные зарплаты (sandbox может переопределять через контракты)
WAGES: Final[dict[str, float]] = {
    "laborer": 1.0,        # Чернорабочий
    "maid": 0.8,           # Служанка
    "guard": 3.0,          # Стражник
    "merchant": 10.0,      # Торговец
    "tavern_keeper": 10.0, # Трактирщик
}

# Минимальные дневные расходы NPC (базовое выживание)
# 3 порции еды × 0.03G = 0.09G/день — без этого NPC умирает
DAILY_EXPENSES_MIN: Final[float] = 0.09


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
TICKS_PER_DAY: Final[int] = 24  # 1 тик = 1 час игрового, 24 тика = 1 день

# Фаза 4 — Время продвигается от действий, не от тиков
TIME_DELTA_DIALOG: int = 0          # диалог — время не идёт (секунды)
TIME_DELTA_WALK_INDOOR: int = 10    # шаг внутри помещения (секунды)
TIME_DELTA_WALK_OUTDOOR: int = 60   # шаг на улице (секунды)
TIME_DELTA_TELEGRAPH: int = 30      # NPC проявил инициативу (секунды)
TIME_DELTA_WAIT_HOUR: int = 3600    # игрок сказал "жду час"
TIME_DELTA_TRAVEL: float = 120.0    # 1 единица = 2 минуты (fallback, не используется)
TIME_UNITS_PER_MINUTE: float = 3.0  # 3 единицы в минуту (переход таверны ~10 мин)

# Фаза 2.1 — Distance-based idle tick intervals (мс на клиенте)
IDLE_TICK_NEAR_MS: Final[int] = 2_000       # NPC в радиусе NEAR — тик каждые 2 сек
IDLE_TICK_MID_MS: Final[int] = 8_000        # NPC в радиусе MID — тик каждые 8 сек
IDLE_TICK_FAR_MS: Final[int] = 30_000       # NPC за FAR — тик каждые 30 сек
IDLE_TICK_NEAR_RADIUS: Final[float] = 5.0   # порог "близко" (метров)
IDLE_TICK_MID_RADIUS: Final[float] = 15.0   # порог "средне" (метров, = perception cap)

# Фаза 2.1 — DecisionHub в idle_tick
IDLE_DECISION_SCORE_THRESHOLD: Final[float] = 0.5  # порог накопленного давления для триггера телеграфа
IDLE_PRESSURE_ACCUM_RATE: Final[float] = 0.1       # 10% от score за тик
IDLE_PRESSURE_DECAY_RATE: Final[float] = 0.05      # 5% decay за тик
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
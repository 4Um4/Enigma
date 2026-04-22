# backend/app/services/character/front_engine.py
"""
Фаза 5.1 — FrontEngine: вычисление давления мира и управление масками персонажа.

Принципы:
  - FrontEngine НЕ пишет CharacterProfile напрямую. Возвращает FrontDecision.
  - Вызывающий код (game_loop) решает, применять ли.
  - WorldPressure вычисляется из ReputationEngine + SocialEngine + фракций.
  - LLM получает описание Front, не числа.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models.character import CharacterProfile
from app.models.front import FrontType, WorldPressure, PRESSURE_FRONT_MAP

logger = logging.getLogger(__name__)


# ── Пороги ────────────────────────────────────────────────────────────────────

# Минимальное давление для提议 принять маску
PRESSURE_ADOPT_THRESHOLD: float = 0.3

# Давление при котором текущая маска усиливается
PRESSURE_INTENSIFY_THRESHOLD: float = 0.5

# Давление при котором маска сбрасывается (перегрузка — срыв лучше чем играть роль)
PRESSURE_BREAK_THRESHOLD: float = 0.9

# Если pressure упал ниже этого — маска больше не нужна
PRESSURE_DROP_THRESHOLD: float = 0.1

# Минимальный возраст маски перед возможным сбросом (не дёргать каждый тик)
MIN_FRONT_AGE_BEFORE_DROP: int = 5


@dataclass
class FrontDecision:
    """Результат работы FrontEngine за один тик."""
    action: str  # "none", "adopt", "intensify", "drop", "break"
    front_type: FrontType = FrontType.NONE
    front_description: str = ""  # человекочитаемое описание для LLM
    integrity_cost: float = 0.0   # сколько self_integrity стоит это решение


# ── Описания масок для LLM ────────────────────────────────────────────────────

FRONT_DESCRIPTIONS: dict = {
    FrontType.NONE: "",
    FrontType.HUMBLE: "персонаж подавляет гордость и ведёт себя смиренно",
    FrontType.TOUGH: "персонаж напускает на себя жёсткость, чтобы скрыть страх",
    FrontType.COMPLIANT: "персонаж чрезмерно согласителен, пытаясь задобрить",
    FrontType.GUARDED: "персонаж замкнулся, minimise контакт и не выдаёт эмоций",
    FrontType.DECEPTIVE: "персонаж играет роль, не соответствующую его истинным ценностям",
}

FRONT_BREAK_DESCRIPTIONS: dict = {
    FrontType.HUMBLE: "персонаж не выдержал унижения — вспышка гордости",
    FrontType.TOUGH: "маска жёсткости треснула — персонаж показал слабость",
    FrontType.COMPLIANT: "угодливость привела к срыву — персонаж отказывается подчиняться",
    FrontType.GUARDED: "защитная стена рухнула — эмоциональный выброс",
    FrontType.DECEPTIVE: "лицемерие раскрыто — окружение видит истинное лицо",
}


class FrontEngine:
    """
    Фасад для вычисления давления мира и управления масками.

    Контракт:
    - НЕ пишет CharacterProfile.
    - Возвращает FrontDecision каждый тик.
    - Вызывающий применяет решение к профилю.
    """

    def compute_pressure(
        self,
        profile: CharacterProfile,
        player_reputation: float = 0.0,  # из ReputationEngine
        nearby_npc_fear: float = 0.0,    # из NPC threat assessment
        player_debt: float = 0.0,        # из EconomicProfile obligations
        rumor_intensity: float = 0.0,    # из SocialEngine propagation
        value_conflict: float = 0.0,     # из CharacterFilter conflict_score
    ) -> WorldPressure:
        """
        Вычисляет WorldPressure из доступных сигналов.
        Каждый сигнал нормализуется в [0..1].
        """
        wp = WorldPressure(
            # Низкая репутация → давление быть "кем-то другим"
            reputation_pressure=max(0.0, min(1.0, (50.0 - player_reputation) / 100.0)),
            # Страх от NPC рядом
            fear_pressure=max(0.0, min(1.0, nearby_npc_fear)),
            # Долг выше 30G → давление
            debt_pressure=max(0.0, min(1.0, player_debt / 50.0)),
            # Слухи о персонаже
            rumor_pressure=max(0.0, min(1.0, rumor_intensity)),
            # Конфликт ценностей с окружением
            value_conflict_pressure=max(0.0, min(1.0, value_conflict)),
        )
        wp.compute_total()
        return wp

    def decide(
        self,
        profile: CharacterProfile,
        pressure: WorldPressure,
        current_tick: int,
    ) -> FrontDecision:
        """
        Принимает решение о маске на основе давления и текущего состояния.
        """
        current_front = profile.front
        total = pressure.total_pressure

        # ── Нет маски ──────────────────────────────────────────────────────
        if current_front is None or not current_front.is_active:
            if total >= PRESSURE_ADOPT_THRESHOLD:
                # Выбираем маску по доминирующему источнику давления
                suggested = PRESSURE_FRONT_MAP.get(pressure.dominant_source, FrontType.GUARDED)
                return FrontDecision(
                    action="adopt",
                    front_type=suggested,
                    front_description=FRONT_DESCRIPTIONS.get(suggested, ""),
                    integrity_cost=0.0,  # стоимость начинается со следующего тика
                )
            return FrontDecision(action="none")

        # ── Есть маска ──────────────────────────────────────────────────────
        # Ageing и стоимость
        maintenance = current_front.age()

        # Перегрузка — срыв лучше чем продолжать играть роль
        if total >= PRESSURE_BREAK_THRESHOLD:
            break_desc = FRONT_BREAK_DESCRIPTIONS.get(current_front.front_type, "маска сорвалась")
            return FrontDecision(
                action="break",
                front_type=FrontType.NONE,
                front_description=break_desc,
                integrity_cost=0.05,  # срыв стоит целостности
            )

        # Усиление если давление растёт
        if total >= PRESSURE_INTENSIFY_THRESHOLD:
            old_intensity = current_front.intensity
            return FrontDecision(
                action="intensify",
                front_type=current_front.front_type,
                front_description=FRONT_DESCRIPTIONS.get(current_front.front_type, ""),
                integrity_cost=maintenance,
            )

        # Проверка: давление упало — маска больше не нужна?
        if (total < PRESSURE_DROP_THRESHOLD
                and current_front.tick_age >= MIN_FRONT_AGE_BEFORE_DROP):
            desc = f"давление спало — персонаж перестаёт {FRONT_DESCRIPTIONS.get(current_front.front_type, 'маскироваться').replace('персонаж ', '')}"
            return FrontDecision(
                action="drop",
                front_type=FrontType.NONE,
                front_description=desc,
                integrity_cost=0.0,
            )

        # Продолжаем носить маску — платим стоимость
        return FrontDecision(
            action="none",
            front_type=current_front.front_type,
            front_description=FRONT_DESCRIPTIONS.get(current_front.front_type, ""),
            integrity_cost=maintenance,
        )
from __future__ import annotations

# path: backend\app\services\will.py
# Назначение: Вычисление Воли и Давления (ADR-031). Pure Functions.
# Зависимости: app.domain.intent, app.models.will
# Основные сущности: resolve_intent_pressure, compute_willpower
"""
TODO: В будущем этот слой может быть расширен до полноценного Will Engine, который будет учитывать не только давление от действий игрока, но и внутренние конфликты NPC, их прошлый опыт и динамические изменения психики. Но для MVP достаточно базового транслятора Intent → Pressure и простого Cumulative Strain Model для вычисления реакции NPC.
"""


import logging
from typing import Any, Dict, Optional

from app.domain.intent import IntentDTO, IntentParametersDTO
from app.domain.intent_profile import CrowdThreatLevel, SocialSignal
from app.models.will import (
    EmbodiedVector,
    IntentPressureProfile,
    WillResponseDTO,
    WillState,
)

logger = logging.getLogger(__name__)

# --- СЛОЙ 1: СЕМАНТИЧЕСКИЙ ПЕРЕВОД (BOOTSTRAP) ---


def resolve_intent_pressure(
    intent: IntentDTO,
    context: Optional[Dict[str, Any]] = None,
) -> IntentPressureProfile:
    """Транслирует синтаксис действия в семантику давления на психику.

    MVP (Bootstrap): маппит action + target на вектор давления.
    В будущем заменяется на LLM-экстрактор или CFRM-наследие.
    """
    pressure = IntentPressureProfile()
    # ADR-035: Приоритет semantic_action из parameters. Защита от AttributeError и None.
    action = (
        getattr(intent, "parameters", None)
        and intent.parameters.semantic_action
        or getattr(intent, "action", "")
        or ""
    ).lower()
    target = (
        getattr(intent, "parameters", None)
        and intent.parameters.target_reference
        or getattr(intent, "target", "")
        or ""
    ).lower()

    # Базовые эвристики давления (Синхронизировано с _EVENT_AXIS_MAP и EventType)
    if action in ("attack", "player_attacks", "player_attack", "combat"):
        pressure = IntentPressureProfile(
            violence=0.8,
            self_risk=0.4,
            moral_violation=0.5,
            identity_deviation=0.6,
        )
        # TODO: В будущем использовать intent.parameters.physical_force для модуляции давления

    elif action == "flee":
        pressure = IntentPressureProfile(
            self_risk=0.1,
            identity_deviation=0.4,  # Страх ломает гордость
            social_exposure=0.6,  # Позор труса
        )

    elif action in ("threaten", "player_threatens", "intimidation", "player_insults"):
        pressure = IntentPressureProfile(
            violence=0.3,
            humiliation=0.6,
            social_exposure=0.5,
            moral_violation=0.4,
        )

    elif action == "steal":
        pressure = IntentPressureProfile(
            social_exposure=0.7,  # Позор вора
            moral_violation=0.6,
            taboo_intensity=0.5,
        )

    # ADR-031 & ADR-043: Социальные директивы и приказы.
    # The Fool Phase 2: Игрок — источник приказа, а не цель.
    # Подчинение чужой воле (identity_deviation) и социальный риск (social_exposure)
    # испытывает ЦЕЛЬ (NPC), а не ИСТОЧНИК (Игрок).
    # Для игрока, отдающего приказ, давление минимально, но моральная ответственность остаётся.
    elif action in (
        "player_social",
        "player_moves",
        "move",
        "approach",
        "halt",
        "order",
    ):
        # V8-WL-2 FIX: Приказ насилия/риска несёт моральную ответственность для игрока.
        _is_order = action == "order"
        pressure = IntentPressureProfile(
            identity_deviation=0.05,  # Игрок проявляет агентность, не подчиняется
            social_exposure=0.05,  # Минимальный социальный фрикшн
            humiliation=0.0,  # Игрок не унижается, отдавая приказ
            moral_violation=0.4 if _is_order else 0.0,  # Приказ = моральный выбор
            self_risk=0.3 if _is_order else 0.0,        # Приказ = ответственность за риск
        )

    elif action in (
        "talk",
        "player_talks",
        "player_spoke",
        "dialogue",
        "player_interacts",
        "idle",
    ):
        # Разговор обычно безопасен, но зависит от контекста
        pressure = IntentPressureProfile(
            identity_deviation=0.05,
            social_exposure=0.1,
        )

    # Модификаторы контекста (если переданы)
    if context:
        if context.get("is_desperate"):
            pressure = IntentPressureProfile(
                **{k: getattr(pressure, k) * 0.7 for k in pressure.__dataclass_fields__}
            )

    return pressure


# --- СЛОЙ 2: CUMULATIVE STRAIN MODEL ---


def compute_willpower(
    pressure: IntentPressureProfile,
    psyche: Dict[str, float],
) -> WillResponseDTO:
    """Вычисляет реакцию аватара на давление (Cumulative Strain Model).

    НЕ ЗНАЕТ о типе действия. Работает ТОЛЬКО с вектором давления и психикой.
    Формула (ADR-031):
    resistance = pressure.identity_deviation * psyche.identity_rigidity
               + pressure.self_risk * psyche.fear
               + pressure.moral_violation * psyche.conviction
               + pressure.social_exposure * psyche.shame
               - pressure.violence * psyche.aggression
               - pressure.taboo_intensity * psyche.curiosity
    """
    # Извлечение черт с безопасными дефолтами
    identity_rigidity = psyche.get("identity_rigidity", 0.5)
    fear = psyche.get("fear", 0.5)
    conviction = psyche.get("conviction", 0.5)
    shame = psyche.get("shame", 0.5)
    aggression = psyche.get("aggression", 0.5)
    curiosity = psyche.get("curiosity", 0.5)
    gregariousness = psyche.get("gregariousness", 0.5)

    # GAP2 FIX: Амнезия Воли. Травмы закаляют идентичность.
    # Обиженный NPC упрямее. Каждая травма повышает resistance к давлению.
    trauma_markers = psyche.get("trauma_markers", [])
    if isinstance(trauma_markers, (list, set, tuple)) and len(trauma_markers) > 0:
        # Каждая травма добавляет 0.1 к rigidity (максимум +0.3, чтобы не стать бессмертным)
        identity_rigidity = min(
            1.0, identity_rigidity + min(len(trauma_markers) * 0.1, 0.3)
        )

    # Расчет кумулятивного напряжения
    resistance = (
        pressure.identity_deviation * identity_rigidity
        + pressure.self_risk * fear
        + pressure.moral_violation * conviction
        + pressure.social_exposure * shame
        - pressure.violence
        * aggression  # Склонность к насилию снижает сопротивление ему
        - pressure.taboo_intensity * curiosity  # Любопытство снижает страх табу
    )

    # Clamp 0.0 - 1.0
    resistance = max(0.0, min(1.0, resistance))

    # Определение WillState на основе напряжения
    state = _map_resistance_to_state(resistance)

    # Расчет побочных эффектов (Урон идентичности, страх, стресс от морального конфликта)
    identity_damage = (
        resistance * pressure.identity_deviation * 0.2 if resistance > 0.4 else 0.0
    )
    fear_delta = resistance * pressure.self_risk * 0.3
    # Стресс аватара: моральное нарушение + сопротивление = внутренний конфликт
    # Масштаб 0-10 за действие (NPCState.stress = 0-100)
    stress_delta = resistance * pressure.moral_violation * 10.0

    # Генерация Counter-Offer (Аватар пытается выжить)
    counter_offer = _generate_counter_offer(pressure, state)

    # Нарративные хуки для LLM
    hooks = _generate_narration_hooks(state, pressure)

    # Вычисление моторного импульса (ADR-037)
    # The Fool Phase 2: Безопасная распаковка 3 слоёв
    _embodied_result = _resolve_embodied_vector(pressure, state)
    embodied_vector = _embodied_result[0] if _embodied_result else None
    social_signal = _embodied_result[1] if _embodied_result else SocialSignal.NONE
    crowd_threat = _embodied_result[2] if _embodied_result else CrowdThreatLevel.NONE

    return WillResponseDTO(
        state=state,
        resistance=resistance,
        fear_delta=fear_delta,
        stress_delta=stress_delta,
        identity_damage=identity_damage,
        counter_offer=counter_offer,
        narration_hooks=hooks,
        embodied_vector=embodied_vector,
        social_signal=social_signal.value,  # Проброс для CFRM
        crowd_threat_level=crowd_threat.value,  # Проброс для CFRM
    )


def _map_resistance_to_state(resistance: float) -> WillState:
    """Маппинг кумулятивного напряжения в шкалу деградации."""
    if resistance < 0.15:
        return WillState.COMPLY
    elif resistance < 0.35:
        return WillState.RELUCTANT
    elif resistance < 0.55:
        return WillState.DISTRESSED
    elif resistance < 0.75:
        return WillState.PANICKED
    elif resistance < 0.90:
        return WillState.DISSOCIATING
    elif resistance < 1.0:
        return WillState.BROKEN
    else:
        return WillState.CONDITIONED


def _generate_counter_offer(
    pressure: IntentPressureProfile, state: WillState
) -> Optional[IntentDTO]:
    """Аватар ищет альтернативу, чтобы сохранить Я."""
    if state in (WillState.COMPLY, WillState.RELUCTANT):
        return None  # Согласие или легкая неохота не требуют компромисса

    if pressure.violence > 0.6:
        # Предлагает избежать прямого насилия
        return IntentDTO(
            action="flee", target="", parameters=IntentParametersDTO()
        )

    if pressure.social_exposure > 0.6:
        # Предлагает скрытный путь
        return IntentDTO(
            action="stealth", target="", parameters=IntentParametersDTO()
        )

    if pressure.self_risk > 0.6:
        # Предлагает переговоры или подчинение ради выживания
        return IntentDTO(action="yield", target="", parameters=IntentParametersDTO())

    return None


def _generate_narration_hooks(
    state: WillState, pressure: IntentPressureProfile
) -> list[str]:
    """Генерирует подсказки для LLM-вербализации."""
    hooks = []
    if state == WillState.DISTRESSED:
        hooks.extend(["дрожит", "голос срывается"])
    elif state == WillState.PANICKED:
        hooks.extend(["пятится", "расширенные глаза", "частое дыхание"])
    elif state == WillState.DISSOCIATING:
        hooks.extend(["взгляд пустеет", "движения механические", "отстраненный вид"])
    elif state == WillState.BROKEN:
        hooks.extend(["опускает голову", "безвольная поза", "слезы без звука"])

    if pressure.violence > 0.7:
        hooks.append("отшатывается от крови")

    return hooks


_EMBODIED_TEXT_MAP = {
    EmbodiedVector.AVOIDANCE: "Убежать...",
    EmbodiedVector.DESTROY: "Ударить...",
    EmbodiedVector.COLLAPSE: "Упасть...",
    EmbodiedVector.SUBMIT: "Подчиниться...",
    EmbodiedVector.FREEZE: "Замереть...",
}


def get_embodied_impulse_text(vector: Optional[EmbodiedVector]) -> str:
    """Транслирует моторный вектор в текст для Resistance Medium (фронтенд)."""
    if vector is None:
        return "Сопротивляться..."
    return _EMBODIED_TEXT_MAP.get(vector, "Сопротивляться...")


def _resolve_embodied_vector(
    pressure: IntentPressureProfile, state: WillState
) -> Optional[tuple]:
    """The Fool Phase 2: Вычисляет моторный импульс, социальный сигнал и уровень угрозы.
    Возвращает: (EmbodiedVector, SocialSignal, CrowdThreatLevel) или None.
    """
    # ADR-083: Инвариант Насилия. Неохотное согласие (RELUCTANT) на насилие
    # подавляет волю, но не инстинкты. Тело сопротивляется убийству.
    if state in (WillState.COMPLY, WillState.RELUCTANT, WillState.PARTIAL_COMPLY):
        if pressure.violence > 0.3 or pressure.self_risk > 0.3:
            return EmbodiedVector.FREEZE, SocialSignal.VIOLENCE, CrowdThreatLevel.MEDIUM
        return None  # Обычное социальное согласие не порождает моторных импульсов

    # Паника или критический риск = бегство, высокий сигнал угрозы.
    if state == WillState.PANICKED or pressure.self_risk > 0.7:
        return (
            EmbodiedVector.AVOIDANCE,
            SocialSignal.PREDATOR_ALERT,
            CrowdThreatLevel.HIGH,
        )

    # Диссоциация или экстремальное насилие = ступор
    if state == WillState.DISSOCIATING or pressure.violence > 0.8:
        return EmbodiedVector.FREEZE, SocialSignal.FEAR, CrowdThreatLevel.MEDIUM

    # Холодная ярость (насилие без искажения идентичности)
    if pressure.violence > 0.5 and pressure.identity_deviation < 0.3:
        return EmbodiedVector.DESTROY, SocialSignal.VIOLENCE, CrowdThreatLevel.HIGH

    # Слом воли или крайнее унижение
    if state == WillState.BROKEN or pressure.humiliation > 0.7:
        return EmbodiedVector.SUBMIT, SocialSignal.DISCOMFORT, CrowdThreatLevel.NONE

    # Риск + тревога = коллапс
    if pressure.self_risk > 0.5 and state == WillState.DISTRESSED:
        return EmbodiedVector.COLLAPSE, SocialSignal.FEAR, CrowdThreatLevel.MEDIUM

    # The Fool Phase 2: Социальная тревога = моторный ступор, но низкая угроза для толпы.
    if state == WillState.DISTRESSED:
        return EmbodiedVector.FREEZE, SocialSignal.DISCOMFORT, CrowdThreatLevel.LOW

    # Дефолтный инстинкт: осторожное отступление без массовой паники.
    return EmbodiedVector.AVOIDANCE, SocialSignal.FEAR, CrowdThreatLevel.LOW


def compose_pressure_from_tags(
    base_pressure: IntentPressureProfile, tags: list[str]
) -> IntentPressureProfile:
    """Накладывает семантические теги интента на базовое давление.
    Решает проблему 'hello = humiliation 0.4'."""
    _mod = {
        "coercive": {"identity_deviation": 0.3, "humiliation": 0.2},
        "humiliating": {
            "identity_deviation": 0.4,
            "humiliation": 0.6,
            "moral_violation": 0.3,
        },
        "moral": {"moral_violation": 0.5, "identity_deviation": 0.2},
        "violent_threat": {"violence": 0.5, "moral_violation": 0.4},
    }

    deltas = {k: 0.0 for k in IntentPressureProfile.__dataclass_fields__}
    for tag in tags:
        for field, val in _mod.get(tag, {}).items():
            deltas[field] += val

    return IntentPressureProfile(
        violence=base_pressure.violence + deltas.get("violence", 0),
        humiliation=base_pressure.humiliation + deltas.get("humiliation", 0),
        self_risk=base_pressure.self_risk + deltas.get("self_risk", 0),
        moral_violation=base_pressure.moral_violation
        + deltas.get("moral_violation", 0),
        identity_deviation=base_pressure.identity_deviation
        + deltas.get("identity_deviation", 0),
    )

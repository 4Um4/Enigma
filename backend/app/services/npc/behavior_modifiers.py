"""
path: backend/app/services/npc/behavior_modifiers.py
Назначение: Вычисление модификаторов поведения из внутренних состояний NPC.
             Предшественник будущего HomeostasisEngine. Когда появятся
             hunger, thirst, boredom, stress, confidence — эта функция
             станет HomeostasisEngine.
Зависимости: Нет (чистая функция, только math)
Основные сущности: BehaviorModifiers
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BehaviorModifiers:
    """Готовые коэффициенты для DecisionHub.

    DecisionHub не знает почему TALK стал привлекательнее.
    Он видит только эти числа.
    """

    social_outgoing: float = 0.0  # TALK, HELP, TRADE, FLIRT, ASK, INVITE
    social_incoming: float = 0.0  # ANSWER, REFUSE, WARN, ACCEPT, REJECT


def compute_behavior_modifiers(
    social_input_ema: float,
    gregariousness: float,
) -> BehaviorModifiers:
    """Чистая функция: Field Channel (EMA + Personality) → модификаторы.

    ADR-O-312: Социальность — это Field Channel.
    Мотивация вычисляется на лету как error = setpoint - EMA.

    social_input_ema: 0.0 (нет входа) ... 1.0 (перегруз)
    gregariousness: 0.0 (интроверт) ... 1.0 (экстраверт)
    """
    # Setpoint: ожидаемый уровень социального входа (0.2 ... 0.8)
    setpoint = 0.2 + (0.6 * gregariousness)

    # Error: > 0 (голод), < 0 (перегруз), ≈ 0 (комфорт)
    error = setpoint - social_input_ema
    tolerance = 0.1  # Зона нечувствительности

    # Outgoing: error > 0 (голод) → хочет инициировать контакт
    if error > tolerance:
        outgoing = min(0.5, (error - tolerance) * 1.0)
    else:
        outgoing = 0.0

    # Incoming: error < 0 (перегруз) → устал от входа, снижает реакцию
    # (В будущем здесь может быть штраф к TALK и буст к FLEE)
    if error < -tolerance:
        incoming = min(0.5, (-error - tolerance) * 1.0)
    else:
        incoming = 0.0

    return BehaviorModifiers(social_outgoing=outgoing, social_incoming=incoming)
